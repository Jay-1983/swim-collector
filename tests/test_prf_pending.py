"""A forecast not published yet is not a feed that is down.

Natural Resources Wales posts the daily pollution risk forecast at about 08:40
and yesterday's expires at 08:29. For roughly three quarters of an hour every
morning, longer when the data.gov.uk relay lags, neither day holds a forecast
still in date. All 114 Welsh beaches correctly went to "can't say" — and then
told the reader "Today's official information could not be fetched from Natural
Resources Wales", which is not what happened. The fetch worked. It was twenty
past eight.

The verdict must stay unknown in both cases: nothing here may produce an
all-clear. Only the sentence differs, and the sentence is the whole value of
saying anything at all.

This path is live for 45 minutes a day, which is why it needed a test rather
than a look.
"""
import io
import importlib.util as u
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = u.spec_from_file_location("cs", ROOT / "collect_swim.py")
m = u.module_from_spec(spec)
sys.argv = ["x"]
try:
    spec.loader.exec_module(m)
except SystemExit:
    pass

checks = failed = 0


def check(name, cond, detail=""):
    global checks, failed
    checks += 1
    if cond:
        print("  ok    %s" % name)
    else:
        failed += 1
        print("  FAIL  %s   %s" % (name, detail))


# ---- prf(): which of the two states it records ---------------------------

def fake_fetch(items):
    def f(url, *a, **kw):
        return {"result": {"items": list(items), "next": None}}
    return f


def run_prf(items, now):
    feed = m.Feed("NRW pollution risk forecast", covers=["Wales"])
    real_fetch, real_now = m.fetch_json, m.NOW
    m.fetch_json = fake_fetch(items)
    m.NOW = now
    try:
        got = m.prf(feed, m.S.NRW_PRF, "W:")
    finally:
        m.fetch_json, m.NOW = real_fetch, real_now
    return feed, got


NOW = datetime(2026, 9, 11, 8, 35, tzinfo=timezone.utc)


def item(site, expires, pub="2026-09-10T08:40:06"):
    return {"stp_bathingWater": {"_about": "http://x/id/bathing-water/" + site},
            "riskLevel": {"_about": "http://x/def/risk/normal"},
            "publishedAt": {"_value": pub},
            "expiresAt": {"_value": expires},
            "comment": {"_value": ""}}


# Yesterday's forecast, already expired, and today's not there.
feed, got = run_prf([item("ukl1", "2026-09-11T08:29:00")], NOW)
check("an all-expired document leaves no forecast", not got, repr(got))
check("the feed is not ok", feed.ok is False)
check("and it is marked pending, not failed",
      feed.pending == "not published yet" and feed.error is None,
      "pending=%r error=%r" % (feed.pending, feed.error))
check("pending reaches the published snapshot",
      feed.as_dict().get("pending") == "not published yet", feed.as_dict())

# Today's forecast, in date.
feed2, got2 = run_prf([item("ukl1", "2026-09-12T08:29:00",
                            pub="2026-09-11T08:40:06")], NOW)
check("a forecast still in date is used", len(got2) == 1, repr(got2))
check("and nothing is marked pending", feed2.pending is None and feed2.ok is True)

# ---- prf() deciding WHICH pending state it is -----------------------------
#
# The wording tests below set `pending` by hand, so on their own they prove the
# sentence and not the detection. This drives prf() itself with a relay age, so
# the branch that tells the two apart is actually executed.

def run_prf_with_relay(items, now, relay_seconds):
    feed = m.Feed("NRW pollution risk forecast", covers=["Wales"])
    real_fetch, real_now = m.fetch_json, m.NOW
    m.fetch_json = fake_fetch(items)
    m.NOW = now
    m.RELAY_AGE.clear()
    try:
        # Every URL prf() asks for reports the same age, which is what the relay
        # does: it is one cached document per day, not per request.
        class AgeingDict(dict):
            def get(self, k, d=None):
                return (relay_seconds, None)
        old_relay = m.RELAY_AGE
        m.RELAY_AGE = AgeingDict()
        try:
            m.prf(feed, m.S.NRW_PRF, "W:")
        finally:
            m.RELAY_AGE = old_relay
    finally:
        m.fetch_json, m.NOW = real_fetch, real_now
    return feed


