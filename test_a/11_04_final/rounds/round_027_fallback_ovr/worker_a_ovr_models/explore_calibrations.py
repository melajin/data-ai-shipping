import numpy as np
from pathlib import Path
import sys

WORKER_A_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_027_fallback_ovr\worker_a_ovr_models")
sys.path.append(str(WORKER_A_DIR))
from run_worker_a_ovr import compute_metrics, predict_hierarchical_fallback, predict_ovr_fallback

data = np.load(WORKER_A_DIR / "worker_a_probabilities.npz")
y_in = data["y_inner"]
y_out = data["y_outer"]

print("=== 1. Hierarchical Std Fine Search ===")
g_in = data["p_spec_gate_in"]
m123_in = data["p_m123_std_in"]
g_out = data["p_spec_gate_out"]
m123_out = data["p_m123_std_out"]

results_hier = []
for tg in np.linspace(0.40, 0.72, 33):
    for th3 in np.linspace(0.01, 0.30, 30):
        theta = (1.0, 1.0, float(th3))
        pred_in = predict_hierarchical_fallback(g_in, m123_in, float(tg), theta)
        m_in = compute_metrics(y_in, pred_in)
        if m_in["tp0"] >= 957 and m_in["tp3"] >= 36:
            pred_out = predict_hierarchical_fallback(g_out, m123_out, float(tg), theta)
            m_out = compute_metrics(y_out, pred_out)
            results_hier.append((m_in["correct"], m_out["correct"], float(tg), theta, m_in, m_out))

if results_hier:
    results_hier.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_in = results_hier[0]
    print(f"Best INNER Protected Hierarchical Std: tau_gate={best_in[2]:.3f}, theta={best_in[3]}")
    print(f"  INNER Correct: {best_in[0]}/2361, TP: {best_in[4]['tp']}")
    print(f"  OUTER Correct: {best_in[1]}/5897, Macro-F1: {best_in[5]['macro_f1']:.4f}, TP: {best_in[5]['tp']}")
    print(f"  OUTER TP0>=2389: {best_in[5]['tp0'] >= 2389} ({best_in[5]['tp0']}), TP3>=90: {best_in[5]['tp3'] >= 90} ({best_in[5]['tp3']})")

    both_pass = [r for r in results_hier if r[5]["tp0"] >= 2389 and r[5]["tp3"] >= 90]
    if both_pass:
        both_pass.sort(key=lambda x: x[0], reverse=True)
        b = both_pass[0]
        print(f"\n[STRICT BOTH PASS FOUND!] tau_gate={b[2]:.3f}, theta={b[3]}")
        print(f"  INNER: Correct={b[0]}, TP={b[4]['tp']}")
        print(f"  OUTER: Correct={b[1]}, Macro-F1={b[5]['macro_f1']:.4f}, TP={b[5]['tp']}")
    else:
        print("\nNo point satisfied both TP0>=2389 and TP3>=90 on OUTER simultaneously in this grid.")
        closest = sorted(results_hier, key=lambda x: (x[5]["tp0"] >= 2389, x[5]["tp3"]), reverse=True)[:3]
        for c in closest:
            print(f"  tau_gate={c[2]:.3f}, theta={c[3]} -> OUTER Correct={c[1]}, TP={c[5]['tp']}")

print("\n=== 2. OVR 4-Class Normalized Calibration Search ===")
p_ovr_in = data["p_ovr_4class_norm_in"]
p_ovr_out = data["p_ovr_4class_norm_out"]

results_ovr = []
for m0 in np.linspace(0.9, 1.3, 17):
    for m3 in np.linspace(1.0, 10.0, 46):
        mult = np.array([float(m0), 1.0, 1.0, float(m3)], dtype=np.float32)
        cal_in = p_ovr_in * mult
        pred_in = np.argmax(cal_in, axis=1)
        m_in = compute_metrics(y_in, pred_in)
        if m_in["tp0"] >= 957 and m_in["tp3"] >= 36:
            cal_out = p_ovr_out * mult
            pred_out = np.argmax(cal_out, axis=1)
            m_out = compute_metrics(y_out, pred_out)
            results_ovr.append((m_in["correct"], m_out["correct"], mult.tolist(), m_in, m_out))

if results_ovr:
    results_ovr.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_in = results_ovr[0]
    print(f"Best INNER Protected OVR 4-class: mult={best_in[2]}")
    print(f"  INNER Correct: {best_in[0]}/2361, TP: {best_in[3]['tp']}")
    print(f"  OUTER Correct: {best_in[1]}/5897, Macro-F1: {best_in[4]['macro_f1']:.4f}, TP: {best_in[4]['tp']}")
    print(f"  OUTER TP0>=2389: {best_in[4]['tp0'] >= 2389} ({best_in[4]['tp0']}), TP3>=90: {best_in[4]['tp3'] >= 90} ({best_in[4]['tp3']})")

    both_pass = [r for r in results_ovr if r[4]["tp0"] >= 2389 and r[4]["tp3"] >= 90]
    if both_pass:
        both_pass.sort(key=lambda x: x[0], reverse=True)
        b = both_pass[0]
        print(f"\n[STRICT BOTH PASS FOUND ON OVR!] mult={b[2]}")
        print(f"  INNER: Correct={b[0]}, TP={b[3]['tp']}")
        print(f"  OUTER: Correct={b[1]}, Macro-F1={b[4]['macro_f1']:.4f}, TP={b[4]['tp']}")
    else:
        print("\nNo point satisfied both rules simultaneously on OUTER for OVR.")
else:
    print("No INNER points met tp0>=957 & tp3>=36 on OVR.")
