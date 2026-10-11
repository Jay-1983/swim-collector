#!/usr/bin/env python3
"""Names, slugs, counties and countries for a river register that is not the EA's.

build_rivers.py does all of this for England inside main(). The Scottish and
Irish registers need the same work and must do it the same way, so it lives here
once rather than three times. Everything in this file is about what a PAGE needs
from a gauge: a name a person would say, a slug that never moves, and a county
and country for the breadcrumb.

THE SLUG RULE IS THE ONE THAT MATTERS. A slug is derived from the name on the
first build that sees a gauge and carried forward for ever after. Recomputing it
means that tidying a name silently moves the page and kills every link to it —
a trap this project has now found three times, in the bathing-water register in
September, in the English river register, and it would have been the fourth here.
"""

import io
import json
import math
import os
import re
import sys
import unicodedata
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from falls_areas import district_of                     # noqa: E402

# Two gauges a few hundred metres apart on the same river are one place, the
# same rule and the same distance the English register uses.
MERGE_KM = 1.5
# Words that stay lower case inside a name once it is unshouted.
SMALL = {"of", "the", "and", "at", "in", "on"}


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


def _word(w):
    """One word of a shouted name. A word that is not all capitals is left alone."""
    core = re.sub(r"[^A-Za-z]", "", w)
    if not core or core != core.upper():
        return w
    low = w.lower()
    out = re.sub(r"(?:^|(?<=[^A-Za-z']))([a-z])", lambda m: m.group(1).upper(), low)
    # "O'BRIEN'S" wants O'Brien's and "KING'S" wants King's. The difference is
    # whether the apostrophe follows a single letter, so only that case is
    # re-capitalised and a possessive is left alone.
    return re.sub(r"(?<=^[A-Za-z]')([a-z])", lambda m: m.group(1).upper(), out)


def title_place(s):
    """A water body name typed in capitals, as a person would write it.

    waterlevel.ie types them "UNSHIN", "OWENMORE [Sligo]", "ST. JOHN'S LAKE",
    "O'BRIEN'S BRIDGE". Printed raw they shout on every one of 338 pages, and
    str.title() mangles them into "St. John'S" and "O'Brien'S". Done per word so
    a row that is already typed properly ("Marfield Lake") is not re-cased, and
    so a mixed-case qualifier does not exempt the rest of the name — "OWENMORE
    [Sligo]" is not a tidy name just because the bracket is.
    """
    s = " ".join(str(s or "").split())
    if not s:
        return ""
    def shouted(w):
        core = re.sub(r"[^A-Za-z]", "", w)
        return bool(core) and core == core.upper()
    return " ".join(
        w.lower() if (i and shouted(w)
                      and re.sub(r"[^A-Za-z]", "", w).lower() in SMALL)
        else _word(w)
        for i, w in enumerate(s.split(" ")))


def label_of(river, town):
    """What the page is called. "Tay at Perth" reads as a place; "10048" does not."""
    river = " ".join(str(river or "").split())
    town = " ".join(str(town or "").split())
    if river and town and river.lower() != town.lower():
        return "%s at %s" % (river, town)
    return river or town


def merge_close(rows):
    """Drop a gauge that describes the same reach as one already kept.

    Same rule as the English register: same river, within MERGE_KM. Two pages
    for one bend of river is two thin pages instead of one useful one. Rows with
    no river name are never merged — without it there is nothing to say they are
    the same water rather than two streams half a mile apart.
    """
    rows = sorted(rows, key=lambda x: (x.get("river") or "", x.get("town") or "", x["id"]))
    kept, used, dropped = [], set(), 0
    for i, a in enumerate(rows):
        if a["id"] in used:
            continue
        used.add(a["id"])
        if a.get("river"):
            for b in rows[i + 1:]:
                if b["id"] in used or (b.get("river") or "") != a["river"]:
                    continue
                if haversine(a["lat"], a["lon"], b["lat"], b["lon"]) <= MERGE_KM:
                    used.add(b["id"])
                    dropped += 1
        kept.append(a)
    return kept, dropped


def published_slugs(out_dir):
    """The slugs already live, so none of them can move."""
    got = {}
    for name in ("rivers.json",):
        try:
            with io.open(os.path.join(out_dir, name), encoding="utf-8") as f:
                for x in json.load(f).get("rivers") or []:
                    if x.get("id") and x.get("slug"):
                        got[x["id"]] = x["slug"]
        except Exception:                                # noqa: BLE001
            pass
    return got


def enrich(rows, out_dir, shout=False):
    """Give every row a name, a locked slug, a county and a country.

    `shout` unshouts the river and town names first, which the Irish register
    needs and the Scottish one does not.
    """
    for r in rows:
        if shout:
            r["river"] = title_place(r.get("river"))
            r["town"] = title_place(r.get("town"))
        r["name"] = label_of(r.get("river"), r.get("town")) or r["id"]

    rows, merged = merge_close(rows)

    existing = published_slugs(out_dir)
    taken, minted = set(), 0
    for r in rows:
        was = existing.get(r["id"])
        if was and was not in taken:
            r["slug"] = was
            taken.add(was)
    for r in rows:
        if r.get("slug"):
            continue
        base = slugify(r["name"]) or slugify(r.get("river")) or r["id"].lower()
        slug, n = base, 1
        while slug in taken:
            n += 1
            slug = "%s-%d" % (base, n)
        r["slug"] = slug
        taken.add(slug)
        minted += 1

    # THE PAIR IS UNPACKED. district_of returns (county, country) and assigning
    # it whole wrote "['Somerset', 'England']" into a field a breadcrumb prints,
    # which is the note left in build_rivers.py where it happened.
    outside = 0
    for r in rows:
        county, country = district_of(r["lat"], r["lon"])
        if county:
            r["district"] = county
        if country:
            r["country"] = country
        else:
            outside += 1
    return rows, {"merged": merged, "slugs_kept": len(rows) - minted,
                  "slugs_new": minted, "no_county": outside}
