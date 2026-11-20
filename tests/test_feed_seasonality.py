"""Which feeds have a season, and which only cover a country.

WHY THIS FILE EXISTS. Feed carries two different facts that look alike:

    covers    which countries a failure is news in  (banner scoping)
    seasonal  whether this feed stops for the winter at all

offseason() used to read `covers` for both. That was harmless while the only
feeds with a covers list were the three daily forecasts, which genuinely stop —
and the comment above the river feeds says so outright: "NOT covers=[...]. A
river gauge has no bathing season, and Feed only consults the season table when
`covers` is set", and it warns that "two more copies of it were about to be
made".

Eleven were. On 6 November the water company feeds were given a covers list so
that a Southern Water outage would stop being announced on Irish, Scottish and
Welsh beach pages. Correct on its own, and it handed every company feed a season
it does not have. By 20 November Southern Water was returning a hard API error —
code 499, "Item does not exist or is inaccessible" — and the snapshot published
it as an expected off-season silence with escalates false, because England is out
of season.

THAT SWITCHED OFF THE DISCLOSURE WRITTEN FOR THIS EXACT CASE. feedDown() in
CORE_JS requires escalates === true, so the 70 beaches that depend on Southern
Water stopped being told its feed had stopped — by a second change made the same
week as the first.

Storm overflows run all year. The site says so on every beach page, in the
sentence right under the verdict. A silence from a storm overflow feed is a
fault, always, and must escalate.
"""

import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_swim as m                                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTC = datetime.timezone.utc
# Deep winter: every season this site knows is closed.
WINTER = datetime.datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
# High summer: every season is open.
SUMMER = datetime.datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)

# The feeds that genuinely stop. Everything else runs all year.
SEASONAL = (
    "EA pollution risk forecast",
    "NRW pollution risk forecast",
    "SEPA daily prediction",
    "NI sample quality",
    "Bathing water samples",
)


def _dict_of(f):
    """Feed's dict builder, found rather than guessed, so a rename fails here."""
    for attr in ("as_dict", "to_dict", "publish", "payload", "json"):
        if hasattr(f, attr):
            return getattr(f, attr)()
    raise AssertionError("Feed has no dict builder this test recognises")


def _down(name, covers, seasonal):
    f = m.Feed(name, covers, True, seasonal)
    f.ok = False
    f.error = RuntimeError("boom")
    return f


def test_a_company_feed_is_never_out_of_season():
    """The regression itself, named."""
    f = _down("Southern Water", ["England"], False)
    assert f.offseason(WINTER) is None, f.offseason(WINTER)


def test_and_its_failure_still_escalates_in_winter():
    """escalates is what feedDown() in CORE_JS reads before telling a reader."""
    f = _down("Southern Water", ["England"], False)
    d = _dict_of(f)
    assert "offseason" not in d, d
    assert d["escalates"] is True, d


def test_scottish_water_too_even_though_scotland_closed_in_september():
    """Scotland's season ended on 15 September, earliest of the five."""
    f = _down("Scottish Water", ["Scotland"], False)
    assert f.offseason(WINTER) is None


def test_a_cross_border_company_is_not_seasonal_either():
    f = _down("Welsh Water", ["England", "Wales"], False)
    assert f.offseason(WINTER) is None


def test_a_forecast_feed_still_goes_off_season():
    """The behaviour this flag exists to preserve."""
    f = _down("EA pollution risk forecast", ["England"], True)
    off = f.offseason(WINTER)
    assert off, "a real forecast feed lost its off-season block"
    assert "ended" in off and "resumes" in off, off


def test_a_forecast_feed_in_season_is_a_real_failure():
    f = _down("EA pollution risk forecast", ["England"], True)
    assert f.offseason(SUMMER) is None


def test_one_country_still_in_season_is_not_off_season():
    """The rule the docstring already made: covers England and Wales, and one of
    them being finished is not the feed being finished. Checked on 20 September,
    when Scotland has closed and England has not."""
    mid = datetime.datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
    f = _down("Bathing water samples", ["England", "Scotland"], True)
    assert f.offseason(mid) is None


def test_no_season_table_entry_means_no_off_season_claim():
    f = _down("Something", ["Atlantis"], True)
    assert f.offseason(WINTER) is None


def test_a_feed_that_is_working_publishes_no_off_season_block():
    """The ok test lives in the dict builder, not in offseason().

    offseason() answers "would this be out of season", which is true of a
    healthy forecast feed in November as much as a silent one. The builder is
    what decides whether to publish it — `off = self.offseason() if not self.ok`
    — so that is the level to assert at. An earlier version of this case asked
    offseason() directly and failed on a correct implementation.
    """
    f = m.Feed("EA pollution risk forecast", ["England"], True, True)
    f.ok = True
    d = _dict_of(f)
    assert "offseason" not in d, d
    assert d["escalates"] is True, d


# ---- and the wiring, which is the half that actually broke ----------------
def _seasonal_calls():
    src = open(os.path.join(ROOT, "collect_swim.py"), encoding="utf-8").read()

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

    calls = [call_at(mm.start()) for mm in re.finditer(r"\brun\(", src)]
    return [c for c in calls if "covers=" in c]


def test_every_feed_with_covers_declares_whether_it_is_seasonal():
    """A covers list must no longer imply a season by accident.

    Any run() call that scopes a feed to countries has to say outright whether
    the feed stops for the winter — seasonal=True, or nothing at all, which the
    constructor reads as False. This is the case that fails if somebody adds a
    twelfth company feed and copies the covers line without thinking about it.
    """
    for c in _seasonal_calls():
        name = re.search(r'run\(\s*"([^"]+)"', c)
        label = name.group(1) if name else " ".join(c.split())[:50]
        if label in SEASONAL:
            assert "seasonal=True" in c, "%s should be seasonal: %s" % (
                label, " ".join(c.split())[:90])
        else:
            assert "seasonal=True" not in c, (
                "%s is marked seasonal but runs all year: %s" % (
                    label, " ".join(c.split())[:90]))


def test_the_spill_feeds_are_scoped_but_not_seasonal():
    """Both halves of the Southern Water story in one case."""
    spill = [c for c in _seasonal_calls() if re.search(r"\bspills_[a-z_]+", c)]
    assert spill, "no scoped spill feed run() calls found"
    for c in spill:
        assert "co_countries" in c, " ".join(c.split())[:90]
        assert "seasonal=True" not in c, " ".join(c.split())[:90]


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
