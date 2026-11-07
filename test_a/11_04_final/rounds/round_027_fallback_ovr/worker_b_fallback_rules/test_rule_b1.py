import csv
import json
import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from resource_guard import check_ram
from test_baseline_leakage import load_data, FOLDS

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    cm = np.bincount(y_true * 4 + y_pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(np.int64)
    support = cm.sum(axis=1).astype(np.int64)
    predicted = cm.sum(axis=0).astype(np.int64)
    
    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros(4, dtype=np.float64), where=predicted > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros(4, dtype=np.float64), where=(precision + recall) > 0)
    correct = int(np.count_nonzero(y_true == y_pred))
    n = len(y_true)
    
    return {
        "n": n,
        "correct": correct,
        "micro_f1": correct / n if n > 0 else 0.0,
        "macro_f1": float(f1.mean()),
        "tp": tp.tolist(),
        "support": support.tolist(),
        "predicted": predicted.tolist(),
        "precision": precision.tolist(),
        "recall": recall.tolist(),
        "f1": f1.tolist(),
        "confusion_matrix": cm.tolist()
    }

def predict_rule_b1(probs: np.ndarray, tau: np.ndarray, mode: str = "ratio") -> np.ndarray:
    """
    probs: (N, 4)
    tau: (tau1, tau2, tau3)
    mode: "ratio" (p_c / tau_c) or "diff" (p_c - tau_c)
    """
    N = probs.shape[0]
    preds = np.zeros(N, dtype=np.int64) # default fallback = 0
    
    p_spec = probs[:, 1:4] # (N, 3) for c=1, 2, 3
    tau = np.asarray(tau, dtype=np.float32)
    
    if mode == "ratio":
        # score = p / tau
        # valid where p >= tau
        scores = np.where(p_spec >= tau, p_spec / (tau + 1e-9), -1.0)
    else:
        scores = np.where(p_spec >= tau, p_spec - tau, -1.0)
        
    max_scores = scores.max(axis=1)
    has_spec = (max_scores >= 0)
    
    # best specialist among {1, 2, 3}
    best_spec = scores.argmax(axis=1) + 1 # +1 because classes are 1, 2, 3
    preds[has_spec] = best_spec[has_spec]
    
    return preds

def optimize_rule_b1(p_in, inner_y, inner_folds, mode="ratio"):
    min_tp0_in = 958
    min_tp3_in = 38
    
    # Grid for tau1, tau2, tau3
    tau1_vals = np.linspace(0.28, 0.50, 12)
    tau2_vals = np.linspace(0.25, 0.45, 9)
    tau3_vals = np.linspace(0.12, 0.32, 11)
    
    oof_preds = np.zeros(len(inner_y), dtype=np.int64)
    fold_taus = []
    
    for val_fold in FOLDS:
        tr_mask = (inner_folds != val_fold)
        val_mask = (inner_folds == val_fold)
        
        y_tr, p_tr = inner_y[tr_mask], p_in[tr_mask]
        y_val, p_val = inner_y[val_mask], p_in[val_mask]
        
        tr_min_tp0 = int(round(min_tp0_in * (tr_mask.sum() / len(inner_y))))
        tr_min_tp3 = int(round(min_tp3_in * (tr_mask.sum() / len(inner_y))))
        
        best_tau = None
        best_score = -1
        best_sub = -1
        
        for t1 in tau1_vals:
            for t2 in tau2_vals:
                for t3 in tau3_vals:
                    tau = np.array([t1, t2, t3], dtype=np.float32)
                    pred_tr = predict_rule_b1(p_tr, tau, mode=mode)
                    cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                    
                    if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                        corr = np.trace(cm_tr)
                        if corr > best_score or (corr == best_score and cm_tr[3, 3] > best_sub):
                            best_score = corr
                            best_sub = cm_tr[3, 3]
                            best_tau = tau
                            
        if best_tau is None:
            # Fallback relaxation
            print(f"Warning: Fold {val_fold} constraint relaxed")
            best_tau = np.array([0.38, 0.35, 0.20], dtype=np.float32)
            
        fold_taus.append(best_tau)
        oof_preds[val_mask] = predict_rule_b1(p_val, best_tau, mode=mode)
        
    m_in = compute_metrics(inner_y, oof_preds)
    mean_tau = np.mean(fold_taus, axis=0)
    return m_in, mean_tau, fold_taus, oof_preds

