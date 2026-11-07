from __future__ import annotations

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

import lightgbm as lgb
import numpy as np

from resource_guard import check_ram

BASE_FEATURES_DIR = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
R2_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
WORKER_C_DIR = Path(__file__).resolve().parent

FOLDS = (0, 1, 2)
SEEDS = (42, 100, 2026)
CLASSES = ["연안복합(0)", "자망(1)", "통발(2)", "채낚기(3)"]

LGB_BASE_PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "colsample_bytree": 0.7,
    "subsample": 0.8,
    "subsample_freq": 1,
    "n_jobs": 1,
    "verbose": -1,
}

def load_canonical_roster() -> Tuple[List[Tuple[int, str, str, int]], List[Tuple[int, str, str, int]]]:
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

def train_pure_304_specialists():
    check_ram("start_pure_304_train", expected_peak_mb=150.0)
    print("=== [Worker C] Step 1: Training Pure 304-Feature Specialist Models (3-Seeds) ===")
    
    inner_records, outer_records = load_canonical_roster()
    n_in_total = len(inner_records)
    n_out_total = len(outer_records)
    print(f"Canonical Roster: INNER={n_in_total}, OUTER={n_out_total}")

    y_inner = np.array([r[3] for r in inner_records], dtype=np.int64)
    y_outer = np.array([r[3] for r in outer_records], dtype=np.int64)

    # Allocate arrays
    p_spec_gate_304_in = np.zeros(n_in_total, dtype=np.float32)
    p_spec_gate_304_out = np.zeros(n_out_total, dtype=np.float32)
    p_m123_std_304_in = np.zeros((n_in_total, 3), dtype=np.float32)
    p_m123_std_304_out = np.zeros((n_out_total, 3), dtype=np.float32)
    p_m123_sqrt_304_in = np.zeros((n_in_total, 3), dtype=np.float32)
    p_m123_sqrt_304_out = np.zeros((n_out_total, 3), dtype=np.float32)
    
    p_ovr_304_in = np.zeros((n_in_total, 3), dtype=np.float32)
    p_ovr_304_out = np.zeros((n_out_total, 3), dtype=np.float32)
    
    p_base_304_in = np.zeros((n_in_total, 4), dtype=np.float32)
    p_base_304_out = np.zeros((n_out_total, 4), dtype=np.float32)

    in_ptr = 0
    out_ptr = 0

    for fold_idx in FOLDS:
        check_ram(f"fold_{fold_idx}_start", expected_peak_mb=150.0)
        t0 = time.perf_counter()
        print(f"\n--- [Fold {fold_idx}] Loading 304 Features ---")
        npz_file = BASE_FEATURES_DIR / f"fold_{fold_idx}_features.npz"
        z = np.load(npz_file)
        rfid_ids = z["rfid_ids"].astype(str)
        y = z["y"].astype(np.int64)
        roles = z["roles"].astype(str)
        X = z["X"].astype(np.float32)
        del z
        gc.collect()

        fit_mask = roles == "FIT"
        inner_mask = roles == "INNER"
        outer_mask = roles == "OUTER"

        fit_X = X[fit_mask]
        fit_y = y[fit_mask]

        inner_ids = rfid_ids[inner_mask]
        inner_y = y[inner_mask]
        inner_X = X[inner_mask]

        outer_ids = rfid_ids[outer_mask]
        outer_y = y[outer_mask]
        outer_X = X[outer_mask]

        del rfid_ids, y, roles, X
        gc.collect()

        # Reorder INNER to match Canonical Roster
        es = np.load(R2_DIR / f"fold_{fold_idx}_baseline_lightgbm_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold_idx}_baseline_lightgbm_inner_select.npz")
        r2_inner_ids = np.concatenate([es["ids"].astype(str), sel["ids"].astype(str)])
        id_to_idx = {vid: i for i, vid in enumerate(inner_ids)}
        reorder_idx = [id_to_idx[vid] for vid in r2_inner_ids]

        inner_X_sorted = inner_X[reorder_idx]
        del inner_X
        gc.collect()

        outer_X_sorted = outer_X
        del outer_X
        gc.collect()

        n_in = len(inner_X_sorted)
        n_out = len(outer_X_sorted)
        print(f"  Shapes: FIT={fit_X.shape}, INNER={inner_X_sorted.shape}, OUTER={outer_X_sorted.shape} ({time.perf_counter()-t0:.1f}s)")

        # -------------------------------------------------------------
        # Specialist Sub-dataset (fit_y != 0)
        # -------------------------------------------------------------
        spec_mask = fit_y != 0
        spec_X = fit_X[spec_mask]
        spec_y = fit_y[spec_mask] - 1  # 1->0, 2->1, 3->2
        print(f"  Specialist sub-dataset size: {len(spec_y)} (Class 1:{np.sum(spec_y==0)}, 2:{np.sum(spec_y==1)}, 3:{np.sum(spec_y==2)})")

        sub_counts = np.bincount(spec_y, minlength=3)
        w_sub = np.sqrt(len(spec_y) / (3.0 * sub_counts))
        w_sub /= w_sub.mean()
        cw_sub = {c: float(w_sub[c]) for c in range(3)}

        # Accumulators for seeds
        gate_in_acc = np.zeros(n_in, dtype=np.float64)
        gate_out_acc = np.zeros(n_out, dtype=np.float64)
        m123_std_in_acc = np.zeros((n_in, 3), dtype=np.float64)
        m123_std_out_acc = np.zeros((n_out, 3), dtype=np.float64)
        m123_sqrt_in_acc = np.zeros((n_in, 3), dtype=np.float64)
        m123_sqrt_out_acc = np.zeros((n_out, 3), dtype=np.float64)
        base_304_in_acc = np.zeros((n_in, 4), dtype=np.float64)
        base_304_out_acc = np.zeros((n_out, 4), dtype=np.float64)

        for seed in SEEDS:
            t_seed = time.perf_counter()
            print(f"    [Fold {fold_idx} | Seed {seed}] Training M0_gate_304, M123_std, M123_sqrt, Base4...")

            # 1. M0_gate_304 (Specialist vs Coastal Complex binary)
            params_seed = dict(LGB_BASE_PARAMS, random_state=seed)
            m0 = lgb.LGBMClassifier(objective="binary", **params_seed)
            m0.fit(fit_X, (fit_y != 0).astype(int))
            gate_in_acc += m0.predict_proba(inner_X_sorted)[:, 1]
            gate_out_acc += m0.predict_proba(outer_X_sorted)[:, 1]
            del m0
            gc.collect()

            # 2. M123_std_304 (3-class specialist on {1,2,3})
            m123_std = lgb.LGBMClassifier(objective="multiclass", num_class=3, **params_seed)
            m123_std.fit(spec_X, spec_y)
            m123_std_in_acc += m123_std.predict_proba(inner_X_sorted)
            m123_std_out_acc += m123_std.predict_proba(outer_X_sorted)
            del m123_std
            gc.collect()

            # 3. M123_sqrt_304 (3-class sqrt_macro on {1,2,3})
            m123_sqrt = lgb.LGBMClassifier(objective="multiclass", num_class=3, class_weight=cw_sub, **params_seed)
            m123_sqrt.fit(spec_X, spec_y)
            m123_sqrt_in_acc += m123_sqrt.predict_proba(inner_X_sorted)
            m123_sqrt_out_acc += m123_sqrt.predict_proba(outer_X_sorted)
            del m123_sqrt
            gc.collect()

            # 4. Standard 4-Class LightGBM Baseline on 304 features
            clf4 = lgb.LGBMClassifier(objective="multiclass", num_class=4, **params_seed)
            clf4.fit(fit_X, fit_y)
            base_304_in_acc += clf4.predict_proba(inner_X_sorted)
            base_304_out_acc += clf4.predict_proba(outer_X_sorted)
            del clf4
            gc.collect()

            print(f"      Seed {seed} done ({time.perf_counter()-t_seed:.1f}s)")

        # Seed average
        p_spec_gate_304_in[in_ptr : in_ptr + n_in] = (gate_in_acc / len(SEEDS)).astype(np.float32)
        p_spec_gate_304_out[out_ptr : out_ptr + n_out] = (gate_out_acc / len(SEEDS)).astype(np.float32)

        p_m123_std_304_in[in_ptr : in_ptr + n_in] = (m123_std_in_acc / len(SEEDS)).astype(np.float32)
        p_m123_std_304_out[out_ptr : out_ptr + n_out] = (m123_std_out_acc / len(SEEDS)).astype(np.float32)

        p_m123_sqrt_304_in[in_ptr : in_ptr + n_in] = (m123_sqrt_in_acc / len(SEEDS)).astype(np.float32)
        p_m123_sqrt_304_out[out_ptr : out_ptr + n_out] = (m123_sqrt_out_acc / len(SEEDS)).astype(np.float32)

        p_base_304_in[in_ptr : in_ptr + n_in] = (base_304_in_acc / len(SEEDS)).astype(np.float32)
        p_base_304_out[out_ptr : out_ptr + n_out] = (base_304_out_acc / len(SEEDS)).astype(np.float32)

        # Train Binary OVR (seed 42)
        print(f"    [Fold {fold_idx}] Training M_ovr_std_304 (classes 1, 2, 3)...")
        m_ovr_in = []
        m_ovr_out = []
        for c_target in [1, 2, 3]:
            movr = lgb.LGBMClassifier(objective="binary", **dict(LGB_BASE_PARAMS, random_state=42))
            movr.fit(fit_X, (fit_y == c_target).astype(int))
            m_ovr_in.append(movr.predict_proba(inner_X_sorted)[:, 1])
            m_ovr_out.append(movr.predict_proba(outer_X_sorted)[:, 1])
            del movr
            gc.collect()

        p_ovr_304_in[in_ptr : in_ptr + n_in] = np.column_stack(m_ovr_in).astype(np.float32)
        p_ovr_304_out[out_ptr : out_ptr + n_out] = np.column_stack(m_ovr_out).astype(np.float32)

        del fit_X, spec_X, spec_y, inner_X_sorted, outer_X_sorted
        gc.collect()

        in_ptr += n_in
        out_ptr += n_out
        print(f"  Fold {fold_idx} completed in {time.perf_counter()-t0:.1f}s.")

    check_ram("finished_pure_304_train", expected_peak_mb=150.0)

    # -------------------------------------------------------------
    # Build 2-Stage Hierarchical Probabilities
    # -------------------------------------------------------------
    # P(0) = 1 - P_gate
    # P(c) = P_gate * P_M123(c-1)
    p_hier_304_std_in = np.column_stack([
        1.0 - p_spec_gate_304_in,
        p_spec_gate_304_in * p_m123_std_304_in[:, 0],
        p_spec_gate_304_in * p_m123_std_304_in[:, 1],
        p_spec_gate_304_in * p_m123_std_304_in[:, 2],
    ]).astype(np.float32)

    p_hier_304_std_out = np.column_stack([
        1.0 - p_spec_gate_304_out,
        p_spec_gate_304_out * p_m123_std_304_out[:, 0],
        p_spec_gate_304_out * p_m123_std_304_out[:, 1],
        p_spec_gate_304_out * p_m123_std_304_out[:, 2],
    ]).astype(np.float32)

    p_hier_304_sqrt_in = np.column_stack([
        1.0 - p_spec_gate_304_in,
        p_spec_gate_304_in * p_m123_sqrt_304_in[:, 0],
        p_spec_gate_304_in * p_m123_sqrt_304_in[:, 1],
        p_spec_gate_304_in * p_m123_sqrt_304_in[:, 2],
    ]).astype(np.float32)

    p_hier_304_sqrt_out = np.column_stack([
        1.0 - p_spec_gate_304_out,
        p_spec_gate_304_out * p_m123_sqrt_304_out[:, 0],
        p_spec_gate_304_out * p_m123_sqrt_304_out[:, 1],
        p_spec_gate_304_out * p_m123_sqrt_304_out[:, 2],
    ]).astype(np.float32)

    # Save to disk temporarily
    npz_out = WORKER_C_DIR / "pure_304_probabilities.npz"
    np.savez_compressed(
        npz_out,
        y_inner=y_inner,
        y_outer=y_outer,
        p_spec_gate_304_in=p_spec_gate_304_in,
        p_spec_gate_304_out=p_spec_gate_304_out,
        p_m123_std_304_in=p_m123_std_304_in,
        p_m123_std_304_out=p_m123_std_304_out,
        p_m123_sqrt_304_in=p_m123_sqrt_304_in,
        p_m123_sqrt_304_out=p_m123_sqrt_304_out,
        p_hier_304_std_in=p_hier_304_std_in,
        p_hier_304_std_out=p_hier_304_std_out,
        p_hier_304_sqrt_in=p_hier_304_sqrt_in,
        p_hier_304_sqrt_out=p_hier_304_sqrt_out,
        p_ovr_304_in=p_ovr_304_in,
        p_ovr_304_out=p_ovr_304_out,
        p_base_304_in=p_base_304_in,
        p_base_304_out=p_base_304_out,
    )
    print(f"Saved pure 304 probabilities to {npz_out}")

    # Check standalone performance on INNER and OUTER
    def eval_pred(name: str, p_in: np.ndarray, p_out: np.ndarray):
        pred_in = np.argmax(p_in, axis=1)
        pred_out = np.argmax(p_out, axis=1)
        acc_in = np.mean(y_inner == pred_in) * 100
        acc_out = np.mean(y_outer == pred_out) * 100
        tp_in = [int(np.sum((y_inner == c) & (pred_in == c))) for c in range(4)]
        tp_out = [int(np.sum((y_outer == c) & (pred_out == c))) for c in range(4)]
        correct_out = int(np.sum(y_outer == pred_out))
        print(f"[{name:25s}] INNER: {np.sum(y_inner == pred_in)}/2361 ({acc_in:.2f}%) | OUTER: {correct_out}/5897 ({acc_out:.2f}%) TP={tp_out}")

    print("\n--- Standalone Argmax Evaluation on 304 Features ---")
    eval_pred("Base 4-Class LightGBM", p_base_304_in, p_base_304_out)
    eval_pred("Hierarchical Std 304", p_hier_304_std_in, p_hier_304_std_out)
    eval_pred("Hierarchical Sqrt 304", p_hier_304_sqrt_in, p_hier_304_sqrt_out)

if __name__ == "__main__":
    train_pure_304_specialists()
