#!/usr/bin/env python3
"""Welsh river gauges, with a typical range this site works out for itself.

WHY THIS ONE IS DIFFERENT FROM THE OTHER THREE.

England, Scotland and the Republic all publish something to judge a reading
against: the Environment Agency a typical band, SEPA a long-term figure per
calendar month, waterlevel.ie a set of exceedance percentiles. Natural Resources
Wales publish none of that. The documented River Levels API is gone — the whole
api.naturalresources.wales host has gone with it — and the live service behind
their own map gives a current reading, a year of history and nothing else. I
read a station's own details page to be sure: a latest reading and a graph.

build_rivers.py drops any gauge with no range, on the rule that a level measured
against a local datum is a number rather than information. Applied literally
that rule gives Wales no river pages at all. So the range here is COMPUTED, from
the twelve months of fifteen-minute readings the service will hand over, and the
page says so in as many words. It is the middle half of what the gauge actually
recorded over a year — the levels it sat between for half of that time — which
is the same quantity waterlevel.ie publishes for Ireland and close to what the
Agency means by a typical band.

WHAT IT IS NOT, and the page must not imply otherwise: it is not a long-term
figure. One year is one year. SEPA's monthly figures rest on decades, so a
Scottish page can say "low for October" and mean it; computing a monthly figure
from a single year would be describing last October's weather and calling it
normal. Wales gets one band for the year and no seasonal claim.

    python3 build_rivers_wales.py             writes rivers_wales.json
    python3 build_rivers_wales.py --limit 20

A YEAR OF HISTORY PER GAUGE IS ABOUT 1.4MB, so a full run moves a few hundred
megabytes off a public service. Cached under /tmp between runs: this is a
register build, run when gauges change, and the matching rules get tuned far
more often than the gauges move.
"""

import io
import json
import os
import ssl
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import river_names as N                                 # noqa: E402
from osgb import to_wgs84                               # noqa: E402

OUT = os.path.join(HERE, "rivers_wales.json")
STATIONS = "https://rivers-and-seas.naturalresources.wales/map/GetStations"
HISTORY = ("https://rivers-and-seas.naturalresources.wales/graph/getdata"
           "?parameterId=%d")
UA = "caniswim/1.0 (personal bathing water tool; open data)"
CTX = ssl.create_default_context()
CACHE = os.path.join("/tmp", "caniswim-nrw")

# A year of fifteen-minute readings is about 35,000 points. Well under half of
# that is a gauge that has been off for months, and a band computed from it
# describes a few weeks rather than a year.
MIN_POINTS = 16000
# A TIDAL REACH CANNOT ANSWER "IS THE RIVER UP". Its level is the tide, so a
# band is meaningless and the verdict would flip twice a day. NRW flag ten
# gauges as Tide Level and those are excluded by their own label; this catches
# a reach that reports as a river level and behaves like a tide. Measured on
# real gauges first: the Aeron at Aberaeron traverses 2 per cent of its annual
# range on a median day, the Dee at Farndon 4 per cent, the Monnow under 1. A
# gauge covering a quarter of its year's range every single day is not a river.
# Measured on all 242 gauges with a year of readings, the eleven above this line
# are: four with "Tidal" in their own title, three more on plainly tidal reaches
# (Cardigan Quay, Rhuddlan, Trefriw), one reservoir, and three at a weir or
# below a hydro dam. Not all of them are tides, which is the point — what the
# number detects is a level driven by something other than rainfall, and a
# typical band is meaningless for every one of them.
TIDAL_RATIO = 0.25
# AND A RESERVOIR IS NOT A REACH OF RIVER. Three survived the swing test because
# their releases are steady: "Usk at Usk Reservoir", "Tywi at Llyn Brianne
# Reservoir", "Fords Lake at Stepaside". The same pattern the Irish register
# uses, which also catches a canal or a dock.
import re                                               # noqa: E402
STILL = re.compile(r"\b(reservoir|lake|llyn|pond|canal|dock)\b", re.I)
# The same distance build_rivers.py calls one reach. NRW republish sixteen
# Environment Agency gauges for catchments that cross the border — titled
# "Environment Agency Station monitoring the Wye" and sitting at exactly the
# same coordinates as gauges this site already has from the EA, with the
# Agency's own published range. Keeping them would have been sixteen duplicate
# pages for one gauge, and the worse copy of the two.
DUPE_KM = 1.5


