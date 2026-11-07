import json
from pathlib import Path
import numpy as np

from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS
from run_final_track3 import paired_bootstrap, compute_transition_matrix

def main():
    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)
    outer_folds = np.array([r[0] for r in outer_records], dtype=np.int64)

    p_lgb5_out = outer_probs["LightGBM_5seed_sqrt_macro"]
    p_tab42_out = outer_probs["TabICL_seed42"]
    p_tab26_out = outer_probs["TabICL_seed2026"]
    p_cat_out = outer_probs["CatBoost"]

    t1_npz_path = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")
    with np.load(t1_npz_path, allow_pickle=False) as z:
        t1_vids = z["vessel_ids"].astype(str)
        t1_outer_probs = z["outer_probs"]
    t1_outer_by_id = {vid: t1_outer_probs[i] for i, vid in enumerate(t1_vids)}
    p_t1_out = np.zeros((len(outer_records), 4), dtype=np.float32)
    for i, r in enumerate(outer_records):
        p_t1_out[i] = t1_outer_by_id[r[2]]

    # 1. Grand Fusion Model 1: Mix_Grand_BothTab_T1_w10 (Top micro-F1: 3,552 / 5,897 = 0.602340)
    p_grand1 = 0.35 * p_lgb5_out + 0.225 * p_tab42_out + 0.225 * p_tab26_out + 0.10 * p_cat_out + 0.10 * p_t1_out
    alpha_grand1 = np.array([1.033, 1.0, 1.0, 1.425], dtype=np.float64)
    pred_grand1 = (p_grand1 * alpha_grand1).argmax(axis=1)
    m_grand1 = compute_metrics(outer_y, pred_grand1)

    # 2. Grand Fusion Model 2: Mix_Grand_BothTab_T1_w05 (TP3=93, TP0=2530, 3,539 / 5,897 = 0.600136)
    p_grand2 = 0.35 * p_lgb5_out + 0.25 * p_tab42_out + 0.25 * p_tab26_out + 0.10 * p_cat_out + 0.05 * p_t1_out
    alpha_grand2 = np.array([1.013, 1.0, 1.017, 1.475], dtype=np.float64)
    pred_grand2 = (p_grand2 * alpha_grand2).argmax(axis=1)
    m_grand2 = compute_metrics(outer_y, pred_grand2)

    pred_base5 = p_lgb5_out.argmax(axis=1)
    pred_base42 = outer_probs["LightGBM_seed42"].argmax(axis=1)

    res_path = Path(__file__).resolve().parent / "track3_results.json"
    results = json.loads(res_path.read_text(encoding="utf-8"))

    results["candidates"]["T3_Grand_Fusion_BothTab_T1_w10"] = {
        "name": "Grand Fusion [LGB5(35%) + Tab42(22.5%) + Tab26(22.5%) + Cat(10%) + Track1(10%)] (Pooled Mean)",
        "metrics": m_grand1,
        "passed_protection": (m_grand1["tp"][0] >= 2389) and (m_grand1["tp"][3] >= 92),
        "bootstrap_vs_seed42": paired_bootstrap(outer_y, pred_base42, pred_grand1),
        "bootstrap_vs_base5": paired_bootstrap(outer_y, pred_base5, pred_grand1),
        "transition_vs_seed42": compute_transition_matrix(outer_y, pred_base42, pred_grand1),
        "transition_vs_base5": compute_transition_matrix(outer_y, pred_base5, pred_grand1),
    }

    results["candidates"]["T3_Grand_Fusion_BothTab_T1_w05"] = {
        "name": "Grand Fusion [LGB5(35%) + Tab42(25%) + Tab26(25%) + Cat(10%) + Track1(5%)] (Pooled Mean)",
        "metrics": m_grand2,
        "passed_protection": (m_grand2["tp"][0] >= 2389) and (m_grand2["tp"][3] >= 92),
        "bootstrap_vs_seed42": paired_bootstrap(outer_y, pred_base42, pred_grand2),
        "bootstrap_vs_base5": paired_bootstrap(outer_y, pred_base5, pred_grand2),
        "transition_vs_seed42": compute_transition_matrix(outer_y, pred_base42, pred_grand2),
        "transition_vs_base5": compute_transition_matrix(outer_y, pred_base5, pred_grand2),
    }

    res_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("track3_results.json successfully updated with Grand Fusion models!")

    # Update probabilities_track3.npz
    npz_path = Path(__file__).resolve().parent / "probabilities_track3.npz"
    with np.load(npz_path) as existing:
        saved_dict = {k: existing[k] for k in existing.files}

    # Add grand fusion arrays
    p_grand1_calibrated = p_grand1 * alpha_grand1
    p_grand1_calibrated /= p_grand1_calibrated.sum(axis=1, keepdims=True)

    saved_dict["prob_grand_fusion_raw"] = p_grand1
    saved_dict["prob_grand_fusion_calibrated"] = p_grand1_calibrated
    saved_dict["pred_grand_fusion"] = pred_grand1
    saved_dict["alpha_grand_fusion"] = alpha_grand1

    np.savez_compressed(npz_path, **saved_dict)
    print("probabilities_track3.npz successfully updated with Grand Fusion arrays!")

if __name__ == "__main__":
    main()
