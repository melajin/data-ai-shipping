"""Track 2 S2 Segment Cross-Fitting and Gate Evaluation Script."""
from __future__ import annotations

import datetime as dt
import gc
import json
import os
from pathlib import Path
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from resource_check import record_resource_check
from s2_models import (
    N_CLASSES,
    CLASS_NAMES,
    sqrt_sample_weights,
    cross_fit_segment_model,
    aggregate_vessel_features,
    metrics,
)

TRACK_DIR = Path(__file__).resolve().parent
ARTIFACTS_EXP01 = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
SEGMENTS_PARQUET = TRACK_DIR / "vessel_day_segments.parquet"
RESULTS_JSON = TRACK_DIR / "track2_results.json"
PROBABILITIES_NPZ = TRACK_DIR / "probabilities_track2.npz"

# Frozen baseline reference: LightGBM_sqrt_macro seed42
# 3,476 / 5,897 = 0.589452, TP = [2389, 889, 108, 90]
FROZEN_BASELINE_CORRECT = 3476
FROZEN_BASELINE_MICRO = 3476 / 5897
FROZEN_BASELINE_TP = [2389, 889, 108, 90]

# Standard LightGBM hyperparameters (matching round_025 / exp01)
LGBM_PARAMS = {
    "objective": "multiclass",
    "num_class": N_CLASSES,
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "colsample_bytree": 0.7,
    "subsample": 0.8,
    "subsample_freq": 1,
    "random_state": 42,
    "n_jobs": 1,
    "verbose": -1,
}


def load_fold_data(fold: int = 0) -> dict:
    """Load 304 features, labels, and roles from exp01 fold artifact."""
    npz_path = ARTIFACTS_EXP01 / f"fold_{fold}_features.npz"
    with np.load(npz_path, allow_pickle=False) as bundle:
        X = np.asarray(bundle["X"], dtype=np.float32)
        y = np.asarray(bundle["y"], dtype=np.int64)
        rfid_ids = bundle["rfid_ids"].astype(str)
        roles = bundle["roles"].astype(str)
        names = bundle["feature_names"].astype(str).tolist()
    return {
        "X": X,
        "y": y,
        "rfid_ids": rfid_ids,
        "roles": roles,
        "feature_names": names,
    }


