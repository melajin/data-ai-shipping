import json
from pathlib import Path
import numpy as np

report_path = Path(__file__).resolve().parent / "experiment_3a_inventory.json"
with open(report_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print("=== INNER (N=2,361) Base Models ===")
for m in ["LightGBM_seed42", "LightGBM_5seed_sqrt_macro", "CatBoost", "TabICL_seed42", "TabICL_seed2026"]:
    met = data["inner_metrics"][m]
    print(f"{m:<28}: Correct={met['correct']}/2361 ({met['micro_f1']:.6f}), TP={met['tp']}, Recall={[round(r, 4) for r in met['recall']]}")

print("\n=== OUTER (N=5,897) Base Models ===")
for m in ["LightGBM_seed42", "LightGBM_5seed_sqrt_macro", "CatBoost", "TabICL_seed42", "TabICL_seed2026"]:
    met = data["outer_metrics"][m]
    print(f"{m:<28}: Correct={met['correct']}/5897 ({met['micro_f1']:.6f}), TP={met['tp']}, Recall={[round(r, 4) for r in met['recall']]}")
