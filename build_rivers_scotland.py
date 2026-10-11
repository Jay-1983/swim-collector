#!/usr/bin/env python3
"""Scotland's river gauges, with the long-term range SEPA publishes for them.

WHY A SEPARATE FILE RATHER THAN MORE ROWS IN rivers.json.

build_rivers.py drops any gauge without a typical range, and it is right to:
a level is measured against a datum belonging to that station alone, so "0.31m"
means nothing on its own, and the only thing that makes it information is where
it sits against what this station usually reads.

SEPA publishes something BETTER than the Environment Agency and it is NOT THE
SAME QUANTITY. England gives one typicalRangeLow and one typicalRangeHigh per
station, for the whole year. SEPA gives, for every one of its 394 level gauges,
a long-term Min, Mean and Max for each calendar month — so a Scottish page can
say "low for October" where an English one can only say "low". Perth in October:
min 0.125m, mean 1.018m, max 4.921m.

Those are long-term EXTREMES, not a typical band. Dropping 0.125 and 4.921 into
the low/high fields would produce a range so wide that no reading is ever high
or low, while the page went on calling it the usual range — the same sentence
describing a different quantity, which is the fault this site keeps finding in
its own copy. So the monthly figures are kept as themselves, under their own
names, and the wording that goes with them is a separate decision from the
English one.

    python3 build_rivers_scotland.py            writes rivers_scotland.json
    python3 build_rivers_scotland.py --limit 20 a quick pass over 20 stations

WHAT IT COSTS. SEPA allocate request credits, 5,000 a day, and a Referer header
gets its own allocation rather than sharing the caller's IP — which matters
because the collector runs from GitHub Actions on shared runner addresses. This
script is a register build, run when gauges change rather than on a schedule:
about 36 calls. The live reading is one call for all 394.

Source: SEPA, timeseries.sepa.org.uk KiWIS service, Open Government Licence.
"""
import io
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "rivers_scotland.json")
BASE = "https://timeseries.sepa.org.uk/KiWIS/KiWIS"
COMMON = {"datasource": "0", "service": "kisters", "type": "queryServices",
          "format": "json"}
UA = "caniswim/1.0 (personal bathing water tool; open data)"
# SEPA document a Referer as an alternative credit allocation to the caller's
# IP address. Set here rather than left to the runner's shared address, so a
# stranger on the same GitHub Actions IP cannot spend this site's allowance.
REFERER = "https://caniswim.co.uk/"
CTX = ssl.create_default_context()

# A ts_id batch bigger than this answers 504. Measured, not guessed: 25 series
# returned 200 in a few kilobytes and 80 timed out.
BATCH = 25
# Eighteen months ending at the end of last month: enough to contain every
# calendar month whatever point of its own cycle the series has reached.
_T = time.gmtime()
LTV_TO = "%04d-%02d-28" % (_T.tm_year, _T.tm_mon)
LTV_FROM = "%04d-%02d-01" % (_T.tm_year - 2 if _T.tm_mon < 6 else _T.tm_year - 1,
                             ((_T.tm_mon - 6) % 12) + 1)
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def call(request, **params):
    q = dict(COMMON)
    q["request"] = request
    q.update({k: v for k, v in params.items() if v is not None})
    url = BASE + "?" + urllib.parse.urlencode(q)
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": REFERER, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            # KiWIS answers 200 with an error OBJECT rather than a status, so a
            # failure looks like data unless this is checked. The first version
            # of this read {"type":"error"} as a list of rows and produced a
            # register of nothing with no complaint.
            if isinstance(d, dict) and d.get("type") == "error":
                raise RuntimeError("%s: %s" % (d.get("code"), d.get("message")))
            return d
        except Exception as e:                          # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("%s failed: %s" % (request, str(last)[:150]))


def rows(d):
    """A KiWIS table, as dicts. The first row is the header."""
    if not isinstance(d, list) or not d or not isinstance(d[0], list):
        return []
    head = d[0]
    return [dict(zip(head, r)) for r in d[1:]]


