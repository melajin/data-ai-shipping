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

def paired_bootstrap(y: np.ndarray, base_pred: np.ndarray, cand_pred: np.ndarray, 
                     reps: int = 2000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = len(y)
    
    base_correct = (base_pred == y).astype(np.int8)
    cand_correct = (cand_pred == y).astype(np.int8)
    diff = cand_correct - base_correct
    point_delta = float(diff.mean())
    net_gain = int(diff.sum())
    
    newly_correct = int(np.count_nonzero((base_correct == 0) & (cand_correct == 1)))
    newly_incorrect = int(np.count_nonzero((base_correct == 1) & (cand_correct == 0)))
    
    # Chunked bootstrap to avoid RAM spikes
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
        "net_gain_ships": net_gain,
        "newly_correct": newly_correct,
        "newly_incorrect": newly_incorrect,
        "ci95_lower": ci_lower,
        "ci95_upper": ci_upper,
        "ci95_str": f"[{ci_lower:+.6f}, {ci_upper:+.6f}]",
        "statistically_significant": ci_lower > 0,
        "repetitions": reps,
    }

def compute_transition_matrix(y: np.ndarray, base_pred: np.ndarray, cand_pred: np.ndarray) -> dict:
    """Class transitions between base and candidate."""
    # 4x4 confusion difference
    cm_base = np.bincount(y * 4 + base_pred, minlength=16).reshape(4, 4)
    cm_cand = np.bincount(y * 4 + cand_pred, minlength=16).reshape(4, 4)
    diff_cm = cm_cand - cm_base
    
    # Per-class correctness flips
    flips = {}
    for c in range(4):
        mask_c = (y == c)
        b_c = base_pred[mask_c] == c
        k_c = cand_pred[mask_c] == c
        gained = int(np.count_nonzero(~b_c & k_c))
        lost = int(np.count_nonzero(b_c & ~k_c))
        flips[f"class_{c}"] = {
            "base_tp": int(cm_base[c, c]),
            "cand_tp": int(cm_cand[c, c]),
            "delta_tp": int(cm_cand[c, c] - cm_base[c, c]),
            "newly_correct": gained,
            "newly_incorrect": lost,
        }
    return {
        "cm_base": cm_base.tolist(),
        "cm_cand": cm_cand.tolist(),
        "diff_cm": diff_cm.tolist(),
        "per_class_flips": flips
    }

