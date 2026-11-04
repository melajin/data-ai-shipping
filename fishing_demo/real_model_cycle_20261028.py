"""Frozen-protocol, vessel-level modeling cycle for real fishing labels.

This is deliberately separate from the S0 synthetic-data pipeline. The caller
provides already scanned vessel aggregates; this module never reads source
files. Final values, labels and source rows are accessed only after a freeze
artifact has been atomically written.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import cmp_to_key
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import platform
import shutil
import sys
import tempfile
import time
from typing import Callable

import numpy as np
import sklearn
from sklearn.ensemble import ExtraTreesClassifier

from .models import Classifier, Preprocessor, classification_metrics, fit_temperature, softmax
from .real_geometry_20261028 import FEATURE_NAMES


BASELINE = "mean9_mlp16"
R1 = "distribution36_mlp16"
R2_LINEAR = "distribution36_linear"
R2_TREES = "distribution36_extratrees256_leaf2"
CANDIDATE_ORDER = (R1, R2_LINEAR, R2_TREES)
INIT_SEEDS = (42, 137)
DEV_SEEDS = (3201, 3202, 3203)
FINAL_SPLIT_SEED = 20261028
BOOTSTRAP_SEED = 20261028
BOOTSTRAP_REPLICATES = 2000

_BASELINE_CONFIG = {"features": "mean9", "model": "mlp", "hidden": 16, "l2": 0.01,
                    "max_epochs": 400, "learning_rate": 0.03, "patience": 35}
_R1_CONFIG = {"features": "distribution36", "model": "mlp", "hidden": 16, "l2": 0.01,
              "max_epochs": 400, "learning_rate": 0.03, "patience": 35}
_R2_LINEAR_CONFIG = {"features": "distribution36", "model": "linear", "hidden": 0,
                     "l2": 0.01, "max_epochs": 400, "learning_rate": 0.03, "patience": 35}
_R2_TREES_CONFIG = {"features": "distribution36", "model": "extra_trees",
                    "n_estimators": 256, "min_samples_leaf": 2, "max_features": 1.0,
                    "n_jobs": 1, "class_weight": None, "probability_clip": 1e-15}


def _canonical_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha256(value) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(_json_safe(value), stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot_sources(output_dir: Path, source_files: dict[str, Path]) -> dict[str, str]:
    snapshot_dir = output_dir / "source_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    copied_hashes = {}
    for name, source in source_files.items():
        destination = snapshot_dir / name
        shutil.copy2(source, destination)
        copied_hashes[name] = _file_sha256(destination)
    return copied_hashes


def _json_safe(value):
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _rank_key(seed: int, label: str, vessel_hash: str) -> str:
    return hashlib.sha256(f"{seed}\0{label}\0{vessel_hash}".encode("utf-8")).hexdigest()


def _stratified_final_split(vessels, class_names):
    grouped = defaultdict(list)
    for vessel in vessels:
        grouped[vessel["label"]].append(vessel["vessel_hash"])
    final, development = [], []
    counts = {}
    for label in class_names:
        hashes = sorted(grouped[label])
        n = len(hashes)
        if n < 10:
            raise ValueError(f"class {label!r} has {n} unique vessels; at least 10 required; evaluation deferred")
        final_n = max(2, int(math.floor(0.20 * n)))
        ordered = sorted(hashes, key=lambda item: (_rank_key(FINAL_SPLIT_SEED, label, item), item))
        final.extend(ordered[:final_n])
        development.extend(ordered[final_n:])
        counts[label] = {"all": n, "final": final_n, "development": n - final_n}
    return sorted(final), sorted(development), counts


def _development_splits(dev_vessels, class_names):
    by_label = defaultdict(list)
    for vessel in dev_vessels:
        by_label[vessel["label"]].append(vessel["vessel_hash"])
    manifests = {}
    for seed in DEV_SEEDS:
        split = {"train": [], "validation": [], "calibration": []}
        for label in class_names:
            hashes = sorted(by_label[label], key=lambda item: (_rank_key(seed, label, item), item))
            n = len(hashes)
            n_train = int(math.floor(0.70 * n))
            n_validation = max(2, int(math.floor(0.15 * n)))
            n_calibration = max(2, n - n_train - n_validation)
            n_train = n - n_validation - n_calibration
            if n_train < 2:
                raise ValueError(f"class {label!r} has too few development vessels for train/validation/calibration")
            split["train"].extend(hashes[:n_train])
            split["validation"].extend(hashes[n_train:n_train + n_validation])
            split["calibration"].extend(hashes[n_train + n_validation:])
        for role in split:
            split[role].sort()
        if (set(split["train"]) & set(split["validation"])
                or set(split["train"]) & set(split["calibration"])
                or set(split["validation"]) & set(split["calibration"])):
            raise AssertionError("development roles overlap")
        manifests[str(seed)] = split
    return manifests


def _validate_roster(vessels, class_names):
    if not isinstance(vessels, list) or not vessels:
        raise ValueError("vessels must be a nonempty list")
    seen = set()
    checked = []
    for row in vessels:
        if not isinstance(row, dict):
            raise ValueError("each vessel roster entry must be an object")
        vessel_hash, label = row.get("vessel_hash"), row.get("label")
        if not isinstance(vessel_hash, str) or not vessel_hash.strip():
            raise ValueError("vessel_hash must be a nonempty string")
        if vessel_hash in seen:
            raise ValueError("vessel_hash values must be unique")
        if label not in class_names:
            raise ValueError("each vessel must have exactly one declared class label")
        seen.add(vessel_hash)
        # Keep only roster fields before freeze. Do not inspect final rows here.
        checked.append({"vessel_hash": vessel_hash, "label": label, "_source": row})
    counts = Counter(item["label"] for item in checked)
    if set(counts) != set(class_names):
        raise ValueError("all declared classes must be present")
    return checked


def _validate_vessel_rows(vessel):
    rows = vessel.get("rows")
    if not isinstance(rows, list):
        raise ValueError("vessel rows must be a list")
    seen_locations = set()
    checked = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each row must be an object")
        file_ordinal, record_ordinal, month = row.get("file_ordinal"), row.get("record_ordinal"), row.get("month")
        if (isinstance(file_ordinal, bool) or not isinstance(file_ordinal, int) or file_ordinal < 0
                or isinstance(record_ordinal, bool) or not isinstance(record_ordinal, int) or record_ordinal < 0):
            raise ValueError("source ordinals must be nonnegative integers")
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise ValueError("month must be an integer in [1, 12]")
        location = (file_ordinal, record_ordinal)
        if location in seen_locations:
            raise ValueError("source row locations must be unique within vessel")
        seen_locations.add(location)
        valid = row.get("valid")
        if type(valid) is not bool:
            raise ValueError("row valid must be boolean")
        reason = row.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("row reason must be a string or null")
        values = _checked_values(row.get("values"), "values")
        degree = _checked_values(row.get("degree_control_values"), "degree_control_values")
        if valid and not any(value is not None for value in values):
            raise ValueError("valid row must contain at least one available feature")
        checked.append({"file_ordinal": file_ordinal, "record_ordinal": record_ordinal,
                        "month": month, "valid": valid, "reason": reason,
                        "values": values, "degree_control_values": degree})
    return checked


def _checked_values(values, name):
    if not isinstance(values, list) or len(values) != len(FEATURE_NAMES):
        raise ValueError(f"{name} must contain exactly {len(FEATURE_NAMES)} shape9 slots")
    checked = []
    for value in values:
        if value is None:
            checked.append(None)
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} entries must be finite numbers or null")
        else:
            checked.append(float(value))
    return checked


def _aggregate_rows(rows, family="mean9", feature_source="values", exclude_month_one=False):
    source_key = "degree_control_values" if feature_source == "degree_control" else feature_source
    selected = [row for row in rows if row["valid"] and not (exclude_month_one and row["month"] == 1)]
    if not selected:
        return np.full(9 if family == "mean9" else 36, np.nan), []
    matrix = np.asarray([[np.nan if value is None else value for value in row[source_key]]
                         for row in selected], dtype=np.float64)
    means = np.full(9, np.nan)
    stds = np.full(9, np.nan)
    q25 = np.full(9, np.nan)
    q75 = np.full(9, np.nan)
    for col in range(9):
        observed = matrix[np.isfinite(matrix[:, col]), col]
        if observed.size:
            means[col] = observed.mean()
            stds[col] = observed.std(ddof=0)
            q25[col], q75[col] = np.quantile(observed, [0.25, 0.75])
    if family == "mean9":
        vector = means
    else:
        vector = np.concatenate((means, stds, q25, q75))
    return vector, selected


def _probability_metrics(y, probabilities, abstain, n_classes):
    y = np.asarray(y, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    abstain = np.asarray(abstain, dtype=bool)
    scorable = ~abstain
    predicted = probabilities.argmax(axis=1)
    predicted[abstain] = -1
    confusion = np.zeros((n_classes, n_classes + 1), dtype=np.int64)
    np.add.at(confusion, (y, np.where(predicted < 0, n_classes, predicted)), 1)
    support = np.bincount(y[scorable], minlength=n_classes) if scorable.any() else np.zeros(n_classes, dtype=np.int64)
    predicted_support = confusion[:, :n_classes].sum(axis=0)
    denom = support + predicted_support
    f1 = np.divide(2 * np.diag(confusion[:, :n_classes]), denom,
                   out=np.zeros(n_classes, dtype=np.float64), where=denom > 0)
    if scorable.any():
        standard = classification_metrics(y[scorable], probabilities[scorable])
        accuracy = standard["accuracy"]
        macro_f1 = standard["macro_f1"]
        nll = standard["nll"]
        brier = standard["brier"]
    else:
        accuracy = macro_f1 = None
        nll = brier = None
    return {"accuracy": accuracy,
            "macro_f1": macro_f1, "nll": nll,
            "brier": brier,
            "confusion_with_abstain_column": confusion.tolist(),
            "support": support.tolist(), "abstain_count": int(abstain.sum()),
            "denominator": int(len(y)), "probability_metric_denominator": int(scorable.sum()),
            "coverage": float(scorable.mean()) if len(y) else 0.0,
            "full_roster_accuracy": float(np.mean(predicted == y)) if len(y) else None}


def _metric_delta(candidate, baseline):
    return {key: (candidate[key] - baseline[key]
                  if candidate[key] is not None and baseline[key] is not None else None)
            for key in ("macro_f1", "accuracy", "nll", "brier")}


def _selection_compare(left, right, means, deltas):
    """Order by F1 improvement, then absolute NLL, with explicit 1e-12 ties."""
    f1_difference = deltas[left]["macro_f1"] - deltas[right]["macro_f1"]
    if abs(f1_difference) > 1e-12:
        return -1 if f1_difference > 0 else 1
    nll_difference = means[left]["nll"] - means[right]["nll"]
    if abs(nll_difference) > 1e-12:
        return -1 if nll_difference < 0 else 1
    return CANDIDATE_ORDER.index(left) - CANDIDATE_ORDER.index(right)


def _best_candidate(names, means, deltas):
    return sorted(names, key=cmp_to_key(lambda left, right:
                                        _selection_compare(left, right, means, deltas)))[0]


def _candidate_spec(name):
    if name == BASELINE:
        return _BASELINE_CONFIG
    if name == R1:
        return _R1_CONFIG
    if name == R2_LINEAR:
        return _R2_LINEAR_CONFIG
    if name == R2_TREES:
        return _R2_TREES_CONFIG
    raise ValueError(f"unknown candidate {name}")


def _feature_key(name):
    return "mean9" if name == BASELINE else "distribution36"


def _x_for(vessels, feature_set, feature_source="values", exclude_month_one=False):
    vectors, selected_rows = [], []
    for vessel in vessels:
        rows = vessel["_rows"]
        values, used_rows = _aggregate_rows(rows, feature_set, feature_source, exclude_month_one)
        if feature_set == "mean9" and len(values) != 9:
            raise AssertionError("mean9 aggregation width changed")
        vectors.append(values)
        selected_rows.append(used_rows)
    return np.asarray(vectors, dtype=np.float64), selected_rows


def _new_estimator(name, input_dim, n_classes, seed):
    if name == R2_TREES:
        return ExtraTreesClassifier(n_estimators=256, min_samples_leaf=2, max_features=1.0,
                                    n_jobs=1, class_weight=None, random_state=seed)
    hidden = 0 if name == R2_LINEAR else 16
    return Classifier(input_dim=input_dim, n_classes=n_classes, hidden=hidden, l2=0.01, seed=seed)


def _fit_one(name, seed, train_x, train_y, val_x, val_y, cal_x, cal_y, n_classes):
    train_mask = np.isfinite(train_x).any(axis=1)
    val_mask = np.isfinite(val_x).any(axis=1)
    cal_mask = np.isfinite(cal_x).any(axis=1)
    if not train_mask.any() or not val_mask.any() or not cal_mask.any():
        raise ValueError("training, validation and calibration each need at least one valid-geometry vessel")
    if set(train_y[train_mask]) != set(range(n_classes)):
        raise ValueError("each class needs valid-geometry training vessels")
    preprocessor = Preprocessor().fit(train_x[train_mask])
    train_z = preprocessor.transform(train_x[train_mask])
    val_z = preprocessor.transform(val_x[val_mask])
    cal_z = preprocessor.transform(cal_x[cal_mask])
    train_y_fit, val_y_fit, cal_y_fit = train_y[train_mask], val_y[val_mask], cal_y[cal_mask]
    estimator = _new_estimator(name, train_z.shape[1], n_classes, seed)
    if name == R2_TREES:
        estimator.fit(train_z, train_y_fit)
        def logits_for(x):
            probs = estimator.predict_proba(x)
            classes = np.asarray(estimator.classes_)
            if not np.array_equal(classes, np.arange(n_classes)):
                raise ValueError("ExtraTrees classes_ order must exactly match declared class indices")
            probs = np.clip(probs, 1e-15, 1.0)
            return np.log(probs)
        cal_logits = logits_for(cal_z)
        val_logits = logits_for(val_z)
        temperature = fit_temperature(cal_logits, cal_y_fit)
        cal_probabilities = softmax(cal_logits, temperature)
        val_probabilities = softmax(val_logits, temperature)
        history = []
    else:
        history = estimator.fit(train_z, train_y_fit, val_z, val_y_fit,
                                epochs=400, learning_rate=0.03, patience=35)
        cal_logits = estimator.predict_logits(cal_z)
        val_logits = estimator.predict_logits(val_z)
        temperature = fit_temperature(cal_logits, cal_y_fit)
        cal_probabilities = softmax(cal_logits, temperature)
        val_probabilities = softmax(val_logits, temperature)
    all_val_probabilities = np.full((len(val_y), n_classes), 1.0 / n_classes)
    all_val_probabilities[val_mask] = val_probabilities
    all_val_logits = np.full((len(val_y), n_classes), np.nan)
    all_val_logits[val_mask] = val_logits
    state = {"preprocessor": preprocessor.to_dict(), "temperature": temperature,
             "estimator_kind": "pickle" if name == R2_TREES else "json_state",
             "history": history}
    if name == R2_TREES:
        state["estimator_pickle"] = pickle.dumps(estimator, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        state["estimator"] = estimator.to_dict()
    return {"state": state, "calibration_logits": cal_logits, "calibration_probabilities": cal_probabilities,
            "validation_logits": all_val_logits, "validation_probabilities": all_val_probabilities,
            "temperature": float(temperature), "history": history,
            "calibration_labels": cal_y_fit.tolist(),
            "validation_labels": val_y[val_mask].tolist()}


def _restore_state(candidate, state, estimator_bytes=None):
    preprocessor = Preprocessor.from_dict(state["preprocessor"])
    if candidate == R2_TREES:
        if estimator_bytes is None:
            estimator_bytes = state.get("estimator_pickle")
        estimator = pickle.loads(estimator_bytes)
    else:
        estimator = Classifier.from_dict(state["estimator"])
    return preprocessor, estimator


def _predict_state(candidate, state, X):
    preprocessor, estimator = _restore_state(candidate, state)
    transformed = preprocessor.transform(X)
    if candidate == R2_TREES:
        probs = estimator.predict_proba(transformed)
        if not np.array_equal(np.asarray(estimator.classes_), np.arange(probs.shape[1])):
            raise ValueError("ExtraTrees classes_ order must exactly match declared class indices")
        logits = np.log(np.clip(probs, 1e-15, 1.0))
    else:
        logits = estimator.predict_logits(transformed)
    return logits, softmax(logits, state["temperature"])


def _train_candidate(name, split, seed, rows_by_hash, class_index, class_names,
                     feature_source="values"):
    role_vessels = {role: [rows_by_hash[h] for h in split[role]] for role in ("train", "validation", "calibration")}
    feature_set = _feature_key(name)
    X = {role: _x_for(vessels, feature_set, feature_source=feature_source)[0]
         for role, vessels in role_vessels.items()}
    y = {role: np.asarray([class_index[v["label"]] for v in role_vessels[role]], dtype=np.int64)
         for role in role_vessels}
    for role in ("train", "validation", "calibration"):
        usable = np.isfinite(X[role]).any(axis=1)
        for label_index, label in enumerate(class_names):
            if not np.any(usable & (y[role] == label_index)):
                raise ValueError(f"class {label!r} needs at least one valid-geometry vessel in {role}")
    fit = _fit_one(name, seed, X["train"], y["train"], X["validation"], y["validation"],
                   X["calibration"], y["calibration"], len(class_names))
    return fit, X, y, role_vessels


def _evaluate_development(roster, development_splits, class_names, output_dir):
    class_index = {label: index for index, label in enumerate(class_names)}
    rows_by_hash = {item["vessel_hash"]: item for item in roster}
    candidate_metrics = {name: [] for name in (BASELINE,) + CANDIDATE_ORDER}
    split_candidate_metrics = {}
    model_audit = {}
    degree_metrics = []
    for split_seed, split in development_splits.items():
        split_candidate_metrics[split_seed] = {}
        for name in (BASELINE,) + CANDIDATE_ORDER:
            init_predictions = []
            init_states = []
            val_y = None
            val_vessels = None
            for init in INIT_SEEDS:
                fit, arrays, labels, roles = _train_candidate(
                    name, split, init, rows_by_hash, class_index, class_names)
                val_y = labels["validation"]
                val_vessels = roles["validation"]
                init_predictions.append(fit["validation_probabilities"])
                init_states.append({"temperature": fit["temperature"],
                                    "calibration_labels": fit["calibration_labels"],
                                    "validation_labels": fit["validation_labels"],
                                    "calibration_logits": fit["calibration_logits"].tolist(),
                                    "calibration_probabilities": fit["calibration_probabilities"].tolist(),
                                    "validation_logits": fit["validation_logits"].tolist(),
                                    "validation_probabilities": fit["validation_probabilities"].tolist(),
                                    "model_state": ({k: v for k, v in fit["state"].items() if k != "estimator_pickle"}),
                                    "estimator_pickle_hex": fit["state"].get("estimator_pickle", b"").hex()
                                    if name == R2_TREES else None,
                                    "history": fit["history"]})
            average = np.mean(init_predictions, axis=0)
            metric = _probability_metrics(val_y, average,
                                         ~np.isfinite(_x_for(val_vessels, _feature_key(name))[0]).any(axis=1),
                                         len(class_names))
            candidate_metrics[name].append(metric)
            split_candidate_metrics[split_seed][name] = metric
            model_audit[f"{split_seed}/{name}"] = init_states

        # Predeclared degree-control sensitivity: baseline model, same split and seeds.
        degree_init = []
        for init in INIT_SEEDS:
            fit, arrays, labels, roles = _train_candidate(
                BASELINE, split, init, rows_by_hash, class_index, class_names,
                feature_source="degree_control")
            degree_init.append(fit["validation_probabilities"])
        degree_probabilities = np.mean(degree_init, axis=0)
        degree_abstain = ~np.isfinite(_x_for(roles["validation"], "mean9", "degree_control")[0]).any(axis=1)
        degree_metrics.append(_probability_metrics(labels["validation"], degree_probabilities,
                                                   degree_abstain, len(class_names)))

    means = {name: {key: float(np.mean([item[key] for item in metrics]))
                    for key in ("accuracy", "macro_f1", "nll", "brier")}
             for name, metrics in candidate_metrics.items()}
    deltas = {name: _metric_delta(means[name], means[BASELINE])
              for name in (BASELINE,) + CANDIDATE_ORDER}
    eligible = []
    for order, name in enumerate(CANDIDATE_ORDER):
        delta = deltas[name]
        positive_splits = sum(
            split_candidate_metrics[str(seed)][name]["macro_f1"]
            > split_candidate_metrics[str(seed)][BASELINE]["macro_f1"]
            for seed in DEV_SEEDS)
        passed = (delta["macro_f1"] >= 0.03 and delta["accuracy"] >= -0.01
                  and delta["nll"] <= 0.02 and delta["brier"] <= 0.01 and positive_splits >= 2)
        if passed:
            eligible.append((name, positive_splits, order))
    if eligible:
        selected = _best_candidate([item[0] for item in eligible], means, deltas)
        selection_reason = "development_admissibility_passed"
        confirmatory = True
    else:
        selected = _best_candidate(CANDIDATE_ORDER, means, deltas)
        selection_reason = "no_candidate_met_development_admissibility; exploratory_comparator_only"
        confirmatory = False
    development = {"split_metrics": split_candidate_metrics,
                   "mean_metrics": means, "deltas_vs_baseline": deltas,
                   "degree_control_baseline_metrics": degree_metrics,
                   "selection": {"candidate": selected, "reason": selection_reason,
                                 "confirmatory_candidate": confirmatory,
                                 "eligible_candidates": [item[0] for item in eligible]},
                   "model_audit": model_audit}
    return development, selected


def _bootstrap_macro_f1_delta(y, baseline_probs, candidate_probs, baseline_abstain,
                              candidate_abstain):
    y = np.asarray(y, dtype=np.int64)
    if not np.array_equal(baseline_abstain, candidate_abstain):
        raise ValueError("paired bootstrap requires one shared scorable roster")
    scorable = ~np.asarray(baseline_abstain, dtype=bool)
    if not scorable.any():
        return {"replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
                "method": "paired class-stratified vessel bootstrap on shared scorable roster",
                "macro_f1_delta_ci95": [None, None], "lower_bound_above_zero": False,
                "scorable_vessels": 0}
    y = y[scorable]
    baseline_probs = np.asarray(baseline_probs)[scorable]
    candidate_probs = np.asarray(candidate_probs)[scorable]
    groups = [np.flatnonzero(y == label) for label in range(baseline_probs.shape[1])]
    groups = [group for group in groups if len(group)]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    deltas = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    for draw in range(BOOTSTRAP_REPLICATES):
        sampled = np.concatenate([rng.choice(group, size=len(group), replace=True) for group in groups])
        baseline = _probability_metrics(y[sampled], baseline_probs[sampled],
                                        np.zeros(len(sampled), dtype=bool), baseline_probs.shape[1])
        candidate = _probability_metrics(y[sampled], candidate_probs[sampled],
                                         np.zeros(len(sampled), dtype=bool), candidate_probs.shape[1])
        deltas[draw] = candidate["macro_f1"] - baseline["macro_f1"]
    low, high = np.quantile(deltas, [0.025, 0.975])
    return {"replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
            "method": "paired class-stratified vessel bootstrap; percentile 95% interval",
            "macro_f1_delta_ci95": [float(low), float(high)],
            "lower_bound_above_zero": bool(low > 0)}


def _write_frozen_artifacts(output_dir, freeze, manifest):
    freeze_path = output_dir / "freeze.json"
    manifest_path = output_dir / "split_manifest.json"
    _atomic_json(manifest_path, manifest)
    _atomic_json(freeze_path, freeze)
    return freeze_path, manifest_path


def _array_diff(saved, recalculated, name):
    saved_array = np.asarray([[np.nan if value is None else value for value in row]
                              for row in saved], dtype=np.float64)
    recalculated_array = np.asarray(recalculated, dtype=np.float64)
    if saved_array.shape != recalculated_array.shape:
        raise ValueError(f"saved/recalculated {name} shapes differ")
    saved_finite, calculated_finite = np.isfinite(saved_array), np.isfinite(recalculated_array)
    if not np.array_equal(saved_finite, calculated_finite):
        raise ValueError(f"saved/recalculated {name} finite masks differ")
    if not saved_finite.any():
        return 0.0
    return float(np.max(np.abs(saved_array[saved_finite] - recalculated_array[saved_finite])))


def _verify_saved_final_models(output_dir, freeze_path, final_hashes, rows_by_hash,
                               training_roster, class_names, candidate,
                               baseline_x, candidate_x, baseline_abstain, candidate_abstain):
    """Reload serialized final states and independently re-predict cached features."""
    output_dir = Path(output_dir)
    freeze = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
    predictions = json.loads((output_dir / "final_predictions.json").read_text(encoding="utf-8"))
    saved_audit = json.loads((output_dir / "final_model_audit.json").read_text(encoding="utf-8"))
    snapshot_dir = output_dir / "source_snapshot"
    snapshot_hashes = {name: _file_sha256(snapshot_dir / name)
                       for name in freeze["source_file_hashes"]}
    if snapshot_hashes != freeze["source_file_hashes"]:
        raise ValueError("source snapshot no longer matches the frozen source hashes")
    prediction_by_hash = {item["vessel_hash"]: item for item in predictions}
    if list(prediction_by_hash) != list(final_hashes):
        raise ValueError("saved final prediction order/hash list differs from frozen manifest")
    split = freeze["split_manifest"]["development"]["3201"]
    calibration_vessels = [training_roster[h] for h in split["calibration"]]
    verification = {"status": "ok", "source_snapshot_verified": True,
                    "source_file_hashes": freeze["source_file_hashes"],
                    "source_snapshot_hashes": snapshot_hashes,
                    "models": {}, "max_abs_diff": 0.0,
                    "tolerance": 1e-12, "fit_repeated": False}
    for name, X, abstain, output_field in (
            (BASELINE, baseline_x, baseline_abstain, "baseline_probabilities"),
            (candidate, candidate_x, candidate_abstain, "candidate_probabilities")):
        calibration_x = _x_for(calibration_vessels, _feature_key(name))[0]
        calibration_mask = np.isfinite(calibration_x).any(axis=1)
        per_init_probabilities = []
        init_reports = []
        model_max_diff = 0.0
        for saved_state in saved_audit[name]:
            model_state = dict(saved_state["model_state"])
            if name == R2_TREES:
                model_state["estimator_pickle"] = bytes.fromhex(saved_state["estimator_pickle_hex"])
            calibration_logits, calibration_probabilities = _predict_state(
                name, model_state, calibration_x[calibration_mask])
            final_logits, final_probabilities = _predict_state(name, model_state, X)
            final_logits[abstain] = np.nan
            final_probabilities[abstain] = 1.0 / len(class_names)
            per_init_probabilities.append(final_probabilities)
            differences = {
                "calibration_logits": _array_diff(saved_state["calibration_logits"],
                                                   calibration_logits, "calibration_logits"),
                "calibration_probabilities": _array_diff(saved_state["calibration_probabilities"],
                                                           calibration_probabilities,
                                                           "calibration_probabilities"),
                "final_logits": _array_diff(saved_state["final_logits"], final_logits, "final_logits"),
                "final_probabilities": _array_diff(saved_state["final_probabilities"],
                                                     final_probabilities, "final_probabilities"),
            }
            if max(differences.values()) > verification["tolerance"]:
                raise ValueError(f"saved final model state failed prediction reload check: {name}")
            init_reports.append({"init_seed": saved_state["init_seed"], "max_abs_diff": differences})
            verification["max_abs_diff"] = max(verification["max_abs_diff"], *differences.values())
            model_max_diff = max(model_max_diff, *differences.values())
        ensemble = np.mean(per_init_probabilities, axis=0)
        for row_index, vessel_hash in enumerate(final_hashes):
            saved_probability = prediction_by_hash[vessel_hash][output_field]
            if abstain[row_index]:
                if saved_probability is not None:
                    raise ValueError("abstained saved prediction must have null probabilities")
                continue
            if saved_probability is None:
                raise ValueError("scorable saved prediction has null probabilities")
            difference = float(np.max(np.abs(np.asarray(saved_probability) - ensemble[row_index])))
            if difference > verification["tolerance"]:
                raise ValueError(f"saved ensemble probability failed reload check: {name}")
            verification["max_abs_diff"] = max(verification["max_abs_diff"], difference)
            model_max_diff = max(model_max_diff, difference)
        verification["models"][name] = {"initializations": init_reports,
                                        "max_abs_diff": model_max_diff}
    _atomic_json(output_dir / "model_reload_verification.json", verification)
    return verification


def _evaluate_final_after_freeze(freeze_path: Path, candidate: str, roster_by_hash,
                                 final_hashes, class_names, output_dir,
                                 final_loader: Callable | None = None):
    """Final gate; reads final values/labels only after the freeze file exists."""
    if not freeze_path.is_file():
        raise RuntimeError("final evaluation is forbidden until freeze.json is stored")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("selection", {}).get("candidate") != candidate:
        raise ValueError("final candidate does not match the frozen selection")
    if final_loader is None:
        final_vessels = [roster_by_hash[h]["_source"] for h in final_hashes]
    else:
        final_vessels = final_loader(list(final_hashes))
    if not isinstance(final_vessels, list):
        raise ValueError("final_loader must return a list of vessel records")
    final_by_hash = {}
    for vessel in final_vessels:
        if not isinstance(vessel, dict):
            raise ValueError("final loader returned a non-object vessel")
        vessel_hash = vessel.get("vessel_hash")
        if vessel_hash in final_by_hash or vessel_hash not in final_hashes:
            raise ValueError("final loader returned duplicate or unexpected vessel hash")
        # Label/row content enters the evaluation path only beyond this gate.
        final_by_hash[vessel_hash] = vessel
    if set(final_by_hash) != set(final_hashes):
        raise ValueError("final loader did not return the frozen final vessel roster")
    expected_labels = {h: roster_by_hash[h]["label"] for h in final_hashes}
    rows_by_hash = {}
    for vessel_hash, vessel in final_by_hash.items():
        if vessel.get("label") != expected_labels[vessel_hash]:
            raise ValueError("final label differs from predeclared stratification label")
        rows_by_hash[vessel_hash] = {"vessel_hash": vessel_hash,
                                     "label": vessel["label"],
                                     "_rows": _validate_vessel_rows(vessel)}

    class_names = tuple(class_names)
    class_index = {label: index for index, label in enumerate(class_names)}
    y = np.asarray([class_index[rows_by_hash[h]["label"]] for h in final_hashes], dtype=np.int64)
    baseline_x, baseline_used = _x_for([rows_by_hash[h] for h in final_hashes], "mean9")
    candidate_x, candidate_used = _x_for([rows_by_hash[h] for h in final_hashes], _feature_key(candidate))
    baseline_month_x, _ = _x_for([rows_by_hash[h] for h in final_hashes], "mean9", exclude_month_one=True)
    candidate_month_x, _ = _x_for([rows_by_hash[h] for h in final_hashes], _feature_key(candidate),
                                  exclude_month_one=True)
    baseline_probs, candidate_probs = [], []
    baseline_abstain = ~np.isfinite(baseline_x).any(axis=1)
    candidate_abstain = ~np.isfinite(candidate_x).any(axis=1)
    baseline_month_abstain = ~np.isfinite(baseline_month_x).any(axis=1)
    candidate_month_abstain = ~np.isfinite(candidate_month_x).any(axis=1)
    if not np.array_equal(baseline_abstain, candidate_abstain):
        raise ValueError("baseline and candidate must have an identical primary scorable roster")
    if not np.array_equal(baseline_month_abstain, candidate_month_abstain):
        raise ValueError("baseline and candidate must have an identical month-robustness scorable roster")
    final_fit_audit = {}
    month_probability_by_name = {}
    majority_train_counts = np.zeros(len(class_names), dtype=np.int64)
    split = freeze["split_manifest"]["development"]["3201"]
    training_roster = {}
    for role in ("train", "validation", "calibration"):
        for h in split[role]:
            source = roster_by_hash[h]["_source"]
            training_roster[h] = {"vessel_hash": h, "label": roster_by_hash[h]["label"],
                                  "_source": source, "_rows": _validate_vessel_rows(source)}
    for h in split["train"]:
        vessel = training_roster[h]
        vector, _ = _aggregate_rows(vessel["_rows"], "mean9")
        if np.isfinite(vector).any():
            majority_train_counts[class_index[vessel["label"]]] += 1
    if np.any(majority_train_counts == 0):
        raise ValueError("fixed final-fit train split lacks valid-geometry support for a class")
    majority_index = int(np.argmax(majority_train_counts))
    majority_probs = np.zeros((len(y), len(class_names)), dtype=np.float64)
    majority_probs[:, majority_index] = 1.0
    for name, X, month_X, abstain, month_abstain, target in (
            (BASELINE, baseline_x, baseline_month_x, baseline_abstain, baseline_month_abstain, baseline_probs),
            (candidate, candidate_x, candidate_month_x, candidate_abstain, candidate_month_abstain, candidate_probs)):
        init_preds, month_preds, init_meta = [], [], []
        # Train and calibrate on the fixed 3201 role assignment only.
        for init in INIT_SEEDS:
            fit, arrays, labels, roles = _train_candidate(name, split, init, training_roster,
                                                          class_index, class_names)
            state = fit["state"]
            raw_logits, probabilities = _predict_state(name, state, X)
            _, month_probabilities = _predict_state(name, state, month_X)
            probabilities[abstain] = 1.0 / len(class_names)
            raw_logits[abstain] = np.nan
            month_probabilities[month_abstain] = 1.0 / len(class_names)
            init_preds.append(probabilities)
            month_preds.append(month_probabilities)
            init_meta.append({"init_seed": init, "temperature": fit["temperature"],
                              "calibration_logits": fit["calibration_logits"].tolist(),
                              "calibration_probabilities": fit["calibration_probabilities"].tolist(),
                              "final_logits": raw_logits.tolist(),
                              "final_probabilities": probabilities.tolist(),
                              "model_state": ({k: v for k, v in state.items() if k != "estimator_pickle"}),
                              "estimator_pickle_hex": state.get("estimator_pickle", b"").hex()
                              if name == R2_TREES else None,
                              "history": fit["history"]})
        target.extend(np.mean(init_preds, axis=0))
        month_probability_by_name[name] = np.mean(month_preds, axis=0)
        final_fit_audit[name] = init_meta
    baseline_probs = np.asarray(baseline_probs)
    candidate_probs = np.asarray(candidate_probs)
    baseline_metrics = _probability_metrics(y, baseline_probs, baseline_abstain, len(class_names))
    candidate_metrics = _probability_metrics(y, candidate_probs, candidate_abstain, len(class_names))
    delta = _metric_delta(candidate_metrics, baseline_metrics)
    ci = _bootstrap_macro_f1_delta(y, baseline_probs, candidate_probs, baseline_abstain,
                                   candidate_abstain)
    baseline_month_metrics = _probability_metrics(y, month_probability_by_name[BASELINE],
                                                   baseline_month_abstain, len(class_names))
    candidate_month_probs = month_probability_by_name[candidate]
    month_metrics = _probability_metrics(y, candidate_month_probs, candidate_month_abstain,
                                         len(class_names))
    candidate_original_on_month_roster = _probability_metrics(
        y, candidate_probs, candidate_month_abstain, len(class_names))
    robustness_drop = (month_metrics["macro_f1"] - candidate_original_on_month_roster["macro_f1"]
                       if (month_metrics["macro_f1"] is not None
                           and candidate_original_on_month_roster["macro_f1"] is not None) else None)
    success = (bool(freeze["selection"]["confirmatory_candidate"])
               and delta["macro_f1"] is not None and delta["macro_f1"] >= 0.03
               and ci["lower_bound_above_zero"]
               and delta["accuracy"] is not None and delta["accuracy"] >= -0.01
               and delta["nll"] is not None and delta["nll"] <= 0.02
               and delta["brier"] is not None and delta["brier"] <= 0.01
               and robustness_drop is not None and robustness_drop >= -0.03
               and all(count > 0 for count in candidate_metrics["support"]))
    predictions = []
    for index, vessel_hash in enumerate(final_hashes):
        vessel = final_by_hash[vessel_hash]
        is_abstained = bool(baseline_abstain[index] or candidate_abstain[index])
        predictions.append({"vessel_hash": vessel_hash, "label": vessel["label"],
                            "true_index": int(y[index]),
                            "baseline_probabilities": None if is_abstained else baseline_probs[index].tolist(),
                            "candidate_probabilities": None if is_abstained else candidate_probs[index].tolist(),
                            "status": "abstained" if is_abstained else "ok",
                            "abstain_reason": "no_valid_geometry_rows" if is_abstained else None,
                            "source_rows": [{"file_ordinal": row["file_ordinal"],
                                             "record_ordinal": row["record_ordinal"]}
                                            for row in vessel["rows"]],
                            "candidate_name": candidate})
    _atomic_json(output_dir / "final_predictions.json", predictions)
    _atomic_json(output_dir / "final_model_audit.json", final_fit_audit)
    reload_verification = _verify_saved_final_models(
        output_dir, freeze_path, final_hashes, rows_by_hash, training_roster, class_names,
        candidate, baseline_x, candidate_x, baseline_abstain, candidate_abstain)
    majority_scored = ~candidate_abstain
    majority_metrics = classification_metrics(y[majority_scored], majority_probs[majority_scored]) \
        if majority_scored.any() else {"accuracy": None, "macro_f1": None, "nll": None, "brier": None,
                                        "confusion": None, "support": [0] * len(class_names)}
    majority_metrics.update({"denominator": int(majority_scored.sum()),
                             "coverage": float(majority_scored.mean()),
                             "full_roster_accuracy": float(np.mean(majority_probs.argmax(axis=1) == y)),
                             "shared_scorable_roster": True})
    true_counts = Counter(rows_by_hash[h]["label"] for h in final_hashes)
    predicted_counts = Counter(class_names[int(index)] for index in candidate_probs[~candidate_abstain].argmax(axis=1))
    baseline_predicted_counts = Counter(class_names[int(index)]
                                        for index in baseline_probs[~baseline_abstain].argmax(axis=1))
    return {"baseline_metrics": baseline_metrics, "candidate_metrics": candidate_metrics,
            "majority_constant_baseline_metrics": majority_metrics,
            "majority_constant_label": class_names[majority_index],
            "majority_constant_train_support": majority_train_counts.tolist(),
            "delta_vs_baseline": delta, "paired_bootstrap": ci,
            "candidate_month1_baseline_metrics": baseline_month_metrics,
            "candidate_month1_excluded_metrics": month_metrics,
            "candidate_original_on_month1_shared_roster_metrics": candidate_original_on_month_roster,
            "candidate_month1_robustness_f1_delta": robustness_drop,
            "success_criteria_passed": bool(success), "confirmatory": bool(freeze["selection"]["confirmatory_candidate"]),
            "denominator_vessels": len(y), "scorable_vessels": int((~candidate_abstain).sum()),
            "coverage": float((~candidate_abstain).mean()),
            "abstained_vessels": int(candidate_abstain.sum()),
            "prediction_status_counts": dict(Counter(item["status"] for item in predictions)),
            "true_label_counts": dict(true_counts), "baseline_predicted_label_counts": dict(baseline_predicted_counts),
            "candidate_predicted_label_counts": dict(predicted_counts),
            "final_predictions_path": "final_predictions.json",
            "model_reload_verification": reload_verification}


def run_cycle(vessels: list[dict], output_dir: Path, protocol: dict,
              final_loader: Callable | None = None) -> dict:
    """Run frozen candidate development and one final evaluation.

    ``protocol`` must contain ``class_names`` in declared label order and a
    nonempty ``source_hash``. The optional loader is called only after freeze.
    """
    output_dir = Path(output_dir)
    if (output_dir / "freeze.json").exists() or (output_dir / "results.json").exists():
        raise FileExistsError("model-cycle output is already frozen; use a new empty output directory")
    run_started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    if not isinstance(protocol, dict):
        raise ValueError("protocol must be an object")
    class_names = protocol.get("class_names")
    source_hash = protocol.get("source_hash")
    if (not isinstance(class_names, list) or len(class_names) < 2
            or any(not isinstance(label, str) or not label for label in class_names)
            or len(set(class_names)) != len(class_names)):
        raise ValueError("protocol.class_names must declare at least two unique nonempty labels in fixed order")
    if not isinstance(source_hash, str) or not source_hash.strip():
        raise ValueError("protocol.source_hash must be a nonempty source fingerprint")
    # Split can inspect only vessel hash/label for stratification. No final rows
    # are validated or transformed before freeze.
    roster = _validate_roster(vessels, class_names)
    final_hashes, development_hashes, stratification_counts = _stratified_final_split(roster, class_names)
    development_lookup = set(development_hashes)
    development_vessels = [item for item in roster if item["vessel_hash"] in development_lookup]
    for item in development_vessels:
        source = item["_source"]
        item["_rows"] = _validate_vessel_rows(source)
    dev_splits = _development_splits(development_vessels, class_names)
    manifest = {"final": final_hashes, "development": dev_splits, "class_names": list(class_names),
                "split_seed": FINAL_SPLIT_SEED, "class_counts": stratification_counts,
                "rank_hash": "sha256(utf8(seed + NUL + label + NUL + vessel_hash))",
                "rounding": {"final": "max(2,floor(0.20*n_class))",
                             "development": "train=floor(0.70*n_dev); validation=max(2,floor(0.15*n_dev)); calibration=max(2,n_dev-train-validation); train=remainder"}}
    manifest_hash = _sha256(manifest)
    protocol_for_hash = {key: value for key, value in protocol.items() if key not in ("final_loader",)}
    # Protocol is data-only. Runtime callables are passed separately and never serialized.
    protocol_hash = _sha256(protocol_for_hash)
    development, selected = _evaluate_development(development_vessels, dev_splits, class_names, output_dir)
    source_files = {"real_geometry_20261028.py": Path(__file__).with_name("real_geometry_20261028.py"),
                    "real_model_cycle_20261028.py": Path(__file__),
                    "models.py": Path(__file__).with_name("models.py"),
                    "real_model_cycle_protocol_20261028.md": Path(__file__).resolve().parents[1]
                    / "docs" / "real_model_cycle_protocol_20261028.md"}
    source_file_hashes = {name: _file_sha256(path) for name, path in source_files.items()}
    snapshot_hashes = _snapshot_sources(output_dir, source_files)
    if snapshot_hashes != source_file_hashes:
        raise RuntimeError("source snapshot hashes do not match the frozen source hashes")
    development_summary = {key: value for key, value in development.items() if key != "model_audit"}
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(output_dir / "protocol.json", protocol)
    _atomic_json(output_dir / "development_results.json", development_summary)
    _atomic_json(output_dir / "development_model_audit.json", development["model_audit"])
    freeze = {"schema_version": 1, "candidate_config": {name: _candidate_spec(name)
                for name in (BASELINE,) + CANDIDATE_ORDER},
              "protocol": protocol, "protocol_hash": protocol_hash, "source_hash": source_hash,
              "source_file_hashes": source_file_hashes,
              "source_snapshot": "source_snapshot/",
              "split_manifest_hash": manifest_hash, "split_manifest": manifest,
              "development_metrics": development_summary,
              "selection": development["selection"],
              "created_utc": datetime.now(timezone.utc).isoformat()}
    freeze_path, manifest_path = _write_frozen_artifacts(output_dir, freeze, manifest)
    roster_by_hash = {item["vessel_hash"]: item for item in roster}
    final = _evaluate_final_after_freeze(freeze_path, selected, roster_by_hash, final_hashes,
                                         class_names, output_dir, final_loader)
    result = {"status": "complete", "selected_candidate": selected,
              "selection": development["selection"], "development": development_summary,
              "final": final, "freeze_path": str(freeze_path),
              "split_manifest_path": str(manifest_path),
              "source_hash": source_hash, "protocol_hash": protocol_hash,
              "split_manifest_hash": manifest_hash}
    _atomic_json(output_dir / "results.json", result)
    run_evidence = {"started_utc": started_utc,
                    "completed_utc": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": float(time.perf_counter() - run_started),
                    "execution_command": protocol.get("execution_command",
                        "run_cycle(vessels, output_dir, protocol)"),
                    "python_executable": sys.executable,
                    "python_version": platform.python_version(),
                    "numpy_version": np.__version__, "scikit_learn_version": sklearn.__version__,
                    "seeds": {"final_split": FINAL_SPLIT_SEED, "development_splits": list(DEV_SEEDS),
                              "initializations": list(INIT_SEEDS), "bootstrap": BOOTSTRAP_SEED},
                    "source_file_hashes": source_file_hashes,
                    "source_snapshot_hashes": snapshot_hashes,
                    "thread_environment": {key: os.environ.get(key) for key in
                        ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")}}
    _atomic_json(output_dir / "run_evidence.json", run_evidence)
    return result

