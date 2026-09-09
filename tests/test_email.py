"""The collector's half of the email warnings.

Almost all of the reasoning lives at the other end, in functions/swim/email.js,
where it is covered by tools/test/email_harness.js. What is decided HERE is what
gets sent over — and two of those decisions can be silently wrong:

  * warnedNow. The other end uses it to check that a warning it owes is still
    true before delivering it. Send the wrong set and a retry announces a
    warning that was lifted hours ago.
  * the trim. places holds all 941 bathing waters and only a handful are ever in
    play. Sending the lot would be a 60KB body every half hour to say nothing —
    but trimming too hard would strip the name and link out of a real warning
    and leave an email that says "a place you follow" with no place in it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swim_email                                          # noqa: E402

checked = failed = 0


def ok(name, cond, detail=""):
    global checked, failed
    checked += 1
    if cond:
        print("  ok    %s" % name)
    else:
        failed += 1
        print("  FAIL  %s%s" % (name, ("  — " + detail) if detail else ""))


PLACES = {
    "b1": {"name": "Bantham", "slug": "bantham"},
    "b2": {"name": "Seaton", "slug": "seaton"},
    "b3": {"name": "Blackpool South", "slug": "blackpool-south"},
    "b4": {"name": "Nowhere In Particular", "slug": "nowhere"},
}


def captured(previous, current, places):
    """Run it with the network replaced, and return the body it tried to post."""
    seen = {}

    def fake_enabled(base):
        return {"enabled": True, "checkState": "ran"}

    def fake_post(base, token, body):
        seen.update(body)
        return {"ok": True, "due": 0, "sent": 0, "failed": 0, "skipped": 0, "owed": 0}

    real = (swim_email._enabled, swim_email._post, swim_email._token)
    swim_email._enabled, swim_email._post = fake_enabled, fake_post
    swim_email._token = lambda aud: "t"
    try:
        line = swim_email.run(previous, current, places,
                              base_url="https://example.invalid/swim")
    finally:
        swim_email._enabled, swim_email._post, swim_email._token = real
    return seen, line


def test_only_new_warnings_are_announced():
    prev = {"b1": {"v": "ok"}, "b2": {"v": "avoid"}}
    cur = {"b1": {"v": "avoid"}, "b2": {"v": "avoid"}}
    body, _ = captured(prev, cur, PLACES)
    ok("the beach that turned bad is fresh", body["fresh"] == {"b1": "avoid"},
       repr(body["fresh"]))
    ok("the one warned yesterday too is not news again", "b2" not in body["fresh"])


def test_a_beach_that_went_clear_produces_nothing():
    prev = {"b1": {"v": "avoid"}}
    cur = {"b1": {"v": "ok"}}
    body, _ = captured(prev, cur, PLACES)
    ok("no all clear is ever announced", body["fresh"] == {},
       "this site does not tell anybody the water is fine")


def test_warned_now_carries_every_warning_not_just_the_new_ones():
    prev = {"b1": {"v": "ok"}, "b2": {"v": "avoid"}}
    cur = {"b1": {"v": "avoid"}, "b2": {"v": "avoid"}, "b3": {"v": "advised"},
           "b4": {"v": "ok"}}
    body, _ = captured(prev, cur, PLACES)
    ok("all three warned places are listed",
       body["warnedNow"] == {"b1": "avoid", "b2": "avoid", "b3": "advised"},
       repr(body["warnedNow"]))
    ok("and the clear one is not", "b4" not in body["warnedNow"])


def test_places_is_trimmed_to_the_beaches_in_play():
    prev = {"b1": {"v": "ok"}}
    cur = {"b1": {"v": "avoid"}, "b3": {"v": "advised"}, "b4": {"v": "ok"}}
    body, _ = captured(prev, cur, PLACES)
    ok("the warned ones keep their name and slug",
       set(body["places"]) == {"b1", "b3"}, repr(sorted(body["places"])))
    ok("b1 still has what the email needs",
       body["places"]["b1"] == {"name": "Bantham", "slug": "bantham"})


def test_it_posts_even_when_nothing_is_new():
    # The other end writes its heartbeat on every call, and that heartbeat is
    # the only thing that lets the site tell "we checked and there was nothing
    # to say" from "the checking has stopped". Returning early here would make
    # a healthy quiet day look exactly like a dead sender.
    prev = {"b1": {"v": "ok"}}
    cur = {"b1": {"v": "ok"}}
    body, line = captured(prev, cur, PLACES)
    ok("it still posted", body != {}, "nothing was sent to the site at all")
    ok("and said so plainly", "0 newly warned" in line, line)


def test_a_first_run_does_not_announce_the_whole_country():
    # No previous snapshot means no transitions. Announcing every warned beach
    # in Britain at once is both useless and the fastest way to be muted, and
    # being muted is how a real warning goes unread later.
    cur = {"b1": {"v": "avoid"}, "b2": {"v": "avoid"}, "b3": {"v": "advised"}}
    body, _ = captured({}, cur, PLACES)
    ok("nothing announced on a cold start", body["fresh"] == {}, repr(body["fresh"]))
    ok("but the warnings are still reported", len(body["warnedNow"]) == 3)


for name, fn in sorted(list(globals().items())):
    if name.startswith("test_"):
        fn()

print("%d checked, %d failed" % (checked, failed))
sys.exit(1 if failed else 0)
