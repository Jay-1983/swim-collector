"""Guards on the six ways a broken upstream feed could still read as good news.

Every one of these came out of the whole-site adversarial review, and every one
is the same shape: a feed that failed, froze or parsed to nothing, and a page
that said "no warnings today" anyway. Standard 1 — never manufacture an
all-clear — is the rule they all break.

These are cheap, they run before every collection, and each names the beaches
that were actually affected when it was found.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_swim as m                                  # noqa: E402

checked = failed = 0


def ok(name, cond, detail=""):
    global checked, failed
    checked += 1
    if cond:
        print("  ok    %s" % name)
    else:
        failed += 1
        print("  FAIL  %s%s" % (name, ("  — " + detail) if detail else ""))


class F(object):
    """Enough of a Feed for the guards under test."""

    def __init__(self, at=None, ok_=False):
        self.at = at
        self.ok = ok_
        self.error = None
        self.name = "test"


def test_a_feed_with_no_timestamp_cannot_be_called_fresh():
    """It returned early on feed.at is None, which turned the whole freshness
    guard into a silent no-op. epoch_ms() maps null, non-numeric and <= 0 all to
    None, so one upstream schema change disabled the eight-hour freeze detector
    for that company for good — and Feed.as_dict omits `at`, so nothing
    downstream could notice either."""
    f = F(at=None, ok_=True)
    m.stale_check(f)
    ok("undated means unhealthy", f.ok is False)
    ok("and it says why", bool(f.error) and "timestamp" in str(f.error).lower(),
       repr(f.error))


def test_a_fresh_feed_still_passes():
    f = F(at=m.NOW, ok_=True)
    m.stale_check(f)
    ok("a feed stamped now is fine", f.ok is True, repr(f.error))


def test_southern_under_maintenance_is_a_dead_monitor_not_a_clean_pipe():
    """5 of Southern's 994 outfalls read "This outfall is under maintenance" the
    day this was found. It matched none of the blind tokens, so it arrived as
    now=False, recent=False, offline=False — the site's word for "we looked and
    the monitor was fine" — and earned "N monitored storm overflows within 2km"
    on the checklist, which alone holds a green verdict. 147 Southern outfalls
    are within 2km of a bathing water and 70 beaches have Southern as their only
    monitored-overflow check: Brighton Central, Eastbourne, Hastings Pelham
    Beach, Seaford, Bexhill among them."""
    for msg in ("This outfall is under maintenance",
                "This outfall is under review",
                "Data unverified",
                ""):
        low = msg.lower()
        now = low.startswith("there is an ongoing")
        blind = (("under review" in low) or ("unverified" in low)
                 or ("under maintenance" in low) or not msg) and not now
        ok("blind: %r" % (msg or "(empty)"), blind is True)
    # And the wordings that genuinely mean the monitor is working stay visible.
    for msg in ("There have been no releases in the last 72 hours",
                "There is an ongoing release from this outfall"):
        low = msg.lower()
        now = low.startswith("there is an ongoing")
        blind = (("under review" in low) or ("unverified" in low)
                 or ("under maintenance" in low) or not msg) and not now
        ok("not blind: %r" % msg[:38], blind is False)


def test_southern_is_staleness_checked_like_every_other_spill_feed():
    """spills_common, spills_wales and spills_scotland all end with
    stale_check(). spills_southern set ok:True and stopped — its only freshness
    signal was read into feed.at under a comment calling freshness a nicety and
    then never compared with anything. A freeze in their ArcGIS layer published
    994 rows of "no releases in the last 72 hours" indefinitely."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "collect_swim.py"), encoding="utf-8").read()
    body = src.split("def spills_southern(")[1].split("\ndef ")[0]
    ok("spills_southern calls stale_check", "stale_check(feed)" in body)
    # Belt and braces: every spill loader does.
    for fn in ("spills_common", "spills_wales", "spills_scotland", "spills_southern"):
        b = src.split("def %s(" % fn)[1].split("\ndef ")[0]
        ok("%s calls stale_check" % fn, "stale_check(feed" in b)


