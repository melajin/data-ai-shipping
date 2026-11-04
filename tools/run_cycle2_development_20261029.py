#!/usr/bin/env python3
"""Cycle 2 development ablation, pre-registered 2026-10-29.

The 2026-10-28 cycle left three hypotheses untested because nothing varied one
factor at a time. This runs a full 2x2x2 factorial over the three factors that
were confounded, holding the model family, the splits and the seeds fixed:

  sample   s4   four rows per vessel per monthly file (the 2026-10-28 selection)
           all  every structurally valid row (3,887,069 rows instead of 129,142)
  weight   none      class_weight=None (the 2026-10-28 setting)
           balanced  class_weight="balanced"
  features dist36          shape9 mean/std/q25/q75 (the 2026-10-28 input)
           dist36_scale32  plus the scale8 block shape9 discards

Every cell is ExtraTrees(256, min_samples_leaf=2, max_features=1.0), the only
candidate that passed the 2026-10-28 development gate, so each contrast moves
exactly one factor. Splits come from the frozen 2026-10-28 functions at the
same seeds, so rosters are identical and the final holdout stays closed: this
script reads development vessels only and never loads a final-split vessel.

Reported per cell: Macro F1, accuracy, per-class recall (pot-trap recall is the
2026-10-28 failure to beat), coverage and abstain count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.real_geometry_20261028 import FEATURE_NAMES as SHAPE9_NAMES
from fishing_demo.real_model_cycle_20261028 import (
    DEV_SEEDS,
    FINAL_SPLIT_SEED,
    _development_splits,
    _stratified_final_split,
)
from fishing_demo.real_scale_features_20261029 import FEATURE_NAMES as SCALE8_NAMES
from fishing_demo.models import Preprocessor

SAMPLES_PER_VESSEL_PER_FILE = 4
TREE_SEEDS = (42, 137)
DEFAULT_EXTRACT = ROOT / "outputs" / "cycle2_20261029" / "extract"
DEFAULT_OUT = ROOT / "outputs" / "cycle2_20261029"

SAMPLE_LEVELS = ("s4", "all")
WEIGHT_LEVELS = ("none", "balanced")
FEATURE_LEVELS = ("dist36", "dist36_scale32")
REFERENCE_CELL = ("s4", "none", "dist36")
SALT = b"fishing-evaluation-cycle-20261028-id-index-v1"
N_CLASSES = 4
CLASS_LABEL_SHA256 = (
    "1edc2d96759a1df336ff96ec264b6d4cbdd6130a757aa2aae8d97b063241af4f",
    "6c451d18f84a5e1d774592d7d05d528b9338e784e541a8413383b5f2edb08f7b",
    "dc049b9b4ebb132462ecf76ac702690b1499775aa662488d5bee1bd0f1ec3159",
    "eedcc6605ecd1794c5a6626a5b40d0570c98e0e666308e51cd8273a48a121e91",
)


def load_class_names(vocabulary: Path) -> tuple[str, ...]:
    """Read the four label strings and refuse any that fails its hash.

    ``_rank_key`` hashes the label text, so the 2026-10-28 split is only
    reproducible with the exact source strings. They are read from the
    vocabulary file rather than written here: transcribing them by hand once
    dropped a whole class without failing.
    """
    payload = json.loads(vocabulary.read_text(encoding="utf-8"))
    names = []
    for index, expected in enumerate(CLASS_LABEL_SHA256):
        entry = payload["labels"][index]
        label = entry["label"]
        actual = hashlib.sha256(SALT + label.encode("utf-8", errors="surrogatepass")).hexdigest()
        if actual != expected or entry["label_sha256"] != expected:
            raise ValueError(f"label {index} in {vocabulary} does not match the 2026-10-28 hash")
        names.append(label)
    return tuple(names)


def load_extract(extract_dir: Path) -> dict:
    """Load every extracted row into compact column arrays.

    3.9 M rows held as Python dicts would cost several GB on a machine with
    under one free, so rows stay in numpy columns and each vessel keeps only an
    index array into them. The s4 membership mask is computed once here rather
    than per cell: the reservoir rule is deterministic and does not change
    between factorial cells.
    """
    blocks: dict[str, list] = {name: [] for name in
                               ("vessel_key", "file_ordinal", "record_ordinal",
                                "valid", "shape9", "scale8")}
    label_by_vessel: dict[str, int] = {}
    vessel_slot: dict[str, int] = {}
    vessel_order: list[str] = []

    for file_ordinal in range(6):
        parts = (sorted(extract_dir.glob(f"train_{file_ordinal}.npz"))
                 + sorted(extract_dir.glob(f"train_{file_ordinal}.s*of*.npz")))
        if not parts:
            raise SystemExit(f"no extract found for monthly file {file_ordinal}")
        for part in parts:
            data = np.load(part, allow_pickle=False)
            names = [str(value) for value in data["vessel_hashes"]]
            local_to_global = np.empty(len(names), dtype=np.int32)
            for local, vessel_hash in enumerate(names):
                slot = vessel_slot.get(vessel_hash)
                if slot is None:
                    slot = len(vessel_order)
                    vessel_slot[vessel_hash] = slot
                    vessel_order.append(vessel_hash)
                local_to_global[local] = slot

            # One label per vessel is a 2026-10-28 invariant; re-check it.
            vessel_id, label_id = data["vessel_id"], data["label_id"]
            seen_first = np.full(len(names), -1, dtype=np.int16)
            seen_first[vessel_id[::-1]] = label_id[::-1]
            for local in np.flatnonzero(seen_first >= 0):
                vessel_hash = names[local]
                label = int(seen_first[local])
                if label_by_vessel.setdefault(vessel_hash, label) != label:
                    raise ValueError(f"vessel {vessel_hash[:12]} carries two labels")

            blocks["vessel_key"].append(local_to_global[vessel_id])
            blocks["file_ordinal"].append(
                np.full(len(vessel_id), file_ordinal, dtype=np.int8))
            blocks["record_ordinal"].append(data["record_ordinal"])
            blocks["valid"].append(data["valid"])
            blocks["shape9"].append(data["shape9"])
            blocks["scale8"].append(data["scale8"])
            del data

    columns = {name: np.concatenate(values) for name, values in blocks.items()}
    blocks.clear()

    # Row positions per vessel, so aggregation gathers rather than copies.
    order = np.argsort(columns["vessel_key"], kind="stable")
    sorted_keys = columns["vessel_key"][order]
    boundaries = np.flatnonzero(np.diff(sorted_keys)) + 1
    rows_for_vessel: dict[str, np.ndarray] = {}
    for group in np.split(order, boundaries):
        rows_for_vessel[vessel_order[int(columns["vessel_key"][group[0]])]] = group
    del order, sorted_keys

    s4_mask = _s4_membership(columns, rows_for_vessel)
    return {
        "columns": columns,
        "rows_for_vessel": rows_for_vessel,
        "label_by_vessel": label_by_vessel,
        "s4_mask": s4_mask,
        "totals": {"rows": int(len(columns["vessel_key"])),
                   "valid": int(np.count_nonzero(columns["valid"])),
                   "s4_rows": int(np.count_nonzero(s4_mask)),
                   "vessels": len(vessel_order)},
    }


def _s4_membership(columns, rows_for_vessel) -> np.ndarray:
    """Mark the rows the 2026-10-28 reservoir rule would have selected."""
    mask = np.zeros(len(columns["vessel_key"]), dtype=bool)
    file_ordinal = columns["file_ordinal"]
    record_ordinal = columns["record_ordinal"]
    for vessel_hash, positions in rows_for_vessel.items():
        per_file: dict[int, list[int]] = defaultdict(list)
        for position in positions:
            per_file[int(file_ordinal[position])].append(int(position))
        for ordinal, candidates in per_file.items():
            candidates.sort(key=lambda position: (
                _selection_score(vessel_hash, ordinal, int(record_ordinal[position])),
                int(record_ordinal[position])))
            mask[candidates[:SAMPLES_PER_VESSEL_PER_FILE]] = True
    return mask


def _selection_score(vessel_hash: str, file_ordinal: int, record_ordinal: int) -> str:
    """The 2026-10-28 reservoir key, reproduced so the s4 cell is comparable."""
    return hashlib.sha256(
        f"{vessel_hash}\0{file_ordinal}\0{record_ordinal}".encode("ascii")).hexdigest()


def _column_stats(matrix: np.ndarray) -> np.ndarray:
    """mean/std/q25/q75 per column over finite entries, NaN where none exist."""
    width = matrix.shape[1]
    out = np.full(4 * width, np.nan)
    for column in range(width):
        observed = matrix[np.isfinite(matrix[:, column]), column]
        if observed.size:
            out[column] = observed.mean()
            out[width + column] = observed.std(ddof=0)
            out[2 * width + column], out[3 * width + column] = np.quantile(
                observed, [0.25, 0.75])
    return out


def aggregate(positions: np.ndarray, columns: dict, sample_mask, features: str) -> np.ndarray:
    """One feature vector per vessel. NaN marks a statistic with no observation.

    ``positions`` indexes this vessel's rows; the sample level narrows them and
    the validity flag narrows them again, in that order, so an s4 vessel whose
    four sampled rows are all unusable abstains exactly as it did in cycle 1.
    """
    width = 36 if features == "dist36" else 68
    chosen = positions if sample_mask is None else positions[sample_mask[positions]]
    chosen = chosen[columns["valid"][chosen]]
    if chosen.size == 0:
        return np.full(width, np.nan)
    shape = _column_stats(columns["shape9"][chosen].astype(np.float64))
    if features == "dist36":
        return shape
    scale = _column_stats(columns["scale8"][chosen].astype(np.float64))
    return np.concatenate((shape, scale))


def build_matrix(hashes, index, sample, features):
    columns = index["columns"]
    sample_mask = index["s4_mask"] if sample == "s4" else None
    if sample not in SAMPLE_LEVELS:
        raise ValueError(f"unknown sample level {sample!r}")
    empty = np.empty(0, dtype=np.int64)
    vectors = [aggregate(index["rows_for_vessel"].get(vessel_hash, empty),
                         columns, sample_mask, features) for vessel_hash in hashes]
    X = np.asarray(vectors, dtype=np.float64)
    y = np.asarray([index["label_by_vessel"][vessel_hash] for vessel_hash in hashes],
                   dtype=np.int64)
    return X, y


def evaluate(y_true, probabilities, abstain, n_classes):
    """Macro F1 over scorable vessels, plus the class detail the gate needs."""
    predicted = probabilities.argmax(axis=1)
    predicted[abstain] = -1
    scorable = ~abstain
    f1s, recalls, supports = [], [], []
    for cls in range(n_classes):
        actual = (y_true == cls)
        guessed = (predicted == cls)
        true_positive = int(np.count_nonzero(actual & guessed))
        denominator = int(np.count_nonzero(actual & scorable)) + int(np.count_nonzero(guessed))
        f1s.append(2 * true_positive / denominator if denominator else 0.0)
        support = int(np.count_nonzero(actual & scorable))
        supports.append(support)
        recalls.append(true_positive / support if support else None)
    correct = int(np.count_nonzero((predicted == y_true) & scorable))
    return {
        "macro_f1": float(np.mean(f1s)),
        "accuracy": correct / int(np.count_nonzero(scorable)) if scorable.any() else None,
        "per_class_f1": [round(value, 5) for value in f1s],
        "per_class_recall": [None if value is None else round(value, 5) for value in recalls],
        "per_class_support": supports,
        "correct": correct,
        "scorable": int(np.count_nonzero(scorable)),
        "abstain": int(np.count_nonzero(abstain)),
        "coverage": float(np.mean(scorable)),
    }


def run_cell(sample, weight, features, splits, index):
    """Fit and score one factorial cell across the three development splits."""
    per_split = []
    for seed in DEV_SEEDS:
        split = splits[str(seed)]
        train_x, train_y = build_matrix(split["train"], index, sample, features)
        val_x, val_y = build_matrix(split["validation"], index, sample, features)
        train_usable = np.isfinite(train_x).any(axis=1)
        if not train_usable.any():
            raise ValueError("no usable training vessel")
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
        metrics = evaluate(val_y, probabilities, abstain, N_CLASSES)
        metrics["seed"] = seed
        metrics["train_vessels"] = int(train_usable.sum())
        metrics["input_width"] = int(fitted_train.shape[1])
        per_split.append(metrics)

    def mean_of(key):
        values = [item[key] for item in per_split if item[key] is not None]
        return float(np.mean(values)) if values else None

    recall_means = []
    for cls in range(N_CLASSES):
        values = [item["per_class_recall"][cls] for item in per_split
                  if item["per_class_recall"][cls] is not None]
        recall_means.append(float(np.mean(values)) if values else None)
    return {
        "cell": {"sample": sample, "weight": weight, "features": features},
        "mean_macro_f1": mean_of("macro_f1"),
        "mean_accuracy": mean_of("accuracy"),
        "mean_coverage": mean_of("coverage"),
        "mean_per_class_recall": [None if value is None else round(value, 5)
                                  for value in recall_means],
        "splits": per_split,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--labels", type=Path,
                        default=DEFAULT_OUT / "label_vocabulary.json")
    args = parser.parse_args()

    started = time.perf_counter()
    class_names = load_class_names(args.labels)
    index = load_extract(args.extract)
    roster = [{"vessel_hash": vessel_hash, "label": class_names[label]}
              for vessel_hash, label in index["label_by_vessel"].items()]
    final_hashes, dev_hashes, counts = _stratified_final_split(roster, list(class_names))
    dev_roster = [item for item in roster if item["vessel_hash"] in set(dev_hashes)]
    splits = _development_splits(dev_roster, list(class_names))

    # The final holdout is not read here. Only its size is reported.
    final_set = set(final_hashes)
    for seed, split in splits.items():
        for role, hashes in split.items():
            if final_set & set(hashes):
                raise AssertionError(f"final holdout leaked into {role} of seed {seed}")

    # One JSON per cell: this environment kills long runs, so a kill costs a
    # single cell rather than the whole factorial.
    cell_dir = args.out / "cells"
    cell_dir.mkdir(parents=True, exist_ok=True)
    cells = []
    for sample in SAMPLE_LEVELS:
        for weight in WEIGHT_LEVELS:
            for features in FEATURE_LEVELS:
                cache = cell_dir / f"{sample}_{weight}_{features}.json"
                if cache.exists():
                    result = json.loads(cache.read_text(encoding="utf-8"))
                    print(f"{sample:4s} {weight:9s} {features:15s} (reused)", flush=True)
                    cells.append(result)
                    continue
                cell_started = time.perf_counter()
                result = run_cell(sample, weight, features, splits, index)
                result["seconds"] = round(time.perf_counter() - cell_started, 1)
                cache.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
                cells.append(result)
                print(f"{sample:4s} {weight:9s} {features:15s} "
                      f"MacroF1={result['mean_macro_f1']:.5f} "
                      f"acc={result['mean_accuracy']:.5f} "
                      f"recall={result['mean_per_class_recall']} "
                      f"({result['seconds']}s)", flush=True)

    by_cell = {(item["cell"]["sample"], item["cell"]["weight"], item["cell"]["features"]): item
               for item in cells}
    contrasts = []
    for key, result in by_cell.items():
        for position, levels in enumerate((SAMPLE_LEVELS, WEIGHT_LEVELS, FEATURE_LEVELS)):
            if key[position] != levels[0]:
                continue
            other = list(key)
            other[position] = levels[1]
            counterpart = by_cell[tuple(other)]
            contrasts.append({
                "factor": ("sample", "weight", "features")[position],
                "from": levels[0], "to": levels[1],
                "held_fixed": {name: key[i] for i, name in
                               enumerate(("sample", "weight", "features")) if i != position},
                "delta_macro_f1": round(counterpart["mean_macro_f1"] - result["mean_macro_f1"], 5),
                "delta_accuracy": round(counterpart["mean_accuracy"] - result["mean_accuracy"], 5),
                "delta_pot_trap_recall": (
                    round((counterpart["mean_per_class_recall"][1] or 0.0)
                          - (result["mean_per_class_recall"][1] or 0.0), 5)),
            })

    report = {
        "schema_version": "cycle2_development_ablation_v1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contract": {
            "design": "2x2x2 factorial, one factor per contrast",
            "model_held_fixed": "ExtraTrees(n_estimators=256, min_samples_leaf=2, "
                                "max_features=1.0), averaged over seeds 42 and 137",
            "split_source": "frozen real_model_cycle_20261028 functions",
            "final_split_seed": FINAL_SPLIT_SEED,
            "development_seeds": list(DEV_SEEDS),
            "class_names": list(class_names),
            "reference_cell": list(REFERENCE_CELL),
            "selection_on": "development validation only; final holdout not read",
        },
        "class_counts": counts,
        "final_holdout_size": len(final_hashes),
        "development_size": len(dev_hashes),
        "extract_totals": index["totals"],
        "feature_names": {"shape9": list(SHAPE9_NAMES), "scale8": list(SCALE8_NAMES)},
        "cells": cells,
        "single_factor_contrasts": contrasts,
        "limitations": [
            "Validation Macro F1 is a selection metric, not a held-out score.",
            "Scale features are polyline geometry in km, never speed.",
            "A contrast shows association under this fixed design, not a general cause.",
        ],
        "wall_seconds": round(time.perf_counter() - started, 1),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "development_ablation.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
