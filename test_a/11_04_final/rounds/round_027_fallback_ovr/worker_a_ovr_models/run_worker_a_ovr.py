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

# Add track1 to path for hellinger_knn
TRACK1_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_026\track1_spatial_knn")
sys.path.append(str(TRACK1_DIR))
import hellinger_knn

# Local resource guard
from resource_guard import check_ram

BASE_FEATURES_DIR = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
R2_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_002\artifacts\probabilities")
WORKER_A_DIR = Path(__file__).resolve().parent

FOLDS = (0, 1, 2)
CLASSES = ["연안복합(0)", "자망(1)", "통발(2)", "채낚기(3)"]

LGB_BASE_PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "colsample_bytree": 0.7,
    "subsample": 0.8,
    "subsample_freq": 1,
    "n_jobs": 1,
    "random_state": 42,
    "verbose": -1,
}


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    cm = np.bincount(y_true * 4 + y_pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(np.int64)
    support = cm.sum(axis=1).astype(np.int64)
    predicted = cm.sum(axis=0).astype(np.int64)

    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros(4, dtype=np.float64), where=predicted > 0)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros(4, dtype=np.float64), where=denom > 0)

    correct = int(np.count_nonzero(y_true == y_pred))
    n = len(y_true)

    return {
        "n": n,
        "correct": correct,
        "micro_f1": float(correct / n) if n > 0 else 0.0,
        "macro_f1": float(f1.mean()),
        "tp": tp.tolist(),
        "tp0": int(tp[0]),
        "tp1": int(tp[1]),
        "tp2": int(tp[2]),
        "tp3": int(tp[3]),
        "support": support.tolist(),
        "predicted": predicted.tolist(),
        "precision": [round(float(x), 4) for x in precision],
        "recall": [round(float(x), 4) for x in recall],
        "class_f1": [round(float(x), 4) for x in f1],
        "confusion_matrix": cm.tolist(),
        "rule_tp0_pass": bool(tp[0] >= (2389 if n > 3000 else 957)),
        "rule_tp3_pass": bool(tp[3] >= (90 if n > 3000 else 36)),
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


def train_and_extract_all_probabilities():
    check_ram("start_data_load_and_train", expected_peak_mb=350.0)
    print("=== [Worker A] Step 1: Sequential Fold Training and Probability Extraction ===")

    inner_records, outer_records = load_canonical_roster()
    print(f"Loaded canonical roster: INNER={len(inner_records)}, OUTER={len(outer_records)}")

    y_inner = np.array([r[3] for r in inner_records], dtype=np.int64)
    y_outer = np.array([r[3] for r in outer_records], dtype=np.int64)

    extractor = hellinger_knn.HellingerKnnFeatureExtractor()

    # Preallocate probability arrays in canonical order
    # INNER: 2361
    p_ovr_std_in = np.zeros((len(inner_records), 3), dtype=np.float32)
    p_ovr_sqrt_in = np.zeros((len(inner_records), 3), dtype=np.float32)
    p_spec_gate_in = np.zeros(len(inner_records), dtype=np.float32)
    p_m123_std_in = np.zeros((len(inner_records), 3), dtype=np.float32)
    p_m123_sqrt_in = np.zeros((len(inner_records), 3), dtype=np.float32)
    p_lgb_knn_std_in = np.zeros((len(inner_records), 4), dtype=np.float32)
    p_lgb_knn_sqrt_in = np.zeros((len(inner_records), 4), dtype=np.float32)

    # OUTER: 5897
    p_ovr_std_out = np.zeros((len(outer_records), 3), dtype=np.float32)
    p_ovr_sqrt_out = np.zeros((len(outer_records), 3), dtype=np.float32)
    p_spec_gate_out = np.zeros(len(outer_records), dtype=np.float32)
    p_m123_std_out = np.zeros((len(outer_records), 3), dtype=np.float32)
    p_m123_sqrt_out = np.zeros((len(outer_records), 3), dtype=np.float32)
    p_lgb_knn_std_out = np.zeros((len(outer_records), 4), dtype=np.float32)
    p_lgb_knn_sqrt_out = np.zeros((len(outer_records), 4), dtype=np.float32)

    # Fold slices
    # Inner: fold 0 (0..787), fold 1 (787..1574), fold 2 (1574..2361)
    # Outer: fold 0 (0..1966), fold 1 (1966..3932), fold 2 (3932..5897)
    in_ptr = 0
    out_ptr = 0

    for fold_idx in FOLDS:
        check_ram(f"fold_{fold_idx}_feature_extraction", expected_peak_mb=350.0)
        print(f"\n--- [Fold {fold_idx}] Feature Loading and Extraction ---")
        t0 = time.perf_counter()

        # Load 304 features
        npz_file = BASE_FEATURES_DIR / f"fold_{fold_idx}_features.npz"
        z = np.load(npz_file)
        rfid_ids = z["rfid_ids"].astype(str)
        y = z["y"].astype(np.int64)
        roles = z["roles"].astype(str)
        X = z["X"]
        del z
        gc.collect()

        fit_mask = roles == "FIT"
        inner_mask = roles == "INNER"
        outer_mask = roles == "OUTER"

        fit_ids = rfid_ids[fit_mask]
        fit_y = y[fit_mask]
        fit_X = X[fit_mask]

        inner_ids = rfid_ids[inner_mask]
        inner_y = y[inner_mask]
        inner_X = X[inner_mask]

        outer_ids = rfid_ids[outer_mask]
        outer_y = y[outer_mask]
        outer_X = X[outer_mask]

        del rfid_ids, y, roles, X
        gc.collect()

        # Extract 22 Hellinger kNN features
        knn_fit = extractor.extract_features(
            query_ids=fit_ids,
            gallery_ids=fit_ids,
            gallery_labels=fit_y,
            is_leave_one_out=True,
        )
        knn_inner = extractor.extract_features(
            query_ids=inner_ids,
            gallery_ids=fit_ids,
            gallery_labels=fit_y,
            is_leave_one_out=False,
        )
        knn_outer = extractor.extract_features(
            query_ids=outer_ids,
            gallery_ids=fit_ids,
            gallery_labels=fit_y,
            is_leave_one_out=False,
        )

        fit_X_326 = np.concatenate([fit_X, knn_fit], axis=1).astype(np.float32)
        inner_X_326 = np.concatenate([inner_X, knn_inner], axis=1).astype(np.float32)
        outer_X_326 = np.concatenate([outer_X, knn_outer], axis=1).astype(np.float32)

        del fit_X, inner_X, outer_X, knn_fit, knn_inner, knn_outer
        gc.collect()

        # Canonical reordering for INNER
        es = np.load(R2_DIR / f"fold_{fold_idx}_baseline_lightgbm_inner_es.npz")
        sel = np.load(R2_DIR / f"fold_{fold_idx}_baseline_lightgbm_inner_select.npz")
        r2_inner_ids = np.concatenate([es["ids"].astype(str), sel["ids"].astype(str)])
        id_to_idx = {vid: i for i, vid in enumerate(inner_ids)}
        reorder_idx = [id_to_idx[vid] for vid in r2_inner_ids]

        inner_X_sorted = inner_X_326[reorder_idx]
        del inner_X_326
        gc.collect()

        # Outer is already in identical order
        outer_X_sorted = outer_X_326
        del outer_X_326
        gc.collect()

        n_in = len(inner_X_sorted)
        n_out = len(outer_X_sorted)
        print(f"  Fold {fold_idx} shapes: FIT={fit_X_326.shape}, INNER={inner_X_sorted.shape}, OUTER={outer_X_sorted.shape} ({time.perf_counter()-t0:.1f}s)")

        # -----------------------------------------------------------------
        # Model Training on FIT (3,144 vessels)
        # -----------------------------------------------------------------
        check_ram(f"fold_{fold_idx}_model_train", expected_peak_mb=350.0)

        # (1) M1_jamang_ovr_std
        print(f"  [Fold {fold_idx}] Training M1 (Jamang OVR Std)...")
        m1 = lgb.LGBMClassifier(objective="binary", **LGB_BASE_PARAMS)
        m1.fit(fit_X_326, (fit_y == 1).astype(int))
        p_m1_in = m1.predict_proba(inner_X_sorted)[:, 1].astype(np.float32)
        p_m1_out = m1.predict_proba(outer_X_sorted)[:, 1].astype(np.float32)
        del m1
        gc.collect()

        # (2) M2_tongbal_ovr_std
        print(f"  [Fold {fold_idx}] Training M2 (Tongbal OVR Std)...")
        m2 = lgb.LGBMClassifier(objective="binary", **LGB_BASE_PARAMS)
        m2.fit(fit_X_326, (fit_y == 2).astype(int))
        p_m2_in = m2.predict_proba(inner_X_sorted)[:, 1].astype(np.float32)
        p_m2_out = m2.predict_proba(outer_X_sorted)[:, 1].astype(np.float32)
        del m2
        gc.collect()

        # (3) M3_chaenakgi_ovr_std
        print(f"  [Fold {fold_idx}] Training M3 (Chaenakgi OVR Std)...")
        m3 = lgb.LGBMClassifier(objective="binary", **LGB_BASE_PARAMS)
        m3.fit(fit_X_326, (fit_y == 3).astype(int))
        p_m3_in = m3.predict_proba(inner_X_sorted)[:, 1].astype(np.float32)
        p_m3_out = m3.predict_proba(outer_X_sorted)[:, 1].astype(np.float32)
        del m3
        gc.collect()

        p_ovr_std_in[in_ptr : in_ptr + n_in] = np.column_stack([p_m1_in, p_m2_in, p_m3_in])
        p_ovr_std_out[out_ptr : out_ptr + n_out] = np.column_stack([p_m1_out, p_m2_out, p_m3_out])

        # (4) M_ovr_sqrt (scale_pos_weight = sqrt(n_neg / n_pos))
        print(f"  [Fold {fold_idx}] Training M1, M2, M3 with sqrt scale_pos_weight...")
        spw1 = float(np.sqrt(np.sum(fit_y != 1) / np.sum(fit_y == 1)))
        m1_sqrt = lgb.LGBMClassifier(objective="binary", scale_pos_weight=spw1, **LGB_BASE_PARAMS)
        m1_sqrt.fit(fit_X_326, (fit_y == 1).astype(int))
        p_m1_sqrt_in = m1_sqrt.predict_proba(inner_X_sorted)[:, 1].astype(np.float32)
        p_m1_sqrt_out = m1_sqrt.predict_proba(outer_X_sorted)[:, 1].astype(np.float32)
        del m1_sqrt
        gc.collect()

        spw2 = float(np.sqrt(np.sum(fit_y != 2) / np.sum(fit_y == 2)))
        m2_sqrt = lgb.LGBMClassifier(objective="binary", scale_pos_weight=spw2, **LGB_BASE_PARAMS)
        m2_sqrt.fit(fit_X_326, (fit_y == 2).astype(int))
        p_m2_sqrt_in = m2_sqrt.predict_proba(inner_X_sorted)[:, 1].astype(np.float32)
        p_m2_sqrt_out = m2_sqrt.predict_proba(outer_X_sorted)[:, 1].astype(np.float32)
        del m2_sqrt
        gc.collect()

        spw3 = float(np.sqrt(np.sum(fit_y != 3) / np.sum(fit_y == 3)))
        m3_sqrt = lgb.LGBMClassifier(objective="binary", scale_pos_weight=spw3, **LGB_BASE_PARAMS)
        m3_sqrt.fit(fit_X_326, (fit_y == 3).astype(int))
        p_m3_sqrt_in = m3_sqrt.predict_proba(inner_X_sorted)[:, 1].astype(np.float32)
        p_m3_sqrt_out = m3_sqrt.predict_proba(outer_X_sorted)[:, 1].astype(np.float32)
        del m3_sqrt
        gc.collect()

        p_ovr_sqrt_in[in_ptr : in_ptr + n_in] = np.column_stack([p_m1_sqrt_in, p_m2_sqrt_in, p_m3_sqrt_in])
        p_ovr_sqrt_out[out_ptr : out_ptr + n_out] = np.column_stack([p_m1_sqrt_out, p_m2_sqrt_out, p_m3_sqrt_out])

        # (5) M0_specialist_gate (Binary: y != 0 vs y == 0)
        print(f"  [Fold {fold_idx}] Training M0 (Specialist Gate)...")
        m0 = lgb.LGBMClassifier(objective="binary", **LGB_BASE_PARAMS)
        m0.fit(fit_X_326, (fit_y != 0).astype(int))
        p_m0_in = m0.predict_proba(inner_X_sorted)[:, 1].astype(np.float32)
        p_m0_out = m0.predict_proba(outer_X_sorted)[:, 1].astype(np.float32)
        del m0
        gc.collect()

        p_spec_gate_in[in_ptr : in_ptr + n_in] = p_m0_in
        p_spec_gate_out[out_ptr : out_ptr + n_out] = p_m0_out

        # (6) M123_specialist_std & M123_specialist_sqrt (Multiclass 3-class on fit_y in {1,2,3})
        print(f"  [Fold {fold_idx}] Training M123 (3-Class Specialist on classes {1,2,3})...")
        spec_mask = fit_y != 0
        spec_X = fit_X_326[spec_mask]
        spec_y = fit_y[spec_mask] - 1  # Map {1,2,3} to {0,1,2}
        print(f"    Sub-dataset vessels: {len(spec_y)} (Class 1:{np.sum(spec_y==0)}, 2:{np.sum(spec_y==1)}, 3:{np.sum(spec_y==2)})")

        m123_std = lgb.LGBMClassifier(objective="multiclass", num_class=3, **LGB_BASE_PARAMS)
        m123_std.fit(spec_X, spec_y)
        p_m123_std_in[in_ptr : in_ptr + n_in] = m123_std.predict_proba(inner_X_sorted).astype(np.float32)
        p_m123_std_out[out_ptr : out_ptr + n_out] = m123_std.predict_proba(outer_X_sorted).astype(np.float32)
        del m123_std
        gc.collect()

        # M123 sqrt macro weighting
        sub_counts = np.bincount(spec_y, minlength=3)
        w_sub = np.sqrt(len(spec_y) / (3.0 * sub_counts))
        w_sub /= w_sub.mean()
        cw_sub = {c: float(w_sub[c]) for c in range(3)}

        m123_sqrt = lgb.LGBMClassifier(objective="multiclass", num_class=3, class_weight=cw_sub, **LGB_BASE_PARAMS)
        m123_sqrt.fit(spec_X, spec_y)
        p_m123_sqrt_in[in_ptr : in_ptr + n_in] = m123_sqrt.predict_proba(inner_X_sorted).astype(np.float32)
        p_m123_sqrt_out[out_ptr : out_ptr + n_out] = m123_sqrt.predict_proba(outer_X_sorted).astype(np.float32)
        del m123_sqrt, spec_X, spec_y
        gc.collect()

        # (7) 4-Class Comparison Baselines: lgb_knn_std & lgb_knn_sqrt
        print(f"  [Fold {fold_idx}] Training 4-class Comparison Baselines...")
        clf_std = lgb.LGBMClassifier(objective="multiclass", num_class=4, **LGB_BASE_PARAMS)
        clf_std.fit(fit_X_326, fit_y)
        p_lgb_knn_std_in[in_ptr : in_ptr + n_in] = clf_std.predict_proba(inner_X_sorted).astype(np.float32)
        p_lgb_knn_std_out[out_ptr : out_ptr + n_out] = clf_std.predict_proba(outer_X_sorted).astype(np.float32)
        del clf_std
        gc.collect()

        counts4 = np.bincount(fit_y, minlength=4)
        w4 = np.sqrt(len(fit_y) / (4.0 * counts4))
        w4 /= w4.mean()
        cw4 = {c: float(w4[c]) for c in range(4)}
        clf_sqrt = lgb.LGBMClassifier(objective="multiclass", num_class=4, class_weight=cw4, **LGB_BASE_PARAMS)
        clf_sqrt.fit(fit_X_326, fit_y)
        p_lgb_knn_sqrt_in[in_ptr : in_ptr + n_in] = clf_sqrt.predict_proba(inner_X_sorted).astype(np.float32)
        p_lgb_knn_sqrt_out[out_ptr : out_ptr + n_out] = clf_sqrt.predict_proba(outer_X_sorted).astype(np.float32)
        del clf_sqrt
        gc.collect()

        del fit_X_326, inner_X_sorted, outer_X_sorted
        gc.collect()

        in_ptr += n_in
        out_ptr += n_out
        print(f"  Fold {fold_idx} completed. Progress: in_ptr={in_ptr}, out_ptr={out_ptr}")

    # Build hierarchical and normalized OVR probabilities
    # 1) Hierarchical std: P(0) = 1 - P_spec, P(c) = P_spec * P_M123_std(c-1)
    p_hierarchical_std_in = np.column_stack([
        1.0 - p_spec_gate_in,
        p_spec_gate_in[:, None] * p_m123_std_in
    ]).astype(np.float32)

    p_hierarchical_std_out = np.column_stack([
        1.0 - p_spec_gate_out,
        p_spec_gate_out[:, None] * p_m123_std_out
    ]).astype(np.float32)

    # 2) Hierarchical sqrt: P(0) = 1 - P_spec, P(c) = P_spec * P_M123_sqrt(c-1)
    p_hierarchical_sqrt_in = np.column_stack([
        1.0 - p_spec_gate_in,
        p_spec_gate_in[:, None] * p_m123_sqrt_in
    ]).astype(np.float32)

    p_hierarchical_sqrt_out = np.column_stack([
        1.0 - p_spec_gate_out,
        p_spec_gate_out[:, None] * p_m123_sqrt_out
    ]).astype(np.float32)

    # 3) OVR 4-Class raw & normalized: [1 - P_spec, P_M1, P_M2, P_M3]
    raw_ovr_in = np.column_stack([1.0 - p_spec_gate_in, p_ovr_std_in]).astype(np.float32)
    p_ovr_4class_norm_in = (raw_ovr_in / raw_ovr_in.sum(axis=1, keepdims=True)).astype(np.float32)

    raw_ovr_out = np.column_stack([1.0 - p_spec_gate_out, p_ovr_std_out]).astype(np.float32)
    p_ovr_4class_norm_out = (raw_ovr_out / raw_ovr_out.sum(axis=1, keepdims=True)).astype(np.float32)

    # Save all probabilities to worker_a_probabilities.npz
    prob_path = WORKER_A_DIR / "worker_a_probabilities.npz"
    np.savez_compressed(
        prob_path,
        # Ground truths & IDs
        y_inner=y_inner,
        y_outer=y_outer,
        # Raw Specialist outputs
        p_ovr_std_in=p_ovr_std_in,
        p_ovr_std_out=p_ovr_std_out,
        p_ovr_sqrt_in=p_ovr_sqrt_in,
        p_ovr_sqrt_out=p_ovr_sqrt_out,
        p_spec_gate_in=p_spec_gate_in,
        p_spec_gate_out=p_spec_gate_out,
        p_m123_std_in=p_m123_std_in,
        p_m123_std_out=p_m123_std_out,
        p_m123_sqrt_in=p_m123_sqrt_in,
        p_m123_sqrt_out=p_m123_sqrt_out,
        # Reconstructed 4-class distributions
        p_hierarchical_std_in=p_hierarchical_std_in,
        p_hierarchical_std_out=p_hierarchical_std_out,
        p_hierarchical_sqrt_in=p_hierarchical_sqrt_in,
        p_hierarchical_sqrt_out=p_hierarchical_sqrt_out,
        p_ovr_4class_norm_in=p_ovr_4class_norm_in,
        p_ovr_4class_norm_out=p_ovr_4class_norm_out,
        # Comparison baselines
        p_lgb_knn_std_in=p_lgb_knn_std_in,
        p_lgb_knn_std_out=p_lgb_knn_std_out,
        p_lgb_knn_sqrt_in=p_lgb_knn_sqrt_in,
        p_lgb_knn_sqrt_out=p_lgb_knn_sqrt_out,
    )
    print(f"\n[Worker A] All model probabilities successfully saved to: {prob_path}")

    return {
        "y_inner": y_inner,
        "y_outer": y_outer,
        "p_ovr_std_in": p_ovr_std_in,
        "p_ovr_std_out": p_ovr_std_out,
        "p_ovr_sqrt_in": p_ovr_sqrt_in,
        "p_ovr_sqrt_out": p_ovr_sqrt_out,
        "p_spec_gate_in": p_spec_gate_in,
        "p_spec_gate_out": p_spec_gate_out,
        "p_m123_std_in": p_m123_std_in,
        "p_m123_std_out": p_m123_std_out,
        "p_m123_sqrt_in": p_m123_sqrt_in,
        "p_m123_sqrt_out": p_m123_sqrt_out,
        "p_hierarchical_std_in": p_hierarchical_std_in,
        "p_hierarchical_std_out": p_hierarchical_std_out,
        "p_hierarchical_sqrt_in": p_hierarchical_sqrt_in,
        "p_hierarchical_sqrt_out": p_hierarchical_sqrt_out,
        "p_ovr_4class_norm_in": p_ovr_4class_norm_in,
        "p_ovr_4class_norm_out": p_ovr_4class_norm_out,
        "p_lgb_knn_std_in": p_lgb_knn_std_in,
        "p_lgb_knn_std_out": p_lgb_knn_std_out,
        "p_lgb_knn_sqrt_in": p_lgb_knn_sqrt_in,
        "p_lgb_knn_sqrt_out": p_lgb_knn_sqrt_out,
    }


def predict_ovr_fallback(p_ovr: np.ndarray, tau: Tuple[float, float, float], mode: str = "ratio") -> np.ndarray:
    """Predict 4 classes with Specialist-then-Fallback rule.
    
    p_ovr: shape (N, 3) for classes 1, 2, 3
    tau: (tau_1, tau_2, tau_3)
    mode: 'ratio' (s_c / tau_c), 'diff' (s_c - tau_c), 'raw' (s_c)
    """
    tau_arr = np.array(tau, dtype=np.float32)
    mask_pass = p_ovr >= tau_arr[None, :]  # shape (N, 3)
    any_pass = np.any(mask_pass, axis=1)   # shape (N,)

    preds = np.zeros(len(p_ovr), dtype=np.int64)

    if not np.any(any_pass):
        return preds

    # For vessels where at least one specialist passed threshold
    p_passed = p_ovr[any_pass]
    mask_sub = mask_pass[any_pass]

    if mode == "ratio":
        scores = np.where(mask_sub, p_passed / tau_arr[None, :], -1e9)
    elif mode == "diff":
        scores = np.where(mask_sub, p_passed - tau_arr[None, :], -1e9)
    else:  # raw
        scores = np.where(mask_sub, p_passed, -1e9)

    best_spec = np.argmax(scores, axis=1) + 1  # Map 0,1,2 -> 1,2,3
    preds[any_pass] = best_spec
    return preds


def predict_hierarchical_fallback(p_gate: np.ndarray, p_m123: np.ndarray, tau_gate: float, theta: Tuple[float, float, float] = (1.0, 1.0, 1.0)) -> np.ndarray:
    """Predict 4 classes with 2-Stage Hierarchical Gate + 3-Class Specialist."""
    theta_arr = np.array(theta, dtype=np.float32)
    preds = np.zeros(len(p_gate), dtype=np.int64)

    pass_gate = p_gate >= tau_gate
    if np.any(pass_gate):
        p_sub = p_m123[pass_gate] / theta_arr[None, :]
        best_spec = np.argmax(p_sub, axis=1) + 1
        preds[pass_gate] = best_spec
    return preds


def run_all_experiments(data: Dict[str, np.ndarray]):
    print("\n" + "=" * 80)
    print("=== [Worker A] Step 2: Specialist-then-Fallback Evaluation & Optimization ===")
    print("=" * 80)

    y_in = data["y_inner"]
    y_out = data["y_outer"]

    results_dict = {}

    # -------------------------------------------------------------
    # 0. Benchmark Baselines (Standard 4-class Argmax)
    # -------------------------------------------------------------
    baselines = {
        "Comp0_lgb_knn_std": (data["p_lgb_knn_std_in"], data["p_lgb_knn_std_out"]),
        "Comp0_lgb_knn_sqrt": (data["p_lgb_knn_sqrt_in"], data["p_lgb_knn_sqrt_out"]),
        "Hier_std_raw_argmax": (data["p_hierarchical_std_in"], data["p_hierarchical_std_out"]),
        "Hier_sqrt_raw_argmax": (data["p_hierarchical_sqrt_in"], data["p_hierarchical_sqrt_out"]),
        "OVR_norm_raw_argmax": (data["p_ovr_4class_norm_in"], data["p_ovr_4class_norm_out"]),
    }

    print("\n--- Benchmark Comparison Baselines (Direct Argmax) ---")
    for bname, (p_in, p_out) in baselines.items():
        m_in = compute_metrics(y_in, np.argmax(p_in, axis=1))
        m_out = compute_metrics(y_out, np.argmax(p_out, axis=1))
        results_dict[bname] = {
            "type": "baseline",
            "inner": m_in,
            "outer": m_out,
        }
        print(f"[{bname}]")
        print(f"  INNER: Correct={m_in['correct']}/{m_in['n']} ({m_in['micro_f1']*100:.2f}%), Macro-F1={m_in['macro_f1']:.4f}, TP={m_in['tp']}")
        print(f"  OUTER: Correct={m_out['correct']}/{m_out['n']} ({m_out['micro_f1']*100:.2f}%), Macro-F1={m_out['macro_f1']:.4f}, TP={m_out['tp']} | TP0>={2389}:{m_out['rule_tp0_pass']} | TP3>={90}:{m_out['rule_tp3_pass']}")

    # -------------------------------------------------------------
    # Experiment A1: OVR Specialist Gate + Fallback to Class 0
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("--- Experiment A1: OVR Specialist Gate + Fallback to Class 0 ---")
    print("-" * 70)

    # Grid search on INNER OOF
    tau1_vals = np.linspace(0.20, 0.60, 9) # 9
    tau2_vals = np.linspace(0.15, 0.50, 8) # 8
    tau3_vals = np.linspace(0.10, 0.45, 8) # 8

    # Test both p_ovr_std and p_ovr_sqrt
    ovr_variants = {
        "A1_ovr_std": (data["p_ovr_std_in"], data["p_ovr_std_out"]),
        "A1_ovr_sqrt": (data["p_ovr_sqrt_in"], data["p_ovr_sqrt_out"]),
    }

    for var_name, (p_in, p_out) in ovr_variants.items():
        print(f"\n[Tuning {var_name}] Grid searching on INNER (2,361 vessels)...")
        best_acc_cand = None
        best_acc_val = -1

        best_prot_cand = None
        best_prot_val = -1

        for mode in ["ratio", "diff", "raw"]:
            for t1 in tau1_vals:
                for t2 in tau2_vals:
                    for t3 in tau3_vals:
                        tau = (float(t1), float(t2), float(t3))
                        pred_in = predict_ovr_fallback(p_in, tau, mode=mode)
                        m_in = compute_metrics(y_in, pred_in)

                        # (1) Pure Accuracy
                        if m_in["correct"] > best_acc_val:
                            best_acc_val = m_in["correct"]
                            best_acc_cand = {
                                "tau": tau,
                                "mode": mode,
                                "inner_metrics": m_in,
                            }

                        # (2) Protection Satisfied (INNER TP0 >= 957, TP3 >= 36)
                        if m_in["rule_tp0_pass"] and m_in["rule_tp3_pass"]:
                            if m_in["correct"] > best_prot_val:
                                best_prot_val = m_in["correct"]
                                best_prot_cand = {
                                    "tau": tau,
                                    "mode": mode,
                                    "inner_metrics": m_in,
                                }

        # Evaluate best found points on OUTER (5,897)
        print(f"  Best Accuracy Point on INNER: Correct={best_acc_cand['inner_metrics']['correct']}/{len(y_in)} ({best_acc_cand['inner_metrics']['micro_f1']*100:.2f}%)")
        print(f"    Params: tau={best_acc_cand['tau']}, mode={best_acc_cand['mode']}")
        pred_out_acc = predict_ovr_fallback(p_out, best_acc_cand["tau"], mode=best_acc_cand["mode"])
        m_out_acc = compute_metrics(y_out, pred_out_acc)
        print(f"    -> OUTER: Correct={m_out_acc['correct']}/{len(y_out)} ({m_out_acc['micro_f1']*100:.2f}%), Macro-F1={m_out_acc['macro_f1']:.4f}, TP={m_out_acc['tp']} | TP0 Pass:{m_out_acc['rule_tp0_pass']}, TP3 Pass:{m_out_acc['rule_tp3_pass']}")

        results_dict[f"{var_name}_acc_optimal"] = {
            "type": "A1_OVR_Fallback",
            "tau": best_acc_cand["tau"],
            "mode": best_acc_cand["mode"],
            "inner": best_acc_cand["inner_metrics"],
            "outer": m_out_acc,
        }

        if best_prot_cand:
            print(f"  Best Protection-Satisfied Point on INNER: Correct={best_prot_cand['inner_metrics']['correct']}/{len(y_in)} ({best_prot_cand['inner_metrics']['micro_f1']*100:.2f}%)")
            print(f"    Params: tau={best_prot_cand['tau']}, mode={best_prot_cand['mode']}")
            pred_out_prot = predict_ovr_fallback(p_out, best_prot_cand["tau"], mode=best_prot_cand["mode"])
            m_out_prot = compute_metrics(y_out, pred_out_prot)
            print(f"    -> OUTER: Correct={m_out_prot['correct']}/{len(y_out)} ({m_out_prot['micro_f1']*100:.2f}%), Macro-F1={m_out_prot['macro_f1']:.4f}, TP={m_out_prot['tp']} | TP0 Pass:{m_out_prot['rule_tp0_pass']}, TP3 Pass:{m_out_prot['rule_tp3_pass']}")

            results_dict[f"{var_name}_protected"] = {
                "type": "A1_OVR_Fallback",
                "tau": best_prot_cand["tau"],
                "mode": best_prot_cand["mode"],
                "inner": best_prot_cand["inner_metrics"],
                "outer": m_out_prot,
            }

    # -------------------------------------------------------------
    # Experiment A2: 2-Stage Hierarchical Gate + 3-Class Specialist
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("--- Experiment A2: 2-Stage Hierarchical Gate + 3-Class Specialist ---")
    print("-" * 70)

    # Strategy A2-1: Gate Threshold tau_gate + (M123 Specialist)
    tau_gate_vals = np.linspace(0.30, 0.70, 41)

    hier_variants = {
        "A2_hier_std": (data["p_spec_gate_in"], data["p_m123_std_in"], data["p_spec_gate_out"], data["p_m123_std_out"]),
        "A2_hier_sqrt": (data["p_spec_gate_in"], data["p_m123_sqrt_in"], data["p_spec_gate_out"], data["p_m123_sqrt_out"]),
    }

    for hname, (g_in, m123_in, g_out, m123_out) in hier_variants.items():
        print(f"\n[Tuning {hname}] Searching optimal tau_gate and specialist multipliers on INNER...")
        best_acc_cand = None
        best_acc_val = -1

        best_prot_cand = None
        best_prot_val = -1

        # Search tau_gate with default theta=(1,1,1) and with Chaenakgi boost theta=(1, 1, theta3)
        for tg in tau_gate_vals:
            for th3 in [1.0, 0.8, 0.6, 0.5, 0.4]: # Lower theta3 means higher chaenakgi boost
                theta = (1.0, 1.0, float(th3))
                pred_in = predict_hierarchical_fallback(g_in, m123_in, float(tg), theta)
                m_in = compute_metrics(y_in, pred_in)

                if m_in["correct"] > best_acc_val:
                    best_acc_val = m_in["correct"]
                    best_acc_cand = {
                        "tau_gate": float(tg),
                        "theta": theta,
                        "inner_metrics": m_in,
                    }

                if m_in["rule_tp0_pass"] and m_in["rule_tp3_pass"]:
                    if m_in["correct"] > best_prot_val:
                        best_prot_val = m_in["correct"]
                        best_prot_cand = {
                            "tau_gate": float(tg),
                            "theta": theta,
                            "inner_metrics": m_in,
                        }

        # Evaluate on OUTER
        print(f"  Best Accuracy Point on INNER: Correct={best_acc_cand['inner_metrics']['correct']}/{len(y_in)} ({best_acc_cand['inner_metrics']['micro_f1']*100:.2f}%)")
        print(f"    Params: tau_gate={best_acc_cand['tau_gate']:.3f}, theta={best_acc_cand['theta']}")
        pred_out_acc = predict_hierarchical_fallback(g_out, m123_out, best_acc_cand["tau_gate"], best_acc_cand["theta"])
        m_out_acc = compute_metrics(y_out, pred_out_acc)
        print(f"    -> OUTER: Correct={m_out_acc['correct']}/{len(y_out)} ({m_out_acc['micro_f1']*100:.2f}%), Macro-F1={m_out_acc['macro_f1']:.4f}, TP={m_out_acc['tp']} | TP0 Pass:{m_out_acc['rule_tp0_pass']}, TP3 Pass:{m_out_acc['rule_tp3_pass']}")

        results_dict[f"{hname}_acc_optimal"] = {
            "type": "A2_Hierarchical_Fallback",
            "tau_gate": best_acc_cand["tau_gate"],
            "theta": best_acc_cand["theta"],
            "inner": best_acc_cand["inner_metrics"],
            "outer": m_out_acc,
        }

        if best_prot_cand:
            print(f"  Best Protection-Satisfied Point on INNER: Correct={best_prot_cand['inner_metrics']['correct']}/{len(y_in)} ({best_prot_cand['inner_metrics']['micro_f1']*100:.2f}%)")
            print(f"    Params: tau_gate={best_prot_cand['tau_gate']:.3f}, theta={best_prot_cand['theta']}")
            pred_out_prot = predict_hierarchical_fallback(g_out, m123_out, best_prot_cand["tau_gate"], best_prot_cand["theta"])
            m_out_prot = compute_metrics(y_out, pred_out_prot)
            print(f"    -> OUTER: Correct={m_out_prot['correct']}/{len(y_out)} ({m_out_prot['micro_f1']*100:.2f}%), Macro-F1={m_out_prot['macro_f1']:.4f}, TP={m_out_prot['tp']} | TP0 Pass:{m_out_prot['rule_tp0_pass']}, TP3 Pass:{m_out_prot['rule_tp3_pass']}")

            results_dict[f"{hname}_protected"] = {
                "type": "A2_Hierarchical_Fallback",
                "tau_gate": best_prot_cand["tau_gate"],
                "theta": best_prot_cand["theta"],
                "inner": best_prot_cand["inner_metrics"],
                "outer": m_out_prot,
            }

    # -------------------------------------------------------------
    # Experiment A3: Blending 4-Class Baseline + Specialist Models
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print("--- Experiment A3: Blending 4-Class Baseline + Specialist Probability Models ---")
    print("-" * 70)

    # Blend baseline 4-class std with Hierarchical std and OVR norm
    p_base_in = data["p_lgb_knn_std_in"]
    p_base_out = data["p_lgb_knn_std_out"]

    blend_targets = {
        "A3_blend_base_and_hier_std": (data["p_hierarchical_std_in"], data["p_hierarchical_std_out"]),
        "A3_blend_base_and_ovr_norm": (data["p_ovr_4class_norm_in"], data["p_ovr_4class_norm_out"]),
    }

    alpha_grid = np.linspace(0.05, 0.50, 10)

    for bname, (p_cand_in, p_cand_out) in blend_targets.items():
        print(f"\n[Evaluating {bname}] Searching optimal alpha on INNER...")
        best_acc_cand = None
        best_acc_val = -1

        best_prot_cand = None
        best_prot_val = -1

        for a in alpha_grid:
            alpha = float(a)
            p_blended_in = (1.0 - alpha) * p_base_in + alpha * p_cand_in
            pred_in = np.argmax(p_blended_in, axis=1)
            m_in = compute_metrics(y_in, pred_in)

            if m_in["correct"] > best_acc_val:
                best_acc_val = m_in["correct"]
                best_acc_cand = {"alpha": alpha, "inner_metrics": m_in}

            # Also check if calibration multiplier [m0, 1, 1, m3] satisfies protection
            for m0 in [1.0, 1.05, 1.10]:
                for m3 in [1.0, 1.3, 1.6, 2.0]:
                    calib_p_in = p_blended_in * np.array([m0, 1.0, 1.0, m3], dtype=np.float32)
                    pred_cal_in = np.argmax(calib_p_in, axis=1)
                    mc_in = compute_metrics(y_in, pred_cal_in)
                    if mc_in["rule_tp0_pass"] and mc_in["rule_tp3_pass"]:
                        if mc_in["correct"] > best_prot_val:
                            best_prot_val = mc_in["correct"]
                            best_prot_cand = {
                                "alpha": alpha,
                                "multipliers": [m0, 1.0, 1.0, m3],
                                "inner_metrics": mc_in,
                            }

        # Evaluate best on OUTER
        print(f"  Best Accuracy Point on INNER: Correct={best_acc_cand['inner_metrics']['correct']}/{len(y_in)} ({best_acc_cand['inner_metrics']['micro_f1']*100:.2f}%)")
        print(f"    Params: alpha={best_acc_cand['alpha']:.2f}")
        p_blended_out = (1.0 - best_acc_cand["alpha"]) * p_base_out + best_acc_cand["alpha"] * p_cand_out
        pred_out_acc = np.argmax(p_blended_out, axis=1)
        m_out_acc = compute_metrics(y_out, pred_out_acc)
        print(f"    -> OUTER: Correct={m_out_acc['correct']}/{len(y_out)} ({m_out_acc['micro_f1']*100:.2f}%), Macro-F1={m_out_acc['macro_f1']:.4f}, TP={m_out_acc['tp']} | TP0 Pass:{m_out_acc['rule_tp0_pass']}, TP3 Pass:{m_out_acc['rule_tp3_pass']}")

        results_dict[f"{bname}_acc_optimal"] = {
            "type": "A3_Blending",
            "alpha": best_acc_cand["alpha"],
            "inner": best_acc_cand["inner_metrics"],
            "outer": m_out_acc,
        }

        if best_prot_cand:
            print(f"  Best Protected Point on INNER: Correct={best_prot_cand['inner_metrics']['correct']}/{len(y_in)} ({best_prot_cand['inner_metrics']['micro_f1']*100:.2f}%)")
            print(f"    Params: alpha={best_prot_cand['alpha']:.2f}, multipliers={best_prot_cand['multipliers']}")
            p_blended_out_prot = (1.0 - best_prot_cand["alpha"]) * p_base_out + best_prot_cand["alpha"] * p_cand_out
            cal_out = p_blended_out_prot * np.array(best_prot_cand["multipliers"], dtype=np.float32)
            pred_out_prot = np.argmax(cal_out, axis=1)
            m_out_prot = compute_metrics(y_out, pred_out_prot)
            print(f"    -> OUTER: Correct={m_out_prot['correct']}/{len(y_out)} ({m_out_prot['micro_f1']*100:.2f}%), Macro-F1={m_out_prot['macro_f1']:.4f}, TP={m_out_prot['tp']} | TP0 Pass:{m_out_prot['rule_tp0_pass']}, TP3 Pass:{m_out_prot['rule_tp3_pass']}")

            results_dict[f"{bname}_protected"] = {
                "type": "A3_Blending",
                "alpha": best_prot_cand["alpha"],
                "multipliers": best_prot_cand["multipliers"],
                "inner": best_prot_cand["inner_metrics"],
                "outer": m_out_prot,
            }

    # Save results to json
    results_json_path = WORKER_A_DIR / "worker_a_results.json"
    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2, ensure_ascii=False)
    print(f"\n[Worker A] All experimental results saved to: {results_json_path}")

    return results_dict


if __name__ == "__main__":
    t_start = time.perf_counter()
    data = train_and_extract_all_probabilities()
    results = run_all_experiments(data)
    elapsed = time.perf_counter() - t_start
    print(f"\n=== Worker A Execution Complete in {elapsed:.1f}s ===")
