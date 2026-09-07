"""Whether a carried-forward sea reading counts as healthy.

WHY THIS EXISTS. The bar here has been wrong twice.

First it compared a count of grid CELLS against a count of coastal SITES — a
bar nothing could clear, so every carry-forward marked the feed down. That was
fixed by counting cells on both sides. It was still wrong: the denominator was
every sea-kind cell, and the marine model does not answer for all of them. Five
are over 20km from the nearest sea point and are dropped outright; more are
estuary and lake points that come back all-null, which is the right answer and
is published as nothing.

So on 7 September a fresh fetch got 298 of 322 cells and reported healthy, and
the identical set on carry-forward reported the feed down. Same data, two
verdicts, and the site said the sea temperature feed was down all day while it
was working perfectly.

The rule these pin: carry the health of the FETCH, do not re-derive it. A
partial set must stay partial while it is carried — that is what the bar is for
— but the model's own permanent coverage is not a fault.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_swim as C                                  # noqa: E402


class Feed(object):
    def __init__(self):
        self.ok, self.count, self.at, self.partial, self.error = None, 0, None, "", None


def recent(minutes):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# 322 cells asked for, 298 the model will ever answer — the real numbers.
SITES = [{"lat": 50.0 + i * 0.3, "lon": -4.0, "kind": "Coastal"} for i in range(322)]
SEA = {"%d,%d" % (i, i): {"t": [[16.0, 16.5]]} for i in range(298)}


def carry(seaOk, minutes=60, sea=None, sites=None):
    feed = Feed()
    prev = {"seaAt": recent(minutes), "sea": sea if sea is not None else SEA}
    if seaOk is not None:
        prev["seaOk"] = seaOk
    # sites=[] where the case is about NOT carrying: with nothing to ask about
    # there are no batches, so the test never reaches the network. A unit test
    # that phones Open-Meteo fails on a train.
    C.sea_temperature(SITES if sites is None else sites, feed, prev)
    return feed


fails = []


def check(name, got, want):
    if got != want:
        fails.append("%s: got %r, wanted %r" % (name, got, want))
    print("%-58s %s" % (name, "pass" if got == want else "FAIL"))


# The fault that was live: a healthy fetch carried forward must stay healthy,
# even though 298 of 322 is under any percentage bar worth setting.
check("healthy fetch, carried forward, stays healthy", carry(True).ok, True)

# The reason a bar existed at all: a partial fetch must not become healthy by
# being carried.
f = carry(False)
check("partial fetch, carried forward, stays partial", f.ok, False)
check("  and says so rather than only giving an age",
      "partial" in f.partial, True)

# An older snapshot written before the fetch recorded its own health.
check("no recorded health: a full-looking set is accepted",
      carry(None).ok, True)
check("no recorded health: a badly short set is not",
      carry(None, sea={"%d,%d" % (i, i): {} for i in range(100)}).ok, False)

# Age still governs whether the carry-forward happens at all.
old = carry(True, minutes=C.SEA_MAX_AGE_MIN + 30, sites=[])
check("beyond the carry window it does not silently carry",
      old.partial.startswith("carried forward"), False)

print()
if fails:
    for f in fails:
        print("  " + f)
    raise SystemExit("%d failed" % len(fails))
print("all pass")