def run_phase1_gate_4cv(segments_df: pd.DataFrame) -> dict:
    """
    Phase 1: Fold 0 FIT internal 4-CV diagnostic gate.
    Evaluates 304 baseline vs 304 + S2 (335 features) with zero leakage.
    Within each of the 4 CV folds, S2 cross-fitting is done strictly on CV train vessels!
    """
    record_resource_check("phase1_gate_4cv_start", expected_peak_mb=350.0)
    print("=" * 70)
    print("PHASE 1: Fold 0 FIT (3,144 vessels) Internal 4-CV Diagnostic Gate")
    print("=" * 70)

    f0_data = load_fold_data(0)
    fit_mask = f0_data["roles"] == "FIT"
    X_fit = f0_data["X"][fit_mask]
    y_fit = f0_data["y"][fit_mask]
    ids_fit = f0_data["rfid_ids"][fit_mask]
    n_fit = len(y_fit)
    assert n_fit == 3144, f"Expected 3144 FIT rows, got {n_fit}"

    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=42)

    # 1. Baseline 304 features (standard & sqrt_macro)
    preds_base_std = np.full(n_fit, -1, dtype=np.int64)
    probs_base_std = np.zeros((n_fit, N_CLASSES), dtype=np.float32)
    preds_base_sqrt = np.full(n_fit, -1, dtype=np.int64)
    probs_base_sqrt = np.zeros((n_fit, N_CLASSES), dtype=np.float32)

    # 2. Candidate 304 + S2 (335 features) (standard & sqrt_macro)
    preds_cand_std = np.full(n_fit, -1, dtype=np.int64)
    probs_cand_std = np.zeros((n_fit, N_CLASSES), dtype=np.float32)
    preds_cand_sqrt = np.full(n_fit, -1, dtype=np.int64)
    probs_cand_sqrt = np.zeros((n_fit, N_CLASSES), dtype=np.float32)

    cv_folds_detail = []

    for cv_fold, (tr_idx, va_idx) in enumerate(skf.split(X_fit, y_fit)):
        record_resource_check(f"gate_cv_fold_{cv_fold}_start", expected_peak_mb=350.0)
        t_fold_start = time.time()
        print(f"\n--- Gate CV Fold {cv_fold + 1} / 4 (Train: {len(tr_idx)}, Val: {len(va_idx)}) ---")

        # Step A: Baseline fit on 304 features
        clf_base_std = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_base_std.fit(X_fit[tr_idx], y_fit[tr_idx])
        p_base_std = clf_base_std.predict_proba(X_fit[va_idx]).astype(np.float32)
        probs_base_std[va_idx] = p_base_std
        preds_base_std[va_idx] = np.argmax(p_base_std, axis=1)

        clf_base_sqrt = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_base_sqrt.fit(X_fit[tr_idx], y_fit[tr_idx], sample_weight=sqrt_sample_weights(y_fit[tr_idx]))
        p_base_sqrt = clf_base_sqrt.predict_proba(X_fit[va_idx]).astype(np.float32)
        probs_base_sqrt[va_idx] = p_base_sqrt
        preds_base_sqrt[va_idx] = np.argmax(p_base_sqrt, axis=1)

        del clf_base_std, clf_base_sqrt
        gc.collect()

        # Step B: S2 Segment Cross-Fitting strictly on CV train vessels
        tr_vids_set = set(ids_fit[tr_idx].astype(np.int32))
        va_vids_set = set(ids_fit[va_idx].astype(np.int32))

        tr_seg_df = segments_df[segments_df["id"].isin(tr_vids_set)].copy()
        va_seg_df = segments_df[segments_df["id"].isin(va_vids_set)].copy()

        # Run 5-inner-fold segment model on tr_seg_df, predict on va_seg_df
        oof_seg_tr, eval_seg_va, seg_meta = cross_fit_segment_model(
            train_segments_df=tr_seg_df,
            eval_segments_df=va_seg_df,
            n_inner_splits=5,
            seed=42 + cv_fold * 10,
            use_sqrt_weight=False,
            stage_name=f"gate_cv{cv_fold}_segment",
        )

        # Aggregate vessel features
        s2_tr, s2_names = aggregate_vessel_features(tr_seg_df, oof_seg_tr, ids_fit[tr_idx])
        s2_va, _ = aggregate_vessel_features(va_seg_df, eval_seg_va, ids_fit[va_idx])

        del tr_seg_df, va_seg_df, oof_seg_tr, eval_seg_va
        gc.collect()

        # Build candidate 335-column matrices
        X_cand_tr = np.hstack([X_fit[tr_idx], s2_tr])
        X_cand_va = np.hstack([X_fit[va_idx], s2_va])

        # Train candidate final LightGBM
        clf_cand_std = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_cand_std.fit(X_cand_tr, y_fit[tr_idx])
        p_cand_std = clf_cand_std.predict_proba(X_cand_va).astype(np.float32)
        probs_cand_std[va_idx] = p_cand_std
        preds_cand_std[va_idx] = np.argmax(p_cand_std, axis=1)

        clf_cand_sqrt = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_cand_sqrt.fit(X_cand_tr, y_fit[tr_idx], sample_weight=sqrt_sample_weights(y_fit[tr_idx]))
        p_cand_sqrt = clf_cand_sqrt.predict_proba(X_cand_va).astype(np.float32)
        probs_cand_sqrt[va_idx] = p_cand_sqrt
        preds_cand_sqrt[va_idx] = np.argmax(p_cand_sqrt, axis=1)

        fold_m_base_std = metrics(y_fit[va_idx], preds_base_std[va_idx])
        fold_m_cand_std = metrics(y_fit[va_idx], preds_cand_std[va_idx])
        fold_m_base_sqrt = metrics(y_fit[va_idx], preds_base_sqrt[va_idx])
        fold_m_cand_sqrt = metrics(y_fit[va_idx], preds_cand_sqrt[va_idx])

        print(f"CV{cv_fold} Standard: Base {fold_m_base_std['correct']}/{len(va_idx)} ({fold_m_base_std['micro_f1']:.4f}) -> "
              f"Cand {fold_m_cand_std['correct']}/{len(va_idx)} ({fold_m_cand_std['micro_f1']:.4f}) | Delta: {fold_m_cand_std['correct'] - fold_m_base_std['correct']:+d}")
        print(f"CV{cv_fold} SqrtMacro: Base {fold_m_base_sqrt['correct']}/{len(va_idx)} ({fold_m_base_sqrt['micro_f1']:.4f}) -> "
              f"Cand {fold_m_cand_sqrt['correct']}/{len(va_idx)} ({fold_m_cand_sqrt['micro_f1']:.4f}) | Delta: {fold_m_cand_sqrt['correct'] - fold_m_base_sqrt['correct']:+d}")

        cv_folds_detail.append({
            "cv_fold": cv_fold,
            "train_vessels": len(tr_idx),
            "val_vessels": len(va_idx),
            "segment_meta": seg_meta,
            "base_std": fold_m_base_std,
            "cand_std": fold_m_cand_std,
            "base_sqrt": fold_m_base_sqrt,
            "cand_sqrt": fold_m_cand_sqrt,
            "elapsed_seconds": round(time.time() - t_fold_start, 2),
        })

        del clf_cand_std, clf_cand_sqrt, X_cand_tr, X_cand_va, s2_tr, s2_va
        gc.collect()

    m_base_std = metrics(y_fit, preds_base_std)
    m_cand_std = metrics(y_fit, preds_cand_std)
    m_base_sqrt = metrics(y_fit, preds_base_sqrt)
    m_cand_sqrt = metrics(y_fit, preds_cand_sqrt)

    delta_std = m_cand_std["correct"] - m_base_std["correct"]
    delta_sqrt = m_cand_sqrt["correct"] - m_base_sqrt["correct"]

    gate_result = {
        "status": "gate_evaluation_complete",
        "n_fit_vessels": n_fit,
        "feature_schema": {
            "baseline_columns": 304,
            "s2_columns": 31,
            "candidate_columns": 335,
            "s2_feature_names": s2_names,
        },
        "metrics_standard": {
            "baseline": m_base_std,
            "candidate": m_cand_std,
            "delta_correct": int(delta_std),
            "delta_micro": float(m_cand_std["micro_f1"] - m_base_std["micro_f1"]),
            "delta_macro": float(m_cand_std["macro_f1"] - m_base_std["macro_f1"]),
        },
        "metrics_sqrt_macro": {
            "baseline": m_base_sqrt,
            "candidate": m_cand_sqrt,
            "delta_correct": int(delta_sqrt),
            "delta_micro": float(m_cand_sqrt["micro_f1"] - m_base_sqrt["micro_f1"]),
            "delta_macro": float(m_cand_sqrt["macro_f1"] - m_base_sqrt["macro_f1"]),
        },
        "cv_folds_detail": cv_folds_detail,
        "gate_pass_rule": "candidate_correct - baseline_correct >= 16 (+0.5%p)",
        "gate_pass_standard": bool(delta_std >= 16),
        "gate_pass_sqrt_macro": bool(delta_sqrt >= 16),
    }

    print("\n" + "=" * 50)
    print("PHASE 1 GATE SUMMARY (FIT 3,144 CV):")
    print(f"Standard Multiclass : Base {m_base_std['correct']}/3144 ({m_base_std['micro_f1']:.6f}) -> Cand {m_cand_std['correct']}/3144 ({m_cand_std['micro_f1']:.6f}) | Delta: {delta_std:+d}")
    print(f"SqrtMacro Multiclass: Base {m_base_sqrt['correct']}/3144 ({m_base_sqrt['micro_f1']:.6f}) -> Cand {m_cand_sqrt['correct']}/3144 ({m_cand_sqrt['micro_f1']:.6f}) | Delta: {delta_sqrt:+d}")
    print(f"Gate Pass (>= +16)  : Standard={gate_result['gate_pass_standard']}, SqrtMacro={gate_result['gate_pass_sqrt_macro']}")
    print("=" * 50 + "\n")

    record_resource_check("phase1_gate_4cv_complete", expected_peak_mb=100.0)
    return gate_result