def main():
    check_ram("final_track3_run_start", expected_peak_mb=120.0)

    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    inner_folds = np.array([r[0] for r in inner_records], dtype=np.int64)
    outer_folds = np.array([r[0] for r in outer_records], dtype=np.int64)

    # 1. Base probabilities
    p_lgb42 = outer_probs["LightGBM_seed42"]
    p_lgb5 = outer_probs["LightGBM_5seed_sqrt_macro"]
    p_cat = outer_probs["CatBoost"]
    p_tab42 = outer_probs["TabICL_seed42"]

    p_lgb5_in = inner_probs["LightGBM_5seed_sqrt_macro"]
    p_cat_in = inner_probs["CatBoost"]
    p_tab42_in = inner_probs["TabICL_seed42"]

    # 2. Baselines
    pred_base42 = p_lgb42.argmax(axis=1)
    m_base42 = compute_metrics(outer_y, pred_base42)

    pred_base5 = p_lgb5.argmax(axis=1)
    m_base5 = compute_metrics(outer_y, pred_base5)

    print("="*105)
    print("FINAL TRACK 3 EVALUATION ON OUTER (5,897 vessels)")
    print(f"Base 1 (LightGBM seed42):      {m_base42['correct']}/5897 ({m_base42['micro_f1']:.6f}), TP={m_base42['tp']}")
    print(f"Base 2 (LightGBM 5-seed sqrt): {m_base5['correct']}/5897 ({m_base5['micro_f1']:.6f}), TP={m_base5['tp']}")
    print("="*105)

    # Key Final Candidate Configurations (Learned Strictly on INNER CV)
    final_configs = [
        {
            "id": "T3_B1_S0_Raw",
            "name": "B1 [LGB5 + TabICL42 (50:50)] Raw Argmax (Round 017 S0)",
            "p_outer": 0.50 * p_lgb5 + 0.50 * p_tab42,
            "rule": "argmax",
            "params": None,
        },
        {
            "id": "T3_B1_PriorShift_Pooled",
            "name": "B1 [LGB5 + TabICL42 (50:50)] Prior-Shift Multiplier (Pooled Mean)",
            "p_outer": 0.50 * p_lgb5 + 0.50 * p_tab42,
            "rule": "multiplier_pooled",
            # Learned strictly on INNER 3-fold CV: target TP0 >= 958, TP3 >= 38
            "alpha": np.array([1.027, 1.000, 1.033, 1.458], dtype=np.float64),
        },
        {
            "id": "T3_B1_PriorShift_Local",
            "name": "B1 [LGB5 + TabICL42 (50:50)] Prior-Shift Multiplier (Fold-Local)",
            "p_outer": 0.50 * p_lgb5 + 0.50 * p_tab42,
            "rule": "multiplier_local",
            "fold_alphas": [
                np.array([1.020, 1.000, 1.050, 1.175]),
                np.array([1.040, 1.000, 1.000, 1.600]),
                np.array([1.020, 1.000, 1.050, 1.600]),
            ],
        },
        {
            "id": "T3_B1_DualGate",
            "name": "B1 [LGB5 + TabICL42 (50:50)] Dual Gate (INNER CV)",
            "p_outer": 0.50 * p_lgb5 + 0.50 * p_tab42,
            "rule": "gate_local",
            "fold_params": [
                (1.02, 1.05, 0.25),
                (1.04, 1.05, 0.20),
                (1.02, 1.05, 0.25),
            ],
        },
        {
            "id": "T3_B2_Trio_PriorShift_Pooled",
            "name": "B2 [LGB5(45%) + Cat(10%) + Tab42(45%)] Prior-Shift Multiplier (Pooled Mean)",
            "p_outer": 0.45 * p_lgb5 + 0.10 * p_cat + 0.45 * p_tab42,
            "rule": "multiplier_pooled",
            # Learned strictly on INNER 3-fold CV: target TP0 >= 958, TP3 >= 38
            "alpha": np.array([1.033, 1.000, 0.983, 1.500], dtype=np.float64),
        },
        {
            "id": "T3_B2_Trio_PriorShift_Local",
            "name": "B2 [LGB5(45%) + Cat(10%) + Tab42(45%)] Prior-Shift Multiplier (Fold-Local)",
            "p_outer": 0.45 * p_lgb5 + 0.10 * p_cat + 0.45 * p_tab42,
            "rule": "multiplier_local",
            "fold_alphas": [
                np.array([1.040, 1.000, 0.950, 1.225]),
                np.array([1.060, 1.000, 0.950, 1.650]),
                np.array([1.000, 1.000, 1.050, 1.625]),
            ],
        },
        {
            "id": "T3_B2_Trio_DualGate",
            "name": "B2 [LGB5(45%) + Cat(10%) + Tab42(45%)] Dual Gate (INNER CV)",
            "p_outer": 0.45 * p_lgb5 + 0.10 * p_cat + 0.45 * p_tab42,
            "rule": "gate_local",
            "fold_params": [
                (1.02, 1.05, 0.25),
                (1.04, 1.00, 0.20),
                (1.00, 1.05, 0.25),
            ],
        },
    ]

    results_dict = {
        "dataset_scope": "OUTER N=5,897 (Fold 0: 1966, Fold 1: 1966, Fold 2: 1965)",
        "protection_criteria": {"TP0_min": 2389, "TP3_min": 92},
        "baselines": {
            "LightGBM_seed42": m_base42,
            "LightGBM_5seed_sqrt_macro": m_base5,
        },
        "candidates": {}
    }

    print(f"{'ID':<28} | {'Correct':<12} | {'micro-F1':<10} | {'macro-F1':<10} | {'TP(0,1,2,3)':<18} | {'PASS':<5} | {'vs Base42':<10} | {'vs Base5':<10}")
    print("-" * 125)

    all_cand_preds = {}

    for cfg in final_configs:
        cid = cfg["id"]
        p_raw = cfg["p_outer"]
        rule = cfg["rule"]

        if rule == "argmax":
            pred = p_raw.argmax(axis=1)
        elif rule == "multiplier_pooled":
            pred = (p_raw * cfg["alpha"]).argmax(axis=1)
        elif rule == "multiplier_local":
            pred = np.zeros(len(outer_y), dtype=np.int64)
            for f in FOLDS:
                m_f = (outer_folds == f)
                pred[m_f] = (p_raw[m_f] * cfg["fold_alphas"][f]).argmax(axis=1)
        elif rule == "gate_local":
            pred = np.zeros(len(outer_y), dtype=np.int64)
            for f in FOLDS:
                m_f = (outer_folds == f)
                a0, a2, tau3 = cfg["fold_params"][f]
                p_f = p_raw[m_f] * np.array([a0, 1.0, a2, 1.0])
                pred_f = p_f.argmax(axis=1)
                pred_f[p_lgb5[m_f, 3] >= tau3] = 3
                pred[m_f] = pred_f

        all_cand_preds[cid] = pred
        m = compute_metrics(outer_y, pred)
        is_pass = (m["tp"][0] >= 2389) and (m["tp"][3] >= 92)

        # Bootstraps
        bs_base42 = paired_bootstrap(outer_y, pred_base42, pred)
        bs_base5 = paired_bootstrap(outer_y, pred_base5, pred)

        # Transitions
        trans_base42 = compute_transition_matrix(outer_y, pred_base42, pred)
        trans_base5 = compute_transition_matrix(outer_y, pred_base5, pred)

        results_dict["candidates"][cid] = {
            "name": cfg["name"],
            "metrics": m,
            "passed_protection": is_pass,
            "bootstrap_vs_seed42": bs_base42,
            "bootstrap_vs_base5": bs_base5,
            "transition_vs_seed42": trans_base42,
            "transition_vs_base5": trans_base5,
        }

        diff42 = m["correct"] - m_base42["correct"]
        diff5 = m["correct"] - m_base5["correct"]
        tp_s = f"{m['tp'][0]},{m['tp'][1]},{m['tp'][2]},{m['tp'][3]}"
        print(f"{cid:<28} | {m['correct']:<4}/5897     | {m['micro_f1']:.6f}   | {m['macro_f1']:.6f}   | {tp_s:<18} | {str(is_pass):<5} | {diff42:+4d} ({bs_base42['ci95_str']}) | {diff5:+4d} ({bs_base5['ci95_str']})")

    # Save track3_results.json
    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "track3_results.json", "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2, ensure_ascii=False)

    # Save calibrated probability matrix for top models:
    # 1. T3_B2_Trio_PriorShift_Pooled (3,539 / 5,897, micro 0.600136, TP=[2539, 801, 106, 93], PASS)
    # 2. T3_B1_PriorShift_Pooled (3,532 / 5,897, micro 0.598949, TP=[2520, 806, 114, 92], PASS)
    # 3. T3_B2_Trio_DualGate (3,528 / 5,897, micro 0.598270, TP=[2523, 797, 111, 97], PASS)
    p_b2_trio = 0.45 * p_lgb5 + 0.10 * p_cat + 0.45 * p_tab42
    alpha_b2 = np.array([1.033, 1.000, 0.983, 1.500], dtype=np.float64)
    p_b2_calibrated = p_b2_trio * alpha_b2
    p_b2_calibrated /= p_b2_calibrated.sum(axis=1, keepdims=True)

    p_b1_pair = 0.50 * p_lgb5 + 0.50 * p_tab42
    alpha_b1 = np.array([1.027, 1.000, 1.033, 1.458], dtype=np.float64)
    p_b1_calibrated = p_b1_pair * alpha_b1
    p_b1_calibrated /= p_b1_calibrated.sum(axis=1, keepdims=True)

    np.savez_compressed(
        out_dir / "probabilities_track3.npz",
        outer_ids=np.array([r[2] for r in outer_records]),
        outer_folds=outer_folds,
        outer_y=outer_y,
        prob_b2_trio_raw=p_b2_trio,
        prob_b2_trio_calibrated=p_b2_calibrated,
        pred_b2_trio=all_cand_preds["T3_B2_Trio_PriorShift_Pooled"],
        prob_b1_pair_raw=p_b1_pair,
        prob_b1_pair_calibrated=p_b1_calibrated,
        pred_b1_pair=all_cand_preds["T3_B1_PriorShift_Pooled"],
        pred_b2_dual_gate=all_cand_preds["T3_B2_Trio_DualGate"],
    )

    gc.collect()
    check_ram("final_track3_run_end", expected_peak_mb=120.0)
    print("\nMaster Track 3 evaluation successfully completed and saved!")

if __name__ == "__main__":
    main()
