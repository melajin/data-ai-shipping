"""Reproducible synthetic experiment with explicit fit/select/calibrate boundaries."""
from __future__ import annotations

import copy
import hashlib
import json
import platform
from pathlib import Path
import time

import numpy as np

from .data import CLASS_NAMES, generate_dataset, load_dataset, validate_dataset, write_dataset
from .features import FEATURE_NAMES, FEATURE_UNITS, feature_matrix
from .models import (AnomalyModel, Classifier, Preprocessor, classification_metrics,
                     fit_temperature, softmax)


MODEL_SCHEMA = "fishing_sample_model_v1"
SPLITS = ("train", "validation", "calibration", "test", "stress")
# This fixed search space is declared before any held-out evaluation.
CANDIDATES = (("linear_l2_001", 0, 0.01), ("linear_l2_01", 0, 0.1),
              ("mlp16_l2_0", 16, 0.0), ("mlp16_l2_001", 16, 0.01),
              ("mlp16_l2_01", 16, 0.1))


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        raise ValueError("Cannot publish nonfinite numeric output")
    return value


def save_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def dataset_digest(dataset):
    data = json.dumps(dataset, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def split_indices(records, details):
    """Select usable labeled rows, preserving complete vessel separation."""
    groups = {s: set() for s in SPLITS}
    indices = {s: [] for s in SPLITS}
    for i, (row, detail) in enumerate(zip(records, details)):
        split = row["split"]
        groups[split].add(row["vessel_id"])
        label = row.get("label")
        if detail["valid"] and isinstance(label, int) and not isinstance(label, bool) and 0 <= label < 3:
            indices[split].append(i)
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            if groups[a] & groups[b]:
                raise ValueError(f"vessel leakage between {a} and {b}")
    for split in SPLITS:
        if len(groups[split]) < 2:
            raise ValueError(f"{split}: at least two independent vessel groups required")
        labels = {records[i]["label"] for i in indices[split]}
        if labels != {0, 1, 2}:
            raise ValueError(f"{split}: all three synthetic classes need valid examples")
    return {s: np.asarray(v, dtype=int) for s, v in indices.items()}, groups


def _bootstrap(y, probs, group_ids, seed, repetitions=200):
    """Vessel-level resampling; uncertainty is conditional on this generator/run."""
    ids = np.asarray(group_ids)
    unique = np.unique(ids)
    positions = {g: np.flatnonzero(ids == g) for g in unique}
    rng = np.random.default_rng(seed)
    values = {"accuracy": [], "macro_f1": []}
    for _ in range(repetitions):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        index = np.concatenate([positions[g] for g in chosen])
        metric = classification_metrics(y[index], probs[index])
        for key in values:
            values[key].append(metric[key])
    return {key: {"low": float(np.quantile(v, .025)), "high": float(np.quantile(v, .975)),
                  "method": "vessel_bootstrap_percentile", "repetitions": repetitions}
            for key, v in values.items()}


def _distribution(scores, threshold):
    scores = np.asarray(scores, dtype=float)
    if not len(scores):
        return {"n": 0, "median": None, "p95": None, "flag_rate": None}
    return {"n": len(scores), "median": float(np.median(scores)),
            "p95": float(np.quantile(scores, .95)),
            "flag_rate": float(np.mean(scores > threshold))}


def predict_records(dataset, bundle):
    """Use frozen transforms and weights; no fitting or label use in predictions."""
    validate_dataset(dataset)
    preprocessor, classifier, anomaly = _validate_bundle(bundle)
    X, details = feature_matrix(dataset["records"])
    usable = np.array([d["valid"] for d in details], dtype=bool)
    chosen = np.flatnonzero(usable)
    lookup = {}
    if len(chosen):
        Z = preprocessor.transform(X[chosen])
        probabilities = softmax(classifier.predict_logits(Z), bundle["temperature"])
        scores = anomaly.score(Z)
        lookup = {int(i): (p, float(s)) for i, p, s in zip(chosen, probabilities, scores)}
    result = []
    for i, (row, detail) in enumerate(zip(dataset["records"], details)):
        p, score = lookup.get(i, (None, None))
        result.append({"sample_id": row["sample_id"], "vessel_id": row["vessel_id"],
                       "split": row["split"], "source_type": "synthetic",
                       "true_label": row.get("label"),
                       "predicted_label": int(np.argmax(p)) if p is not None else None,
                       "probabilities": p.tolist() if p is not None else None,
                       "anomaly_score": score,
                       "anomaly_flag": bool(score > bundle["anomaly_threshold"]) if score is not None else None,
                       "status": "ok" if usable[i] else "abstained", "reason": detail["reason"],
                       "parts": row["parts"], "features": detail["values"],
                       "part_metrics": detail["parts"], "quality": detail["quality"]})
    return result


def _validate_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("schema_version") != MODEL_SCHEMA:
        raise ValueError("unsupported model schema")
    if bundle.get("source_type") != "synthetic" or bundle.get("coordinate_system") != "local_xy_m":
        raise ValueError("model only accepts explicitly synthetic local XY metres")
    if bundle.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("model feature order/version differs from this implementation")
    if bundle.get("feature_units") != list(FEATURE_UNITS):
        raise ValueError("model feature units differ from this implementation")
    if bundle.get("class_names") != CLASS_NAMES:
        raise ValueError("model class order differs from this implementation")
    for key in ("temperature", "anomaly_threshold"):
        value = bundle.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError(f"invalid model {key}")
    if bundle["temperature"] <= 0 or bundle["anomaly_threshold"] < 0:
        raise ValueError("invalid temperature or anomaly threshold")
    preprocessor = Preprocessor.from_dict(bundle.get("preprocessor"))
    classifier = Classifier.from_dict(bundle.get("classifier"))
    anomaly = AnomalyModel.from_dict(bundle.get("anomaly_model"))
    if preprocessor.n_features_ != len(FEATURE_NAMES):
        raise ValueError("model preprocessing requires eight geometric features")
    expected_dim = 2 * len(FEATURE_NAMES)
    if classifier.input_dim != expected_dim or anomaly.input_dim != expected_dim:
        raise ValueError("model modules require scaled features plus missing masks")
    if classifier.n_classes != len(CLASS_NAMES) or anomaly.n_classes != len(CLASS_NAMES):
        raise ValueError("model modules require exactly three synthetic classes")
    return preprocessor, classifier, anomaly


def load_model(path):
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate_bundle(bundle)
    return bundle


def _perturbation_check(dataset, index, bundle):
    """Label-free sensitivity check with isolated coordinate spikes, not accidents."""
    rows = [copy.deepcopy(dataset["records"][int(i)]) for i in index[:60]]
    original = {"metadata": dataset["metadata"], "records": rows}
    baseline = predict_records(original, bundle)
    modified = copy.deepcopy(original)
    for row in modified["records"]:
        part = max(row["parts"], key=len)
        midpoint = len(part) // 2
        part[midpoint][0] += 1500.0
        part[midpoint][1] -= 1500.0
        row["label"] = None
    changed = predict_records(modified, bundle)
    delta = [b["anomaly_score"] - a["anomaly_score"] for a, b in zip(baseline, changed)
             if a["anomaly_score"] is not None and b["anomaly_score"] is not None]
    return {"kind": "single_point_coordinate_spike", "offset_m": [1500, -1500],
            "n_pairs": len(delta), "median_score_change": float(np.median(delta)) if delta else None,
            "score_increase_fraction": float(np.mean(np.array(delta) > 0)) if delta else None,
            "meaning": "Synthetic measurement corruption sensitivity; no accident labels or detection accuracy."}


def train_experiment(dataset, output_dir, *, seed=42, epochs=400):
    """Train on train, select on validation, temperature-fit on calibration, then evaluate."""
    started = time.perf_counter()
    validate_dataset(dataset)
    records = dataset["records"]
    X, details = feature_matrix(records)
    indices, groups = split_indices(records, details)
    y = np.asarray([r["label"] if r.get("label") is not None else -1 for r in records], dtype=int)
    preprocessor = Preprocessor().fit(X[indices["train"]])
    Z = {s: preprocessor.transform(X[ix]) for s, ix in indices.items()}
    candidates = []
    fitted = []
    for name, hidden, l2 in CANDIDATES:
        model = Classifier(Z["train"].shape[1], n_classes=3, hidden=hidden, l2=l2, seed=seed)
        history = model.fit(Z["train"], y[indices["train"]], Z["validation"], y[indices["validation"]],
                            epochs=epochs, learning_rate=.03, patience=35)
        val_metrics = classification_metrics(y[indices["validation"]], softmax(model.predict_logits(Z["validation"])))
        candidates.append({"name": name, "hidden": hidden, "l2": l2,
                           "best_epoch": model.best_epoch,
                           "validation_metrics": val_metrics, "history": history})
        fitted.append(model)
    # Sorting only validation NLL; fixed candidate order breaks ties in favor of simpler models.
    best = min(range(len(candidates)), key=lambda i: (candidates[i]["validation_metrics"]["nll"], i))
    model = fitted[best]
    temperature = fit_temperature(model.predict_logits(Z["calibration"]), y[indices["calibration"]])
    anomaly = AnomalyModel().fit(Z["train"], y[indices["train"]], n_classes=3, shrinkage=.2)
    val_scores = anomaly.score(Z["validation"])
    threshold = float(np.quantile(val_scores, .95))
    bundle = {"schema_version": MODEL_SCHEMA, "source_type": "synthetic",
              "coordinate_system": "local_xy_m", "class_names": dataset["metadata"]["class_names"],
              "feature_names": list(FEATURE_NAMES), "feature_units": list(FEATURE_UNITS),
              "dataset_sha256": dataset_digest(dataset), "seed": seed,
              "selected_model": candidates[best]["name"], "preprocessor": preprocessor.to_dict(),
              "classifier": model.to_dict(), "temperature": float(temperature),
              "anomaly_model": anomaly.to_dict(), "anomaly_threshold": threshold,
              "fit_groups": sorted(groups["train"]), "selection_groups": sorted(groups["validation"]),
              "calibration_groups": sorted(groups["calibration"])}
    metrics, before, score_summary = {}, {}, {}
    for split in SPLITS:
        logits = model.predict_logits(Z[split])
        probs = softmax(logits, temperature)
        metrics[split] = classification_metrics(y[indices[split]], probs)
        before[split] = classification_metrics(y[indices[split]], softmax(logits))
        if split in ("test", "stress"):
            metrics[split]["ci95"] = _bootstrap(y[indices[split]], probs,
                [records[int(i)]["vessel_id"] for i in indices[split]], seed + (100 if split == "test" else 200))
        score_summary[split] = _distribution(anomaly.score(Z[split]), threshold)
    train_y = y[indices["train"]]
    frequencies = np.bincount(train_y, minlength=3) / len(train_y)
    majority = {s: classification_metrics(y[indices[s]], np.tile(frequencies, (len(indices[s]), 1)))
                for s in ("test", "stress")}
    summary = {}
    for split in SPLITS:
        positions = [i for i, r in enumerate(records) if r["split"] == split]
        valid = sum(bool(details[i]["valid"]) for i in positions)
        summary[split] = {"samples": len(positions), "groups": len(groups[split]), "valid": valid,
                          "abstained": len(positions) - valid, "evaluated_labeled": len(indices[split])}
    report = {"schema_version": "fishing_sample_report_v1", "source_type": "synthetic",
              "seed": seed, "class_names": bundle["class_names"], "feature_names": list(FEATURE_NAMES),
              "feature_units": list(FEATURE_UNITS), "split_summary": summary,
              "candidates": candidates, "selected_model": bundle["selected_model"],
              "temperature": float(temperature), "metrics": metrics, "before_calibration": before,
              "majority_baseline": majority, "anomaly": {"threshold": threshold,
              "threshold_source": "validation_95_percentile", "score_description": "minimum class-conditional shrinkage squared Mahalanobis distance; not accident probability",
              **score_summary, "perturbation": _perturbation_check(dataset, indices["test"], bundle)},
              "audit": {"group_overlap_count": 0, "dataset_sha256": bundle["dataset_sha256"],
                        "fit_split": "train", "selection_split": "validation", "calibration_split": "calibration",
                        "final_splits": ["test", "stress"], "selection_metric": "validation_nll_before_temperature",
                        "feature_excludes": ["label", "vessel_id", "split", "scenario", "sim_times", "quality"],
                        "generator_metadata": dataset["metadata"], "groups": {s: sorted(g) for s, g in groups.items()},
                        "test_used_for_selection": False, "stress_used_for_selection": False},
              "limitations": ["합성 경로 유형 실험이며 실제 조업 분류 정확도가 아닙니다.",
                  "같은 생성기 내부의 새 선박 평가입니다. 실제 해역·계절·선종 일반화를 보장하지 않습니다.",
                  "stress는 사전 고정한 생성 조건 변화이며 실제 분포 변화의 대체물이 아닙니다.",
                  "이상 점수와 좌표 교란 실험은 사고 확률 또는 사고 탐지율이 아닙니다.",
                  "CI는 선박 단위 bootstrap이며 생성기 편향과 학습 seed 불확실성을 포함하지 않습니다.",
                  "같은 test를 보고 설계를 바꾸면 새 고정 평가자료가 필요합니다.",
                  "실제 원자료·외부 관측 수집·장치 실측·학습자 성취는 이번 실행으로 검증되지 않습니다."],
              "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                          "seconds": round(time.perf_counter() - started, 3)}}
    predictions = predict_records(dataset, bundle)
    # Verify serialized inference, not just in-memory training output.
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    save_json(root / "model.json", bundle)
    reloaded = predict_records(dataset, load_model(root / "model.json"))
    if predictions != reloaded:
        raise RuntimeError("serialized model inference differs from in-memory inference")
    report["audit"]["serialization_predictions_identical"] = True
    save_json(root / "report.json", report)
    save_json(root / "predictions.json", predictions)
    from .visualization import write_dashboard
    write_dashboard(report, predictions, root / "dashboard.html")
    return report


def run_demo(output_dir, *, seed=42, epochs=400):
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    dataset = generate_dataset(seed=seed)
    write_dataset(dataset, root / "sample_dataset.json")
    return train_experiment(dataset, root, seed=seed, epochs=epochs)
