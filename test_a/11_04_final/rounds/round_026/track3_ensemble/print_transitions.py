import json
from pathlib import Path

p = Path(__file__).resolve().parent / "track3_results.json"
results = json.loads(p.read_text(encoding="utf-8"))

print("=== TRANSITION DETAILS FOR TOP CANDIDATES ===")
for cid in ["T3_B1_PriorShift_Pooled", "T3_B2_Trio_PriorShift_Pooled", "T3_B2_Trio_DualGate"]:
    c = results["candidates"][cid]
    print(f"\n--- {cid} ({c['name']}) ---")
    m = c["metrics"]
    print(f"OUTER Correct: {m['correct']}/5897 (micro: {m['micro_f1']:.6f}, macro: {m['macro_f1']:.6f})")
    print(f"TP: {m['tp']}")
    print(f"Confusion Matrix:")
    for row in m["confusion_matrix"]:
        print(" ", row)

    print("\nVs Baseline 1 (seed42: 3,476, TP=[2389, 889, 108, 90]):")
    t42 = c["transition_vs_seed42"]["per_class_flips"]
    b42 = c["bootstrap_vs_seed42"]
    print(f"  Net gain: {b42['net_gain_ships']:+d} (Newly correct: {b42['newly_correct']}, Newly incorrect: {b42['newly_incorrect']})")
    print(f"  95% CI: {b42['ci95_str']}")
    for cls_k, v in t42.items():
        print(f"    {cls_k}: Base TP={v['base_tp']}, Cand TP={v['cand_tp']} (delta: {v['delta_tp']:+d}, +{v['newly_correct']} / -{v['newly_incorrect']})")

    print("\nVs Baseline 2 (5-seed sqrt: 3,497, TP=[2381, 908, 116, 92]):")
    t5 = c["transition_vs_base5"]["per_class_flips"]
    b5 = c["bootstrap_vs_base5"]
    print(f"  Net gain: {b5['net_gain_ships']:+d} (Newly correct: {b5['newly_correct']}, Newly incorrect: {b5['newly_incorrect']})")
    print(f"  95% CI: {b5['ci95_str']}")
    for cls_k, v in t5.items():
        print(f"    {cls_k}: Base TP={v['base_tp']}, Cand TP={v['cand_tp']} (delta: {v['delta_tp']:+d}, +{v['newly_correct']} / -{v['newly_incorrect']})")
