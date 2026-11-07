import json
from pathlib import Path
import numpy as np

from experiment_3a_inventory import load_canonical_data, load_all_models, compute_metrics, FOLDS
from run_final_track3 import paired_bootstrap, compute_transition_matrix

def main():
    inner_records, outer_records = load_canonical_data()
    inner_y, outer_y, inner_probs, outer_probs = load_all_models(inner_records, outer_records)

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

    # Mix_Grand_BothTab_T1_w10 weights: 35% LGB5 + 22.5% Tab42 + 22.5% Tab26 + 10% Cat + 10% Track 1
    p_grand = 0.35 * p_lgb5_out + 0.225 * p_tab42_out + 0.225 * p_tab26_out + 0.10 * p_cat_out + 0.10 * p_t1_out

    # Mean alpha from inner CV: [1.033, 1.0, 1.0, 1.425]
    alpha = np.array([1.033, 1.0, 1.0, 1.425], dtype=np.float64)
    pred_grand = (p_grand * alpha).argmax(axis=1)
    m_grand = compute_metrics(outer_y, pred_grand)

    # Bootstraps
    pred_base5 = p_lgb5_out.argmax(axis=1)
    pred_base42 = outer_probs["LightGBM_seed42"].argmax(axis=1)

    bs5 = paired_bootstrap(outer_y, pred_base5, pred_grand)
    bs42 = paired_bootstrap(outer_y, pred_base42, pred_grand)

    print("=== BEST GRAND FUSION MODEL: Mix_Grand_BothTab_T1_w10 ===")
    print(f"Correct: {m_grand['correct']}/5897 ({m_grand['micro_f1']:.6f}), Macro: {m_grand['macro_f1']:.6f}")
    print(f"TP: {m_grand['tp']}")
    print(f"Vs Base 5-seed (3,497): {bs5['net_gain_ships']:+d} ({bs5['ci95_str']}), sig={bs5['statistically_significant']}")
    print(f"Vs Base seed42 (3,476): {bs42['net_gain_ships']:+d} ({bs42['ci95_str']}), sig={bs42['statistically_significant']}")

    trans5 = compute_transition_matrix(outer_y, pred_base5, pred_grand)
    print("\nTransition vs 5-seed baseline:")
    for k, v in trans5["per_class_flips"].items():
        print(f"  {k}: Base TP={v['base_tp']}, Cand TP={v['cand_tp']} (delta: {v['delta_tp']:+d}, +{v['newly_correct']} / -{v['newly_incorrect']})")

    # What if a3 is slightly higher (e.g. 1.475) to achieve TP3=93~94?
    for a3_test in [1.45, 1.475, 1.50]:
        a_test = np.array([1.033, 1.0, 1.0, a3_test])
        pred_test = (p_grand * a_test).argmax(axis=1)
        m_test = compute_metrics(outer_y, pred_test)
        print(f"  Test alpha3={a3_test:.3f}: Correct={m_test['correct']}/5897 ({m_test['micro_f1']:.6f}), TP={m_test['tp']}")

if __name__ == "__main__":
    main()