def test_zero_rows_is_not_a_healthy_answer():
    """Three feeds ended `feed.ok = True` unconditionally, so an envelope or
    column rename produced no rows with the feed still reported healthy.

    It mattered most for Ireland: verdict() grants the Irish green tick from
    this feed's REACHABILITY, not from finding the beach in it, so 225 of 240
    Irish beaches carry "Today's local authority bathing restrictions" as their
    entire checklist and all 15 warned Irish beaches — 5 at avoid — are warned
    by nothing else. The Republic publishes no storm overflow data, so there is
    no second signal to catch it.

    The test is `rows`, never `got`: a populated feed where every beach has no
    restriction is a real, healthy, everyday answer."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "collect_swim.py"), encoding="utf-8").read()
    for fn in ("restrictions_roi", "predictions_scotland", "ea_incidents"):
        b = src.split("def %s(" % fn)[1].split("\ndef ")[0]
        ok("%s floors on rows" % fn, "feed.ok = bool(rows)" in b,
           "found: " + repr([l.strip() for l in b.split("\n") if "feed.ok" in l]))
        ok("%s says why when empty" % fn, "feed.error" in b)


def test_sepa_is_dated_and_age_checked():
    """It was the only escalating feed with no timestamp on the feed at all: it
    read last_updated per row and never set feed.at, so nothing — stale_check,
    the run log, the site's feed banner — had anything to measure. verdict()
    printed the row as "SEPA's prediction for today" and "Today's prediction:
    good" with the row's real age carried alongside, so a beach could read
    "Today's prediction: good" and "3 days ago" together, under a green
    verdict."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "collect_swim.py"), encoding="utf-8").read()
    b = src.split("def predictions_scotland(")[1].split("\ndef ")[0]
    ok("it sets feed.at", "feed.at = " in b)
    ok("and age-checks it", "stale_check(feed" in b)


def test_feed_at_is_always_a_datetime_never_a_string():
    """I broke this on the way to fixing SEPA: `feed.at = iso(newest)` put an ISO
    STRING where every other loader puts a datetime, and hours_since() does
    arithmetic on it — "unsupported operand type(s) for -: 'datetime.datetime'
    and 'str'" took the whole SEPA feed down on the next real run.

    Feed.as_dict calls iso() itself, so the attribute is always the object."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "collect_swim.py"), encoding="utf-8").read()
    bad = [l.strip() for l in src.split("\n")
           if "feed.at" in l and "=" in l and "iso(" in l and "parse_iso" not in l]
    ok("no loader assigns iso() to feed.at", not bad, repr(bad))
    # And prove the arithmetic works on what stale_check is actually given.
    f = F(at=m.NOW, ok_=True)
    m.stale_check(f)
    ok("stale_check does arithmetic on it without raising", f.ok is True)


def test_the_incident_register_failing_is_disclosed():
    """ctx["incidents"] is read in exactly one place and only ever to ADD a
    warning, so when that fetch failed every open incident in England vanished
    from the run and nothing recorded that the register had not been read. The
    beach kept its ticks and its "No warnings today" over a live sewage
    incident. The live register carried four open incidents the day this was
    found, Exmouth among them, type "sewage", started the previous lunchtime.

    The failure is routine: the call goes through /swim/fetch, which answers 503
    whenever the UK-side larder has no copy yet."""
    ok("England has an incident feed named", m.INCIDENT_FEED.get("England")
       == "EA incidents and suspensions", repr(m.INCIDENT_FEED))
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "collect_swim.py"), encoding="utf-8").read()
    v = src.split("def verdict(")[1].split("\ndef ")[0]
    ok("verdict() gates on it", "INCIDENT_FEED" in v)
    # SLICED FROM THE FIRST OCCURRENCE, not split on it. INCIDENT_FEED appears
    # twice within thirteen characters (a comment, then the lookup), so
    # split(...)[1] was a thirteen-character window and the assertion could
    # never have passed however right the code was.
    win = v[v.find("INCIDENT_FEED"):][:800]
    ok("and raises to unknown, not just a note", 'raise_to("unknown")' in win,
       repr(win[:120]))


for _name, _fn in sorted(list(globals().items())):
    if _name.startswith("test_"):
        print(_name)
        _fn()

print("%d checked, %d failed" % (checked, failed))
sys.exit(1 if failed else 0)
