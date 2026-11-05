"""Where a water company's outage is announced, and where it is not.

WHY THIS FILE EXISTS. Feed(covers=...) is how this collector tells the site
whether a feed's failure matters on a given page. CORE_JS coversHere() reads it,
and reads a MISSING list as "everywhere".

Every forecast feed was given a covers list. None of the eleven water company
feeds was. So when Southern Water stopped publishing at 12:42 on 4 November
2026, the banner about it was painted on all 240 Irish, 33 Northern Irish, 90
Scottish and 114 Welsh beach pages — about an English company with no monitored
outfall within range of any of them, on pages whose own copy says no overflow
data is published for them at all. 477 pages warning about a feed that could not
have told them anything.

The failure mode to guard against here is the opposite one: narrowing a
company's coverage too far and silencing an outage on a page where it does
matter. Welsh Water is the case that catches it — Dwr Cymru serves part of the
English border, so its list must hold England as well as Wales.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_swim as m                                  # noqa: E402

SITES = [
    {"id": "E:eng1", "country": "England"},
    {"id": "E:eng2", "country": "England"},
    {"id": "W:wal1", "country": "Wales"},
    {"id": "S:sco1", "country": "Scotland"},
    {"id": "N:ni1", "country": "Northern Ireland"},
    {"id": "I:irl1", "country": "Ireland"},
]
# Outfall ids to owners, as outfalls.json gives them.
OWNERS = {
    "SW:1": "Southern Water",
    "SW:2": "Southern Water",
    "DC:1": "Welsh Water",
    "DC:2": "Welsh Water",
    "SC:1": "Scottish Water",
    "OR:1": "Orphan Water",
}
# nearby.json: beach -> [[outfall id, km], ...]
NEARBY = {
    "E:eng1": [["SW:1", 0.4], ["SW:2", 1.2]],
    "E:eng2": [["DC:2", 2.1]],          # Welsh Water reaching an English beach
    "W:wal1": [["DC:1", 0.8]],
    "S:sco1": [["SC:1", 1.1]],
    "N:ni1": [],                        # no overflow data exists here at all
    "I:irl1": [],
}


def test_an_english_company_covers_england_only():
    cov = m.company_coverage(SITES, NEARBY, OWNERS)
    assert cov["Southern Water"] == ["England"], cov.get("Southern Water")


def test_it_does_not_cover_the_four_nations_it_has_no_outfalls_in():
    """The 477 pages. Stated as its own case because it is the whole point."""
    cov = m.company_coverage(SITES, NEARBY, OWNERS)
    sw = cov["Southern Water"]
    for nation in ("Ireland", "Northern Ireland", "Scotland", "Wales"):
        assert nation not in sw, nation


def test_a_cross_border_company_keeps_both_countries():
    """NARROWING TOO FAR IS THE DANGEROUS DIRECTION.

    Dwr Cymru serves part of the English border, so an English beach really can
    depend on the Welsh Water feed. Clipping this to Wales would silence a real
    outage on a page where it decides the answer.
    """
    cov = m.company_coverage(SITES, NEARBY, OWNERS)
    assert cov["Welsh Water"] == ["England", "Wales"], cov.get("Welsh Water")


def test_scotland_is_scotland():
    cov = m.company_coverage(SITES, NEARBY, OWNERS)
    assert cov["Scottish Water"] == ["Scotland"]


def test_a_company_reaching_no_beach_is_absent_rather_than_empty():
    """Absent means "everywhere" to coversHere(), which is the safe answer.

    An empty list would mean "nowhere" and would hide the outage completely. A
    company whose outfalls are in the register but near nothing is a case this
    cannot answer, so it must not answer it.
    """
    cov = m.company_coverage(SITES, NEARBY, OWNERS)
    assert "Orphan Water" not in cov


def test_a_site_with_no_country_is_skipped_not_crashed():
    sites = SITES + [{"id": "X:odd"}]
    nearby = dict(NEARBY)
    nearby["X:odd"] = [["SW:1", 0.2]]
    cov = m.company_coverage(sites, nearby, OWNERS)
    assert cov["Southern Water"] == ["England"]


def test_an_unknown_outfall_contributes_nothing():
    nearby = dict(NEARBY)
    nearby["I:irl1"] = [["NOT:IN:REGISTER", 0.5]]
    cov = m.company_coverage(SITES, nearby, OWNERS)
    assert "Ireland" not in cov.get("Southern Water", [])
    assert all("Ireland" not in v for v in cov.values())


def test_empty_inputs_do_not_raise():
    assert m.company_coverage([], {}, {}) == {}
    assert m.company_coverage(None, None, None) == {}
    assert m.company_coverage(SITES, None, OWNERS) == {}


def test_a_bare_id_is_accepted_as_well_as_a_pair():
    """nearby.json stores [id, km]; a plain id must not be mistaken for a list."""
    cov = m.company_coverage(SITES, {"E:eng1": ["SW:1"]}, OWNERS)
    assert cov["Southern Water"] == ["England"]


def test_every_company_feed_is_actually_given_its_coverage():
    """The helper is useless if a run() call forgets to pass it.

    This is the half that produced the fault: Feed already took a covers
    argument and the eleven company feeds simply never supplied one. A correct
    helper with one unwired call site puts the banner back on 477 pages, and
    nothing else here would notice.
    """
    import io
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(root, "collect_swim.py"), encoding="utf-8").read()
    # BALANCED PARENTHESES, NOT [^)]*. One of these calls passes a lambda, so a
    # non-greedy match to the first ")" stops inside `spills_common(c, u, f)`
    # and reports a correctly wired call as missing — which it did, and the
    # failure looked exactly like the real fault.
    def call_at(i):
        depth = 0
        for j in range(i, len(src)):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    return src[i:j + 1]
        return src[i:]

    calls = [call_at(m2.start()) for m2 in re.finditer(r"\brun\(", src)]
    calls = [c for c in calls if re.search(r"\bspills_[a-z_]+", c)]
    assert calls, "no spill feed run() calls found — has run() been renamed?"
    assert len(calls) >= 4, "expected at least four spill feeds, found %d" % len(calls)
    missing = [c for c in calls if "co_countries" not in c]
    assert not missing, "company feed started with no coverage: %s" % (
        [" ".join(c.split())[:70] for c in missing],)


def test_countries_come_back_sorted():
    cov = m.company_coverage(SITES, NEARBY, OWNERS)
    for name, countries in cov.items():
        assert countries == sorted(countries), name


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print("  ok    %s" % name)
        except Exception as e:                            # noqa: BLE001
            fails += 1
            print("  FAIL  %s  %s" % (name, e))
    print("%d checked, %d failed" % (
        len([k for k in globals() if k.startswith("test_")]), fails))
    sys.exit(1 if fails else 0)
