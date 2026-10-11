#!/usr/bin/env python3
"""The Republic's river level gauges, with the percentile range published for them.

WHY A SEPARATE FILE, AND WHY THE NUMBERS ARE NOT THE ENGLISH ONES. See the head
of build_rivers_scotland.py: the Environment Agency publishes one typical band
per station, and nobody else publishes that same quantity. waterlevel.ie
publishes exceedance percentiles — the level exceeded 5 per cent of the time, 50
per cent, 95 per cent — which is a better description of a river than a band,
and is a different thing.

THE ONE WAY THIS GOES BADLY WRONG. They are EXCEEDANCE percentiles, so the
numbers run DOWNWARDS as the percentile rises: at Corryosla, P05 is 10.106m,
P50 is 8.858m and P95 is 8.359m. P95 is a LOW river, not a high one. Reading
them the familiar way round — as though P95 were the 95th highest — would print
"higher than usual" on a river at its summer minimum, and the opposite, on 406
pages. Verified rather than assumed: P05 >= P50 >= P95 holds on all 407 records
that have the three values, with no exceptions.

A LEVEL HERE IS NOT A STAGE. These are absolute levels above Malin Head datum,
so they read 8 to 111 metres, where an English gauge reads 0.3m above its own
zero. Nothing may compare one country's number with another's, and no page may
describe these as a height of water.

    python3 build_rivers_ireland.py             writes rivers_ireland.json

The register call returns the live reading as well as the metadata, so this is
one request for everything except the percentiles, and the join is station_id —
not station_no, which is a different number in the same record.

Source: Office of Public Works / EPA, waterlevel.ie.
"""
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "rivers_ireland.json")

REGISTER = "https://waterlevel.ie/hydro-data/data/internet/layers/10/index.json"
PERCENTILES = "https://waterlevel.ie/hydro-data/thresholds/spercentiles.json"
UA = "caniswim/1.0 (personal bathing water tool; open data)"
CTX = ssl.create_default_context()

# The three that carry the page. P05 is the wet end, P50 the middle, P95 the dry
# end — see the warning above.
WET, MID, DRY = "WEB.Percentile-05", "WEB.Percentile-50", "WEB.Percentile-95"

# A TIDAL GAUGE CANNOT ANSWER "IS THE RIVER UP". Its level is the tide, so a
# reading above the median means the tide is in, and a page saying "higher than
# usual for the time of year" would be wrong twice a day, every day. 28 of the
# 491 are classed Tidal. 46 more are Inactive, and build_rivers.py already
# refuses those for England on the grounds that a page whose reading never
# changes is worse than no page.
SKIP_CLASS = ("inactive", "tidal")
# And a lake is not a reach of river. Six of them, named in capitals in the
# water body field: "GARADICE LAKE", "LOUGH RINN", "LADY'S ISLAND LAKE".
LAKE = re.compile(r"\b(?:lake|lough|loch|reservoir|pond)\b|\bl\.\s", re.I)


def fetch(url):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:                          # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("%s failed: %s" % (url, str(last)[:140]))


