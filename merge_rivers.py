#!/usr/bin/env python3
"""One river register out of three regulators' worth of gauges.

swim/rivers.json is what the site builds pages from and what the collector reads
to know which gauges exist. It held England only. This folds the Scottish and
Irish registers into it so there is ONE file: the build reads one, the collector
makes one load_static call, and every row says which feed it belongs to.

Three published registers would have been three things to keep in step and three
ways for a page to exist with no live feed behind it.

    python3 merge_rivers.py                     writes ../jhw-mobile-pr/swim/rivers.json
    python3 merge_rivers.py --out DIR

WHAT IT REFUSES TO DO. It will not drop England on the floor: if the English
rows are missing or fewer than the file already has, it stops. build_rivers.py
is the only thing that writes those rows and it is not run here, so they are
read back out of the existing file and carried forward.
"""

import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("SWIM_SITE") or os.path.join(
    os.path.dirname(HERE), "jhw-mobile-pr", "swim")

EXTRA = (("rivers_scotland.json", "sepa"), ("rivers_ireland.json", "opw"),
         ("rivers_wales.json", "nrw"))
# The fields a page or the collector actually reads. Everything else in the two
# source files — the twelve-month mean/mmin/mmax arrays, the percentile ladder,
# the station numbers — is working material for the builders and has no business
# in a file the site downloads on every collector run.
KEEP = ("id", "src", "lat", "lon", "river", "town", "catchment", "name", "slug",
        "district", "country", "low", "high", "lowM", "highM", "minRec",
        "maxRec", "unit", "measure", "ts", "station", "pct", "datum",
        "param", "welsh", "to")


def main():
    out_dir = SITE
    if "--out" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--out") + 1]
    path = os.path.join(out_dir, "rivers.json")
    if not os.path.exists(path):
        raise SystemExit("no %s to merge into" % path)
    doc = json.load(io.open(path, encoding="utf-8"))
    rows = doc.get("rivers") or []
    english = [r for r in rows if (r.get("src") or "ea") == "ea"]
    if len(english) < 1000:
        raise SystemExit(
            "REFUSING TO WRITE: only %d English gauges in %s. build_rivers.py "
            "writes those and is not run here, so they are carried forward from "
            "this file — if they are missing, something else is wrong and "
            "merging would publish a register with most of England gone."
            % (len(english), path))
    for r in english:
        r.setdefault("src", "ea")

    merged = list(english)
    seen = {r["id"] for r in merged}
    slugs = {r["slug"] for r in merged if r.get("slug")}
    added = {}
    for name, src in EXTRA:
        f = os.path.join(HERE, name)
        if not os.path.exists(f):
            print("  %s not built yet, skipped" % name)
            continue
        got = json.load(io.open(f, encoding="utf-8")).get("rivers") or []
        n = 0
        for r in got:
            if r.get("id") in seen:
                print("  duplicate id %s skipped" % r.get("id"))
                continue
            # A SLUG COLLISION WOULD SILENTLY OVERWRITE A PAGE. The two builders
            # lock their slugs against this file, so a clash means one of them
            # minted before the other was merged; say so rather than serve two
            # rivers at one URL.
            if r.get("slug") in slugs:
                print("  slug clash on %s (%s) — skipped"
                      % (r.get("slug"), r.get("id")))
                continue
            seen.add(r["id"])
            slugs.add(r["slug"])
            merged.append({k: r[k] for k in KEEP if k in r})
            n += 1
        added[src] = n

    merged.sort(key=lambda r: (r.get("country") or "", r.get("river") or "",
                               r.get("town") or "", r["id"]))
    doc["rivers"] = merged
    # FOUR SOURCES, NOT THREE, AND THE RANGES ARE NOT WHAT THIS SAID.
    #
    # Wales was added on 11 October and neither this note nor `sources` was
    # touched, so the register documented three feeds and announced "the three"
    # while carrying 219 nrw rows — and it is the register's own description of
    # itself, published at /swim/rivers.json for anybody reusing the data.
    #
    # The ranges were wrong as well as incomplete. low/high is the interquartile
    # range for WALES, which this site computes because Natural Resources Wales
    # publishes no range at all; Ireland's comes from waterlevel.ie's exceedance
    # percentiles, which run downwards. Saying the interquartile range was the
    # Irish one got both nations wrong in the same sentence.
    doc["note"] = (
        "Gauged river reaches with a range to judge today's reading against. "
        "src says which feed each row belongs to: ea = Environment Agency "
        "(England), sepa = SEPA (Scotland), nrw = Natural Resources Wales, "
        "opw = waterlevel.ie (Republic of Ireland). The four do not publish the "
        "same quantity. low/high is the Agency's own typical band in England; "
        "in Wales it is the 25th to 75th percentile of twelve months of history, "
        "computed here because Natural Resources Wales publishes no range, and "
        "it carries no seasonal meaning; in Ireland it is derived from "
        "waterlevel.ie's exceedance percentiles, which run downwards, so P05 is "
        "a high level and P95 a low one. Scotland has no low/high at all and "
        "uses lowM/highM, a band per calendar month. Irish levels are absolute "
        "heights above Malin Head datum rather than a stage above a local zero, "
        "so no level here is comparable with a level at another gauge — "
        "only with the range published for that gauge.")
    doc["sources"] = {
        "ea": "https://environment.data.gov.uk/flood-monitoring",
        "sepa": "https://timeseries.sepa.org.uk/",
        "nrw": "https://rivers-and-seas.naturalresources.wales/",
        "opw": "https://waterlevel.ie/",
    }
    # THE NOTE DESCRIBES THE FILE, SO IT HAS TO KEEP UP WITH IT.
    #
    # Wales was merged in and the note kept saying "the three" for three weeks,
    # on a file published at /swim/rivers.json as the register's own account of
    # itself. The failure was silent because nothing compares the prose with the
    # rows. This does: every src actually present must appear in `sources` and
    # be named in the note, and the note must not claim a count that is wrong.
    present = sorted({r.get("src") for r in merged if r.get("src")})
    missing_src = [s for s in present if s not in doc["sources"]]
    unnamed = [s for s in present if ("%s = " % s) not in doc["note"]]
    counts = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    wrong_count = [w for n, w in counts.items()
                   if n != len(present) and ("The %s do not" % w) in doc["note"]]
    problems = []
    if missing_src:
        problems.append("no sources entry for %s" % ", ".join(missing_src))
    if unnamed:
        problems.append("the note does not name %s" % ", ".join(unnamed))
    if wrong_count:
        problems.append("the note says \"The %s\" for %d feeds"
                        % (wrong_count[0], len(present)))
    if problems:
        raise SystemExit(
            "REFUSING TO WRITE rivers.json: its own note no longer describes "
            "it.\n  %s\n  feeds present: %s\nThis file is published for other "
            "people to reuse; a note that documents three of four sources is "
            "worse than none." % ("\n  ".join(problems), ", ".join(present)))

    doc["built"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    io.open(path, "w", encoding="utf-8").write(
        json.dumps(doc, indent=1, sort_keys=True) + "\n")

    import collections
    by = collections.Counter(r.get("src") for r in merged)
    print("%d gauges in %s: %s" % (len(merged), path, dict(by)))
    print("added this run: %s" % (added or "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