EXPIRED = [item("ukl1", "2026-09-11T08:29:00")]

feed = run_prf_with_relay(EXPIRED, NOW, 9 * 3600)
check("a 9-hour-old relayed copy is recorded as a stale copy",
      feed.pending == "stale copy", feed.pending)
check("...and carries the age", round(feed.pending_hours or 0) == 9,
      feed.pending_hours)
check("...which reaches the snapshot",
      feed.as_dict().get("pendingHours") == 9.0, feed.as_dict())

feed = run_prf_with_relay(EXPIRED, NOW, 10 * 60)
check("a fresh relayed copy with nothing in it is 'not published yet'",
      feed.pending == "not published yet", feed.pending)

# ---- the sentence a page shows -------------------------------------------
#
# Called through verdict() rather than grepped out of the source, so this fails
# if the branch stops being reached as well as if the words change.

class OkFeed:
    ok = True
    escalates = True
    count = 1
    partial = None
    error = None
    pending = None
    at = None


class Feeds(dict):
    """Every feed healthy except the one under test."""

    def __init__(self, broken_name, broken):
        dict.__init__(self)
        self.broken_name = broken_name
        self.broken = broken

    def get(self, k, d=None):
        return self.broken if k == self.broken_name else OkFeed()

    def __getitem__(self, k):
        return self.get(k)


CTX_KEYS = ["incidents", "ni", "outfall_co", "outfall_name", "outfall_pos",
            "prf", "rain", "roi", "sepa", "southern", "spills"]


def gaps_for(pending, hours=None):
    feed = m.Feed("NRW pollution risk forecast", covers=["Wales"])
    feed.ok = False
    feed.pending = pending
    feed.pending_hours = hours
    ctx = {k: {} for k in CTX_KEYS}
    ctx["nearby"] = {}
    ctx["feeds"] = Feeds("NRW pollution risk forecast", feed)
    site = {"id": "W:1", "name": "Test", "country": "Wales", "cls": "Good",
            "lat": 51.6, "lon": -4.0}
    real_now, m.NOW = m.NOW, NOW
    try:
        r = m.verdict(site, ctx)
    finally:
        m.NOW = real_now
    return r


r = gaps_for("not published yet")
joined = " ".join(r.get("gaps") or [])
check("a pending feed says the forecast is not published yet",
      "has not published today" in joined, joined[:120])
check("...and does NOT blame a failed fetch",
      "could not be fetched" not in joined, joined[:120])
check("...and still refuses to give a verdict",
      r.get("level") == "unknown", r.get("level"))

# THE CASE THAT ACTUALLY BIT. NRW published at 08:40 and the forecast was valid
# for another twenty hours, but the relay served a copy older than that moment,
# so the feed saw nothing current — and the page told 114 Welsh beaches the
# regulator had not published. Saying a public body has not done something it
# has done is the kind of claim this site exists not to make.
r = gaps_for("stale copy", hours=9.0)
joined = " ".join(r.get("gaps") or [])
check("a stale relayed copy blames this site, not the regulator",
      "limit of this site" in joined, joined[:150])
check("...and does NOT say the regulator has not published",
      "has not published" not in joined, joined[:150])
check("...and says how old the copy is",
      "9 hours old" in joined, joined[:150])
check("...and still refuses to give a verdict",
      r.get("level") == "unknown", r.get("level"))

r = gaps_for(None)
joined = " ".join(r.get("gaps") or [])
check("a genuinely failed feed still says so",
      "could not be fetched" in joined, joined[:120])
check("...and also refuses to give a verdict",
      r.get("level") == "unknown", r.get("level"))

print("%d checked, %d failed" % (checks, failed))
sys.exit(1 if failed else 0)