def fetch(url, timeout=180, tries=4):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:                          # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("%s: %s" % (url[-40:], str(last)[:110]))


def history(pid):
    """A year of readings for one parameter, cached on disk.

    ONE PARAMETER ID PER GAUGE, and this is the trap in this service. The
    history endpoint ignores locationId entirely and keys only on parameterId.
    The Aeron at Aberaeron happens to have parameterId 1, so passing
    "locationId=<x>&parameterId=1" for three different rivers returned the Aeron
    three times — identical point counts and identical ranges for the Wye at
    Chepstow and the Dee at Farndon, which is how it was caught. The 266
    river-level parameters have 266 distinct ids and the id is the only thing
    that selects a series.
    """
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "p%d.json" % pid)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        try:
            return json.load(io.open(path, encoding="utf-8"))
        except Exception:                               # noqa: BLE001
            pass
    d = fetch(HISTORY % pid)
    pts = [(p.get("x"), p.get("y")) for p in (d.get("data") or [])
           if isinstance(p.get("y"), (int, float))]
    io.open(path, "w", encoding="utf-8").write(json.dumps(pts))
    return pts


def pct(sorted_vals, q):
    """The q-th percentile of an already-sorted list, linearly interpolated."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    f = (len(sorted_vals) - 1) * (q / 100.0)
    lo = int(f)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (f - lo)


def tidal_ratio(pts):
    """How much of its annual range this gauge covers on a median day."""
    byday = defaultdict(list)
    for when, v in pts:
        byday[str(when)[:10]].append(v)
    daily = sorted(max(v) - min(v) for v in byday.values() if len(v) > 40)
    vals = sorted(v for _, v in pts)
    ann = (vals[-1] - vals[0]) if vals else 0.0
    if not daily or ann <= 0:
        return 0.0
    return pct(daily, 50) / ann


def tidy(s):
    return " ".join(str(s or "").split())


def eng(v):
    """The English half of one of this service's bilingual fields."""
    if isinstance(v, dict):
        return tidy(v.get("english") or v.get("welsh"))
    return tidy(v)


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    print("Welsh river gauges, from Natural Resources Wales")
    stations = fetch(STATIONS)
    if not isinstance(stations, list) or len(stations) < 200:
        raise SystemExit("GetStations returned %s rows — refusing to build "
                         "from a partial answer"
                         % (len(stations) if isinstance(stations, list) else "no"))
    print("    %d locations offered" % len(stations))

    want, dropped = [], {}

    def drop(why):
        dropped[why] = dropped.get(why, 0) + 1

    for r in stations:
        params = r.get("parameters") or []
        level = next((p for p in params if p.get("typeId") == 1), None)
        if not level or not level.get("id"):
            continue
        # NRW's own label for a tide gauge. Taken at face value: if they say a
        # location measures tide level, no amount of river-level data beside it
        # makes a band meaningful.
        if any(p.get("typeId") == 3 for p in params):
            drop("NRW label it a tide gauge")
            continue
        g = r.get("britishNationalGrid") or {}
        if not g.get("x") or not g.get("y"):
            drop("no grid reference")
            continue
        lat, lon = to_wgs84(g["x"], g["y"])
        want.append({
            "pid": int(level["id"]),
            "loc": r.get("id"),
            "lat": round(lat, 5), "lon": round(lon, 5),
            "name": eng(r.get("title")) or eng(r.get("name")),
            "welsh": (r.get("title") or {}).get("welsh") if isinstance(r.get("title"), dict) else None,
            "river": eng(r.get("waterBody")),
            "town": eng(r.get("name")),
            "catchment": eng(r.get("catchment")),
            "unit": tidy(level.get("unit")) or "m",
        })
    if limit:
        want = want[:limit]
    print("    %d river-level gauges to read" % len(want))

    # THE DUPLICATES GO BEFORE ANY HISTORY IS FETCHED, because fetching a year
    # of readings for a gauge we are about to throw away is a few megabytes off
    # somebody else's service for nothing.
    try:
        existing = [r for r in json.load(io.open(
            os.path.join(os.path.dirname(HERE), "jhw-mobile-pr", "swim",
                         "rivers.json"), encoding="utf-8")).get("rivers") or []
            if isinstance(r.get("lat"), (int, float))]
    except Exception as e:                              # noqa: BLE001
        raise SystemExit("cannot read the published register to check for "
                         "duplicates (%s). NRW republish sixteen Environment "
                         "Agency gauges and this is the only thing that catches "
                         "them." % str(e)[:70])
    keep = []
    for w in want:
        near = min((N.haversine(w["lat"], w["lon"], e["lat"], e["lon"]), e)
                   for e in existing)
        if near[0] <= DUPE_KM:
            drop("already published as %s" % (near[1].get("src") or "ea"))
            continue
        keep.append(w)
    want = keep
    print("    %d after dropping gauges this site already has" % len(want))

    print("    reading a year of levels for each (cached under %s) ..." % CACHE)
    done = [0]

    def work(w):
        try:
            w["pts"] = history(w["pid"])
        except Exception as e:                          # noqa: BLE001
            w["pts"] = []
            w["err"] = str(e)[:80]
        done[0] += 1
        if done[0] % 40 == 0:
            print("      %d/%d" % (done[0], len(want)))
        return w

    with ThreadPoolExecutor(max_workers=5) as pool:
        want = list(pool.map(work, want))

    out = []
    for w in want:
        pts = w.pop("pts", [])
        if w.get("err"):
            drop("history could not be read")
            continue
        if len(pts) < MIN_POINTS:
            # The Wye at Chepstow Bridge returns no history at all, which is
            # how the one gauge on this list that is plainly tidal removes
            # itself.
            drop("fewer than %d readings in the year" % MIN_POINTS)
            continue
        ratio = tidal_ratio(pts)
        if ratio > TIDAL_RATIO:
            drop("level swings daily (tide, weir or release), so a band means "
                 "nothing")
            continue
        if STILL.search(w["name"]) or STILL.search(w["river"] or ""):
            drop("a reservoir, lake or canal, not a reach of river")
            continue
        vals = sorted(v for _, v in pts)
        low, high = pct(vals, 25), pct(vals, 75)
        if low is None or high is None or high <= low:
            drop("no usable range in the year")
            continue
        out.append({
            "id": "R:W%d" % w["pid"],
            # Said outright, like the others: neither the id nor the country can
            # be trusted to carry it.
            "src": "nrw",
            "lat": w["lat"], "lon": w["lon"],
            "river": w["river"], "town": w["town"],
            "catchment": w["catchment"],
            "name": w["name"],
            "welsh": w["welsh"],
            "param": w["pid"],
            "low": round(low, 3), "high": round(high, 3),
            # The ends of the year, for the faulty-sensor gate the collector
            # applies to every source. A reading outside anything the gauge
            # recorded in twelve months, by more than the band's own width, is
            # a broken sensor rather than a remarkable river.
            "minRec": round(vals[0], 3), "maxRec": round(vals[-1], 3),
            "n": len(pts),
            "from": str(pts[0][0])[:10], "to": str(pts[-1][0])[:10],
            "unit": w["unit"],
        })

    # The names already read as places — NRW title them "Aeron at Aberaeron" —
    # so enrich() only has to lock a slug and find a county. shout=False: they
    # are typed properly.
    out, info = N.enrich(out, HERE)
    out.sort(key=lambda x: (x.get("country") or "", x["river"], x["town"], x["id"]))
    print("    kept %d, dropped %s" % (len(out), dropped or "nothing"))
    print("    names: %d merged as the same reach, %d slugs kept, %d minted, "
          "%d outside any county" % (info["merged"], info["slugs_kept"],
                                     info["slugs_new"], info["no_county"]))

    io.open(OUT, "w", encoding="utf-8").write(json.dumps({
        "note": ("Welsh river level gauges. low/high is the middle half of "
                 "everything the gauge recorded over the twelve months named "
                 "in from/to — the levels it sat between for half of that "
                 "time. COMPUTED BY THIS SITE, not published by Natural "
                 "Resources Wales, who publish no typical range of any kind; "
                 "the page says so. One year is one year, so unlike Scotland "
                 "there is no figure per calendar month and no seasonal claim "
                 "is made. Positions are converted from British National Grid, "
                 "which is all NRW give."),
        "source": "https://rivers-and-seas.naturalresources.wales/",
        "stations": STATIONS,
        "history": HISTORY % 0,
        "window": {"from": min((r["from"] for r in out), default=None),
                   "to": max((r["to"] for r in out), default=None)},
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rivers": out}, indent=1, sort_keys=True) + "\n")
    print("written to %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