def main():
    check_ram("test_rule_b1_start")
    inner_y, outer_y, inner_folds, outer_folds, models = load_data()
    
    target_models = [
        "LightGBM_seed42",
        "LightGBM_5seed_sqrt_macro",
        "Track1_LGB_kNN",
        "Blend_Trio",
        "Blend_Grand",
    ]
    
    print("="*105)
    print("TESTING RULE B1: SPECIALIST ABSOLUTE THRESHOLD + DEFAULT FALLBACK TO CLASS 0")
    print("="*105)
    
    for name in target_models:
        p_in, p_out = models[name]
        
        # Baseline argmax
        base_in_pred = p_in.argmax(axis=1)
        base_out_pred = p_out.argmax(axis=1)
        base_in_m = compute_metrics(inner_y, base_in_pred)
        base_out_m = compute_metrics(outer_y, base_out_pred)
        
        # Optimize Rule B1 (ratio mode)
        m_in, mean_tau, fold_taus, oof_preds = optimize_rule_b1(p_in, inner_y, inner_folds, mode="ratio")
        
        # Outer evaluation with Pooled Mean Tau
        out_pred_pooled = predict_rule_b1(p_out, mean_tau, mode="ratio")
        out_m_pooled = compute_metrics(outer_y, out_pred_pooled)
        
        # Outer evaluation with Fold-Local Tau
        out_pred_local = np.zeros(len(outer_y), dtype=np.int64)
        for f in FOLDS:
            m_f = (outer_folds == f)
            out_pred_local[m_f] = predict_rule_b1(p_out[m_f], fold_taus[f], mode="ratio")
        out_m_local = compute_metrics(outer_y, out_pred_local)
        
        # Comparison metrics
        fp0_base = base_out_m["confusion_matrix"][0][1] + base_out_m["confusion_matrix"][0][2] + base_out_m["confusion_matrix"][0][3]
        fp0_b1_p = out_m_pooled["confusion_matrix"][0][1] + out_m_pooled["confusion_matrix"][0][2] + out_m_pooled["confusion_matrix"][0][3]
        recovered_0_p = fp0_base - fp0_b1_p
        
        print(f"\nModel: {name}")
        print(f"  INNER Baseline Argmax: Correct={base_in_m['correct']}/2361 | TP={base_in_m['tp']}")
        print(f"  INNER Rule B1 OOF:     Correct={m_in['correct']}/2361 | TP={m_in['tp']} | PASS: {m_in['tp'][0]>=958 and m_in['tp'][3]>=38}")
        print(f"  Tuned Mean Tau: {[round(float(x), 3) for x in mean_tau]}")
        print(f"  OUTER Baseline Argmax: Correct={base_out_m['correct']}/5897 | TP={base_out_m['tp']} | Class0 FP leak: {fp0_base}")
        print(f"  OUTER Rule B1 Pooled:  Correct={out_m_pooled['correct']}/5897 | TP={out_m_pooled['tp']} | Class0 FP leak: {fp0_b1_p} (Recovered: {recovered_0_p:+d}) | Gain: {out_m_pooled['correct'] - base_out_m['correct']:+d}")
        print(f"  OUTER Rule B1 Local:   Correct={out_m_local['correct']}/5897 | TP={out_m_local['tp']} | Gain: {out_m_local['correct'] - base_out_m['correct']:+d}")

if __name__ == "__main__":
    main()
