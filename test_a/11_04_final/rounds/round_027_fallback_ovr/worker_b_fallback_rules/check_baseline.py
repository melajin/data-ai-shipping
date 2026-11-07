import json
from pathlib import Path

p = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track3_ensemble\grand_fusion_results.json")
if p.exists():
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    print("Grand Fusion results:")
    for k, v in d["outer_evaluation"].items():
        p_m = v["pooled"]["metrics"]
        l_m = v["local"]["metrics"]
        print(f"  {k:<28} | Pooled: {p_m['correct']} (TP: {p_m['tp']}) | Local: {l_m['correct']} (TP: {l_m['tp']})")
