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

def main():
    check_ram("verify_alignment_start", expected_peak_mb=80.0)

    # 1. Round 002 Baseline LightGBM & CatBoost
    r2_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
    
    # Check fold 0, 1, 2
    for fold in (0, 1, 2):
        lgb_es = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_inner_es.npz")
        lgb_sel = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_inner_select.npz")
        lgb_out = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_outer.npz")

        cat_es = np.load(r2_dir / f"fold_{fold}_candidate_catboost_inner_es.npz")
        cat_sel = np.load(r2_dir / f"fold_{fold}_candidate_catboost_inner_select.npz")
        cat_out = np.load(r2_dir / f"fold_{fold}_candidate_catboost_outer.npz")

        # Verify ID alignment between LGB and CAT
        assert list(lgb_es["ids"]) == list(cat_es["ids"]), f"fold {fold} ES IDs mismatch"
        assert list(lgb_sel["ids"]) == list(cat_sel["ids"]), f"fold {fold} SELECT IDs mismatch"
        assert list(lgb_out["ids"]) == list(cat_out["ids"]), f"fold {fold} OUTER IDs mismatch"

        assert np.array_equal(lgb_es["y_true"], cat_es["y_true"]), f"fold {fold} ES y mismatch"
        assert np.array_equal(lgb_sel["y_true"], cat_sel["y_true"]), f"fold {fold} SELECT y mismatch"
        assert np.array_equal(lgb_out["y_true"], cat_out["y_true"]), f"fold {fold} OUTER y mismatch"

        print(f"Fold {fold}: ES={len(lgb_es['ids'])}, SELECT={len(lgb_sel['ids'])}, OUTER={len(lgb_out['ids'])} perfectly aligned between LGB and CAT.")

    # 2. Check TabICLv2 INNER & OUTER
    tab_dir = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation")
    
    # TabICL OOF (5,897)
    tab_oof_path = tab_dir / "seed_42" / "original_oof_predictions.csv"
    with open(tab_oof_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        tab_oof_rows = list(reader)
    tab_oof_by_id = {r["rfid_id"]: (int(r["y_true"]), int(r["fold"]), [float(r[f"p{c}"]) for c in range(4)], float(r["observed_days"])) for r in tab_oof_rows}
    print(f"TabICL seed_42 OOF rows: {len(tab_oof_by_id)}")

    # TabICL INNER
    tab_inner_by_fold_id = {}
    for fold in (0, 1, 2):
        inner_path = tab_dir / "seed_42" / f"fold_{fold}" / "inner_predictions.csv"
        with open(inner_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                tab_inner_by_fold_id[(fold, r["rfid_id"])] = (int(r["y_true"]), [float(r[f"p{c}"]) for c in range(4)], float(r["observed_days"]))
    print(f"TabICL seed_42 INNER entries across 3 folds: {len(tab_inner_by_fold_id)}")

    # Check alignment of TabICL with Round 002
    for fold in (0, 1, 2):
        lgb_es = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_inner_es.npz")
        lgb_sel = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_inner_select.npz")
        lgb_out = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_outer.npz")

        inner_combined_ids = list(lgb_es["ids"]) + list(lgb_sel["ids"])
        inner_combined_y = list(lgb_es["y_true"]) + list(lgb_sel["y_true"])
        
        # Check every ID in inner_combined exists in TabICL fold inner
        for vid, y in zip(inner_combined_ids, inner_combined_y):
            assert (fold, vid) in tab_inner_by_fold_id, f"ID ({fold}, {vid}) missing in TabICL inner"
            ty, tp, tdays = tab_inner_by_fold_id[(fold, vid)]
            assert ty == y, f"Label mismatch for ({fold}, {vid}): {ty} vs {y}"

        for vid, y in zip(lgb_out["ids"], lgb_out["y_true"]):
            assert vid in tab_oof_by_id, f"ID {vid} missing in TabICL OOF"
            ty, tfold, tp, tdays = tab_oof_by_id[vid]
            assert ty == y, f"Label mismatch for outer {vid}: {ty} vs {y}"
            assert tfold == fold, f"Fold mismatch for outer {vid}: {tfold} vs {fold}"

    print("TabICLv2 perfectly aligns with Round 002 ES/SELECT and OUTER on all IDs, folds, and labels!")

    # 3. Check rank1_experiments exp01 sqrt_macro
    exp01_inner = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\sqrt_macro\inner_predictions.csv")
    exp01_outer = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\sqrt_macro\outer_predictions.csv")

    with open(exp01_inner, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        exp_inner_rows = list(reader)
    print(f"exp01 sqrt_macro inner rows: {len(exp_inner_rows)}, columns: {list(exp_inner_rows[0].keys())}")

    with open(exp01_outer, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        exp_outer_rows = list(reader)
    print(f"exp01 sqrt_macro outer rows: {len(exp_outer_rows)}, columns: {list(exp_outer_rows[0].keys())}")

    exp_inner_by_fold_id = {(int(r["fold"]), r["rfid_id"]): (int(r["y_true"]), [float(r[f"p{c}"]) for c in range(4)]) for r in exp_inner_rows}
    exp_outer_by_id = {r["rfid_id"]: (int(r["y_true"]), int(r["fold"]), [float(r[f"p{c}"]) for c in range(4)]) for r in exp_outer_rows}

    # Verify ID match
    for fold in (0, 1, 2):
        lgb_es = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_inner_es.npz")
        lgb_sel = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_inner_select.npz")
        lgb_out = np.load(r2_dir / f"fold_{fold}_baseline_lightgbm_outer.npz")

        for vid, y in zip(list(lgb_es["ids"]) + list(lgb_sel["ids"]), list(lgb_es["y_true"]) + list(lgb_sel["y_true"])):
            assert (fold, vid) in exp_inner_by_fold_id, f"ID ({fold}, {vid}) missing in exp01 inner"
            ey, ep = exp_inner_by_fold_id[(fold, vid)]
            assert ey == y, f"Label mismatch for exp01 inner ({fold}, {vid}): {ey} vs {y}"

        for vid, y in zip(lgb_out["ids"], lgb_out["y_true"]):
            assert vid in exp_outer_by_id, f"ID {vid} missing in exp01 outer"
            ey, efold, ep = exp_outer_by_id[vid]
            assert ey == y, f"Label mismatch for exp01 outer {vid}: {ey} vs {y}"
            assert efold == fold, f"Fold mismatch for exp01 outer {vid}: {efold} vs {fold}"

    print("exp01 sqrt_macro perfectly aligns with Round 002 and TabICL on all IDs, folds, and labels!")

    gc.collect()
    check_ram("verify_alignment_end", expected_peak_mb=80.0)

if __name__ == "__main__":
    main()
