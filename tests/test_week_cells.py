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


def updates_of(target):
    """Every `target.update(...)` call in the file."""
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "update" and isinstance(n.func.value, ast.Name)
            and n.func.value.id == target]


def comps_in(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.DictComp)]


def iters_of(comps):
    out = set()
    for dc in comps:
        for gen in dc.generators:
            out |= names_in(gen.iter)
    return out


# FOLLOW WHAT FEEDS THE NAME, NOT THE SHAPE IT HAPPENS TO HAVE.
#
# The first version of this insisted `cells` itself was a dict comprehension.
# The 16 September fix — merge the previously published copy in, then this
# run's own cells over the top — replaced that comprehension with
# `fresh_cells = {...}` plus two `cells.update(...)` calls, so the test failed
# on correct code. A guard that cries wolf on a fix is a guard that gets left
# out of the workflow, which is exactly where this one was found.
fresh = [a for a in assigns_to("fresh_cells") if comps_in(a)]
check("this run's cells come from a comprehension", bool(fresh))
f_iters = iters_of([c for a in fresh for c in comps_in(a)])
check("they iterate DAILY (both passes)", "DAILY" in f_iters)
check("they do not iterate beach_daily", "beach_daily" not in f_iters)
check("and they are merged into cells, not swapped for it",
      any(any(isinstance(a, ast.Name) and a.id == "fresh_cells" for a in n.args)
          for n in updates_of("cells")))
check("the previously published cells are carried in too",
      any("prev" in names_in(n) for n in updates_of("cells")))

# rain_past: same rule, and it is merged the same way.
rp = [c for n in updates_of("rain_past") for a in n.args for c in comps_in(a)]
check("rain_past is fed by a comprehension", bool(rp))
rp_iters = iters_of(rp)
check("rain_past iterates DAILY (both passes)", "DAILY" in rp_iters)
check("rain_past does not iterate beach_daily", "beach_daily" not in rp_iters)
check("the previously published rainPast is carried in too",
      any("prev" in names_in(n) for n in updates_of("rain_past")))

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
