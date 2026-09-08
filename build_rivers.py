#!/usr/bin/env python3
"""Build the river reach register from the Environment Agency's gauging stations.

WHAT A RIVER PAGE IS, AND WHAT IT IS NOT.

It is a stretch of river with a level gauge on it — "the River Wharfe at
Addingham" — and it answers the question a river swimmer actually asks: is the
river up or down today, has anything discharged upstream, when did it last rain.

It is NOT a bathing water and it is NOT a swimming spot. Nobody samples these,
nobody forecasts them, nobody puts up a sign. The gauge is a piece of flood
infrastructure that happens to sit in the water, not a place anyone gets in, and
the pages must never imply otherwise.

WHY THE TYPICAL RANGE IS LOAD-BEARING. A level is measured against a datum that
belongs to that station alone, so "0.31m" is meaningless on its own and 0.31m
here is not 0.31m ten miles away. What is meaningful is where today's reading
sits against the range this station usually runs at, which the Agency publishes
per station. A station with no typical range is dropped rather than shown with a
number nobody can interpret.

Source: Environment Agency real-time flood-monitoring API, Open Government
Licence v3.0. England only — SEPA and Natural Resources Wales publish their own
and are not in this file.

    python3 build_rivers.py
"""
import gzip
import io
import json
import math
import os
import ssl
import sys
import time
import unicodedata
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import places                                            # noqa: E402
from falls_areas import district_of                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("SWIM_OUT") or (
    os.path.join(ROOT, "swim") if os.path.isdir(os.path.join(ROOT, "swim"))
    else os.getcwd())

STATIONS = ("https://environment.data.gov.uk/flood-monitoring/id/stations"
            "?parameter=level&_limit=10000&_view=full")

CTX = ssl.create_default_context()
UA = "caniswim/1.0 (personal bathing water tool; open data)"

# TWO GAUGES A FEW HUNDRED METRES APART ARE ONE PLACE. Some sites carry an
# upstream and a downstream gauge, and a weir often has one either side. Two
# pages for the same bend of river is two thin pages instead of one useful one.
MERGE_KM = 1.5


def fetch_json(url, tries=3, timeout=180):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json",
                "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return json.loads(raw.decode("utf-8"))
        except Exception as e:                          # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def slugify(text):
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("'", "").replace("’", "")
    out = []
    for ch in t.lower():
        if ch.isalnum() and ord(ch) < 128:
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:70].strip("-")


def haversine(a, b, c, d):
    r = 6371.0088
    p1, p2 = math.radians(a), math.radians(c)
    x = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(x))


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def tidy_river(name):
    """The Agency's river names, as a person would write them.

    They arrive as "River Wharfe", "Wharfe", "R. Wharfe" and occasionally with
    trailing notes. A page titled "The River River Wharfe" is the sort of thing
    that tells a reader nobody looked.
    """
    t = " ".join(str(name or "").split())
    if not t:
        return ""
    low = t.lower()
    if low.startswith("r. "):
        t = "River " + t[3:]
    elif low.startswith("r "):
        t = "River " + t[2:]
    return t


def label_of(river, town, fallback):
    """What the page is called.

    "The River Wharfe at Addingham" reads as a place. The station's own label is
    the fallback, because some of them are named for the structure rather than
    the settlement and there is nothing better to use.
    """
    river = tidy_river(river)
    town = " ".join(str(town or "").split())
    if river and town:
        return "%s at %s" % (river, town)
    if river:
        return river
    return " ".join(str(fallback or "").split())