def run_phase2_full_3fold(segments_df: pd.DataFrame) -> dict:
    """
    Phase 2: Full 3-Fold OUTER (5,897 vessels) and INNER (787 vessels) evaluation.
    For each fold f in {0, 1, 2}:
    - S2 segment models trained on fold f FIT vessels.
    - S2 features generated via OOF for FIT, and ensemble for INNER/OUTER.
    - Final LightGBM trained on FIT (335 cols), evaluated on INNER and OUTER.
    """
    record_resource_check("phase2_full_3fold_start", expected_peak_mb=350.0)
    print("=" * 70)
    print("PHASE 2: Full 3-Fold OUTER (5,897 vessels) and INNER Evaluation")
    print("=" * 70)

    # Placeholders for outer predictions across 3 folds
    # Outer sizes: fold0: 1966, fold1: 1966, fold2: 1965 (total 5,897)
    outer_vessel_ids: list[str] = []
    outer_y_true: list[int] = []
    outer_preds_std: list[int] = []
    outer_probs_std: list[np.ndarray] = []
    outer_preds_sqrt: list[int] = []
    outer_probs_sqrt: list[np.ndarray] = []

    # Baseline outer predictions
    base_outer_preds_std: list[int] = []
    base_outer_probs_std: list[np.ndarray] = []
    base_outer_preds_sqrt: list[int] = []
    base_outer_probs_sqrt: list[np.ndarray] = []

    inner_records = []
    fold_details = []

    for fold_idx in range(3):
        record_resource_check(f"outer_fold_{fold_idx}_start", expected_peak_mb=350.0)
        t_fold_start = time.time()
        print(f"\n>>> Running External Fold {fold_idx} / 3 <<<")

        fdata = load_fold_data(fold_idx)
        X_all = fdata["X"]
        y_all = fdata["y"]
        rfid_ids = fdata["rfid_ids"]
        roles = fdata["roles"]

        fit_mask = roles == "FIT"
        inner_mask = roles == "INNER"
        outer_mask = roles == "OUTER"

        print(f"Fold {fold_idx} counts: FIT={fit_mask.sum()}, INNER={inner_mask.sum()}, OUTER={outer_mask.sum()}")

        # 1. Baseline Model on 304 features
        clf_base_std = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_base_std.fit(X_all[fit_mask], y_all[fit_mask])
        p_base_in_std = clf_base_std.predict_proba(X_all[inner_mask]).astype(np.float32)
        p_base_out_std = clf_base_std.predict_proba(X_all[outer_mask]).astype(np.float32)

        clf_base_sqrt = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_base_sqrt.fit(X_all[fit_mask], y_all[fit_mask], sample_weight=sqrt_sample_weights(y_all[fit_mask]))
        p_base_in_sqrt = clf_base_sqrt.predict_proba(X_all[inner_mask]).astype(np.float32)
        p_base_out_sqrt = clf_base_sqrt.predict_proba(X_all[outer_mask]).astype(np.float32)

        del clf_base_std, clf_base_sqrt
        gc.collect()

        # 2. Candidate S2 Segment Cross-Fitting
        fit_vids_set = set(rfid_ids[fit_mask].astype(np.int32))
        eval_vids_set = set(rfid_ids[~fit_mask].astype(np.int32))

        fit_seg_df = segments_df[segments_df["id"].isin(fit_vids_set)].copy()
        eval_seg_df = segments_df[segments_df["id"].isin(eval_vids_set)].copy()

        # S2 cross-fitting on FIT, predict on eval (INNER + OUTER)
        oof_seg_fit, eval_seg_probs, seg_meta = cross_fit_segment_model(
            train_segments_df=fit_seg_df,
            eval_segments_df=eval_seg_df,
            n_inner_splits=5,
            seed=42 + fold_idx * 100,
            use_sqrt_weight=False,
            stage_name=f"outer_fold{fold_idx}_segment",
        )

        # Aggregate S2 features
        s2_fit, s2_names = aggregate_vessel_features(fit_seg_df, oof_seg_fit, rfid_ids[fit_mask])
        s2_eval, _ = aggregate_vessel_features(eval_seg_df, eval_seg_probs, rfid_ids[~fit_mask])

        # Separate eval into INNER and OUTER
        eval_roles = roles[~fit_mask]
        in_eval_mask = eval_roles == "INNER"
        out_eval_mask = eval_roles == "OUTER"

        s2_inner = s2_eval[in_eval_mask]
        s2_outer = s2_eval[out_eval_mask]

        del fit_seg_df, eval_seg_df, oof_seg_fit, eval_seg_probs, s2_eval
        gc.collect()

        # Build candidate 335 feature matrices
        X_cand_fit = np.hstack([X_all[fit_mask], s2_fit])
        X_cand_inner = np.hstack([X_all[inner_mask], s2_inner])
        X_cand_outer = np.hstack([X_all[outer_mask], s2_outer])

        # Train Candidate LightGBM
        clf_cand_std = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_cand_std.fit(X_cand_fit, y_all[fit_mask])
        p_cand_in_std = clf_cand_std.predict_proba(X_cand_inner).astype(np.float32)
        p_cand_out_std = clf_cand_std.predict_proba(X_cand_outer).astype(np.float32)

        clf_cand_sqrt = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf_cand_sqrt.fit(X_cand_fit, y_all[fit_mask], sample_weight=sqrt_sample_weights(y_all[fit_mask]))
        p_cand_in_sqrt = clf_cand_sqrt.predict_proba(X_cand_inner).astype(np.float32)
        p_cand_out_sqrt = clf_cand_sqrt.predict_proba(X_cand_outer).astype(np.float32)

        # INNER metrics
        m_in_base_std = metrics(y_all[inner_mask], np.argmax(p_base_in_std, axis=1))
        m_in_cand_std = metrics(y_all[inner_mask], np.argmax(p_cand_in_std, axis=1))
        m_in_base_sqrt = metrics(y_all[inner_mask], np.argmax(p_base_in_sqrt, axis=1))
        m_in_cand_sqrt = metrics(y_all[inner_mask], np.argmax(p_cand_in_sqrt, axis=1))

        # OUTER fold metrics
        m_out_base_std = metrics(y_all[outer_mask], np.argmax(p_base_out_std, axis=1))
        m_out_cand_std = metrics(y_all[outer_mask], np.argmax(p_cand_out_std, axis=1))
        m_out_base_sqrt = metrics(y_all[outer_mask], np.argmax(p_base_out_sqrt, axis=1))
        m_out_cand_sqrt = metrics(y_all[outer_mask], np.argmax(p_cand_out_sqrt, axis=1))

        print(f"Fold {fold_idx} INNER: Base_std={m_in_base_std['correct']}/787 ({m_in_base_std['micro_f1']:.4f}) -> Cand_std={m_in_cand_std['correct']}/787 ({m_in_cand_std['micro_f1']:.4f}) | Delta: {m_in_cand_std['correct'] - m_in_base_std['correct']:+d}")
        print(f"Fold {fold_idx} INNER: Base_sqrt={m_in_base_sqrt['correct']}/787 ({m_in_base_sqrt['micro_f1']:.4f}) -> Cand_sqrt={m_in_cand_sqrt['correct']}/787 ({m_in_cand_sqrt['micro_f1']:.4f}) | Delta: {m_in_cand_sqrt['correct'] - m_in_base_sqrt['correct']:+d}")
        print(f"Fold {fold_idx} OUTER: Base_std={m_out_base_std['correct']}/{outer_mask.sum()} ({m_out_base_std['micro_f1']:.4f}) -> Cand_std={m_out_cand_std['correct']}/{outer_mask.sum()} ({m_out_cand_std['micro_f1']:.4f}) | Delta: {m_out_cand_std['correct'] - m_out_base_std['correct']:+d}")
        print(f"Fold {fold_idx} OUTER: Base_sqrt={m_out_base_sqrt['correct']}/{outer_mask.sum()} ({m_out_base_sqrt['micro_f1']:.4f}) -> Cand_sqrt={m_out_cand_sqrt['correct']}/{outer_mask.sum()} ({m_out_cand_sqrt['micro_f1']:.4f}) | Delta: {m_out_cand_sqrt['correct'] - m_out_base_sqrt['correct']:+d}")

        inner_records.append({
            "fold": fold_idx,
            "base_std": m_in_base_std,
            "cand_std": m_in_cand_std,
            "base_sqrt": m_in_base_sqrt,
            "cand_sqrt": m_in_cand_sqrt,
        })

        fold_details.append({
            "fold": fold_idx,
            "segment_meta": seg_meta,
            "outer_base_std": m_out_base_std,
            "outer_cand_std": m_out_cand_std,
            "outer_base_sqrt": m_out_base_sqrt,
            "outer_cand_sqrt": m_out_cand_sqrt,
            "elapsed_seconds": round(time.time() - t_fold_start, 2),
        })

        # Append OUTER predictions to global accumulator
        outer_vessel_ids.extend(rfid_ids[outer_mask].tolist())
        outer_y_true.extend(y_all[outer_mask].tolist())
        outer_preds_std.extend(np.argmax(p_cand_out_std, axis=1).tolist())
        outer_probs_std.append(p_cand_out_std)
        outer_preds_sqrt.extend(np.argmax(p_cand_out_sqrt, axis=1).tolist())
        outer_probs_sqrt.append(p_cand_out_sqrt)

        base_outer_preds_std.extend(np.argmax(p_base_out_std, axis=1).tolist())
        base_outer_probs_std.append(p_base_out_std)
        base_outer_preds_sqrt.extend(np.argmax(p_base_out_sqrt, axis=1).tolist())
        base_outer_probs_sqrt.append(p_base_out_sqrt)

        del clf_cand_std, clf_cand_sqrt, X_cand_fit, X_cand_inner, X_cand_outer, s2_fit, s2_inner, s2_outer
        gc.collect()

    # Concatenate all 3 folds to cover 5,897 vessels
    all_y_true = np.array(outer_y_true, dtype=np.int64)
    all_cand_preds_std = np.array(outer_preds_std, dtype=np.int64)
    all_cand_probs_std = np.vstack(outer_probs_std)
    all_cand_preds_sqrt = np.array(outer_preds_sqrt, dtype=np.int64)
    all_cand_probs_sqrt = np.vstack(outer_probs_sqrt)

    all_base_preds_std = np.array(base_outer_preds_std, dtype=np.int64)
    all_base_probs_std = np.vstack(base_outer_probs_std)
    all_base_preds_sqrt = np.array(base_outer_preds_sqrt, dtype=np.int64)
    all_base_probs_sqrt = np.vstack(base_outer_probs_sqrt)

    assert len(all_y_true) == 5897, f"Expected 5897 total OUTER vessels, got {len(all_y_true)}"

    # Global 5,897 OUTER metrics
    m_global_base_std = metrics(all_y_true, all_base_preds_std)
    m_global_cand_std = metrics(all_y_true, all_cand_preds_std)
    m_global_base_sqrt = metrics(all_y_true, all_base_preds_sqrt)
    m_global_cand_sqrt = metrics(all_y_true, all_cand_preds_sqrt)

    # Class 0 and Class 3 protection check
    # Protection rules: class 0 TP >= 2389, class 3 TP >= 90
    prot_std_c0 = m_global_cand_std["tp"][0] >= 2389
    prot_std_c3 = m_global_cand_std["tp"][3] >= 90
    prot_sqrt_c0 = m_global_cand_sqrt["tp"][0] >= 2389
    prot_sqrt_c3 = m_global_cand_sqrt["tp"][3] >= 90

    # Save probability artifact
    print(f"\nSaving full 3-fold probabilities artifact to {PROBABILITIES_NPZ}...")
    np.savez_compressed(
        PROBABILITIES_NPZ,
        vessel_ids=np.array(outer_vessel_ids),
        y_true=all_y_true,
        base_outer_probs_std=all_base_probs_std,
        base_outer_probs_sqrt=all_base_probs_sqrt,
        cand_outer_probs_std=all_cand_probs_std,
        cand_outer_probs_sqrt=all_cand_probs_sqrt,
        cand_outer_preds_std=all_cand_preds_std,
        cand_outer_preds_sqrt=all_cand_preds_sqrt,
    )

    results = {
        "status": "full_3fold_outer_complete",
        "total_outer_vessels": 5897,
        "frozen_baseline_reference": {
            "name": "LightGBM_sqrt_macro (seed42)",
            "correct": FROZEN_BASELINE_CORRECT,
            "micro_f1": FROZEN_BASELINE_MICRO,
            "tp": FROZEN_BASELINE_TP,
        },
        "global_outer_summary": {
            "baseline_standard": m_global_base_std,
            "candidate_standard": m_global_cand_std,
            "delta_standard_correct": int(m_global_cand_std["correct"] - m_global_base_std["correct"]),
            "delta_standard_micro": float(m_global_cand_std["micro_f1"] - m_global_base_std["micro_f1"]),
            "protection_standard_c0_pass": bool(prot_std_c0),
            "protection_standard_c3_pass": bool(prot_std_c3),
            "baseline_sqrt_macro": m_global_base_sqrt,
            "candidate_sqrt_macro": m_global_cand_sqrt,
            "delta_sqrt_macro_correct": int(m_global_cand_sqrt["correct"] - m_global_base_sqrt["correct"]),
            "delta_sqrt_macro_micro": float(m_global_cand_sqrt["micro_f1"] - m_global_base_sqrt["micro_f1"]),
            "delta_vs_frozen_reference": int(m_global_cand_sqrt["correct"] - FROZEN_BASELINE_CORRECT),
            "protection_sqrt_macro_c0_pass": bool(prot_sqrt_c0),
            "protection_sqrt_macro_c3_pass": bool(prot_sqrt_c3),
        },
        "fold_details": fold_details,
        "inner_records": inner_records,
    }

    print("\n" + "=" * 60)
    print("PHASE 2 GLOBAL 3-FOLD OUTER (5,897 vessels) SUMMARY:")
    print(f"Standard Multiclass : Base {m_global_base_std['correct']}/5897 ({m_global_base_std['micro_f1']:.6f}) -> Cand {m_global_cand_std['correct']}/5897 ({m_global_cand_std['micro_f1']:.6f}) | Delta: {m_global_cand_std['correct'] - m_global_base_std['correct']:+d}")
    print(f"  TP: Base {m_global_base_std['tp']} -> Cand {m_global_cand_std['tp']}")
    print(f"SqrtMacro Multiclass: Base {m_global_base_sqrt['correct']}/5897 ({m_global_base_sqrt['micro_f1']:.6f}) -> Cand {m_global_cand_sqrt['correct']}/5897 ({m_global_cand_sqrt['micro_f1']:.6f}) | Delta: {m_global_cand_sqrt['correct'] - m_global_base_sqrt['correct']:+d}")
    print(f"  TP: Base {m_global_base_sqrt['tp']} -> Cand {m_global_cand_sqrt['tp']}")
    print(f"  Frozen Reference Delta: {m_global_cand_sqrt['correct'] - FROZEN_BASELINE_CORRECT:+d} vs {FROZEN_BASELINE_CORRECT}")
    print(f"  Protection Pass (c0>=2389, c3>=90): c0={prot_sqrt_c0} (TP={m_global_cand_sqrt['tp'][0]}), c3={prot_sqrt_c3} (TP={m_global_cand_sqrt['tp'][3]})")
    print("=" * 60 + "\n")

    record_resource_check("phase2_full_3fold_complete", expected_peak_mb=100.0)
    return results


def main() -> int:
    t_start = time.time()
    record_resource_check("track2_pipeline_start", expected_peak_mb=350.0)
    print(f"Loading segment dataset: {SEGMENTS_PARQUET}")
    segments_df = pd.read_parquet(SEGMENTS_PARQUET)
    print(f"Loaded {len(segments_df)} segments across {segments_df['id'].nunique()} vessels.")

    # Phase 1: FIT 4-CV Diagnostic Gate
    gate_results = run_phase1_gate_4cv(segments_df)

    # Phase 2: Full 3-Fold OUTER & INNER Evaluation
    outer_results = run_phase2_full_3fold(segments_df)

    # Save comprehensive results JSON
    full_output = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_elapsed_seconds": round(time.time() - t_start, 2),
        "gate_results": gate_results,
        "outer_results": outer_results,
    }
    RESULTS_JSON.write_text(json.dumps(full_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"All experiment results saved to {RESULTS_JSON}")

    record_resource_check("track2_pipeline_finished", expected_peak_mb=50.0)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
