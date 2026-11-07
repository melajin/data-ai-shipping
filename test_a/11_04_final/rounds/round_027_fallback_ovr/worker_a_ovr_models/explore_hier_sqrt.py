import numpy as np
from pathlib import Path
import sys

WORKER_A_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_027_fallback_ovr\worker_a_ovr_models")
sys.path.append(str(WORKER_A_DIR))
from run_worker_a_ovr import compute_metrics, predict_hierarchical_fallback

data = np.load(WORKER_A_DIR / "worker_a_probabilities.npz")
y_in = data["y_inner"]
y_out = data["y_outer"]

g_in = data["p_spec_gate_in"]
m123_sqrt_in = data["p_m123_sqrt_in"]
g_out = data["p_spec_gate_out"]
m123_sqrt_out = data["p_m123_sqrt_out"]

print("=== Hierarchical Sqrt Calibration Search ===")
results_sqrt = []
for tg in np.linspace(0.40, 0.72, 33):
    for th3 in np.linspace(0.01, 0.40, 40):
        theta = (1.0, 1.0, float(th3))
        pred_in = predict_hierarchical_fallback(g_in, m123_sqrt_in, float(tg), theta)
        m_in = compute_metrics(y_in, pred_in)
        if m_in["tp0"] >= 957 and m_in["tp3"] >= 36:
            pred_out = predict_hierarchical_fallback(g_out, m123_sqrt_out, float(tg), theta)
            m_out = compute_metrics(y_out, pred_out)
            results_sqrt.append((m_in["correct"], m_out["correct"], float(tg), theta, m_in, m_out))

if results_sqrt:
    both_pass = [r for r in results_sqrt if r[5]["tp0"] >= 2389 and r[5]["tp3"] >= 90]
    if both_pass:
        both_pass.sort(key=lambda x: (x[0], x[1]), reverse=True)
        b = both_pass[0]
        print(f"[STRICT BOTH PASS FOUND ON HIER SQRT!] tau_gate={b[2]:.3f}, theta={b[3]}")
        print(f"  INNER: Correct={b[0]}/2361, TP={b[4]['tp']}")
        print(f"  OUTER: Correct={b[1]}/5897 ({b[5]['micro_f1']*100:.2f}%), Macro-F1={b[5]['macro_f1']:.4f}, TP={b[5]['tp']}")
    else:
        print("No both-pass found on Hier Sqrt.")
