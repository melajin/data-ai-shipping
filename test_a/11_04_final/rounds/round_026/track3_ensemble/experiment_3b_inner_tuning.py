import csv
import gc
import json
import os
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from resource_guard import check_ram
from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS

def main():
    check_ram("exp3b_inner_tuning_start", expected_peak_mb=120.0)

    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)

    # Inner fold identifiers
    inner_folds = np.array([r[0] for r in inner_records], dtype=np.int64)
    
    # Base models for tuning
    p_lgb42 = inner_probs["LightGBM_seed42"]
    p_lgb5 = inner_probs["LightGBM_5seed_sqrt_macro"]
    p_cat = inner_probs["CatBoost"]
    p_tab42 = inner_probs["TabICL_seed42"]
    p_tab26 = inner_probs["TabICL_seed2026"]
    
    # Target protection on INNER:
    # Baseline LightGBM seed42: TP0 = 959, TP3 = 36
    # Baseline 5-seed: TP0 = 946, TP3 = 36
    min_tp0 = 959
    min_tp3 = 36

    print("="*90)
    print(f"INNER GRID SEARCH 1: LINEAR WEIGHT SEARCH (LGB5 vs CAT vs TAB42 vs TAB26)")
    print(f"Target Constraints on INNER (N=2,361): TP0 >= {min_tp0}, TP3 >= {min_tp3}")
    print("="*90)

    # Grid of weights for (LGB, CAT, TAB42, TAB26)
    # Let's explore combinations of weights
    best_unconstrained = None
    best_constrained = None
    
    weight_candidates = []
    # 2-model: LGB5 + TAB42
    for w_lgb in np.linspace(0.1, 0.9, 17):
        weight_candidates.append(("LGB5_TAB42", (w_lgb, 0.0, 1.0 - w_lgb, 0.0)))
        weight_candidates.append(("LGB42_TAB42", (w_lgb, 0.0, 1.0 - w_lgb, 0.0)))
    # 3-model: LGB5 + CAT + TAB42
    for w_lgb in np.linspace(0.2, 0.6, 9):
        for w_cat in np.linspace(0.05, 0.4, 8):
            w_tab = 1.0 - w_lgb - w_cat
            if w_tab > 0.05:
                weight_candidates.append(("LGB5_CAT_TAB42", (w_lgb, w_cat, w_tab, 0.0)))
    # 4-model: LGB5 + CAT + TAB42 + TAB26
    for w_lgb in [0.3, 0.4, 0.5]:
        for w_cat in [0.1, 0.15, 0.2]:
            w_tab_tot = 1.0 - w_lgb - w_cat
            if w_tab_tot > 0.1:
                weight_candidates.append(("LGB5_CAT_TAB_BOTH", (w_lgb, w_cat, w_tab_tot * 0.5, w_tab_tot * 0.5)))

    linear_results = []
    for model_type, (w1, w2, w3, w4) in weight_candidates:
        if model_type.startswith("LGB42"):
            p_blend = w1 * p_lgb42 + w2 * p_cat + w3 * p_tab42 + w4 * p_tab26
        else:
            p_blend = w1 * p_lgb5 + w2 * p_cat + w3 * p_tab42 + w4 * p_tab26
            
        pred = p_blend.argmax(axis=1)
        met = compute_metrics(inner_y, pred)
        
        is_constrained = (met["tp"][0] >= min_tp0) and (met["tp"][3] >= min_tp3)
        linear_results.append({
            "model_type": model_type,
            "weights": (round(w1, 3), round(w2, 3), round(w3, 3), round(w4, 3)),
            "correct": met["correct"],
            "micro_f1": met["micro_f1"],
            "macro_f1": met["macro_f1"],
            "tp": met["tp"],
            "constrained": is_constrained,
        })
        
    linear_results.sort(key=lambda x: x["micro_f1"], reverse=True)
    print("Top 5 Unconstrained Linear Blends on INNER:")
    for r in linear_results[:5]:
        print(f"  {r['model_type']} w={r['weights']}: Correct={r['correct']}/2361 ({r['micro_f1']:.6f}), TP={r['tp']}, pass={r['constrained']}")

    constrained_linear = [r for r in linear_results if r["constrained"]]
    print(f"\nConstrained Linear Blends (TP0 >= {min_tp0}, TP3 >= {min_tp3}): {len(constrained_linear)} found")
    for r in constrained_linear[:5]:
        print(f"  {r['model_type']} w={r['weights']}: Correct={r['correct']}/2361 ({r['micro_f1']:.6f}), TP={r['tp']}")

    # Notice: In pure unconstrained linear blend, TP3 is often 32-34 (< 36)!
    # Why? Because TabICL has low P(3), pulling down Class 3 predictions.
    # Now let's test Log-Linear (Geometric mean) and Temperature scaling!
    print("\n" + "="*90)
    print("INNER GRID SEARCH 2: LOG-LINEAR (GEOMETRIC MEAN) & TEMPERATURE")
    print("="*90)
    log_linear_results = []
    eps = 1e-12
    for w_lgb in [0.3, 0.4, 0.5, 0.6, 0.7]:
        w_tab = 1.0 - w_lgb
        # Geometric blend
        log_p = w_lgb * np.log(np.clip(p_lgb5, eps, 1.0)) + w_tab * np.log(np.clip(p_tab42, eps, 1.0))
        p_geom = np.exp(log_p)
        pred = p_geom.argmax(axis=1)
        met = compute_metrics(inner_y, pred)
        is_constrained = (met["tp"][0] >= min_tp0) and (met["tp"][3] >= min_tp3)
        log_linear_results.append({
            "type": "LGB5+TAB42 Geom", "w": (w_lgb, w_tab),
            "correct": met["correct"], "micro_f1": met["micro_f1"], "tp": met["tp"], "constrained": is_constrained
        })
    for r in log_linear_results:
        print(f"  {r['type']} w={r['w']}: Correct={r['correct']}/2361 ({r['micro_f1']:.6f}), TP={r['tp']}, pass={r['constrained']}")

    # Search 3: Prior-Shift / Class Multiplier Tuning
    # Formula: y_hat = argmax_c (alpha_c * P_blend(c))
    # We fix alpha_1 = 1.0. We search alpha_0 in [0.95, 1.15], alpha_2 in [0.9, 1.2], alpha_3 in [1.0, 1.6]
    print("\n" + "="*90)
    print("INNER GRID SEARCH 3: CLASS MULTIPLIER / PRIOR-SHIFT OPTIMIZATION")
    print("="*90)

    # Let's test on top base blends:
    # Blend A: 0.5 * LGB5 + 0.5 * TAB42
    # Blend B: 0.45 * LGB5 + 0.15 * CAT + 0.40 * TAB42
    # Blend C: 0.4 * LGB5 + 0.1 * CAT + 0.25 * TAB42 + 0.25 * TAB26
    # Blend D: 0.5 * LGB42 + 0.5 * TAB42
    
    test_blends = {
        "Blend_LGB5_TAB42 (50:50)": 0.5 * p_lgb5 + 0.5 * p_tab42,
        "Blend_LGB5_CAT_TAB42 (45:15:40)": 0.45 * p_lgb5 + 0.15 * p_cat + 0.40 * p_tab42,
        "Blend_LGB5_CAT_TAB_BOTH (40:10:25:25)": 0.40 * p_lgb5 + 0.10 * p_cat + 0.25 * p_tab42 + 0.25 * p_tab26,
        "Blend_LGB42_TAB42 (50:50)": 0.5 * p_lgb42 + 0.5 * p_tab42,
    }

    # K-fold Cross-Validation within INNER:
    # We have 3 folds (fold 0: 787, fold 1: 787, fold 2: 787).
    # To prevent any overfitting on INNER, let's perform Out-Of-Fold parameter search on the 3 INNER folds!
    print("Running 3-fold Nested CV on INNER (Fit multipliers on 2 inner folds, evaluate OOF on 3rd inner fold)...")
    
    cv_multiplier_results = {}
    for blend_name, p_blend in test_blends.items():
        oof_preds = np.zeros(len(inner_y), dtype=np.int64)
        fold_alphas = []
        
        for val_fold in FOLDS:
            train_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            
            y_tr, p_tr = inner_y[train_mask], p_blend[train_mask]
            y_val, p_val = inner_y[val_mask], p_blend[val_mask]
            
            # Grid search on train_mask for optimal (alpha_0, alpha_2, alpha_3)
            # Train target constraints: scaled to 2/3 of INNER
            # 2/3 of min_tp0 is ~640, 2/3 of min_tp3 is ~24
            tr_min_tp0 = int(round(min_tp0 * (train_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(min_tp3 * (train_mask.sum() / len(inner_y))))
            
            best_alpha = None
            best_score = -1
            best_val_pred = None
            
            # Focused search grid
            for a0 in np.linspace(0.95, 1.15, 9):
                for a2 in np.linspace(0.9, 1.2, 7):
                    for a3 in np.linspace(1.0, 1.5, 11):
                        alpha = np.array([a0, 1.0, a2, a3], dtype=np.float64)
                        scaled_p_tr = p_tr * alpha
                        pred_tr = scaled_p_tr.argmax(axis=1)
                        
                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                        tp0_tr = cm_tr[0, 0]
                        tp3_tr = cm_tr[3, 3]
                        correct_tr = np.trace(cm_tr)
                        
                        # Strict constraint satisfaction on train folds
                        if tp0_tr >= tr_min_tp0 and tp3_tr >= tr_min_tp3:
                            if correct_tr > best_score:
                                best_score = correct_tr
                                best_alpha = alpha
                                
            # If no strict alpha found, take the one closest to constraint
            if best_alpha is None:
                print(f"  Warning: No alpha satisfied strict constraint on train fold {val_fold}, falling back to unconstrained max.")
                best_alpha = np.array([1.05, 1.0, 1.0, 1.25], dtype=np.float64)
                
            fold_alphas.append(best_alpha)
            # Predict on val_fold using the learned alpha
            oof_preds[val_mask] = (p_val * best_alpha).argmax(axis=1)
            
        oof_metrics = compute_metrics(inner_y, oof_preds)
        is_constrained = (oof_metrics["tp"][0] >= min_tp0) and (oof_metrics["tp"][3] >= min_tp3)
        mean_alpha = np.mean(fold_alphas, axis=0)
        cv_multiplier_results[blend_name] = {
            "oof_correct": oof_metrics["correct"],
            "oof_micro_f1": oof_metrics["micro_f1"],
            "oof_macro_f1": oof_metrics["macro_f1"],
            "oof_tp": oof_metrics["tp"],
            "passed_protection": is_constrained,
            "mean_alpha": [round(x, 4) for x in mean_alpha.tolist()],
            "fold_alphas": [[round(x, 4) for x in a.tolist()] for a in fold_alphas],
        }
        print(f"\n{blend_name}:")
        print(f"  Learned Mean Alpha [a0, a1, a2, a3] = {[round(x, 3) for x in mean_alpha]}")
        print(f"  Fold Alphas: {[[round(x, 3) for x in a] for a in fold_alphas]}")
        print(f"  OOF Correct = {oof_metrics['correct']}/2361 ({oof_metrics['micro_f1']:.6f}), TP = {oof_metrics['tp']}, PASS = {is_constrained}")

    # Search 4: Gated Class 3 Protection
    # Rule: If P_lgb(3) >= tau_lgb or P_blend(3) >= tau_blend, predict 3; else argmax(alpha * P_blend)
    print("\n" + "="*90)
    print("INNER GRID SEARCH 4: GATED DUAL THRESHOLD FOR CLASS 3")
    print("="*90)
    
    for blend_name, p_blend in test_blends.items():
        oof_preds_gate = np.zeros(len(inner_y), dtype=np.int64)
        gate_params = []
        for val_fold in FOLDS:
            train_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            
            y_tr, p_tr, lgb_tr = inner_y[train_mask], p_blend[train_mask], p_lgb5[train_mask]
            y_val, p_val, lgb_val = inner_y[val_mask], p_blend[val_mask], p_lgb5[val_mask]
            
            tr_min_tp0 = int(round(min_tp0 * (train_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(min_tp3 * (train_mask.sum() / len(inner_y))))
            
            best_param = None
            best_score = -1
            
            for tau_lgb3 in [0.20, 0.25, 0.30, 0.35, 0.40]:
                for a0 in [1.0, 1.02, 1.05]:
                    pred_tr = (p_tr * np.array([a0, 1.0, 1.0, 1.0])).argmax(axis=1)
                    # Gate condition: if lgb3 is confident, override to 3
                    pred_tr[lgb_tr[:, 3] >= tau_lgb3] = 3
                    
                    cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                    if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                        if np.trace(cm_tr) > best_score:
                            best_score = np.trace(cm_tr)
                            best_param = (tau_lgb3, a0)
                            
            if best_param is None:
                best_param = (0.30, 1.02)
            gate_params.append(best_param)
            
            # Predict on val fold
            pred_v = (p_val * np.array([best_param[1], 1.0, 1.0, 1.0])).argmax(axis=1)
            pred_v[lgb_val[:, 3] >= best_param[0]] = 3
            oof_preds_gate[val_mask] = pred_v
            
        m_gate = compute_metrics(inner_y, oof_preds_gate)
        is_constrained = (m_gate["tp"][0] >= min_tp0) and (m_gate["tp"][3] >= min_tp3)
        print(f"{blend_name} + LGB3 Gate:")
        print(f"  Gate params per fold: {gate_params}")
        print(f"  OOF Correct = {m_gate['correct']}/2361 ({m_gate['micro_f1']:.6f}), TP = {m_gate['tp']}, PASS = {is_constrained}")

    # Search 5: Routing by Observation Days (n_days)
    print("\n" + "="*90)
    print("INNER EXPERIMENT 5: ROUTING BY OBSERVATION DAYS (n_days)")
    print("="*90)
    tab_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation\seed_42")
    inner_days_map = {}
    for fold in FOLDS:
        with open(tab_dir / f"fold_{fold}" / "inner_predictions.csv", "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                inner_days_map[(fold, r["rfid_id"])] = float(r["observed_days"])
    inner_keys = [(r[0], r[2]) for r in inner_records]
    inner_days = np.array([inner_days_map[k] for k in inner_keys], dtype=np.float64)
    
    # We observed:
    # 1-7 days: TabICL (0.6173) > LGB42 (0.6119) > Cat (0.6011) > LGB5 (0.5957)
    # 8-30 days: Tab26 (0.5728) > Cat (0.5709) > LGB42 (0.5689)
    # 31-90 days: Tab26 (0.5882) > Tab42 (0.5850) > LGB42 (0.5744) > Cat (0.5649)
    # 91+ days: Cat (0.6243) > LGB5 (0.6168) > LGB42 (0.6150) > Tab26 (0.6131) > Tab42 (0.6112)
    
    # Test day-based dynamic weight routing:
    # short (<=30d): TabICL 60%, LGB 40%
    # mid (31-90d): TabICL 60%, LGB 30%, Cat 10%
    # long (91+d): LGB 45%, Cat 25%, TabICL 30%
    p_routed = np.zeros_like(p_lgb5)
    mask_short = inner_days <= 30
    mask_mid = (inner_days > 30) & (inner_days <= 90)
    mask_long = inner_days > 90
    
    p_routed[mask_short] = 0.40 * p_lgb5[mask_short] + 0.60 * p_tab42[mask_short]
    p_routed[mask_mid] = 0.30 * p_lgb5[mask_mid] + 0.15 * p_cat[mask_mid] + 0.55 * p_tab42[mask_mid]
    p_routed[mask_long] = 0.45 * p_lgb5[mask_long] + 0.25 * p_cat[mask_long] + 0.30 * p_tab42[mask_long]
    
    # Check uncalibrated routed
    m_routed_raw = compute_metrics(inner_y, p_routed.argmax(axis=1))
    print(f"Raw Routed (n_days dynamic weights): Correct={m_routed_raw['correct']}/2361 ({m_routed_raw['micro_f1']:.6f}), TP={m_routed_raw['tp']}")
    
    # Multiplier calibration on routed
    oof_preds_routed = np.zeros(len(inner_y), dtype=np.int64)
    for val_fold in FOLDS:
        train_mask = (inner_folds != val_fold)
        val_mask = (inner_folds == val_fold)
        y_tr, p_tr = inner_y[train_mask], p_routed[train_mask]
        y_val, p_val = inner_y[val_mask], p_routed[val_mask]
        
        tr_min_tp0 = int(round(min_tp0 * (train_mask.sum() / len(inner_y))))
        tr_min_tp3 = int(round(min_tp3 * (train_mask.sum() / len(inner_y))))
        
        best_alpha = None
        best_score = -1
        for a0 in np.linspace(0.98, 1.12, 8):
            for a2 in np.linspace(0.95, 1.15, 5):
                for a3 in np.linspace(1.05, 1.45, 9):
                    alpha = np.array([a0, 1.0, a2, a3], dtype=np.float64)
                    pred_tr = (p_tr * alpha).argmax(axis=1)
                    cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                    if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                        if np.trace(cm_tr) > best_score:
                            best_score = np.trace(cm_tr)
                            best_alpha = alpha
        if best_alpha is None:
            best_alpha = np.array([1.04, 1.0, 1.0, 1.25], dtype=np.float64)
            
        oof_preds_routed[val_mask] = (p_val * best_alpha).argmax(axis=1)
        
    m_routed_cal = compute_metrics(inner_y, oof_preds_routed)
    is_constrained = (m_routed_cal["tp"][0] >= min_tp0) and (m_routed_cal["tp"][3] >= min_tp3)
    print(f"Calibrated Routed (OOF CV): Correct={m_routed_cal['correct']}/2361 ({m_routed_cal['micro_f1']:.6f}), TP={m_routed_cal['tp']}, PASS={is_constrained}")

    # Save results to json
    exp3b_summary = {
        "linear_top5": linear_results[:5],
        "constrained_linear_top5": constrained_linear[:5],
        "cv_multiplier_results": cv_multiplier_results,
        "routed_raw": m_routed_raw,
        "routed_calibrated": m_routed_cal,
    }
    with open(Path(__file__).resolve().parent / "experiment_3b_summary.json", "w", encoding="utf-8") as f:
        json.dump(exp3b_summary, f, indent=2, ensure_ascii=False)
        
    gc.collect()
    check_ram("exp3b_inner_tuning_end", expected_peak_mb=120.0)
    print("\nExperiment 3B finished and saved to experiment_3b_summary.json!")

if __name__ == "__main__":
    main()