def fnum(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def tidy(s):
    return " ".join(str(s or "").split())


def catchment_of(r):
    """The catchment, from whichever of the two fields actually holds one."""
    for key in ("catchment_name", "CATCHMENT", "SW_RBD", "RBD"):
        v = tidy(r.get(key))
        if v and v not in ("---", "-", "n/a", "N/A", "0"):
            return v
    return ""


def main():
    print("Irish river gauges, from waterlevel.ie")
    reg = fetch(REGISTER)
    if not isinstance(reg, list) or len(reg) < 300:
        raise SystemExit("register returned %s rows — refusing to build from a "
                         "partial answer" % (len(reg) if isinstance(reg, list) else "no"))
    print("    %d gauges in the register" % len(reg))

    praw = fetch(PERCENTILES)
    pct = {str(r.get("station_id")): r for r in praw if isinstance(r, dict)}
    print("    %d percentile records" % len(pct))

    # THE DIRECTION IS CHECKED, NOT TRUSTED, and checked on every record rather
    # than a sample. If waterlevel.ie ever switched to the other convention this
    # would print the opposite of the truth on hundreds of pages, and nothing
    # downstream could tell.
    checked = wrong = 0
    for v in pct.values():
        a, b, c = fnum(v.get(WET)), fnum(v.get(MID)), fnum(v.get(DRY))
        if None in (a, b, c):
            continue
        checked += 1
        if not (a >= b >= c):
            wrong += 1
    print("    exceedance direction holds on %d of %d records" % (checked - wrong, checked))
    if checked < 100 or wrong > checked * 0.02:
        raise SystemExit(
            "%d of %d percentile records do not run P05 >= P50 >= P95. These are "
            "meant to be EXCEEDANCE percentiles; if that has changed, every "
            "high/low sentence built on them is backwards. Refusing to build."
            % (wrong, checked))

    out, dropped = [], {}
    def drop(why):
        dropped[why] = dropped.get(why, 0) + 1

    seen = set()
    for r in reg:
        sid = str(r.get("station_id") or "")
        lat, lon = fnum(r.get("station_latitude")), fnum(r.get("station_longitude"))
        if not sid or sid in seen:
            drop("no station id, or a duplicate")
            continue
        if lat is None or lon is None:
            drop("no coordinates")
            continue
        cls = tidy(r.get("Stn_Class")).lower()
        if any(k in cls for k in SKIP_CLASS):
            drop("classed %s" % (tidy(r.get("Stn_Class")) or "unknown"))
            continue
        body = tidy(r.get("WTO_OBJECT"))
        if LAKE.search(body):
            drop("a lake, not a reach of river")
            continue
        v = pct.get(sid)
        wet = fnum((v or {}).get(WET))
        mid = fnum((v or {}).get(MID))
        dry = fnum((v or {}).get(DRY))
        # THE SAME RULE AS ENGLAND AND SCOTLAND. A level above Malin Head datum
        # with nothing to compare it against is a number, not information, and a
        # page carrying one would be a page that cannot answer its own question.
        if None in (wet, mid, dry) or not (wet > dry):
            drop("no usable percentile range")
            continue
        seen.add(sid)
        out.append({
            "id": "R:I" + sid,
            "lat": round(lat, 5), "lon": round(lon, 5),
            "river": body,
            "town": tidy(r.get("station_name")),
            # "---" IS NOT A CATCHMENT. catchment_name carries that placeholder
            # on 11 gauges and CATCHMENT is blank on 106, so neither alone is
            # enough and a page would have printed the dashes.
            "catchment": catchment_of(r),
            "station": sid,
            "no": tidy(r.get("station_no")),
            # NOT low/high, for the same reason Scotland's are not: these are
            # exceedance percentiles against an absolute datum, and the English
            # fields mean a typical band above a local zero.
            "wet": round(wet, 3), "mid": round(mid, 3), "dry": round(dry, 3),
            "amax": fnum((v or {}).get("WEB.YearHyd.Amax(median)")),
            "datum": tidy(r.get("station_gauge_datum_unit")),
            "unit": "mAOD",
        })

    out.sort(key=lambda x: (x["catchment"], x["town"], x["id"]))
    print("    kept %d, dropped %s" % (len(out), dropped or "nothing"))

    io.open(OUT, "w", encoding="utf-8").write(json.dumps({
        "note": ("River level gauges in the Republic of Ireland with the "
                 "exceedance percentiles waterlevel.ie publishes for them. "
                 "wet/mid/dry are Percentile-05, -50 and -95: the level "
                 "exceeded 5 per cent of the time, half the time, and 95 per "
                 "cent of the time. THEY RUN DOWNWARDS — wet > mid > dry "
                 "— because a level exceeded 95 per cent of the time is a "
                 "LOW river. Values are absolute levels above Malin Head "
                 "datum, not a stage above a local zero, so they read 8 to 111 "
                 "metres and cannot be compared with an English gauge's number."),
        "source": "https://waterlevel.ie/",
        "register": REGISTER,
        "percentiles": PERCENTILES,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rivers": out}, indent=1, sort_keys=True) + "\n")
    print("written to %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
