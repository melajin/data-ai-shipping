import csv
import os
import sys
from pathlib import Path
import numpy as np

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

R2_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
TAB_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation")
RANK1_DIR = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts")
T1_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")

FOLDS = (0, 1, 2)

def load_canonical_data():
    inner_records = []
    outer_records = []
    for fold in FOLDS:
        es = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_select.npz")
        out = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_outer.npz")
        
        for vid, y in zip(es["ids"], es["y_true"]):
            inner_records.append((fold, "INNER_ES", str(vid), int(y)))
        for vid, y in zip(sel["ids"], sel["y_true"]):
            inner_records.append((fold, "INNER_SELECT", str(vid), int(y)))
        for vid, y in zip(out["ids"], out["y_true"]):
            outer_records.append((fold, "OUTER", str(vid), int(y)))
    return inner_records, outer_records

def load_data():
    inner_records, outer_records = load_canonical_data()
    inner_keys = [(r[0], r[2]) for r in inner_records]
    outer_keys = [r[2] for r in outer_records]
    inner_y = np.array([r[3] for r in inner_records], dtype=np.int64)
    outer_y = np.array([r[3] for r in outer_records], dtype=np.int64)
    inner_folds = np.array([r[0] for r in inner_records], dtype=np.int64)
    outer_folds = np.array([r[0] for r in outer_records], dtype=np.int64)

    # 1. LGB seed 42
    p_in_lgb42 = np.zeros((len(inner_records), 4), dtype=np.float32)
    p_out_lgb42 = np.zeros((len(outer_records), 4), dtype=np.float32)
    idx_in, idx_out = 0, 0
    for fold in FOLDS:
        es = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_inner_select.npz")
        out = np.load(R2_DIR / f"fold_{fold}_baseline_lightgbm_outer.npz")
        p_in_lgb42[idx_in : idx_in + len(es["ids"])] = es["probabilities"]
        idx_in += len(es["ids"])
        p_in_lgb42[idx_in : idx_in + len(sel["ids"])] = sel["probabilities"]
        idx_in += len(sel["ids"])
        p_out_lgb42[idx_out : idx_out + len(out["ids"])] = out["probabilities"]
        idx_out += len(out["ids"])

    # 2. CatBoost
    p_in_cat = np.zeros((len(inner_records), 4), dtype=np.float32)
    p_out_cat = np.zeros((len(outer_records), 4), dtype=np.float32)
    idx_in, idx_out = 0, 0
    for fold in FOLDS:
        es = np.load(R2_DIR / f"fold_{fold}_candidate_catboost_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold}_candidate_catboost_inner_select.npz")
        out = np.load(R2_DIR / f"fold_{fold}_candidate_catboost_outer.npz")
        p_in_cat[idx_in : idx_in + len(es["ids"])] = es["probabilities"]
        idx_in += len(es["ids"])
        p_in_cat[idx_in : idx_in + len(sel["ids"])] = sel["probabilities"]
        idx_in += len(sel["ids"])
        p_out_cat[idx_out : idx_out + len(out["ids"])] = out["probabilities"]
        idx_out += len(out["ids"])

    # 3. TabICL 42 & 2026
    tab_probs = {}
    for seed in [42, 2026]:
        tab_in_map = {}
        for fold in FOLDS:
            p = TAB_DIR / f"seed_{seed}" / f"fold_{fold}" / "inner_predictions.csv"
            with open(p, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    tab_in_map[(fold, r["rfid_id"])] = [float(r[f"p{c}"]) for c in range(4)]
        p_in = np.array([tab_in_map[k] for k in inner_keys], dtype=np.float32)
        
        tab_out_map = {}
        p = TAB_DIR / f"seed_{seed}" / "original_oof_predictions.csv"
        with open(p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                tab_out_map[r["rfid_id"]] = [float(r[f"p{c}"]) for c in range(4)]
        p_out = np.array([tab_out_map[k] for k in outer_keys], dtype=np.float32)
        tab_probs[seed] = (p_in, p_out)

    # 4. LGB 5seed sqrt_macro
    sqrt_dir = RANK1_DIR / "exp01" / "sqrt_macro"
    with open(sqrt_dir / "inner_predictions.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        in_map = {(int(r["fold"]), r["rfid_id"]): [float(r[f"p{c}"]) for c in range(4)] for r in reader}
    with open(sqrt_dir / "outer_predictions.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        out_map = {r["rfid_id"]: [float(r[f"p{c}"]) for c in range(4)] for r in reader}
    p_in_lgb5 = np.array([in_map[k] for k in inner_keys], dtype=np.float32)
    p_out_lgb5 = np.array([out_map[k] for k in outer_keys], dtype=np.float32)

    # 5. Track 1 (Spatial kNN)
    with np.load(T1_PATH, allow_pickle=False) as z:
        t1_vids = z["vessel_ids"].astype(str)
        t1_outer_probs = z["outer_probs"]
        t1_inner_f0 = z["inner_probs_fold0"]
        t1_inner_f1 = z["inner_probs_fold1"]
        t1_inner_f2 = z["inner_probs_fold2"]

    t1_outer_by_id = {vid: t1_outer_probs[i] for i, vid in enumerate(t1_vids)}
    p_out_t1 = np.zeros((len(outer_records), 4), dtype=np.float32)
    for i, r in enumerate(outer_records):
        p_out_t1[i] = t1_outer_by_id[r[2]]

    exp01_dir = RANK1_DIR / "exp01"
    t1_in_by_fid = {}
    for f in FOLDS:
        with np.load(exp01_dir / f"fold_{f}_features.npz") as zf:
            f_ids = zf["rfid_ids"].astype(str)[zf["roles"].astype(str) == "INNER"]
            p_f = [t1_inner_f0, t1_inner_f1, t1_inner_f2][f]
            for j, vid in enumerate(f_ids):
                t1_in_by_fid[(f, vid)] = p_f[j]
    p_in_t1 = np.zeros((len(inner_records), 4), dtype=np.float32)
    for i, r in enumerate(inner_records):
        p_in_t1[i] = t1_in_by_fid[(r[0], r[2])]

    # Blends
    p_in_trio = 0.45 * p_in_lgb5 + 0.45 * tab_probs[42][0] + 0.10 * p_in_cat
    p_out_trio = 0.45 * p_out_lgb5 + 0.45 * tab_probs[42][1] + 0.10 * p_out_cat

    p_in_grand = 0.35 * p_in_lgb5 + 0.225 * tab_probs[42][0] + 0.225 * tab_probs[2026][0] + 0.10 * p_in_cat + 0.10 * p_in_t1
    p_out_grand = 0.35 * p_out_lgb5 + 0.225 * tab_probs[42][1] + 0.225 * tab_probs[2026][1] + 0.10 * p_out_cat + 0.10 * p_out_t1

    models = {
        "LightGBM_seed42": (p_in_lgb42, p_out_lgb42),
        "LightGBM_5seed_sqrt_macro": (p_in_lgb5, p_out_lgb5),
        "CatBoost": (p_in_cat, p_out_cat),
        "TabICL_seed42": (tab_probs[42][0], tab_probs[42][1]),
        "TabICL_seed2026": (tab_probs[2026][0], tab_probs[2026][1]),
        "Track1_LGB_kNN": (p_in_t1, p_out_t1),
        "Blend_Trio": (p_in_trio, p_out_trio),
        "Blend_Grand": (p_in_grand, p_out_grand),
    }
    
    return inner_y, outer_y, inner_folds, outer_folds, models

if __name__ == "__main__":
    inner_y, outer_y, inner_folds, outer_folds, models = load_data()
    print("Class distribution INNER (N=2361):", np.bincount(inner_y))
    print("Class distribution OUTER (N=5897):", np.bincount(outer_y))
    print("\n--- BASELINE ARGMAX (RULE B0) ---")
    for name, (p_in, p_out) in models.items():
        pred_out = p_out.argmax(axis=1)
        cm_out = np.bincount(outer_y * 4 + pred_out, minlength=16).reshape(4, 4)
        correct_out = int(np.trace(cm_out))
        tp_out = np.diag(cm_out).tolist()
        # How many actual Class 0 were falsely predicted as 1, 2, 3?
        fp_0_out = int(cm_out[0, 1] + cm_out[0, 2] + cm_out[0, 3])
        print(f"{name:<28} | OUTER Correct: {correct_out:4d}/5897 | TP: {tp_out} | Class0 FP leak: {fp_0_out:4d} (leak rate: {fp_0_out / cm_out[0].sum():.1%})")
