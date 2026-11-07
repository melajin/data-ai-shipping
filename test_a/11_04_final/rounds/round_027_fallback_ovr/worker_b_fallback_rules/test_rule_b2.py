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
from test_rule_b1 import compute_metrics

def predict_rule_b2(probs: np.ndarray, params: dict) -> np.ndarray:
    """
    params:
      tau1, tau2, tau3: absolute thresholds for specialist classes 1, 2, 3
      gamma1, gamma2, gamma3: relative margin over class 0 (P(c) >= gamma_c * P(0))
      gamma21: separation of pot(2) vs gillnet(1) (P(2) >= gamma21 * P(1))
    """
    N = probs.shape[0]
    preds = np.zeros(N, dtype=np.int64)
    
    p0 = probs[:, 0]
    p1 = probs[:, 1]
    p2 = probs[:, 2]
    p3 = probs[:, 3]
    
    tau1 = params["tau1"]
    tau2 = params["tau2"]
    tau3 = params["tau3"]
    gamma1 = params.get("gamma1", 1.0)
    gamma2 = params.get("gamma2", 1.0)
    gamma3 = params.get("gamma3", 1.0)
    gamma21 = params.get("gamma21", 0.0)
    
    # Gate checks
    # Class 3: Squid jigging (Rare, high priority)
    gate3 = (p3 >= tau3) & (p3 >= gamma3 * p0)
    score3 = np.where(gate3, p3 / (tau3 + 1e-6), -1.0)
    
    # Class 2: Trap/Pot
    gate2 = (p2 >= tau2) & (p2 >= gamma2 * p0) & (p2 >= gamma21 * p1)
    score2 = np.where(gate2, p2 / (tau2 + 1e-6), -1.0)
    
    # Class 1: Gillnet
    gate1 = (p1 >= tau1) & (p1 >= gamma1 * p0)
    score1 = np.where(gate1, p1 / (tau1 + 1e-6), -1.0)
    
    scores = np.stack([score1, score2, score3], axis=1) # (N, 3)
    max_scores = scores.max(axis=1)
    has_spec = (max_scores >= 0)
    
    best_spec = scores.argmax(axis=1) + 1
    preds[has_spec] = best_spec[has_spec]
    
    return preds

def test_search():
    inner_y, outer_y, inner_folds, outer_folds, models = load_data()
    min_tp0_in = 958
    min_tp3_in = 38
    
    print("Testing Rule B2 parameter space on Blend_Grand and Blend_Trio...")
    for model_name in ["Blend_Grand", "Blend_Trio", "LightGBM_5seed_sqrt_macro"]:
        p_in, p_out = models[model_name]
        
        # Baseline
        base_out_pred = p_out.argmax(axis=1)
        base_out_m = compute_metrics(outer_y, base_out_pred)
        
        best_overall = None
        best_inner_corr = -1
        
        # Nested CV
        oof_preds = np.zeros(len(inner_y), dtype=np.int64)
        fold_best_params = []
        
        for val_fold in FOLDS:
            tr_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            y_tr, p_tr = inner_y[tr_mask], p_in[tr_mask]
            y_val, p_val = inner_y[val_mask], p_in[val_mask]
            
            tr_min_tp0 = int(round(min_tp0_in * (tr_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(min_tp3_in * (tr_mask.sum() / len(inner_y))))
            
            best_fold_p = None
            best_fold_score = -1
            best_fold_sub = -1
            
            # Grid
            for t1 in [0.28, 0.32, 0.35, 0.38, 0.42]:
                for t2 in [0.22, 0.25, 0.28, 0.32]:
                    for t3 in [0.12, 0.15, 0.18, 0.22]:
                        for g1 in [0.85, 0.95, 1.0, 1.05]:
                            for g2 in [0.85, 0.95, 1.0, 1.05]:
                                for g3 in [0.60, 0.75, 0.90]:
                                    for g21 in [0.0, 0.7, 0.85, 1.0]:
                                        p = {
                                            "tau1": t1, "tau2": t2, "tau3": t3,
                                            "gamma1": g1, "gamma2": g2, "gamma3": g3,
                                            "gamma21": g21
                                        }
                                        pred_tr = predict_rule_b2(p_tr, p)
                                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                                        if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                                            corr = np.trace(cm_tr)
                                            if corr > best_fold_score or (corr == best_fold_score and cm_tr[3, 3] > best_fold_sub):
                                                best_fold_score = corr
                                                best_fold_sub = cm_tr[3, 3]
                                                best_fold_p = p
            fold_best_params.append(best_fold_p)
            oof_preds[val_mask] = predict_rule_b2(p_val, best_fold_p)
            
        m_in = compute_metrics(inner_y, oof_preds)
        print(f"\n[{model_name}] INNER OOF Correct={m_in['correct']}/2361 | TP={m_in['tp']} | PASS: {m_in['tp'][0]>=min_tp0_in and m_in['tp'][3]>=min_tp3_in}")
        
        # Mean params
        mean_p = {
            k: float(np.mean([fp[k] for fp in fold_best_params]))
            for k in fold_best_params[0]
        }
        print(f"  Mean Params: {mean_p}")
        
        # Outer Pooled
        out_pred_pooled = predict_rule_b2(p_out, mean_p)
        m_out_p = compute_metrics(outer_y, out_pred_pooled)
        pass_p = m_out_p['tp'][0] >= 2389 and m_out_p['tp'][3] >= 92
        diff_p = m_out_p['correct'] - base_out_m['correct']
        print(f"  OUTER Pooled: Correct={m_out_p['correct']}/5897 | TP={m_out_p['tp']} | PASS: {pass_p} | Diff vs Argmax: {diff_p:+d}")
        
        # Outer Local
        out_pred_local = np.zeros(len(outer_y), dtype=np.int64)
        for f in FOLDS:
            m_f = (outer_folds == f)
            out_pred_local[m_f] = predict_rule_b2(p_out[m_f], fold_best_params[f])
        m_out_l = compute_metrics(outer_y, out_pred_local)
        pass_l = m_out_l['tp'][0] >= 2389 and m_out_l['tp'][3] >= 92
        diff_l = m_out_l['correct'] - base_out_m['correct']
        print(f"  OUTER Local:  Correct={m_out_l['correct']}/5897 | TP={m_out_l['tp']} | PASS: {pass_l} | Diff vs Argmax: {diff_l:+d}")

if __name__ == "__main__":
    test_search()
