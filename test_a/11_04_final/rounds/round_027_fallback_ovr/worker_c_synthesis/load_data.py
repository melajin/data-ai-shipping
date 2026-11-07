from __future__ import annotations

import csv
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from resource_guard import check_ram
from synthesis_utils import (
    compute_metrics,
    run_paired_bootstrap,
    compute_transition_breakdown,
    CLASSES,
    MIN_TP0_IN,
    MIN_TP3_IN,
    MIN_TP0_OUT,
    MIN_TP3_OUT,
)

WORKER_C_DIR = Path(__file__).resolve().parent
WORKER_A_DIR = WORKER_C_DIR.parent / "worker_a_ovr_models"
WORKER_B_DIR = WORKER_C_DIR.parent / "worker_b_fallback_rules"
R2_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
TAB_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료\evaluation")
RANK1_DIR = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts")
T1_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn\probabilities_track1.npz")
T3_PATH = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track3_ensemble\probabilities_track3.npz")

FOLDS = (0, 1, 2)

def load_canonical_data():
    check_ram("load_canonical_data_start", expected_peak_mb=120.0)
    print("=== [Worker C] Loading Canonical Roster & Multi-Model Probabilities ===")
    
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

    # 6. Grand Blends
    p_in_grand = 0.35 * p_in_lgb5 + 0.225 * tab_probs[42][0] + 0.225 * tab_probs[2026][0] + 0.10 * p_in_cat + 0.10 * p_in_t1
    p_out_grand = 0.35 * p_out_lgb5 + 0.225 * tab_probs[42][1] + 0.225 * tab_probs[2026][1] + 0.10 * p_out_cat + 0.10 * p_out_t1

    p_in_trio = 0.45 * p_in_lgb5 + 0.45 * tab_probs[42][0] + 0.10 * p_in_cat
    p_out_trio = 0.45 * p_out_lgb5 + 0.45 * tab_probs[42][1] + 0.10 * p_out_cat

    # 7. Round 026 Grand Fusion prediction (OUTER, 3552)
    with np.load(T3_PATH) as z:
        pred_r26_grand_fusion = z["pred_grand_fusion"]

    # 8. Worker A Probabilities (326 features)
    za = np.load(WORKER_A_DIR / "worker_a_probabilities.npz")
    p_hier_326_std_in = za["p_hierarchical_std_in"]
    p_hier_326_std_out = za["p_hierarchical_std_out"]
    p_hier_326_sqrt_in = za["p_hierarchical_sqrt_in"]
    p_hier_326_sqrt_out = za["p_hierarchical_sqrt_out"]
    p_spec_gate_326_in = za["p_spec_gate_in"]
    p_spec_gate_326_out = za["p_spec_gate_out"]
    p_m123_std_326_in = za["p_m123_std_in"]
    p_m123_std_326_out = za["p_m123_std_out"]
    p_ovr_326_norm_in = za["p_ovr_4class_norm_in"]
    p_ovr_326_norm_out = za["p_ovr_4class_norm_out"]

    # 9. Worker C Pure 304 Probabilities
    zc = np.load(WORKER_C_DIR / "pure_304_probabilities.npz")
    p_spec_gate_304_in = zc["p_spec_gate_304_in"]
    p_spec_gate_304_out = zc["p_spec_gate_304_out"]
    p_m123_std_304_in = zc["p_m123_std_304_in"]
    p_m123_std_304_out = zc["p_m123_std_304_out"]
    p_m123_sqrt_304_in = zc["p_m123_sqrt_304_in"]
    p_m123_sqrt_304_out = zc["p_m123_sqrt_304_out"]
    p_hier_304_std_in = zc["p_hier_304_std_in"]
    p_hier_304_std_out = zc["p_hier_304_std_out"]
    p_hier_304_sqrt_in = zc["p_hier_304_sqrt_in"]
    p_hier_304_sqrt_out = zc["p_hier_304_sqrt_out"]
    p_base_304_in = zc["p_base_304_in"]
    p_base_304_out = zc["p_base_304_out"]
    p_ovr_304_in = zc["p_ovr_304_in"]
    p_ovr_304_out = zc["p_ovr_304_out"]

    check_ram("loaded_all_probabilities", expected_peak_mb=120.0)

    data = {
        "inner_y": inner_y,
        "outer_y": outer_y,
        "inner_folds": inner_folds,
        "outer_folds": outer_folds,
        "p_lgb42": (p_in_lgb42, p_out_lgb42),
        "p_lgb5": (p_in_lgb5, p_out_lgb5),
        "p_cat": (p_in_cat, p_out_cat),
        "tab42": tab_probs[42],
        "tab2026": tab_probs[2026],
        "p_t1": (p_in_t1, p_out_t1),
        "p_grand": (p_in_grand, p_out_grand),
        "p_trio": (p_in_trio, p_out_trio),
        "pred_r26_grand_fusion": pred_r26_grand_fusion,
        "worker_a": {
            "p_hier_std": (p_hier_326_std_in, p_hier_326_std_out),
            "p_hier_sqrt": (p_hier_326_sqrt_in, p_hier_326_sqrt_out),
            "p_spec_gate": (p_spec_gate_326_in, p_spec_gate_326_out),
            "p_m123_std": (p_m123_std_326_in, p_m123_std_326_out),
            "p_ovr_norm": (p_ovr_326_norm_in, p_ovr_326_norm_out),
        },
        "worker_c": {
            "p_spec_gate": (p_spec_gate_304_in, p_spec_gate_304_out),
            "p_m123_std": (p_m123_std_304_in, p_m123_std_304_out),
            "p_m123_sqrt": (p_m123_sqrt_304_in, p_m123_sqrt_304_out),
            "p_hier_std": (p_hier_304_std_in, p_hier_304_std_out),
            "p_hier_sqrt": (p_hier_304_sqrt_in, p_hier_304_sqrt_out),
            "p_base": (p_base_304_in, p_base_304_out),
            "p_ovr": (p_ovr_304_in, p_ovr_304_out),
        }
    }
    return data