def main():
    print("Rivers")
    d = fetch_json(STATIONS)
    items = d.get("items") or []
    print("    %d level stations offered" % len(items))

    kept, dropped = [], defaultdict(int)
    for s in items:
        lat, lon = num(s.get("lat")), num(s.get("long"))
        if lat is None or lon is None:
            dropped["no coordinates"] += 1
            continue
        # Retired gauges are still published. A page whose reading never
        # changes is worse than no page.
        if "statusActive" not in str(s.get("status") or ""):
            dropped["not active"] += 1
            continue
        ss = s.get("stageScale")
        if not isinstance(ss, dict):
            dropped["no stage scale"] += 1
            continue
        low, high = num(ss.get("typicalRangeLow")), num(ss.get("typicalRangeHigh"))
        # THE WHOLE POINT. Without the range there is no way to say whether a
        # reading is high, and a bare number against a local datum is not
        # information — it is a number.
        if low is None or high is None or high <= low:
            dropped["no typical range"] += 1
            continue
        river = tidy_river(s.get("riverName"))
        if not river:
            dropped["no river named"] += 1
            continue
        # A reservoir is not a river reach, and on the drinking-water ones
        # swimming is banned outright — a page here would read as an invitation.
        if "reservoir" in river.lower():
            dropped["reservoir, not a river"] += 1
            continue
        # THE QUALIFIER SAYS WHAT IS BEING MEASURED, AND THE NAME DOES NOT.
        #
        # 658 of these gauges measure GROUNDWATER — a borehole in a field, with
        # riverName set to the literal string "Groundwater Level". A first pass
        # filtered on the name and produced 46 pages about "the Groundwater
        # Level at Kingston Russell", which is not a river and not a place. 274
        # more read a tidal level, which is the sea rather than the river, and
        # reservoir and sump gauges are neither.
        #
        # Only "Stage" is the river running past the gauge. Nothing else here is
        # the thing these pages claim to be about.
        stage = None
        for m in (s.get("measures") or []):
            if not isinstance(m, dict) or m.get("parameter") != "level":
                continue
            if str(m.get("qualifier") or "").strip().lower() == "stage":
                stage = m
                break
        if not stage or not stage.get("@id"):
            dropped["not a river stage gauge"] += 1
            continue
        # AND THE UNIT HAS TO BE A DEPTH. Seven of these gauges report volts and
        # two report degrees Celsius under a "Stage" qualifier — miscoded at
        # source, and published as a river level they would be a lie in the
        # plainest sense. 186 more give no unit at all; the reading is probably
        # metres, but "probably" is not the standard this site holds itself to
        # for a number it puts on a page, so they go too.
        unit = str(stage.get("unitName") or "").strip()
        if unit not in ("m", "mASD", "mAOD"):
            dropped["level not measured in metres"] += 1
            continue
        kept.append({
            "id": "R:" + str(s.get("notation")),
            "lat": round(lat, 5), "lon": round(lon, 5),
            "river": river,
            "town": " ".join(str(s.get("town") or "").split()),
            "catchment": " ".join(str(s.get("catchmentName") or "").split()),
            "name": label_of(river, s.get("town"), s.get("label")),
            "low": low, "high": high,
            # WHAT THIS GAUGE HAS EVER READ, both ends. Used to throw out a
            # broken sensor: Spring Brook at Grove Park reports -27.6m against
            # a typical range of 0.39-0.45, and published as a level that is
            # not a dry brook, it is a fault. The Agency's own record is the
            # right yardstick for "this cannot be a real reading".
            "maxRec": num((ss.get("maxOnRecord") or {}).get("value")
                          if isinstance(ss.get("maxOnRecord"), dict) else None),
            "minRec": num((ss.get("minOnRecord") or {}).get("value")
                          if isinstance(ss.get("minOnRecord"), dict) else None),
            "unit": unit,
            "measure": str(stage["@id"]).rsplit("/", 1)[-1],
        })

    print("    dropped: %s" % dict(dropped))

    # Merge gauges that describe the same reach.
    kept.sort(key=lambda x: (x["river"], x["town"], x["id"]))
    merged, used = [], set()
    for i, a in enumerate(kept):
        if a["id"] in used:
            continue
        used.add(a["id"])
        for b in kept[i + 1:]:
            if b["id"] in used or b["river"] != a["river"]:
                continue
            if haversine(a["lat"], a["lon"], b["lat"], b["lon"]) <= MERGE_KM:
                used.add(b["id"])
                dropped["merged into a neighbour"] += 1
        merged.append(a)

    # Slugs, unique. Two reaches can genuinely share a river and a town.
    seen = defaultdict(int)
    for r in merged:
        base = slugify(r["name"]) or slugify(r["river"]) or r["id"].lower()
        seen[base] += 1
        r["slug"] = base if seen[base] == 1 else "%s-%d" % (base, seen[base])

    # The county AND the country, unpacked. district_of returns a pair, and
    # assigning the pair whole wrote "['Somerset', 'England']" into the field a
    # breadcrumb prints.
    outside = 0
    placed = []
    for r in merged:
        district, country = district_of(r["lat"], r["lon"])
        if not district:
            outside += 1
            continue
        r["district"], r["country"] = district, country
        placed.append(r)
    merged = placed
    if outside:
        print("    %d gauges outside the counties dropped" % outside)

    print("    %d river reaches kept (%d merged away)"
          % (len(merged), dropped["merged into a neighbour"]))
    by_river = defaultdict(int)
    for r in merged:
        by_river[r["river"]] += 1
    top = sorted(by_river.items(), key=lambda kv: -kv[1])[:5]
    print("    most-gauged rivers: %s" % ", ".join("%s (%d)" % t for t in top))

    payload = {
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": ("Environment Agency real-time flood-monitoring API, "
                   "Open Government Licence v3.0"),
        "note": ("Level gauges on English rivers. Not bathing waters: nobody "
                 "samples these, and a gauge is flood infrastructure rather "
                 "than a place to get in."),
        "rivers": merged,
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    path = os.path.join(OUT, "rivers.json")
    io.open(path, "w", encoding="utf-8").write(body)
    print("    wrote rivers.json %.0f KB (%.0f KB gzipped)"
          % (len(body.encode()) / 1024.0, len(gzip.compress(body.encode())) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
