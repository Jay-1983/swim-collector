"""Guards on the one string the edge writes into every beach page's HTML.

WHY THIS FILE EXISTS. brief.sites carries, per beach, the verdict and the one
sentence explaining it. functions/_middleware.js writes that sentence into
#v-body before any script runs, so it is what a crawler indexes, what a link
preview shows and what anybody without JavaScript reads under the answer.

It was cut with a bare [:140]. On 4 November 2026 all 452 beaches answering
"Can't say today" fell back to their first gap, every one of those gaps was
longer than 140 characters — median 208, longest 255 — and 196 of them were
severed inside a word:

    "...the daily pollution forecast stopped on 30 September and start again o"

The clause it threw away was the one that mattered: "so nothing official stands
behind a clear verdict here."

The cap itself is right and stays. This pins what the cap must not do.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_swim as m                                  # noqa: E402

# The three real out-of-season sentences, copied from the live snapshot on
# 4 November 2026. Between them they cover 400 of the 452 affected beaches.
ENGLAND = ("Out of bathing season — the Environment Agency's routine sampling "
           "and the daily pollution forecast stopped on 30 September and start "
           "again on 15 May, so nothing official stands behind a clear verdict "
           "here. The storm overflow monitors are still being read")
IRELAND = ("Out of bathing season — EPA Ireland's routine sampling stopped on "
           "15 September and starts again on 1 June, so nothing official stands "
           "behind a clear verdict here. The restrictions register is still "
           "being read")
SCOTLAND = ("Out of bathing season — SEPA's routine sampling and the daily "
            "pollution forecast stopped on 15 September and start again on 1 "
            "June, so nothing official stands behind a clear verdict here")

REAL = (ENGLAND, IRELAND, SCOTLAND)


def _cuts_a_word(original, clipped):
    """Did the cut land inside a word of the original?"""
    if clipped == original or len(clipped) >= len(original):
        return False
    k = len(clipped.rstrip("…"))
    return 0 < k < len(original) and original[k - 1].isalnum() and original[k].isalnum()


def test_no_real_gap_sentence_is_cut_inside_a_word():
    for t in REAL:
        out = m.brief_clip(t, 230)
        assert not _cuts_a_word(t, out), "cut mid-word: %r" % out[-40:]


def test_the_old_cap_really_did_cut_these():
    """The fault this file is about, so the cases cannot quietly stop testing it.

    If a future edit shortens these sentences below 140 characters, the cases
    above would pass while proving nothing. This fails first and says why.
    """
    assert all(len(t) > 140 for t in REAL)
    assert any(_cuts_a_word(t, t[:140]) for t in REAL)


def test_the_clause_that_matters_survives():
    """Losing the end of the sentence lost the point of it."""
    for t in REAL:
        assert "nothing official stands behind" in m.brief_clip(t, 230)


def test_a_sentence_inside_the_cap_is_untouched():
    assert m.brief_clip(SCOTLAND, 230) == SCOTLAND
    assert m.brief_clip("Short.", 230) == "Short."
    assert m.brief_clip("", 230) == ""
    assert m.brief_clip(None, 230) == ""


def test_it_prefers_a_whole_sentence():
    t = "First part here. Second part that runs past the cap and keeps going."
    assert m.brief_clip(t, 40) == "First part here."


def test_otherwise_it_cuts_at_a_space_and_marks_it():
    t = "one two three four five six seven eight nine ten eleven twelve"
    out = m.brief_clip(t, 20)
    assert out.endswith("…"), out
    assert not _cuts_a_word(t, out), out
    assert len(out) <= 21, out


def test_a_full_stop_too_early_is_not_used():
    """An opening abbreviation must not clip the sentence to three words.

    "Dr. Smith said..." has a full stop at character three. Taking it would
    serve "Dr." as the whole explanation, which is a worse fault than the one
    this replaces — so a sentence break is only taken past a third of the cap.
    """
    t = "Dr. Smith reported the water here was fine on every visit this year."
    out = m.brief_clip(t, 40)
    assert out != "Dr."
    assert "Smith" in out


def test_a_single_unbroken_token_still_obeys_the_cap():
    """No space to cut at, so it is cut hard rather than served whole."""
    t = "x" * 500
    assert len(m.brief_clip(t, 230)) == 230


def test_the_cap_is_never_exceeded():
    for t in list(REAL) + ["a " * 400, "no spaces" + "y" * 300]:
        for cap in (40, 120, 230):
            assert len(m.brief_clip(t, cap)) <= cap + 1, (cap, t[:20])


def test_reasons_use_the_same_clip():
    """The why line shares the mechanism at a tighter cap.

    Nothing exceeds 120 today, which is exactly when a latent cut is easiest to
    reintroduce: there is no failing page to notice it on.
    """
    t = ("1 storm overflow discharged within 2km in the last 48 hours and the "
         "monitor nearest the bathing water has not reported since Tuesday "
         "morning, which the page says beside it")
    out = m.brief_clip(t, 120)
    assert len(out) <= 121 and not _cuts_a_word(t, out), out


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