def fnum(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    print("Scottish river gauges, from SEPA")

    # 1. The live level series, which is the set of gauges that actually report.
    live = rows(call("getTimeseriesList", stationparameter_no="SG",
                     ts_shortname="15m.Cmd",
                     returnfields="station_no,station_name,ts_id,"
                                  "station_latitude,station_longitude"))
    print("    %d gauges publish a 15-minute level" % len(live))
    if len(live) < 300:
        raise SystemExit("only %d level series — refusing to build a register "
                         "from a partial answer" % len(live))

    # 2. Names, rivers and catchments. A separate call because river_name and
    #    catchment_name are not valid returnfields on getTimeseriesList — asking
    #    for them there is an InvalidParameterValue, not an empty column.
    meta = {r["station_no"]: r for r in
            rows(call("getStationList",
                      returnfields="station_no,station_name,station_latitude,"
                                   "station_longitude,river_name,catchment_name"))}
    print("    %d stations in the register, %d of them with a river name"
          % (len(meta), sum(1 for r in meta.values() if (r.get("river_name") or "").strip())))

    # 3. The long-term monthly series ids, one call per statistic.
    ltv = {}
    for stat, short in (("min", "LTV.HMonth.Min"), ("mean", "LTV.HMonth.Mean"),
                        ("max", "LTV.HMonth.Max")):
        got = rows(call("getTimeseriesList", stationparameter_no="SG",
                        ts_shortname=short, returnfields="station_no,ts_id"))
        for r in got:
            ltv.setdefault(r["station_no"], {})[stat] = r["ts_id"]
        print("    %d stations publish %s" % (len(got), short))

    want = [r for r in live if r["station_no"] in ltv]
    if limit:
        want = want[:limit]
    print("    %d gauges have both a live level and a long-term range" % len(want))

    # 4. The twelve monthly values for each. Batched, because a large multi-series
    #    historical query answers 504.
    ids, owner = [], {}
    for r in want:
        for stat, tid in sorted(ltv[r["station_no"]].items()):
            ids.append(tid)
            owner[str(tid)] = (r["station_no"], stat)
    print("    reading %d long-term series in batches of %d ..." % (len(ids), BATCH))

    monthly = {}
    for i in range(0, len(ids), BATCH):
        batch = ids[i:i + BATCH]
        # A WINDOW WIDE ENOUGH TO HOLD EVERY CALENDAR MONTH.
        #
        # These are long-term climatologies, not readings: the value stamped
        # 2025-10-01 and the one stamped 2026-10-01 are both 1.018 at Perth. But
        # the series is extended as time passes rather than published a year
        # ahead, so today it runs out at 2026-11-01 — and a single calendar year
        # window came back with no December for any of the 359 gauges, which
        # would have left every Scottish page with nothing to compare against
        # for a month of the year. Eighteen months back always contains all
        # twelve, and the loop below keeps the latest value seen for each.
        d = call("getTimeseriesValues", ts_id=",".join(str(x) for x in batch),
                 **{"from": LTV_FROM, "to": LTV_TO})
        if not isinstance(d, list):
            print("      batch at %d returned no list" % i)
            continue
        for blk in d:
            # ts_name comes back NULL in a values response, so which statistic a
            # block holds can only be known from the id that was asked for. The
            # blocks come back in the order requested; the ts_id is echoed, so
            # it is read rather than assumed.
            tid = str(blk.get("ts_id") or "")
            if tid not in owner:
                continue
            sn, stat = owner[tid]
            for when, val in (blk.get("data") or []):
                try:
                    m = int(str(when)[5:7]) - 1
                except ValueError:
                    continue
                if 0 <= m < 12 and fnum(val) is not None:
                    monthly.setdefault(sn, {}).setdefault(stat, [None] * 12)[m] = \
                        round(fnum(val), 3)
        if i + BATCH < len(ids):
            time.sleep(1)
        if (i // BATCH) % 6 == 5:
            print("      %d/%d series" % (min(i + BATCH, len(ids)), len(ids)))

    # 5. Assemble, keeping only gauges whose range can actually be used.
    out, dropped = [], {}
    def drop(why):
        dropped[why] = dropped.get(why, 0) + 1

    for r in want:
        sn = r["station_no"]
        lat, lon = fnum(r.get("station_latitude")), fnum(r.get("station_longitude"))
        m = monthly.get(sn) or {}
        mean = m.get("mean") or [None] * 12
        mmin = m.get("min") or [None] * 12
        mmax = m.get("max") or [None] * 12
        if lat is None or lon is None:
            drop("no coordinates")
            continue
        # THE SAME RULE AS ENGLAND, applied to what Scotland actually gives. A
        # gauge with no monthly mean has nothing to compare today against, and a
        # bare level above a local datum is a number rather than information.
        have = sum(1 for v in mean if v is not None)
        if have < 6:
            drop("fewer than six months of long-term mean")
            continue
        md = meta.get(sn) or {}
        river = " ".join(str(md.get("river_name") or "").split())
        town = " ".join(str(md.get("station_name") or r.get("station_name") or "").split())
        # A RANGE PER CALENDAR MONTH, built from the month own published
        # figures. low is the lowest level ever recorded at this gauge for
        # this month, and high is the same distance above the month mean, so
        # the five words the page already has land where they should: "Very
        # low" means below anything on record for the month, which is a
        # statement England cannot make, and the middle band is the month
        # average either way.
        #
        # NOT mmin..mmax. Those are both extremes and they are wildly
        # asymmetric: the median gauge monthly maximum sits 5.6 times
        # further above the mean than its minimum sits below, because the
        # top end is floods. A band drawn between them is so wide that
        # nothing is ever high, while the page goes on calling it the usual
        # range.
        lowM, highM = [], []
        for i in range(12):
            me, mn = mean[i], mmin[i]
            if me is None or mn is None or me <= mn:
                lowM.append(None)
                highM.append(None)
                continue
            lowM.append(round(mn, 3))
            highM.append(round(me + (me - mn), 3))
        out.append({
            "id": "R:S" + str(sn),
            # THE SOURCE, SAID OUTRIGHT, because neither the id nor the
            # country can be trusted to say it. swim/rivers.json already
            # holds two ENGLISH gauges whose ids begin R:S - Combe Haven at
            # Crowhurst (R:SE7050) and the Medway at Golden Green (R:SE561) -
            # so a prefix test would route two live English pages into
            # Scottish copy. It also already holds three gauges in Scotland
            # and two in Wales that are Environment Agency stations with EA
            # figures, so country is not the switch either. The feed a row
            # belongs to is its own field.
            "src": "sepa",
            "lat": round(lat, 5), "lon": round(lon, 5),
            "river": river,
            "town": town,
            "catchment": " ".join(str(md.get("catchment_name") or "").split()),
            "station": str(sn),
            "ts": str(r.get("ts_id")),
            "unit": "m",
            # NOT low/high. These are long-term monthly figures and they are
            # kept under names that say so, because the English low/high is a
            # typical band and these are extremes — writing them into the same
            # fields would leave the page calling an extreme a usual range.
            "mean": mean, "mmin": mmin, "mmax": mmax,
            "lowM": lowM, "highM": highM,
            # The faulty-sensor gate the collector already applies to
            # England needs a floor and a ceiling, and these are exactly
            # that: the lowest and highest this gauge has recorded in any
            # month. Proved necessary rather than assumed - the Lossie at
            # Ballachraggan was reporting -9.000 against a record of 0.322
            # to 1.966, which is a sentinel for "no data", not a level.
            "minRec": round(min(v for v in mmin if v is not None), 3),
            "maxRec": round(max(v for v in mmax if v is not None), 3),
            "months": have,
        })

    import river_names as N
    out, info = N.enrich(out, HERE)
    out.sort(key=lambda x: (x["river"], x["town"], x["id"]))
    print("    kept %d, dropped %s" % (len(out), dropped or "nothing"))
    print("    names: %d merged as the same reach, %d slugs kept, %d minted, "
          "%d outside any county" % (info["merged"], info["slugs_kept"],
                                     info["slugs_new"], info["no_county"]))

    io.open(OUT, "w", encoding="utf-8").write(json.dumps({
        "note": ("Scottish river level gauges with SEPA's long-term monthly "
                 "statistics. mean/mmin/mmax are twelve values each, January "
                 "to December: the long-term average, lowest and highest level "
                 "recorded for that calendar month. These are NOT the English "
                 "typicalRangeLow/High — that is a typical band and these are "
                 "extremes, so a reading inside mmin..mmax is not necessarily "
                 "normal. The comparison that means something is against mean "
                 "for the month in question."),
        "source": "https://timeseries.sepa.org.uk/",
        "licence": "Open Government Licence",
        "months": list(MONTHS),
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "live": ("https://timeseries.sepa.org.uk/KiWIS/KiWIS?datasource=0&"
                 "service=kisters&type=queryServices&request="
                 "getTimeseriesValueLayer&format=json&bbox=-9,54,0,61&"
                 "stationparameter_no=SG&ts_shortname=15m.Cmd"),
        "rivers": out}, indent=1, sort_keys=True) + "\n")
    print("written to %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
