"""The week payload's cells must cover the waterfalls too.

I broke this once. Fixing a real bug — `days` and `pastDays` were taken from
whichever of the two rainfall passes happened to be longest — I also narrowed
the CELL maps to the beach pass, and 2,336 of the 2,521 waterfalls lost their
forecast and their rain chart, because they sit in inland cells no bathing
water occupies. Nothing failed; the payload was simply smaller.

The invariant: cells and rainPast come from the whole of DAILY (both passes),
days and pastDays from beach_daily (the beach pass alone). This reads the
source because the week block lives inline in main() and cannot be called.
"""
import ast
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / "collect_swim.py"
tree = ast.parse(SRC.read_text())

checks, failed = 0, 0


def check(name, cond):
    global checks, failed
    checks += 1
    if cond:
        print("  ok    %s" % name)
    else:
        failed += 1
        print("  FAIL  %s" % name)


def assigns_to(target):
    """Every assignment statement whose target is this bare name."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == target:
                    out.append(node)
    return out


def names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


# cells / rain_past: built by a dict comprehension over DAILY, not beach_daily.
for var in ("cells", "rain_past"):
    comps = [a for a in assigns_to(var)
             if any(isinstance(n, ast.DictComp) for n in ast.walk(a))]
    check("%s is built by a comprehension" % var, bool(comps))
    if not comps:
        continue
    iters = set()
    for a in comps:
        for dc in (n for n in ast.walk(a) if isinstance(n, ast.DictComp)):
            for gen in dc.generators:
                iters |= names_in(gen.iter)
    check("%s iterates DAILY (both passes)" % var, "DAILY" in iters)
    check("%s does not iterate beach_daily only" % var,
          "beach_daily" not in iters)

# days / past_days: accumulated from beach_daily, so the column labels come
# from one pass on one clock.
for var in ("days", "past_days"):
    loops = [n for n in ast.walk(tree)
             if isinstance(n, ast.For)
             and var in {t.id for t in ast.walk(n)
                         if isinstance(t, ast.Name)}
             and "beach_daily" in names_in(n.iter)]
    check("%s is taken from beach_daily" % var, bool(loops))

# And the payload actually carries all four keys.
for key in ("cells", "rainPast", "days", "pastDays"):
    check("week payload has %r" % key,
          ('"%s":' % key) in SRC.read_text() or ('"%s"' % key) in SRC.read_text())

print("%d checked, %d failed" % (checks, failed))
sys.exit(1 if failed else 0)
