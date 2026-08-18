"""List divergence details: kind, gt, sol, bad statement."""
import json

data = json.load(open("baseline_results/failures_v9.json"))
items = data if isinstance(data, list) else data.get("divergences", [])
for it in items:
    src = it["source"]
    lines = [l.strip() for l in src.splitlines() if l.strip() and not l.strip().startswith(("func ", "}", "{", "main"))]
    stmt = lines[-1] if lines else "?"
    print("{} gt={:<4d} sol={} | {} | {}".format(
        it["kind"][:14], it["gt"], it["solution"], it["desc"][:26], stmt[:75]))
