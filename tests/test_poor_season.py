"""A Poor rating is a standing fact. "Advice against bathing today" is not.

WHY THIS FILE EXISTS. Article 12 of the bathing water directive requires advice
against bathing to be given at a bathing water classified as Poor, and it stands
for the whole bathing season. The collector applied it every day of the year.

So on 5 November 2026 all 39 Poor bathing waters were serving a red "Advice
against bathing today" over the reason "advice against bathing is in place here
FOR THE SEASON", on a card whose own verdict line says the season ended on 30
September, and underneath an explanation of this very rule saying it sets the
verdict "every day until the season closes". Three sentences on one card, and no
two of them agreed.

WHAT MUST NOT HAPPEN AS A RESULT. The rating itself is the most useful thing
known about a Poor beach in November and must survive — just as a `class`
reason, which is what that type is for, rather than as a live warning about
today. A fix that dropped the Poor rating entirely would be worse than the
fault, so these cases check both halves: the warning goes out of season, and the
rating does not.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_swim as m                                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(ROOT, "collect_swim.py"), encoding="utf-8").read()

# The whole standing-rating branch, from its own test to the start of the next
# numbered step. Sliced rather than grepped line by line so a case cannot pass
# by matching the right words in the wrong branch.
BLOCK = SRC.split('if (site.get("cls") or "").lower().startswith("poor"):', 1)[1] \
           .split("# ---- 5.", 1)[0]


def test_the_branch_is_gated_on_the_season():
    assert "if in_season(country):" in BLOCK, \
        "the Poor rule no longer tests the season"


def test_the_live_warning_is_inside_the_in_season_half():
    """raise_to("advised") must not be reachable out of season.

    This is the line that paints the red verdict. If it moves outside the gate
    the fault is back, whatever the wording underneath says.
    """
    before, after = BLOCK.split("else:", 1)
    assert 'raise_to("advised")' in before, "the advised verdict left the gate"
    assert 'raise_to("advised")' not in after, \
        "the advised verdict is still raised out of season"
    assert '"t": "advised"' not in after, \
        "out of season still emits an advised reason"


def test_out_of_season_still_states_the_rating():
    """Dropping the Poor rating would be worse than the fault it replaces."""
    after = BLOCK.split("else:", 1)[1]
    assert '"t": "class"' in after, "out of season emits no reason at all"
    assert "Rated Poor" in after, "out of season no longer says it is rated Poor"


def test_out_of_season_does_not_claim_advice_is_in_force():
    after = BLOCK.split("else:", 1)[1]
    low = " ".join(after.split()).lower()
    assert "is in place here for the season" not in low, \
        "out of season still says advice is in place"
    assert "has ended" in low or "which has ended" in low, \
        "out of season does not say the season has ended"


def test_the_reason_type_it_uses_is_one_the_site_ranks():
    """A type nothing ranks sorts to the default and can outrank a live spill.

    The same fault test_verdicts.py guards for "spill-now". "class" is in
    WHY_ORDER and in KNOWN_WHY_TYPES; this fails if that stops being true.
    """
    block = SRC.split("WHY_ORDER = {", 1)[1].split("}", 1)[0]
    ranked = dict((k, int(v)) for k, v in re.findall(r'"([a-z-]+)":\s*(\d+)', block))
    assert "class" in ranked, "WHY_ORDER has no rank for class"
    assert "class" in m.KNOWN_WHY_TYPES, "class is not a known reason type"
    # And it must rank BELOW a live discharge, or a November page would lead on
    # last year's grade instead of a pipe running today.
    assert ranked["class"] > ranked["spill"], ranked


def test_in_season_is_what_the_gate_thinks_it_is():
    """The gate is only as good as the function behind it.

    Checked on a date inside every nation's season and one outside all of them,
    passed explicitly so these do not become true or false with the calendar.
    """
    # UTC-AWARE, because in_season builds its own bounds with tzinfo=utc and
    # Python refuses to compare those with a naive datetime. A test that passed
    # a naive one failed on the comparison rather than on the behaviour, which
    # would have read as the gate being broken.
    import datetime
    utc = datetime.timezone.utc
    july = datetime.datetime(2026, 7, 15, 12, 0, 0, tzinfo=utc)
    november = datetime.datetime(2026, 11, 5, 12, 0, 0, tzinfo=utc)
    for country in ("England", "Wales", "Scotland", "Northern Ireland", "Ireland"):
        assert m.in_season(country, july) is True, country
        assert m.in_season(country, november) is False, country


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
