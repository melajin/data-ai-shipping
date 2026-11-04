#!/usr/bin/env python3
"""Re-run the 2026-10-29 factorial and keep the per-vessel predictions.

The first pass stored only aggregate metrics, which left four questions open:
where the weight contrast loses the accuracy it buys, whether the negative
interactions are one bias being fixed repeatedly, what NLL and Brier are, and
how the sample contrast reads once the two cells are restricted to the vessels
both can score. All four need per-vessel probabilities, so this run saves them.

Design is unchanged from run_cycle2_development_20261029.py: same frozen
splits, same seeds, same ExtraTrees, same aggregation. It is a re-run that
records more, not a new experiment. The final holdout stays closed: only
development vessels are built, fitted or scored.

Only fitted statistic in the pipeline is the Preprocessor, fitted on each
split's training rows alone. Per-vessel quantiles pool nothing across vessels.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.models import Preprocessor, classification_metrics
from fishing_demo.real_model_cycle_20261028 import (
    DEV_SEEDS,
    FINAL_SPLIT_SEED,
    _development_splits,
    _stratified_final_split,
)

_spec = importlib.util.spec_from_file_location(
    "_cycle2_dev", ROOT / "tools" / "run_cycle2_development_20261029.py")
_dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dev)

SAMPLE_LEVELS = _dev.SAMPLE_LEVELS
WEIGHT_LEVELS = _dev.WEIGHT_LEVELS
FEATURE_LEVELS = _dev.FEATURE_LEVELS
TREE_SEEDS = _dev.TREE_SEEDS
N_CLASSES = _dev.N_CLASSES
DEFAULT_EXTRACT = ROOT / "outputs" / "cycle2_20261029" / "extract"
DEFAULT_OUT = ROOT / "outputs" / "cycle2_20261029" / "predictions"


def fit_and_predict(sample, weight, features, split, index):
    """Fit one cell on one split and return per-vessel probabilities."""
    train_x, train_y = _dev.build_matrix(split["train"], index, sample, features)
    val_x, val_y = _dev.build_matrix(split["validation"], index, sample, features)
    train_usable = np.isfinite(train_x).any(axis=1)
    if not train_usable.any():
        raise ValueError("no usable training vessel")

    # The only statistic fitted on data, and it sees training rows only.
    pre = Preprocessor().fit(train_x[train_usable])
    fitted_train = pre.transform(train_x[train_usable])
    fitted_val = pre.transform(val_x)

    probabilities = np.zeros((len(val_y), N_CLASSES), dtype=np.float64)
    for tree_seed in TREE_SEEDS:
        model = ExtraTreesClassifier(
            n_estimators=256, min_samples_leaf=2, max_features=1.0, n_jobs=-1,
            class_weight=None if weight == "none" else "balanced",
            random_state=tree_seed)
        model.fit(fitted_train, train_y[train_usable])
        probabilities += model.predict_proba(fitted_val) / len(TREE_SEEDS)

    abstain = ~np.isfinite(val_x).any(axis=1)
    return {
        "vessel_hash": np.asarray(split["validation"], dtype="U64"),
        "y_true": val_y.astype(np.int8),
        "probabilities": probabilities,
        "abstain": abstain,
        "train_vessels": int(train_usable.sum()),
        "input_width": int(fitted_train.shape[1]),
    }


def score(y_true, probabilities, abstain):
    """Metrics over scorable vessels, including the uncalibrated NLL and Brier."""
    scorable = ~abstain
    predicted = probabilities.argmax(axis=1)
    predicted[abstain] = -1
    confusion = np.zeros((N_CLASSES, N_CLASSES + 1), dtype=np.int64)
    np.add.at(confusion, (y_true, np.where(predicted < 0, N_CLASSES, predicted)), 1)

    standard = classification_metrics(y_true[scorable], probabilities[scorable])
    support = confusion[:, :N_CLASSES].sum(axis=1)
    predicted_share = confusion[:, :N_CLASSES].sum(axis=0) / max(int(scorable.sum()), 1)
    recalls = [float(confusion[c, c]) / support[c] if support[c] else None
               for c in range(N_CLASSES)]
    return {
        "macro_f1": standard["macro_f1"],
        "accuracy": standard["accuracy"],
        "nll_uncalibrated": standard["nll"],
        "brier_uncalibrated": standard["brier"],
        "confusion_with_abstain_column": confusion.tolist(),
        "scorable_support": support.tolist(),
        "predicted_share": [round(float(v), 5) for v in predicted_share],
        "per_class_recall": [None if r is None else round(r, 5) for r in recalls],
        "correct": int(np.trace(confusion[:, :N_CLASSES])),
        "scorable": int(scorable.sum()),
        "abstain": int(abstain.sum()),
        "coverage": float(scorable.mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--labels", type=Path,
                        default=ROOT / "outputs" / "cycle2_20261029" / "label_vocabulary.json")
    args = parser.parse_args()

    started = time.perf_counter()
    class_names = _dev.load_class_names(args.labels)
    index = _dev.load_extract(args.extract)

    roster = [{"vessel_hash": vessel_hash, "label": class_names[label]}
              for vessel_hash, label in index["label_by_vessel"].items()]
    final_hashes, dev_hashes, class_counts = _stratified_final_split(
        roster, list(class_names))
    dev_roster = [item for item in roster if item["vessel_hash"] in set(dev_hashes)]
    splits = _development_splits(dev_roster, list(class_names))
    final_set = set(final_hashes)
    for seed, split in splits.items():
        for role, hashes in split.items():
            if final_set & set(hashes):
                raise AssertionError(f"final holdout leaked into {role} of seed {seed}")

    args.out.mkdir(parents=True, exist_ok=True)
    cells = {}
    for sample in SAMPLE_LEVELS:
        for weight in WEIGHT_LEVELS:
            for features in FEATURE_LEVELS:
                key = f"{sample}_{weight}_{features}"
                path = args.out / f"{key}.npz"
                cell_started = time.perf_counter()
                per_split, payload = [], {}
                for seed in DEV_SEEDS:
                    result = fit_and_predict(sample, weight, features,
                                             splits[str(seed)], index)
                    metrics = score(result["y_true"], result["probabilities"],
                                    result["abstain"])
                    metrics["seed"] = seed
                    metrics["train_vessels"] = result["train_vessels"]
                    metrics["input_width"] = result["input_width"]
                    per_split.append(metrics)
                    payload[f"{seed}_vessel_hash"] = result["vessel_hash"]
                    payload[f"{seed}_y_true"] = result["y_true"]
                    payload[f"{seed}_probabilities"] = result["probabilities"].astype(np.float32)
                    payload[f"{seed}_abstain"] = result["abstain"]
                np.savez_compressed(path, **payload)
                cells[key] = {
                    "cell": {"sample": sample, "weight": weight, "features": features},
                    "splits": per_split,
                    "predictions": str(path),
                    "seconds": round(time.perf_counter() - cell_started, 1),
                }
                means = {name: float(np.mean([s[name] for s in per_split]))
                         for name in ("macro_f1", "accuracy", "nll_uncalibrated",
                                      "brier_uncalibrated", "coverage")}
                cells[key]["means"] = means
                print(f"{sample:4s} {weight:9s} {features:15s} "
                      f"F1={means['macro_f1']:.5f} acc={means['accuracy']:.5f} "
                      f"NLL={means['nll_uncalibrated']:.5f} "
                      f"Brier={means['brier_uncalibrated']:.5f} "
                      f"({cells[key]['seconds']}s)", flush=True)

    report = {
        "schema_version": "cycle2_predictions_v1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Re-run of the pre-registered factorial, storing per-vessel "
                "probabilities. Design, splits and seeds are unchanged.",
        "calibration": "none; NLL and Brier are uncalibrated and are not "
                       "comparable to the temperature-calibrated 2026-10-28 final values",
        "only_fitted_statistic": "Preprocessor, fitted on each split's training rows",
        "final_split_seed": FINAL_SPLIT_SEED,
        "development_seeds": list(DEV_SEEDS),
        "class_names": list(class_names),
        "class_counts": class_counts,
        "final_holdout_size": len(final_hashes),
        "final_holdout_used": False,
        "extract_totals": index["totals"],
        "cells": cells,
        "wall_seconds": round(time.perf_counter() - started, 1),
    }
    path = args.out.parent / "predictions_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
