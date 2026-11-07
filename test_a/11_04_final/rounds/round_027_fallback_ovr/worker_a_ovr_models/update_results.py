import json
import numpy as np
from pathlib import Path
import sys

WORKER_A_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_027_fallback_ovr\worker_a_ovr_models")
sys.path.append(str(WORKER_A_DIR))
from run_worker_a_ovr import compute_metrics, predict_hierarchical_fallback, predict_ovr_fallback

data = np.load(WORKER_A_DIR / "worker_a_probabilities.npz")
y_in = data["y_inner"]
y_out = data["y_outer"]

results_json_path = WORKER_A_DIR / "worker_a_results.json"
with open(results_json_path, "r", encoding="utf-8") as f:
    results_dict = json.load(f)

# Add Strict Protection points
# 1. Hierarchical Std Protected Point
g_in = data["p_spec_gate_in"]
m123_in = data["p_m123_std_in"]
g_out = data["p_spec_gate_out"]
m123_out = data["p_m123_std_out"]

pred_hier_std_in = predict_hierarchical_fallback(g_in, m123_in, 0.710, (1.0, 1.0, 0.02))
pred_hier_std_out = predict_hierarchical_fallback(g_out, m123_out, 0.710, (1.0, 1.0, 0.02))
m_hier_std_in = compute_metrics(y_in, pred_hier_std_in)
m_hier_std_out = compute_metrics(y_out, pred_hier_std_out)

results_dict["A2_hier_std_strict_protected"] = {
    "type": "A2_Hierarchical_Fallback_Strict_Protected",
    "tau_gate": 0.710,
    "theta": [1.0, 1.0, 0.02],
    "inner": m_hier_std_in,
    "outer": m_hier_std_out,
}

# 2. Hierarchical Sqrt Protected Point
m123_sqrt_in = data["p_m123_sqrt_in"]
m123_sqrt_out = data["p_m123_sqrt_out"]

pred_hier_sqrt_in = predict_hierarchical_fallback(g_in, m123_sqrt_in, 0.710, (1.0, 1.0, 0.10))
pred_hier_sqrt_out = predict_hierarchical_fallback(g_out, m123_sqrt_out, 0.710, (1.0, 1.0, 0.10))
m_hier_sqrt_in = compute_metrics(y_in, pred_hier_sqrt_in)
m_hier_sqrt_out = compute_metrics(y_out, pred_hier_sqrt_out)

results_dict["A2_hier_sqrt_strict_protected"] = {
    "type": "A2_Hierarchical_Fallback_Strict_Protected",
    "tau_gate": 0.710,
    "theta": [1.0, 1.0, 0.10],
    "inner": m_hier_sqrt_in,
    "outer": m_hier_sqrt_out,
}

# 3. Add Summary and Best Candidate
results_dict["summary"] = {
    "worker": "Worker A (Gemini 3.8 Flash)",
    "hypothesis": "Specialist Detection + Default Fallback to Class 0",
    "baseline_outer_correct": 3356, # Comp0_lgb_knn_std
    "best_accuracy_outer_candidate": "A2_hier_std_acc_optimal",
    "best_accuracy_outer_correct": results_dict["A2_hier_std_acc_optimal"]["outer"]["correct"],
    "best_accuracy_outer_delta": results_dict["A2_hier_std_acc_optimal"]["outer"]["correct"] - 3356,
    "best_protected_outer_candidate": "A2_hier_std_strict_protected",
    "best_protected_outer_correct": m_hier_std_out["correct"],
    "best_protected_outer_delta": m_hier_std_out["correct"] - 3356,
    "best_protected_outer_tp": m_hier_std_out["tp"],
    "best_protected_rules_met": bool(m_hier_std_out["tp0"] >= 2389 and m_hier_std_out["tp3"] >= 90),
}

with open(results_json_path, "w", encoding="utf-8") as f:
    json.dump(results_dict, f, indent=2, ensure_ascii=False)

print("Updated worker_a_results.json successfully!")
print(f"Summary: Best Protected Correct = {m_hier_std_out['correct']}, Delta = +{m_hier_std_out['correct']-3356}, TP = {m_hier_std_out['tp']}")
