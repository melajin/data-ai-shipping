"""Fixed evaluation contract shared by rank-1 experiments.

Import-safe: no filesystem access or job launch occurs on import.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

CLASS_NAMES: tuple[str, ...] = ("연안복합", "자망", "통발", "채낚기연승낚시")
CLASS_TO_INDEX: Mapping[str, int] = MappingProxyType({name: i for i, name in enumerate(CLASS_NAMES)})
INDEX_TO_CLASS: Mapping[int, str] = MappingProxyType({i: name for i, name in enumerate(CLASS_NAMES)})
FOLDS: tuple[int, ...] = (0, 1, 2)
SEEDS: tuple[int, ...] = (42, 2026, 7, 1, 2024)
N_CLASSES = 4
N_FEATURES = 304
TRAP_INDEX = 2
DECISION_WEIGHT = 1.0
EARLY_STOPPING_ROUNDS = 200
N_ESTIMATORS = 8000
FEATURE_COMPONENTS: tuple[tuple[str, int], ...] = (
    ("F156", 156), ("T5", 10), ("B_behavior_without_obs_days", 68), ("local_rel", 70)
)
OBS_DAYS_BUCKETS: tuple[tuple[str, float, float | None], ...] = (
    ("1-7", 1, 7), ("8-30", 8, 30), ("31-90", 31, 90), ("91+", 91, None)
)

@dataclass(frozen=True)
class Condition:
    name: str
    sample_weight: str
    early_stop_metric: str
    decision_weight: float = DECISION_WEIGHT

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "sample_weight": self.sample_weight,
                "early_stop_metric": self.early_stop_metric,
                "decision_weight": self.decision_weight}

CONDITIONS: Mapping[str, Condition] = MappingProxyType({
    "sqrt_macro": Condition("sqrt_macro", "sqrt", "macro_f1"),
    "sqrt_micro": Condition("sqrt_micro", "sqrt", "micro_f1"),
    "none_macro": Condition("none_macro", "none", "macro_f1"),
    "none_micro": Condition("none_micro", "none", "micro_f1"),
})


def validate_class_order(class_by_index: Mapping[int | str, str]) -> None:
    actual = {int(k): str(v) for k, v in class_by_index.items()}
    expected = {i: name for i, name in enumerate(CLASS_NAMES)}
    if actual != expected:
        raise ValueError(f"class order mismatch: expected {expected}, got {actual}")


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


def lightgbm_eval_metric(metric: str):
    """Return LightGBM multiclass macro-F1 or micro-F1 callback."""
    if metric not in {"macro_f1", "micro_f1"}:
        raise ValueError(f"unsupported early-stop metric: {metric}")

    def callback(y_true, y_pred):
        y = np.asarray(y_true, dtype=np.int64)
        p = np.asarray(y_pred)
        if p.ndim == 1:
            if p.size != y.size * N_CLASSES:
                raise ValueError(f"unexpected prediction size {p.size} for {len(y)} rows")
            p = p.reshape(N_CLASSES, -1).T
        if p.shape != (len(y), N_CLASSES):
            raise ValueError(f"unexpected LightGBM prediction shape {p.shape}")
        pred = p.argmax(axis=1)
        score = float(np.mean(pred == y)) if metric == "micro_f1" else metrics(y, pred)["macro_f1"]
        return metric, score, True
    return callback


def validate_probabilities(probabilities: np.ndarray, n_rows: int | None = None,
                           atol: float = 1e-5) -> np.ndarray:
    p = np.asarray(probabilities, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != N_CLASSES:
        raise ValueError(f"probabilities must have shape (n, 4), got {p.shape}")
    if n_rows is not None and len(p) != n_rows:
        raise ValueError(f"probability rows {len(p)} != expected {n_rows}")
    if not np.isfinite(p).all() or np.any(p < -atol) or np.any(p > 1 + atol):
        raise ValueError("probabilities must be finite and lie in [0, 1]")
    sums = p.sum(axis=1)
    if not np.allclose(sums, 1.0, atol=atol, rtol=0):
        raise ValueError(f"probability row sums outside tolerance: min={sums.min()} max={sums.max()}")
    return p


def metrics(y_true: Sequence[int] | np.ndarray,
            y_pred: Sequence[int] | np.ndarray) -> dict[str, Any]:
    y = np.asarray(y_true, dtype=np.int64)
    pred = np.asarray(y_pred, dtype=np.int64)
    if y.ndim != 1 or pred.shape != y.shape or y.size == 0:
        raise ValueError("y_true and y_pred must be nonempty vectors of equal length")
    if np.any((y < 0) | (y >= N_CLASSES) | (pred < 0) | (pred >= N_CLASSES)):
        raise ValueError("labels and predictions must use class indices 0..3")
    cm = np.bincount(y * N_CLASSES + pred, minlength=N_CLASSES ** 2).reshape(N_CLASSES, N_CLASSES)
    tp = np.diag(cm).astype(np.float64)
    true_n, pred_n = cm.sum(axis=1), cm.sum(axis=0)
    recall = np.divide(tp, true_n, out=np.zeros(N_CLASSES), where=true_n > 0)
    precision = np.divide(tp, pred_n, out=np.zeros(N_CLASSES), where=pred_n > 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros(N_CLASSES), where=(precision + recall) > 0)
    micro = float(np.mean(y == pred))
    return {"n": int(y.size), "micro_f1": micro, "accuracy": micro,
            "macro_recall": float(recall.mean()), "macro_f1": float(f1.mean()),
            "class_recall": recall.tolist(), "class_f1": f1.tolist(),
            "confusion_matrix": cm.tolist()}


def obs_days_metrics(y_true: Sequence[int] | np.ndarray,
                     y_pred: Sequence[int] | np.ndarray,
                     obs_days: Sequence[float] | np.ndarray) -> dict[str, Any]:
    y, pred = np.asarray(y_true, dtype=np.int64), np.asarray(y_pred, dtype=np.int64)
    days = np.asarray(obs_days, dtype=np.float64)
    if days.shape != y.shape or pred.shape != y.shape:
        raise ValueError("obs_days, y_true, and y_pred must have equal lengths")
    out: dict[str, Any] = {}
    for name, lo, hi in OBS_DAYS_BUCKETS:
        mask = days >= lo if hi is None else (days >= lo) & (days <= hi)
        out[name] = metrics(y[mask], pred[mask]) if mask.any() else {"n": 0}
    unusual = ~np.isfinite(days) | (days <= 0)
    if unusual.any():
        out["0_or_missing"] = metrics(y[unusual], pred[unusual])
    return out


def prediction_frame(rfid_ids: Sequence[str], fold: int, role: str,
                     y_true: Sequence[int] | np.ndarray,
                     probabilities: np.ndarray) -> pd.DataFrame:
    ids = [str(r) for r in rfid_ids]
    y = np.asarray(y_true, dtype=np.int64)
    p = validate_probabilities(probabilities, n_rows=len(ids))
    if len(ids) != len(y) or len(set(ids)) != len(ids):
        raise ValueError("rfid_ids must be unique and align with labels/probabilities")
    if role not in {"INNER", "OUTER"}:
        raise ValueError(f"prediction role must be INNER or OUTER, got {role!r}")
    if np.any((y < 0) | (y >= N_CLASSES)):
        raise ValueError("y_true must use class indices 0..3")
    out = pd.DataFrame({"rfid_id": ids, "fold": int(fold), "role": role, "y_true": y})
    for i in range(N_CLASSES):
        out[f"p{i}"] = p[:, i]
    out["pred"] = p.argmax(axis=1).astype(np.int64)
    return out


def paired_comparison(reference: pd.DataFrame, candidate: pd.DataFrame,
                      obs_days_by_id: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Compare prediction frames on identical `(rfid_id, fold, role)` rows."""
    keys = ["rfid_id", "fold", "role"]
    required = set(keys + ["y_true", "pred"])
    if not required.issubset(reference.columns) or not required.issubset(candidate.columns):
        raise ValueError("prediction frames lack paired-comparison columns")
    if reference.duplicated(keys).any() or candidate.duplicated(keys).any():
        raise ValueError("prediction frames contain duplicate pairing keys")
    left = reference[keys + ["y_true", "pred"]].rename(columns={"y_true": "y_ref", "pred": "pred_ref"})
    right = candidate[keys + ["y_true", "pred"]].rename(columns={"y_true": "y_cand", "pred": "pred_cand"})
    paired = left.merge(right, on=keys, how="outer", validate="one_to_one", indicator=True)
    if not (paired["_merge"] == "both").all():
        raise ValueError("paired comparison requires identical rfid/fold/role rows")
    if not np.array_equal(paired["y_ref"].to_numpy(), paired["y_cand"].to_numpy()):
        raise ValueError("paired rows have different true labels")
    y = paired["y_ref"].to_numpy(dtype=np.int64)
    p_ref = paired["pred_ref"].to_numpy(dtype=np.int64)
    p_cand = paired["pred_cand"].to_numpy(dtype=np.int64)
    mr, mc = metrics(y, p_ref), metrics(y, p_cand)
    gained, lost = (p_ref != y) & (p_cand == y), (p_ref == y) & (p_cand != y)
    result: dict[str, Any] = {
        "n": int(len(paired)), "reference": mr, "candidate": mc,
        "delta": {key: mc[key] - mr[key] for key in ("micro_f1", "macro_recall", "macro_f1")},
        "paired_correctness": {"newly_correct": int(gained.sum()),
                               "newly_incorrect": int(lost.sum()),
                               "net_additional_correct": int(gained.sum() - lost.sum())},
    }
    if obs_days_by_id is not None:
        days = np.asarray([obs_days_by_id[str(r)] for r in paired["rfid_id"]], dtype=np.float64)
        ref_by_days = obs_days_metrics(y, p_ref, days)
        cand_by_days = obs_days_metrics(y, p_cand, days)
        deltas_by_days = {}
        for bucket in set(ref_by_days) & set(cand_by_days):
            ref_bucket, cand_bucket = ref_by_days[bucket], cand_by_days[bucket]
            if ref_bucket.get("n", 0) and cand_bucket.get("n", 0):
                deltas_by_days[bucket] = {
                    key: cand_bucket[key] - ref_bucket[key]
                    for key in ("micro_f1", "macro_recall", "macro_f1")
                }
        result["obs_days"] = {"reference": ref_by_days, "candidate": cand_by_days,
                               "delta": deltas_by_days}
        result["obs_days_paired_correctness"] = {}
        for name, lo, hi in OBS_DAYS_BUCKETS:
            mask = days >= lo if hi is None else (days >= lo) & (days <= hi)
            g, l = int((gained & mask).sum()), int((lost & mask).sum())
            result["obs_days_paired_correctness"][name] = {
                "n": int(mask.sum()), "newly_correct": g, "newly_incorrect": l,
                "net_additional_correct": g - l}
    return result
