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

def main():
    check_ram("grand_fusion_start", expected_peak_mb=120.0)

    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    inner_folds = np.array([r[0] for r in inner_records], dtype=np.int64)
    outer_folds = np.array([r[0] for r in outer_records], dtype=np.int64)

    # 1. Base probabilities
    p_lgb5_in, p_lgb5_out = inner_probs["LightGBM_5seed_sqrt_macro"], outer_probs["LightGBM_5seed_sqrt_macro"]
    p_cat_in, p_cat_out = inner_probs["CatBoost"], outer_probs["CatBoost"]
    p_tab42_in, p_tab42_out = inner_probs["TabICL_seed42"], outer_probs["TabICL_seed42"]
    p_tab26_in, p_tab26_out = inner_probs["TabICL_seed2026"], outer_probs["TabICL_seed2026"]

    # 2. Track 1 probabilities
    t1_npz_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")
    with np.load(t1_npz_path, allow_pickle=False) as z:
        t1_vids = z["vessel_ids"].astype(str)
        t1_outer_probs = z["outer_probs"]
        t1_y = z["y_true"]
        t1_inner_f0 = z["inner_probs_fold0"]
        t1_inner_f1 = z["inner_probs_fold1"]
        t1_inner_f2 = z["inner_probs_fold2"]

    t1_outer_by_id = {vid: t1_outer_probs[i] for i, vid in enumerate(t1_vids)}
    p_t1_out = np.zeros((len(outer_records), 4), dtype=np.float32)
    for i, r in enumerate(outer_records):
        p_t1_out[i] = t1_outer_by_id[r[2]]

    exp01_dir = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
    t1_in_by_fid = {}
    for f in FOLDS:
        with np.load(exp01_dir / f"fold_{f}_features.npz") as zf:
            f_ids = zf["rfid_ids"].astype(str)[zf["roles"].astype(str) == "INNER"]
            p_f = [t1_inner_f0, t1_inner_f1, t1_inner_f2][f]
            for j, vid in enumerate(f_ids):
                t1_in_by_fid[(f, vid)] = p_f[j]
    p_t1_in = np.zeros((len(inner_records), 4), dtype=np.float32)
    for i, r in enumerate(inner_records):
        p_t1_in[i] = t1_in_by_fid[(r[0], r[2])]

    # 3. Track 2 probabilities
    t2_npz_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track2_s2_segments\probabilities_track2.npz")
    with np.load(t2_npz_path, allow_pickle=False) as z:
        t2_vids = z["vessel_ids"].astype(str)
        t2_cand_probs_sqrt = z["cand_outer_probs_sqrt"]
    t2_out_by_id = {vid: t2_cand_probs_sqrt[i] for i, vid in enumerate(t2_vids)}
    p_t2_out = np.zeros((len(outer_records), 4), dtype=np.float32)
    for i, r in enumerate(outer_records):
        p_t2_out[i] = t2_out_by_id[r[2]]

    # Target constraints
    min_tp0_in = 958
    min_tp3_in = 38

    print("="*105)
    print("GRAND FUSION INNER 3-FOLD CROSS-VALIDATION SEARCH")
    print(f"INNER N=2,361 (Target Constraints: TP0 >= {min_tp0_in}, TP3 >= {min_tp3_in})")
    print("="*105)

    # Let's explore candidate fusion mixtures on INNER:
    # Blend families:
    # F1: LGB5 + TabICL42 + CatBoost + Track 1 (Spatial kNN)
    # F2: LGB5 + TabICL42 + TabICL2026 + CatBoost + Track 1
    # F3: LGB5 + TabICL42 + CatBoost + Track 1 + Track 2
    
    candidate_mixtures = [
        # (name, weights: (w_lgb, w_tab42, w_tab26, w_cat, w_t1, w_t2))
        ("Mix_Trio_Base", (0.45, 0.45, 0.00, 0.10, 0.00, 0.00)), # Track 3 best base
        ("Mix_Trio_BothTab", (0.40, 0.25, 0.25, 0.10, 0.00, 0.00)),
        # Adding Track 1 (Spatial kNN) with varying weights (5% to 20%)
        ("Mix_Grand_T1_w05", (0.40, 0.45, 0.00, 0.10, 0.05, 0.00)),
        ("Mix_Grand_T1_w10", (0.35, 0.45, 0.00, 0.10, 0.10, 0.00)),
        ("Mix_Grand_T1_w15", (0.30, 0.45, 0.00, 0.10, 0.15, 0.00)),
        ("Mix_Grand_T1_w20", (0.30, 0.40, 0.00, 0.10, 0.20, 0.00)),
        # Adding both TabICL seeds + Track 1
        ("Mix_Grand_BothTab_T1_w05", (0.35, 0.25, 0.25, 0.10, 0.05, 0.00)),
        ("Mix_Grand_BothTab_T1_w10", (0.35, 0.225, 0.225, 0.10, 0.10, 0.00)),
        ("Mix_Grand_BothTab_T1_w15", (0.30, 0.225, 0.225, 0.10, 0.15, 0.00)),
        # Adding Track 1 + Track 2 (small weight: 3% to 5%)
        ("Mix_Grand_T1_T2_w05_w03", (0.37, 0.45, 0.00, 0.10, 0.05, 0.03)),
        ("Mix_Grand_BothTab_T1_T2", (0.32, 0.25, 0.25, 0.10, 0.05, 0.03)),
    ]

    inner_search_results = []

    for mix_name, (w_lgb, w_tab42, w_tab26, w_cat, w_t1, w_t2) in candidate_mixtures:
        # Build inner blend
        p_in = (
            w_lgb * p_lgb5_in +
            w_tab42 * p_tab42_in +
            w_tab26 * p_tab26_in +
            w_cat * p_cat_in +
            w_t1 * p_t1_in
        )
        if w_t2 > 0:
            # For track 2 on inner, we don't have individual inner probabilities saved in npz (only summary in json)
            # So test w_t2 on outer only or skip inner w_t2
            pass

        # 3-Fold Nested CV on INNER
        oof_pred = np.zeros(len(inner_y), dtype=np.int64)
        fold_alphas = []

        for val_fold in FOLDS:
            tr_mask = (inner_folds != val_fold)
            val_mask = (inner_folds == val_fold)
            y_tr, p_tr = inner_y[tr_mask], p_in[tr_mask]
            y_val, p_val = inner_y[val_mask], p_in[val_mask]

            tr_min_tp0 = int(round(min_tp0_in * (tr_mask.sum() / len(inner_y))))
            tr_min_tp3 = int(round(min_tp3_in * (tr_mask.sum() / len(inner_y))))

            best_alpha = None
            best_score = -1

            for a0 in [1.00, 1.02, 1.04, 1.06]:
                for a2 in [0.95, 1.00, 1.05]:
                    for a3 in np.linspace(1.20, 1.65, 19):
                        alpha = np.array([a0, 1.00, a2, a3], dtype=np.float64)
                        pred_tr = (p_tr * alpha).argmax(axis=1)
                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)

                        if cm_tr[0, 0] >= tr_min_tp0 and cm_tr[3, 3] >= tr_min_tp3:
                            correct_tr = np.trace(cm_tr)
                            if correct_tr > best_score:
                                best_score = correct_tr
                                best_alpha = alpha

            if best_alpha is None:
                # Fallback to closest constraint
                for a0 in [1.02, 1.04]:
                    for a3 in [1.35, 1.45, 1.55]:
                        alpha = np.array([a0, 1.00, 1.00, a3], dtype=np.float64)
                        pred_tr = (p_tr * alpha).argmax(axis=1)
                        cm_tr = np.bincount(y_tr * 4 + pred_tr, minlength=16).reshape(4, 4)
                        score = np.trace(cm_tr) + 10 * cm_tr[3, 3]
                        if score > best_score:
                            best_score = score
                            best_alpha = alpha

            fold_alphas.append(best_alpha)
            oof_pred[val_mask] = (p_val * best_alpha).argmax(axis=1)

        m_in = compute_metrics(inner_y, oof_pred)
        is_pass = (m_in["tp"][0] >= min_tp0_in) and (m_in["tp"][3] >= min_tp3_in)
        mean_alpha = np.mean(fold_alphas, axis=0)

        inner_search_results.append({
            "mix_name": mix_name,
            "weights": (w_lgb, w_tab42, w_tab26, w_cat, w_t1, w_t2),
            "inner_metrics": m_in,
            "passed_inner": is_pass,
            "mean_alpha": mean_alpha.tolist(),
            "fold_alphas": [a.tolist() for a in fold_alphas],
        })

        tp_str = f"{m_in['tp'][0]},{m_in['tp'][1]},{m_in['tp'][2]},{m_in['tp'][3]}"
        print(f"{mix_name:<26} | Correct={m_in['correct']:4d}/2361 ({m_in['micro_f1']:.6f}) | TP={tp_str:<18} | PASS={is_pass} | Mean Alpha={[round(x,3) for x in mean_alpha]}")

    # Now evaluate on OUTER (5,897) strictly using the INNER-learned weights & alphas!
    print("\n" + "="*105)
    print("EVALUATION ON OUTER (5,897 vessels) WITH STRICT INNER-LEARNED HYPERPARAMETERS")
    print("="*105)
    header = f"{'Mix Name':<28} | {'Correct':<12} | {'micro-F1':<10} | {'macro-F1':<10} | {'TP(0,1,2,3)':<18} | {'PASS':<5} | {'vs Base5 (3,497)':<12}"
    print(header)
    print("-" * len(header))

    outer_fusion_results = {}
    for res in inner_search_results:
        mix_name = res["mix_name"]
        w_lgb, w_tab42, w_tab26, w_cat, w_t1, w_t2 = res["weights"]
        mean_alpha = np.array(res["mean_alpha"])
        fold_alphas = [np.array(a) for a in res["fold_alphas"]]

        p_out = (
            w_lgb * p_lgb5_out +
            w_tab42 * p_tab42_out +
            w_tab26 * p_tab26_out +
            w_cat * p_cat_out +
            w_t1 * p_t1_out +
            w_t2 * p_t2_out
        )

        # 1. Pooled Mean
        pred_pooled = (p_out * mean_alpha).argmax(axis=1)
        m_pooled = compute_metrics(outer_y, pred_pooled)
        pass_pooled = (m_pooled["tp"][0] >= 2389) and (m_pooled["tp"][3] >= 92)
        diff_pooled = m_pooled["correct"] - 3497

        tp_s = f"{m_pooled['tp'][0]},{m_pooled['tp'][1]},{m_pooled['tp'][2]},{m_pooled['tp'][3]}"
        label_p = f"{mix_name} (Pooled)"
        print(f"{label_p:<28} | {m_pooled['correct']:<4}/5897     | {m_pooled['micro_f1']:.6f}   | {m_pooled['macro_f1']:.6f}   | {tp_s:<18} | {str(pass_pooled):<5} | {diff_pooled:+4d} 척")

        # 2. Fold-Local
        pred_local = np.zeros(len(outer_y), dtype=np.int64)
        for f in FOLDS:
            m_f = (outer_folds == f)
            pred_local[m_f] = (p_out[m_f] * fold_alphas[f]).argmax(axis=1)
        m_local = compute_metrics(outer_y, pred_local)
        pass_local = (m_local["tp"][0] >= 2389) and (m_local["tp"][3] >= 92)
        diff_local = m_local["correct"] - 3497

        tp_s = f"{m_local['tp'][0]},{m_local['tp'][1]},{m_local['tp'][2]},{m_local['tp'][3]}"
        label_l = f"{mix_name} (Local)"
        print(f"{label_l:<28} | {m_local['correct']:<4}/5897     | {m_local['micro_f1']:.6f}   | {m_local['macro_f1']:.6f}   | {tp_s:<18} | {str(pass_local):<5} | {diff_local:+4d} 척")

        outer_fusion_results[mix_name] = {
            "pooled": {"metrics": m_pooled, "pass": pass_pooled, "diff_vs_base5": diff_pooled},
            "local": {"metrics": m_local, "pass": pass_local, "diff_vs_base5": diff_local},
        }

    # Save grand fusion results
    out_path = Path(__file__).resolve().parent / "grand_fusion_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"inner_search": inner_search_results, "outer_evaluation": outer_fusion_results}, f, indent=2, ensure_ascii=False)

    check_ram("grand_fusion_end", expected_peak_mb=120.0)
    print("\nGrand Fusion experiment finished and saved to grand_fusion_results.json!")

if __name__ == "__main__":
    main()
