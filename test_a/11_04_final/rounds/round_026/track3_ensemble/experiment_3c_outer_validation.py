import csv
import gc
import json
import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from resource_guard import check_ram
from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS

def paired_bootstrap_ci(y: np.ndarray, base_pred: np.ndarray, cand_pred: np.ndarray, 
                        reps: int = 2000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = len(y)
    
    base_correct = (base_pred == y).astype(np.int8)
    cand_correct = (cand_pred == y).astype(np.int8)
    diff = cand_correct - base_correct
    point_delta = float(diff.mean())
    
    # Chunked bootstrap to keep memory minimal
    chunk_size = 200
    means = np.empty(reps, dtype=np.float64)
    for start in range(0, reps, chunk_size):
        end = min(start + chunk_size, reps)
        batch = end - start
        indices = rng.integers(0, n, size=(batch, n), dtype=np.int32)
        means[start:end] = diff[indices].mean(axis=1)
        
    ci_lower, ci_upper = np.quantile(means, [0.025, 0.975]).tolist()
    return {
        "point_delta_micro_f1": point_delta,
        "ci95_lower": ci_lower,
        "ci95_upper": ci_upper,
        "significant_positive": ci_lower > 0,
        "repetitions": reps,
    }

def main():
    check_ram("exp3c_outer_validation_start", expected_peak_mb=120.0)

    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    outer_folds = np.array([r[0] for r in outer_records], dtype=np.int64)

    # Load outer observed_days from TabICL original_oof_predictions.csv
    tab_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation\seed_42")
    outer_days_map = {}
    with open(tab_dir / "original_oof_predictions.csv", "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            outer_days_map[r["rfid_id"]] = float(r["observed_days"])
    outer_days = np.array([outer_days_map[r[2]] for r in outer_records], dtype=np.float64)

    # 1. Base models probabilities on OUTER
    p_lgb42 = outer_probs["LightGBM_seed42"]
    p_lgb5 = outer_probs["LightGBM_5seed_sqrt_macro"]
    p_cat = outer_probs["CatBoost"]
    p_tab42 = outer_probs["TabICL_seed42"]
    p_tab26 = outer_probs["TabICL_seed2026"]

    # 2. Outer Blends
    blends_outer = {
        "B1_LGB5_TAB42": 0.50 * p_lgb5 + 0.50 * p_tab42,
        "B2_LGB5_CAT_TAB42": 0.45 * p_lgb5 + 0.10 * p_cat + 0.45 * p_tab42,
        "B3_LGB5_CAT_TAB_BOTH": 0.40 * p_lgb5 + 0.10 * p_cat + 0.25 * p_tab42 + 0.25 * p_tab26,
        "B4_LGB42_TAB42": 0.50 * p_lgb42 + 0.50 * p_tab42,
        "B5_LGB42_CAT_TAB42": 0.45 * p_lgb42 + 0.10 * p_cat + 0.45 * p_tab42,
    }

    # Routed blend on OUTER
    p_routed_out = np.zeros_like(p_lgb5)
    mask_short = outer_days <= 30
    mask_mid = (outer_days > 30) & (outer_days <= 90)
    mask_long = outer_days > 90
    p_routed_out[mask_short] = 0.40 * p_lgb5[mask_short] + 0.60 * p_tab42[mask_short]
    p_routed_out[mask_mid] = 0.35 * p_lgb5[mask_mid] + 0.15 * p_cat[mask_mid] + 0.50 * p_tab42[mask_mid]
    p_routed_out[mask_long] = 0.50 * p_lgb5[mask_long] + 0.20 * p_cat[mask_long] + 0.30 * p_tab42[mask_long]
    blends_outer["B6_ROUTED_DAYS"] = p_routed_out

    # 3. Load INNER-tuned hyperparameters from detailed_inner_optimization.json
    inner_opt_path = Path(__file__).resolve().parent / "detailed_inner_optimization.json"
    inner_records_list = json.loads(inner_opt_path.read_text(encoding="utf-8"))
    inner_by_name = {r["name"]: r for r in inner_records_list}

    # Baselines
    pred_base42 = p_lgb42.argmax(axis=1)
    m_base42 = compute_metrics(outer_y, pred_base42)

    pred_base5 = p_lgb5.argmax(axis=1)
    m_base5 = compute_metrics(outer_y, pred_base5)

    print("="*105)
    print("OUTER VALIDATION (N=5,897 vessels) — STRICT INNER-ONLY HYPERPARAMETER APPLICATION")
    print(f"Baseline 1: LightGBM seed42        = {m_base42['correct']}/5897 ({m_base42['micro_f1']:.6f}), TP={m_base42['tp']}")
    print(f"Baseline 2: LightGBM 5-seed sqrt    = {m_base5['correct']}/5897 ({m_base5['micro_f1']:.6f}), TP={m_base5['tp']}")
    print(f"Protection Target: TP0 >= 2389, TP3 >= 92")
    print("="*105)

    header = f"{'Method Description':<48} | {'Correct':<12} | {'micro-F1':<10} | {'macro-F1':<10} | {'TP(0,1,2,3)':<18} | {'PASS':<5} | {'vs Base5':<9}"
    print(header)
    print("-" * len(header))

    outer_results = {
        "baselines": {
            "LightGBM_seed42": m_base42,
            "LightGBM_5seed_sqrt_macro": m_base5,
        },
        "candidates": {}
    }

    # Evaluate all candidate models on OUTER
    for key, p_blend in blends_outer.items():
        # 1. R0: Raw Argmax
        pred_r0 = p_blend.argmax(axis=1)
        m_r0 = compute_metrics(outer_y, pred_r0)
        pass_r0 = (m_r0["tp"][0] >= 2389) and (m_r0["tp"][3] >= 92)
        diff_base5_r0 = m_r0["correct"] - m_base5["correct"]
        label_r0 = f"{key} [R0:Raw Argmax]"
        tp_str = f"{m_r0['tp'][0]},{m_r0['tp'][1]},{m_r0['tp'][2]},{m_r0['tp'][3]}"
        print(f"{label_r0:<48} | {m_r0['correct']:<4}/5897     | {m_r0['micro_f1']:.6f}   | {m_r0['macro_f1']:.6f}   | {tp_str:<18} | {str(pass_r0):<5} | {diff_base5_r0:+4d} 척")

        # 2. R1: Fold-Local Prior Multipliers (strictly from INNER)
        # Search inner record
        inner_rec_r1 = [r for r in inner_records_list if key in r["name"] and "R1" in r["name"]][0]
        fold_alphas = [np.array(a, dtype=np.float64) for a in inner_rec_r1["fold_alphas"]]
        pred_r1_local = np.zeros(len(outer_y), dtype=np.int64)
        for f in FOLDS:
            mask_f = (outer_folds == f)
            pred_r1_local[mask_f] = (p_blend[mask_f] * fold_alphas[f]).argmax(axis=1)

        m_r1_local = compute_metrics(outer_y, pred_r1_local)
        pass_r1_local = (m_r1_local["tp"][0] >= 2389) and (m_r1_local["tp"][3] >= 92)
        diff_base5_r1_local = m_r1_local["correct"] - m_base5["correct"]
        label_r1_local = f"{key} [R1:Fold-Local Multipliers]"
        tp_str = f"{m_r1_local['tp'][0]},{m_r1_local['tp'][1]},{m_r1_local['tp'][2]},{m_r1_local['tp'][3]}"
        print(f"{label_r1_local:<48} | {m_r1_local['correct']:<4}/5897     | {m_r1_local['micro_f1']:.6f}   | {m_r1_local['macro_f1']:.6f}   | {tp_str:<18} | {str(pass_r1_local):<5} | {diff_base5_r1_local:+4d} 척")

        # 3. R1: Pooled Mean Prior Multipliers (strictly mean of INNER fold alphas)
        mean_alpha = np.mean(fold_alphas, axis=0)
        pred_r1_pooled = (p_blend * mean_alpha).argmax(axis=1)
        m_r1_pooled = compute_metrics(outer_y, pred_r1_pooled)
        pass_r1_pooled = (m_r1_pooled["tp"][0] >= 2389) and (m_r1_pooled["tp"][3] >= 92)
        diff_base5_r1_pooled = m_r1_pooled["correct"] - m_base5["correct"]
        label_r1_pooled = f"{key} [R1:Pooled Mean Multiplier]"
        tp_str = f"{m_r1_pooled['tp'][0]},{m_r1_pooled['tp'][1]},{m_r1_pooled['tp'][2]},{m_r1_pooled['tp'][3]}"
        print(f"{label_r1_pooled:<48} | {m_r1_pooled['correct']:<4}/5897     | {m_r1_pooled['micro_f1']:.6f}   | {m_r1_pooled['macro_f1']:.6f}   | {tp_str:<18} | {diff_base5_r1_pooled:+4d} 척")

        # 4. R2: Gate + Multiplier (strictly from INNER)
        inner_rec_r2 = [r for r in inner_records_list if key in r["name"] and "R2" in r["name"]][0]
        fold_params_r2 = inner_rec_r2["fold_params"]
        lgb_source = p_lgb42 if "LGB42" in key else p_lgb5
        pred_r2 = np.zeros(len(outer_y), dtype=np.int64)
        for f in FOLDS:
            mask_f = (outer_folds == f)
            a0, a2, tau3 = fold_params_r2[f]
            p_val = p_blend[mask_f] * np.array([a0, 1.0, a2, 1.0])
            pred_f = p_val.argmax(axis=1)
            pred_f[lgb_source[mask_f, 3] >= tau3] = 3
            pred_r2[mask_f] = pred_f

        m_r2 = compute_metrics(outer_y, pred_r2)
        pass_r2 = (m_r2["tp"][0] >= 2389) and (m_r2["tp"][3] >= 92)
        diff_base5_r2 = m_r2["correct"] - m_base5["correct"]
        label_r2 = f"{key} [R2:Gate+Multiplier]"
        tp_str = f"{m_r2['tp'][0]},{m_r2['tp'][1]},{m_r2['tp'][2]},{m_r2['tp'][3]}"
        print(f"{label_r2:<48} | {m_r2['correct']:<4}/5897     | {m_r2['micro_f1']:.6f}   | {m_r2['macro_f1']:.6f}   | {tp_str:<18} | {str(pass_r2):<5} | {diff_base5_r2:+4d} 척")

        # Store in dict
        for lbl, met, prd, pss in [
            (label_r0, m_r0, pred_r0, pass_r0),
            (label_r1_local, m_r1_local, pred_r1_local, pass_r1_local),
            (label_r1_pooled, m_r1_pooled, pred_r1_pooled, pass_r1_pooled),
            (label_r2, m_r2, pred_r2, pass_r2),
        ]:
            ci_vs_base42 = paired_bootstrap_ci(outer_y, pred_base42, prd)
            ci_vs_base5 = paired_bootstrap_ci(outer_y, pred_base5, prd)
            outer_results["candidates"][lbl] = {
                "metrics": met,
                "passed_protection": pss,
                "net_gain_vs_seed42": met["correct"] - m_base42["correct"],
                "net_gain_vs_base5": met["correct"] - m_base5["correct"],
                "bootstrap_vs_seed42": ci_vs_base42,
                "bootstrap_vs_base5": ci_vs_base5,
            }

    # Save complete results
    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "track3_results.json", "w", encoding="utf-8") as f:
        json.dump(outer_results, f, indent=2, ensure_ascii=False)

    # Save calibrated probability matrix of top protected model
    # Top protected model is B1_LGB5_TAB42 [R1:Fold-Local Multipliers] or B1_LGB5_TAB42 [R1:Pooled Mean Multiplier]
    # Let's save both uncalibrated and calibrated probabilities
    p_b1_outer = blends_outer["B1_LGB5_TAB42"]
    b1_inner_r1 = [r for r in inner_records_list if "B1" in r["name"] and "R1" in r["name"]][0]
    b1_mean_alpha = np.mean([np.array(a) for a in b1_inner_r1["fold_alphas"]], axis=0)
    p_b1_calibrated = p_b1_outer * b1_mean_alpha
    p_b1_calibrated /= p_b1_calibrated.sum(axis=1, keepdims=True)

    np.savez_compressed(
        out_dir / "probabilities_track3.npz",
        outer_ids=np.array([r[2] for r in outer_records]),
        outer_folds=outer_folds,
        outer_y=outer_y,
        probabilities_raw_b1=p_b1_outer,
        probabilities_calibrated_b1=p_b1_calibrated,
        mean_alpha=b1_mean_alpha,
    )
    print("\nSaved track3_results.json and probabilities_track3.npz successfully!")

    gc.collect()
    check_ram("exp3c_outer_validation_end", expected_peak_mb=120.0)

if __name__ == "__main__":
    main()
