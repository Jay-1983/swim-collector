"""Derive the council area for each Scottish bathing water, once.

SEPA publishes five fields per bathing water and none of them is a council, so
90 beach pages had no place smaller than "Scotland" on them. This asks the ONS
Local Authority Districts (December 2024) FULL EXTENT boundaries which council
each beach's own coordinates fall in, and writes scottish_councils.json.

FULL EXTENT, not the clipped version. The clipped boundaries stop at the
coastline, and a point standing on a beach is frequently just outside them.
Where a point still misses, this widens the search to 500m, then 2km, then 8km
before giving up — a beach is never 8km from its own council.

Run it when SEPA adds a bathing water, or when council boundaries change (about
once a decade). The output is committed, so building the register needs no live
call and the answer cannot change without showing up in a diff.

    python3 tools/derive_scottish_councils.py
"""

import io
import json
import os
import ssl
import time
import urllib.parse
import urllib.request

BASE = ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "Local_Authority_Districts_December_2024_Boundaries_UK_BFE/FeatureServer/0/query")
SITES = "https://caniswim.co.uk/swim/sites.json"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "scottish_councils.json")
UA = {"User-Agent": "swim-collector/1.0 (personal bathing water tool; open data)"}
CTX = ssl.create_default_context()


def council(lat, lon, distance=None):
    q = {
        "geometry": json.dumps({"x": lon, "y": lat,
                                "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "LAD24NM",
        "returnGeometry": "false",
        "f": "json",
    }
    if distance:
        q["distance"] = str(distance)
        q["units"] = "esriSRUnit_Meter"
    req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(q), headers=UA)
    d = json.loads(urllib.request.urlopen(req, timeout=40, context=CTX).read())
    got = d.get("features") or []
    return got[0]["attributes"]["LAD24NM"] if got else None


def main():
    req = urllib.request.Request(SITES, headers=UA)
    sites = json.loads(urllib.request.urlopen(req, timeout=60, context=CTX).read())["sites"]
    scots = [s for s in sites if s.get("country") == "Scotland"]
    print("%d Scottish bathing waters" % len(scots))

    out, missed = {}, []
    for i, s in enumerate(scots):
        name = None
        for dist in (None, 500, 2000, 8000):
            try:
                name = council(s["lat"], s["lon"], dist)
            except Exception as e:                      # noqa: BLE001
                print("    %s: %s" % (s["name"], str(e)[:60]))
                name = None
            if name:
                break
        if name:
            out[s["id"]] = name
        else:
            missed.append(s["name"])
        time.sleep(0.25)
        if (i + 1) % 20 == 0:
            print("    ...%d/%d" % (i + 1, len(scots)))

    # NEVER WRITE A SHORTER FILE WITHOUT SAYING SO. A run that half-failed would
    # otherwise quietly strip councils off pages that already had them.
    if os.path.exists(OUT):
        had = len(json.load(io.open(OUT, encoding="utf-8")))
        if len(out) < had:
            raise SystemExit(
                "REFUSING TO WRITE: resolved %d councils but the committed file "
                "has %d. Missed: %s" % (len(out), had, ", ".join(missed)))
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote %s: %d beaches across %d councils%s"
          % (OUT, len(out), len(set(out.values())),
             "" if not missed else ", %d unresolved: %s" % (len(missed), missed)))


if __name__ == "__main__":
    main()
