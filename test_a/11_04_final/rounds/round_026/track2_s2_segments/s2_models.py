"""S2 segment cross-fitting, spatial prior, and vessel-level aggregation."""
from __future__ import annotations

import gc
from pathlib import Path
import time
from typing import Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from resource_check import record_resource_check

TRACK_DIR = Path(__file__).resolve().parent
N_CLASSES = 4
CLASS_NAMES = ("연안복합", "자망", "통발", "채낚기연승낚시")


def sqrt_sample_weights(y_fit: Sequence[int] | np.ndarray) -> np.ndarray:
    """S6 inverse-square-root class weights, estimated from FIT labels only."""
    y = np.asarray(y_fit, dtype=np.int64)
    if y.ndim != 1 or y.size == 0 or np.any((y < 0) | (y >= N_CLASSES)):
        raise ValueError("FIT labels must be a nonempty vector of class indices 0..3")
    counts = np.bincount(y, minlength=N_CLASSES)
    if np.any(counts == 0):
        raise ValueError(f"all four classes must occur in FIT; counts={counts.tolist()}")
    per_class = np.sqrt(len(y) / (N_CLASSES * counts.astype(np.float64)))
    per_class /= per_class.mean()
    return per_class[y]


def compute_spatial_priors(
    train_segments_df: pd.DataFrame,
    eval_segments_df: pd.DataFrame | None = None,
    alpha: float = 5.0,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Compute Laplace-smoothed cell_005 prior distribution per cell from training segments."""
    counts = (
        train_segments_df.groupby(["dom_cell_005", "y_vessel"])
        .size()
        .unstack(fill_value=0)
    )
    for c in range(N_CLASSES):
        if c not in counts.columns:
            counts[c] = 0
    counts = counts[[0, 1, 2, 3]]
    total_per_cell = counts.sum(axis=1)
    cell_priors = (counts + alpha).div(total_per_cell + N_CLASSES * alpha, axis=0)

    total_train = counts.sum().sum()
    global_prior = (counts.sum(axis=0) + alpha) / (total_train + N_CLASSES * alpha)

    def _lookup(series: pd.Series) -> np.ndarray:
        return cell_priors.reindex(series).fillna(global_prior).values.astype(np.float32)

    train_priors = _lookup(train_segments_df["dom_cell_005"])
    eval_priors = _lookup(eval_segments_df["dom_cell_005"]) if eval_segments_df is not None else None
    return train_priors, eval_priors


def cross_fit_segment_model(
    train_segments_df: pd.DataFrame,
    eval_segments_df: pd.DataFrame | None = None,
    n_inner_splits: int = 5,
    seed: int = 42,
    use_sqrt_weight: bool = False,
    stage_name: str = "segment_crossfit",
) -> tuple[np.ndarray, np.ndarray | None, dict]:
    """
    Leak-free out-of-fold segment probability prediction.
    - Inside train_segments: Stratified split on vessel IDs into n_inner_splits folds.
      Train LightGBM on n-1 folds, predict on held-out fold segments.
    - On eval_segments (if provided): average predictions across all n_inner_splits models.
    """
    record_resource_check(f"{stage_name}_start", expected_peak_mb=300.0)
    t0 = time.time()

    # Identify vessels and labels in train_segments
    vessel_labels = (
        train_segments_df[["id", "y_vessel"]]
        .drop_duplicates(subset=["id"])
        .sort_values("id")
        .reset_index(drop=True)
    )
    vids = vessel_labels["id"].values
    vy = vessel_labels["y_vessel"].values

    base_feature_cols = [
        c for c in train_segments_df.columns
        if c not in ["id", "date", "dom_cell_005", "y_vessel", "p_seg_0", "p_seg_1", "p_seg_2", "p_seg_3"]
    ]

    skf = StratifiedKFold(n_splits=n_inner_splits, shuffle=True, random_state=seed)
    
    oof_probs = np.full((len(train_segments_df), N_CLASSES), np.nan, dtype=np.float32)
    models: list[lgb.LGBMClassifier] = []

    # Map segment row index to train_segments_df
    train_segments_df = train_segments_df.copy().reset_index(drop=True)

    for fold_idx, (tr_v_idx, va_v_idx) in enumerate(skf.split(vids, vy)):
        tr_vids_set = set(vids[tr_v_idx])
        va_vids_set = set(vids[va_v_idx])

        tr_seg_mask = train_segments_df["id"].isin(tr_vids_set).values
        va_seg_mask = train_segments_df["id"].isin(va_vids_set).values

        tr_seg = train_segments_df.iloc[tr_seg_mask]
        va_seg = train_segments_df.iloc[va_seg_mask]

        # Spatial priors built strictly on tr_seg
        tr_priors, va_priors = compute_spatial_priors(tr_seg, va_seg, alpha=5.0)

        X_tr = np.hstack([tr_seg[base_feature_cols].values.astype(np.float32), tr_priors])
        y_tr = tr_seg["y_vessel"].values.astype(np.int64)
        X_va = np.hstack([va_seg[base_feature_cols].values.astype(np.float32), va_priors])

        sample_weight = sqrt_sample_weights(y_tr) if use_sqrt_weight else None

        clf = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=N_CLASSES,
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            colsample_bytree=0.8,
            subsample=0.8,
            subsample_freq=1,
            random_state=seed + fold_idx,
            n_jobs=1,
            verbose=-1,
        )
        clf.fit(X_tr, y_tr, sample_weight=sample_weight)
        
        p_va = clf.predict_proba(X_va).astype(np.float32)
        oof_probs[va_seg_mask] = p_va
        models.append(clf)

        del tr_seg, va_seg, tr_priors, va_priors, X_tr, y_tr, X_va, sample_weight
        gc.collect()

    if np.isnan(oof_probs).any():
        raise RuntimeError("OOF segment probabilities contain NaNs; inner fold coverage incomplete")

    oof_preds = np.argmax(oof_probs, axis=1)
    seg_acc = float((oof_preds == train_segments_df["y_vessel"].values).mean())
    print(f"[{stage_name}] OOF segment accuracy: {seg_acc:.4f} across {len(train_segments_df)} segments")

    eval_probs = None
    if eval_segments_df is not None and len(eval_segments_df) > 0:
        eval_segments_df = eval_segments_df.copy().reset_index(drop=True)
        # Compute spatial prior using all train_segments
        _, eval_priors = compute_spatial_priors(train_segments_df, eval_segments_df, alpha=5.0)
        X_eval = np.hstack([eval_segments_df[base_feature_cols].values.astype(np.float32), eval_priors])
        
        accum_p = np.zeros((len(eval_segments_df), N_CLASSES), dtype=np.float32)
        for clf in models:
            accum_p += clf.predict_proba(X_eval).astype(np.float32)
        eval_probs = accum_p / float(len(models))
        del X_eval, eval_priors, accum_p
        gc.collect()

    elapsed = round(time.time() - t0, 2)
    meta = {
        "stage": stage_name,
        "elapsed_seconds": elapsed,
        "segment_oof_accuracy": seg_acc,
        "num_models": len(models),
        "use_sqrt_weight": use_sqrt_weight,
    }
    record_resource_check(f"{stage_name}_complete", expected_peak_mb=100.0)
    return oof_probs, eval_probs, meta


def aggregate_vessel_features(
    segments_df: pd.DataFrame,
    probs: np.ndarray,
    vessel_ids_order: Sequence[int | str],
) -> tuple[np.ndarray, list[str]]:
    """
    Aggregate segment-level probabilities and behavioral variability into vessel-level features.
    Returns (matrix, feature_names).
    """
    t0 = time.time()
    df = segments_df.copy()
    for c in range(N_CLASSES):
        df[f"p_seg_{c}"] = probs[:, c]

    # Pre-calculate argmax class
    df["argmax_c"] = np.argmax(probs, axis=1).astype(np.int8)

    # Pre-calculate entropy
    eps = 1e-9
    ent = -np.sum(probs * np.log(probs + eps), axis=1).astype(np.float32)
    df["entropy"] = ent

    # Top1 and Top2 margin
    p_sort = np.sort(probs, axis=1)
    df["top_margin"] = (p_sort[:, -1] - p_sort[:, -2]).astype(np.float32)

    # Sort by vessel and date
    df = df.sort_values(["id", "date"]).reset_index(drop=True)

    grouped = df.groupby("id", sort=False)

    # 1. Probability distributions (20 cols)
    agg_dict = {}
    for c in range(N_CLASSES):
        agg_dict[f"p_mean_{c}"] = (f"p_seg_{c}", "mean")
        agg_dict[f"p_std_{c}"] = (f"p_seg_{c}", "std")
        agg_dict[f"p_median_{c}"] = (f"p_seg_{c}", "median")
        agg_dict[f"p_p90_{c}"] = (f"p_seg_{c}", lambda s: np.percentile(s, 90))

    # Argmax ratios
    for c in range(N_CLASSES):
        agg_dict[f"argmax_ratio_{c}"] = ("argmax_c", lambda s, cls=c: float((s == cls).mean()))

    # Diversity & uncertainty (5 cols)
    agg_dict["mean_entropy"] = ("entropy", "mean")
    agg_dict["unique_pred_classes_count"] = ("argmax_c", lambda s: float(len(np.unique(s))))
    agg_dict["mean_top_margin"] = ("top_margin", "mean")

    # Physical variability (5 cols)
    agg_dict["std_night_ratio"] = ("ratio_night", "std")
    agg_dict["std_daily_dist"] = ("daily_dist_sum_km", "std")
    agg_dict["p90_daily_dist"] = ("daily_dist_sum_km", lambda s: np.percentile(s, 90))
    agg_dict["std_dist_from_home"] = ("dist_from_home_mean_km", "std")
    agg_dict["p90_dist_from_home"] = ("dist_from_home_max_km", lambda s: np.percentile(s, 90))

    # Grid transition rate (1 col)
    def _grid_trans(s):
        arr = s.values
        if len(arr) <= 1:
            return 0.0
        return float((arr[1:] != arr[:-1]).mean())
    agg_dict["grid_transition_rate"] = ("dom_cell_005", _grid_trans)

    # Run groupby agg
    v_agg = grouped.agg(**agg_dict).reset_index()

    # Derived top1 and top2 class ratio from argmax_ratios
    ratio_matrix = v_agg[[f"argmax_ratio_{c}" for c in range(N_CLASSES)]].values
    sorted_ratios = np.sort(ratio_matrix, axis=1)
    v_agg["top1_class_ratio"] = sorted_ratios[:, -1].astype(np.float32)
    v_agg["top2_class_ratio"] = sorted_ratios[:, -2].astype(np.float32)

    # Fill NaNs from std of single days with 0.0
    v_agg.fillna(0.0, inplace=True)

    # Order rows to match vessel_ids_order exactly
    target_ids = pd.DataFrame({"id": [int(x) for x in vessel_ids_order]})
    merged = target_ids.merge(v_agg, on="id", how="left").fillna(0.0)

    feature_cols = [c for c in merged.columns if c != "id"]
    matrix = merged[feature_cols].values.astype(np.float32)

    del df, grouped, v_agg, merged
    gc.collect()

    return matrix, feature_cols


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Calculate standard micro, macro, and classwise confusion matrix."""
    cm = np.zeros((N_CLASSES, N_CLASSES), dtype=np.int64)
    for actual, predicted in zip(y_true.tolist(), y_pred.tolist()):
        cm[int(actual), int(predicted)] += 1
    support = cm.sum(axis=1)
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = support - tp
    precision = np.divide(tp, tp + fp, out=np.zeros(N_CLASSES, dtype=np.float64), where=(tp + fp) != 0)
    recall = np.divide(tp, support, out=np.zeros(N_CLASSES, dtype=np.float64), where=support != 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros(N_CLASSES, dtype=np.float64), where=(precision + recall) != 0)
    return {
        "n": int(len(y_true)),
        "correct": int(tp.sum()),
        "micro_f1": float(tp.sum() / len(y_true)),
        "macro_f1": float(f1.mean()),
        "support": support.tolist(),
        "tp": tp.tolist(),
        "fp": fp.tolist(),
        "fn": fn.tolist(),
        "precision": precision.tolist(),
        "recall": recall.tolist(),
        "class_f1": f1.tolist(),
        "confusion": cm.tolist(),
    }
