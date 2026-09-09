"""Hand the newly warned beaches to the site, which sends the emails.

WHY THIS FILE IS SO SHORT, next to swim_push.py. Push is signed and posted from
here, because Web Push crypto wants a maintained library and there is one for
Python. Email cannot be: the only thing on this account that is allowed to send
is a Cloudflare Worker holding the EMAIL binding, and that is not something a
GitHub runner can borrow.

That turns out to be the better arrangement. The addresses never leave
Cloudflare, never pass through this process's memory, and can never end up in an
Actions log — which, on a public repository, they would eventually. All this
file does is say which beaches turned bad; who hears about it is decided inside
functions/swim/email.js and stays there.

So the bookkeeping that swim_push.py does at length — the daily cap, the owed
retry, the per-subscriber delivery count — lives at the other end here. What is
sent over is:

    fresh      beaches that were not warned yesterday and are warned now. Only
               this end holds the previous snapshot, so only this end can work
               it out.
    warnedNow  every beach currently under a warning, so a warning owed from an
               earlier run can be checked for still being TRUE before it is
               finally delivered. An email about a warning that has since been
               lifted is worse than no email.
    places     name and slug per beach, for the wording and the link.

Sending is skipped entirely unless the site says the binding is there, so a run
against a site with email switched off does everything else as normal.
"""

import json
import os
import ssl
import urllib.request

from swim_push import newly_warned, WARNED, _token

CTX = ssl.create_default_context()
TIMEOUT = 30


def _post(base, token, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/email", data=data,
                                 method="POST", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": "swim-collector",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def _enabled(base):
    """Whether the site can actually send. Public, so no token needed."""
    req = urllib.request.Request(base.rstrip("/") + "/email",
                                 headers={"User-Agent": "swim-collector"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def run(previous_sites, current_sites, places, base_url=None, dry_run=False,
        test=False):
    """Returns a short summary for the run log. Never raises.

    test=True asks the site to send everybody a message that says plainly it is
    a test and says nothing about their water. It is the only way to answer
    "are the emails still arriving" without waiting for a beach to turn bad,
    which is the wrong way round on a safety site.
    """
    base = base_url or os.environ.get("SWIM_DATA_BASE") or ""
    if not base:
        return "email: no SWIM_DATA_BASE — skipped"

    if test:
        try:
            token = _token("swim-email")
            if not token:
                return "email: no OIDC token — test skipped"
            r = _post(base, token, {"test": True})
        except Exception as e:                            # noqa: BLE001
            return "email TEST: could not reach the sender (%s)" % str(e)[:120]
        if not r.get("ok"):
            return "email TEST: refused (%s)" % str(r.get("error"))[:120]
        return ("email TEST: %d sent, %d failed, %d subscribers"
                % (r.get("sent", 0), r.get("failed", 0), r.get("subscribers", 0)))

    fresh = newly_warned(previous_sites, current_sites)
    # EVERY WARNED BEACH, not just the new ones. The other end needs this to
    # decide whether a warning it owes from a failed run is still true; without
    # it, a retry could deliver an email about a beach that went clear hours ago.
    warned_now = {sid: (row or {}).get("v")
                  for sid, row in (current_sites or {}).items()
                  if (row or {}).get("v") in WARNED}

    # BEFORE THE NETWORK, not after. A dry run that has to reach the site is not
    # a dry run: it fails on a machine with no connection and it fails while the
    # endpoint is still being built, which is exactly when it is wanted.
    if dry_run:
        return "email: dry run — %d newly warned, %d warned in all" % (
            len(fresh), len(warned_now))

    try:
        cfg = _enabled(base)
    except Exception as e:                                # noqa: BLE001
        return "email: could not ask whether sending is on (%s)" % str(e)[:120]
    if not cfg.get("enabled"):
        return ("email: the site says sending is not configured — nothing sent, "
                "which is correct until the EMAIL binding is added")

    # ONLY THE BEACHES IN PLAY. places holds all 941; sending the lot would be a
    # 60KB body every half hour to say nothing.
    wanted = set(fresh) | set(warned_now)
    trimmed = {sid: places[sid] for sid in wanted if sid in places}

    try:
        token = _token("swim-email")
        if not token:
            return "email: no OIDC token — skipped"
        # POSTED EVEN WHEN NOTHING IS NEW. The other end writes a heartbeat on
        # every call, and that heartbeat is the only thing that lets the site
        # tell "we checked and there was nothing to say" from "the checking has
        # stopped". A run that returns early on an empty `fresh` would look
        # identical to a dead sender.
        r = _post(base, token, {"fresh": fresh, "warnedNow": warned_now,
                                "places": trimmed})
    except Exception as e:                                # noqa: BLE001
        # Never fail the collector over this. The readings matter more than the
        # emails, and the heartbeat going missing is itself the signal.
        return "email: could not reach the sender (%s)" % str(e)[:120]

    if not r.get("ok"):
        return "email: the sender refused the run (%s)" % str(r.get("error"))[:120]
    return ("email: %d newly warned, %d due after the daily cap, %d sent, "
            "%d failed, %d over the per-run cap, %d owed and carried forward"
            % (len(fresh), r.get("due", 0), r.get("sent", 0), r.get("failed", 0),
               r.get("skipped", 0), r.get("owed", 0)))
