import json
from pathlib import Path

p = Path(__file__).resolve().parent / "detailed_inner_optimization.json"
records = json.loads(p.read_text(encoding="utf-8"))

for r in records:
    if "B1" in r["name"] and "R1" in r["name"]:
        print("Name:", r["name"])
        print("Mean Alpha:", r.get("mean_alpha"))
        print("Fold Alphas:", r.get("fold_alphas"))
        print("Metrics:", r["metrics"])
