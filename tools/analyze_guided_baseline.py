#!/usr/bin/env python3
"""Audit frozen S0 outputs and expose one reproducible prediction; never fit."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fishing_demo.data import CLASS_NAMES, load_dataset
from fishing_demo.features import FEATURE_NAMES, FEATURE_UNITS, feature_matrix
from fishing_demo.models import AnomalyModel, Classifier, Preprocessor, softmax
from fishing_demo.pipeline import (SPLITS, dataset_digest, load_model, predict_records,
                                   save_json, split_indices)

ATOL = 1e-10
HIGH_CONFIDENCE = 0.8  # A display/count cutoff fixed by the protocol, not a fitted rule.
INPUT_NAMES = ("sample_dataset.json", "model.json", "report.json", "predictions.json",
               "baseline_model.json", "baseline_metrics.json")
OUTPUT_NAMES = ("analysis.json", "trace.json", "walkthrough.png")
METRIC_KEYS = ("accuracy", "macro_f1", "nll", "brier", "confusion", "support")


def _read_json(path):
    def reject(token):
        raise ValueError(f"nonfinite JSON constant: {token}")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=reject, object_pairs_hook=unique)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _close(actual, expected, context, *, rtol=0):
    np.testing.assert_allclose(actual, expected, rtol=rtol, atol=ATOL,
                               err_msg=context, equal_nan=False)


def _same(actual, expected, context):
    """Compare JSON trees without letting bools masquerade as numeric labels."""
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise AssertionError(f"{context}: object keys differ")
        for key in actual:
            _same(actual[key], expected[key], f"{context}.{key}")
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise AssertionError(f"{context}: list lengths differ")
        for i, (left, right) in enumerate(zip(actual, expected)):
            _same(left, right, f"{context}[{i}]")
    elif (type(actual) in (int, float) and type(expected) in (int, float)):
        # Whole predictions contain many coordinate scalars. A scalar check
        # keeps the same tolerance without constructing a NumPy assertion for
        # every point in a large synthetic dataset.
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=ATOL):
            raise AssertionError(f"{context}: numbers differ by more than {ATOL}")
    elif type(actual) is not type(expected) or actual != expected:
        raise AssertionError(f"{context}: values differ")


def _label(value, n_classes):
    return (isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))
            and 0 <= value < n_classes)


def recompute_metrics(labels, probabilities, class_names=CLASS_NAMES):
    """Independent metric calculation: confusion rows=true, columns=predicted.

    Invalid labels are removed before integer conversion/indexing. Probabilities
    are still checked for every row, and an empty evaluable set is an error.
    """
    p = np.asarray(probabilities, dtype=np.float64)
    n_classes = len(class_names)
    if (p.ndim != 2 or p.shape[1] != n_classes or not np.isfinite(p).all()
            or np.any(p < 0) or np.any(p > 1)):
        raise ValueError("probabilities must be a finite N by class-count matrix in [0, 1]")
    if not np.allclose(p.sum(axis=1), 1, rtol=0, atol=1e-7):
        raise ValueError("probability rows must sum to one")
    values = list(labels)
    if len(values) != len(p):
        raise ValueError("labels and probabilities must have matching row counts")
    positions = [i for i, value in enumerate(values) if _label(value, n_classes)]
    if not positions:
        raise ValueError("at least one valid label is required")
    y = [int(values[i]) for i in positions]
    p = p[positions]
    predicted = p.argmax(axis=1)
    confusion = np.zeros((n_classes, n_classes), dtype=np.int64)
    for truth, guess in zip(y, predicted):
        confusion[truth, int(guess)] += 1
    support = confusion.sum(axis=1)
    predicted_support = confusion.sum(axis=0)
    per_class = []
    for i, name in enumerate(class_names):
        true_positive = int(confusion[i, i])
        precision = true_positive / int(predicted_support[i]) if predicted_support[i] else 0.0
        recall = true_positive / int(support[i]) if support[i] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class.append({"index": i, "name": name, "precision": precision,
                          "recall": recall, "f1": f1, "support": int(support[i])})
    nll_values, brier_values = [], []
    for truth, row in zip(y, p):
        nll_values.append(-math.log(max(float(row[truth]), np.finfo(np.float64).tiny)))
        brier_values.append(math.fsum((float(value) - int(i == truth)) ** 2
                                     for i, value in enumerate(row)))
    count = len(y)
    return {"accuracy": int(np.trace(confusion)) / count,
            "macro_f1": math.fsum(item["f1"] for item in per_class) / n_classes,
            "nll": math.fsum(nll_values) / count,
            "brier": math.fsum(brier_values) / count,
            "confusion": confusion.tolist(), "support": support.tolist(),
            "per_class": per_class, "evaluated_labeled": count,
            "confusion_orientation": "rows=true, columns=predicted"}


def _check_metrics(calculated, saved, context):
    for key in METRIC_KEYS:
        if key not in saved:
            raise ValueError(f"{context}: saved metric missing {key}")
        _close(calculated[key], saved[key], f"{context}.{key}")


def select_cases(predictions):
    """Select examples by sample_id, independent of input order or confidence."""
    eligible = [p for p in predictions if p["status"] == "ok"
                and _label(p.get("true_label"), len(CLASS_NAMES))]
    test = sorted((p for p in eligible if p["split"] == "test"), key=lambda p: p["sample_id"])
    if not test:
        raise ValueError("no evaluable labeled test examples for the walkthrough")
    errors = [p for p in test if p["predicted_label"] != p["true_label"]]
    selected = errors[0] if errors else test[0]
    comparisons = [p for p in test if p["true_label"] == selected["true_label"]
                   and p["predicted_label"] == p["true_label"]
                   and p["sample_id"] != selected["sample_id"]]
    stress = sorted((p for p in eligible if p["split"] == "stress"
                     and p["predicted_label"] != p["true_label"]), key=lambda p: p["sample_id"])
    return {"selected": selected, "comparison": comparisons[0] if comparisons else None,
            "selected_kind": "first_test_misclassification" if errors else "first_test_correct_fallback",
            "comparison_status": "available" if comparisons else "no_other_same_class_correct_test_example",
            "stress_misclassification": stress[0] if stress else None}


def manual_forward(classifier, model_input):
    """NumPy equations independent of Classifier's private forward method."""
    values = np.asarray(model_input, dtype=np.float64)
    if (values.ndim != 2 or values.shape[1] != classifier.input_dim
            or not np.isfinite(values).all()):
        raise ValueError("manual forward requires a finite compatible model-input matrix")
    params = classifier.params
    if classifier.hidden:
        preactivation = values @ params["W1"] + params["b1"]
        hidden = np.tanh(preactivation)
        logits = hidden @ params["W2"] + params["b2"]
    else:
        preactivation = hidden = None
        logits = values @ params["W"] + params["b"]
    _close(logits, classifier.predict_logits(values), "manual/public predict_logits")
    return logits, preactivation, hidden


def manual_geometry(record, extracted):
    """Check lengths within each part; never introduce a cross-boundary segment."""
    measured, straightnesses = [], []
    for part in record["parts"]:
        length = math.fsum(math.hypot(b[0] - a[0], b[1] - a[1])
                           for a, b in zip(part, part[1:]))
        displacement = math.hypot(part[-1][0] - part[0][0], part[-1][1] - part[0][1]) if len(part) > 1 else 0.0
        straightness = displacement / length if length > 0 else None
        measured.append({"length_m": length, "displacement_m": displacement,
                         "straightness": straightness})
        if straightness is not None:
            straightnesses.append(straightness)
    if len(measured) != len(extracted["parts"]):
        raise AssertionError("manual geometry: part count differs")
    for i, (manual, public) in enumerate(zip(measured, extracted["parts"])):
        for key in ("length_m", "displacement_m", "straightness"):
            if manual[key] is None or public[key] is None:
                if manual[key] is not public[key]:
                    raise AssertionError("manual geometry: missing straightness differs")
            else:
                _close(manual[key], public[key], f"part {i} {key}", rtol=1e-12)
    total = math.fsum(item["length_m"] for item in measured)
    mean_straightness = math.fsum(straightnesses) / len(straightnesses) if straightnesses else None
    if extracted["valid"]:
        _close(math.log1p(total), extracted["values"][0], "manual log1p total length")
        _close(mean_straightness, extracted["values"][1], "manual mean part straightness")
    return {"parts": measured, "total_length_m": total,
            "mean_part_straightness": mean_straightness,
            "aggregation": "arithmetic mean over positive-length parts; not sum(D)/sum(L)",
            "checks_passed": True, "part_boundaries_preserved": True}


def _network_trace(bundle, raw, true_label):
    preprocessor = Preprocessor.from_dict(bundle["preprocessor"])
    classifier = Classifier.from_dict(bundle["classifier"])
    mask = np.isnan(raw)
    imputed = np.where(mask, preprocessor.medians_, raw)
    scaled = (imputed - preprocessor.means_) / preprocessor.scales_
    model_input = np.concatenate((scaled, mask.astype(np.float64)), axis=1)
    _close(model_input, preprocessor.transform(raw), "manual/public preprocessing")
    logits, preactivation, hidden = manual_forward(classifier, model_input)
    probabilities = []
    for temperature in (1.0, bundle["temperature"]):
        shifted = (logits - logits.max(axis=1, keepdims=True)) / temperature
        exponentials = np.exp(shifted)
        p = exponentials / exponentials.sum(axis=1, keepdims=True)
        _close(p, softmax(classifier.predict_logits(model_input), temperature), "manual/public softmax")
        probabilities.append(p[0])
    before, after = probabilities
    predicted = int(np.argmax(after))
    result = {"model_name": bundle["selected_model"],
              "model_type": "tanh_mlp16" if classifier.hidden else "linear_softmax",
              "hidden_units": classifier.hidden, "l2": classifier.l2,
              "equations": ("a=z@W1+b1; h=tanh(a); logits=h@W2+b2" if classifier.hidden
                            else "logits=z@W+b"),
              "hidden_preactivation": preactivation[0].tolist() if preactivation is not None else None,
              "hidden16": hidden[0].tolist() if hidden is not None else None,
              "logits": logits[0].tolist(), "temperature": float(bundle["temperature"]),
              "probabilities_before_calibration": before.tolist(),
              "probabilities_after_calibration": after.tolist(),
              "true_index": int(true_label), "true_name": CLASS_NAMES[true_label],
              "predicted_index": predicted, "predicted_name": CLASS_NAMES[predicted],
              "correct": predicted == true_label,
              "confidence": float(after[predicted]),
              "nll_before_calibration": -math.log(max(float(before[true_label]), np.finfo(float).tiny)),
              "nll": -math.log(max(float(after[true_label]), np.finfo(float).tiny)),
              "manual_forward_matches_public_atol_1e_10": True}
    preprocessing = {"train_median": preprocessor.medians_.tolist(),
                     "train_mean": preprocessor.means_.tolist(),
                     "train_scale": preprocessor.scales_.tolist(),
                     "train_all_missing": preprocessor.all_missing_.tolist(),
                     "statistics_source": "frozen model; train-only arithmetic checked separately",
                     "imputed8": imputed[0].tolist(), "scaled8": scaled[0].tolist(),
                     "missing_mask8": mask[0].astype(int).tolist(),
                     "model_input16": model_input[0].tolist(),
                     "output_order": "scaled8 then missing_mask8"}
    return result, preprocessing, model_input


def build_trace_case(record, extracted, bundle, baseline_bundle, saved_prediction,
                     baseline_prediction=None):
    if not extracted["valid"] or not _label(record.get("label"), len(CLASS_NAMES)):
        raise ValueError("trace requires a valid labeled synthetic record")
    raw = np.asarray([[np.nan if value is None else value for value in extracted["values"]]])
    forward, preprocessing, model_input = _network_trace(bundle, raw, record["label"])
    _close(forward["probabilities_after_calibration"], saved_prediction["probabilities"],
           "manual forward/saved selected probabilities")
    if forward["predicted_index"] != saved_prediction["predicted_label"]:
        raise AssertionError("manual forward/saved selected class differs")
    anomaly = AnomalyModel.from_dict(bundle["anomaly_model"])
    distances = []
    for mean, precision in zip(anomaly.means_, anomaly.precisions_):
        difference = model_input - mean
        distances.append(float(np.einsum("ni,ij,nj->n", difference, precision, difference)[0]))
    score = max(min(distances), 0.0)
    _close(score, anomaly.score(model_input)[0], "manual/public anomaly score")
    _close(score, saved_prediction["anomaly_score"], "manual/saved anomaly score")
    threshold = float(bundle["anomaly_threshold"])
    flag = score > threshold
    if flag != saved_prediction["anomaly_flag"]:
        raise AssertionError("manual/saved anomaly flag differs")
    baseline, baseline_preprocessing, baseline_input = _network_trace(baseline_bundle, raw, record["label"])
    _close(model_input, baseline_input, "selected/baseline identical model input")
    if baseline_prediction is not None:
        _close(baseline["probabilities_after_calibration"], baseline_prediction["probabilities"],
               "manual forward/saved baseline probabilities")
        if baseline["predicted_index"] != baseline_prediction["predicted_label"]:
            raise AssertionError("manual forward/saved baseline class differs")
    baseline["model_input16"] = baseline_preprocessing["model_input16"]
    baseline["same_model_input_as_selected"] = True
    return {"sample_id": record["sample_id"], "split": record["split"],
            "source_type": "synthetic", "raw_record_is_real_observation": False,
            "raw_record": copy.deepcopy(record),
            "raw8": extracted["values"],
            "features": [{"index": i, "name": name, "unit": FEATURE_UNITS[i],
                          "raw_value": extracted["values"][i]}
                         for i, name in enumerate(FEATURE_NAMES)],
            "geometry_check": manual_geometry(record, extracted),
            "preprocessing": preprocessing, "selected_prediction": forward,
            "anomaly": {"class_squared_mahalanobis": [
                {"index": i, "name": CLASS_NAMES[i], "distance": distance}
                for i, distance in enumerate(distances)],
                "minimum_distance": score, "threshold": threshold,
                "threshold_source": "validation_95_percentile", "flag": flag,
                "meaning": "distance from every fitted synthetic class; not accident probability"},
            "baseline_prediction": baseline,
            "checks": {"manual_preprocessing_matches_public": True,
                       "manual_logits_match_predict_logits": True,
                       "manual_probabilities_match_saved_prediction": True,
                       "manual_geometry_matches_feature_extractor": True}}


def _check_training_statistics(X_train, bundle):
    """Verify frozen values arithmetically, without calling or updating any fit."""
    all_missing = np.isnan(X_train).all(axis=0)
    medians = np.array([np.median(column[~np.isnan(column)]) if np.any(~np.isnan(column)) else 0.0
                        for column in X_train.T])
    filled = np.where(np.isnan(X_train), medians, X_train)
    means, scales = filled.mean(axis=0), filled.std(axis=0, ddof=0)
    scales[scales == 0] = 1.0
    means[all_missing], scales[all_missing] = 0.0, 1.0
    state = bundle["preprocessor"]
    for key, values in (("medians", medians), ("means", means), ("scales", scales)):
        _close(values, state[key], f"train-only arithmetic/frozen {key}")
    if state["all_missing"] != all_missing.tolist():
        raise AssertionError("train-only arithmetic/frozen all_missing differs")


def _case_summary(prediction, baseline):
    truth, guess = prediction["true_label"], prediction["predicted_label"]
    probabilities = prediction["probabilities"]
    return {"sample_id": prediction["sample_id"], "vessel_id": prediction["vessel_id"],
            "true_index": truth, "true_name": CLASS_NAMES[truth],
            "predicted_index": guess, "predicted_name": CLASS_NAMES[guess],
            "confidence": float(max(probabilities)), "true_class_probability": float(probabilities[truth]),
            "nll": -math.log(max(float(probabilities[truth]), np.finfo(float).tiny)),
            "anomaly_score": prediction["anomaly_score"], "anomaly_flag": prediction["anomaly_flag"],
            "baseline_predicted_index": baseline["predicted_label"],
            "baseline_predicted_name": CLASS_NAMES[baseline["predicted_label"]],
            "baseline_confidence": float(max(baseline["probabilities"]))}


def _final_split_summary(split, predictions, baseline_lookup, metrics):
    usable = [p for p in predictions if p["split"] == split and p["status"] == "ok"
              and _label(p["true_label"], len(CLASS_NAMES))]
    errors = sorted((p for p in usable if p["predicted_label"] != p["true_label"]),
                    key=lambda p: p["sample_id"])
    confusion = np.asarray(metrics["confusion"], dtype=int)
    pairs = [{"true_index": i, "true_name": CLASS_NAMES[i], "predicted_index": j,
              "predicted_name": CLASS_NAMES[j], "count": int(confusion[i, j])}
             for i in range(len(CLASS_NAMES)) for j in range(len(CLASS_NAMES)) if i != j and confusion[i, j]]
    pairs.sort(key=lambda p: (-p["count"], p["true_index"], p["predicted_index"]))
    high = sum(max(p["probabilities"]) >= HIGH_CONFIDENCE for p in errors)
    return {"metrics": metrics, "misclassified_count": len(errors),
            "misclassified": [_case_summary(p, baseline_lookup[p["sample_id"]]) for p in errors],
            "high_confidence_cutoff": HIGH_CONFIDENCE, "high_confidence_misclassified_count": high,
            "most_common_directed_confusion": pairs[0] if pairs else None,
            "tied_most_common_directed_confusions": [p for p in pairs if p["count"] == pairs[0]["count"]] if pairs else [],
            "confidence_is_not_correctness": True}


def _feature_comparison(selected, comparison):
    if comparison is None:
        return {"available": False, "reason": "no other same-class correct test example",
                "causal_explanation": False}
    left, right = selected["raw8"], comparison["raw8"]
    return {"available": True, "selected_sample_id": selected["sample_id"],
            "comparison_sample_id": comparison["sample_id"],
            "same_true_class": True,
            "differences_selected_minus_comparison": [
                {"name": name, "unit": FEATURE_UNITS[i], "selected": a, "comparison": b,
                 "difference": a - b if a is not None and b is not None else None}
                for i, (name, a, b) in enumerate(zip(FEATURE_NAMES, left, right))],
            "interpretation": "Observed feature differences between two examples; not an identified cause of error.",
            "causal_explanation": False}


def _layers(dataset, details, final_splits, preprocessing_summary):
    invalid = sum(not detail["valid"] for detail in details)
    return [
        {"layer": "원자료", "observations": [f"synthetic records={len(details)}; abstained geometry={invalid}"],
         "hypotheses_to_test": [], "limitations": ["No original observational data or official fishing labels evaluated."]},
        {"layer": "계약", "observations": ["Dataset/model contracts pass; split vessel groups do not overlap."],
         "hypotheses_to_test": [], "limitations": ["A valid synthetic schema does not establish an actual sensor or real-data contract."]},
        {"layer": "특징", "observations": ["Trace part lengths and arithmetic mean straightness agree with the extractor; no boundary is joined."],
         "hypotheses_to_test": ["Geometric feature overlap may accompany confusion; these examples cannot identify a causal contribution."],
         "limitations": ["Eight geometry summaries omit operational context; no actual speed/acceleration is computed."]},
        {"layer": "전처리", "observations": ["Frozen train statistics match train-only arithmetic; label removal leaves inference unchanged.",
                                                f"Scaled-feature observations are recorded for {len(preprocessing_summary)} splits."],
         "hypotheses_to_test": [], "limitations": ["Arithmetic agreement verifies these saved values, not every possible leakage mechanism."]},
        {"layer": "모델", "observations": [f"test errors={final_splits['test']['misclassified_count']}; stress errors={final_splits['stress']['misclassified_count']}",
                                                f"confidence>=0.8 errors: test={final_splits['test']['high_confidence_misclassified_count']}, stress={final_splits['stress']['high_confidence_misclassified_count']}"],
         "hypotheses_to_test": ["Feature overlap or distribution changes could contribute; no model is changed after inspecting final splits."],
         "limitations": ["Known seed replay; no new blind test, accident labels, real-vessel generalization, or causal stress decomposition."]},
        {"layer": "표시", "observations": ["Saved predictions match frozen inference; PNG plots each part separately with local-metre axes."],
         "hypotheses_to_test": [], "limitations": ["Display cutoff 0.8 is not an operating threshold; learner understanding and usability are not assessed."]},
    ]


def _write_walkthrough(path, trace, confusion):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)
    chosen, comparison = trace["selected_case"], trace["same_class_correct_comparison"]

    def draw_path(ax, case, title):
        if case is None:
            ax.text(0.5, 0.5, "No other same-class correct example", ha="center", va="center", transform=ax.transAxes)
        else:
            for i, part in enumerate(case["raw_record"]["parts"]):
                if not part:
                    continue
                xy = np.asarray(part, dtype=float)
                ax.plot(xy[:, 0], xy[:, 1], ".-", linewidth=1.4, markersize=2.5,
                        label=f"part {i + 1}")
            result = case["selected_prediction"]
            ax.set_title(f"{title}\n{case['sample_id']}\ntrue={result['true_name']}, pred={result['predicted_name']}", fontsize=10)
        ax.set_xlabel("Local x (m)")
        ax.set_ylabel("Local y (m)")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(alpha=0.25)

    draw_path(axes[0, 0], chosen, "Selected test error" if trace["selection"]["selected_kind"] == "first_test_misclassification" else "First test correct (no errors)")
    draw_path(axes[0, 1], comparison, "Same true class: correct comparison")
    ax = axes[1, 0]
    x = np.arange(len(CLASS_NAMES))
    selected_result = chosen["selected_prediction"]
    ax.bar(x - 0.24, selected_result["probabilities_before_calibration"], width=0.24, label="Selected T=1")
    ax.bar(x, selected_result["probabilities_after_calibration"], width=0.24, label="Selected calibrated")
    ax.bar(x + 0.24, chosen["baseline_prediction"]["probabilities_after_calibration"], width=0.24, label="Linear calibrated")
    ax.set_xticks(x, CLASS_NAMES)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Class probability")
    ax.set_title("Selected example: frozen model probabilities")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.2)
    ax = axes[1, 1]
    matrix = np.asarray(confusion, dtype=int)
    display = ax.imshow(matrix, cmap="Blues", vmin=0)
    for i in range(len(CLASS_NAMES)):
        for j in range(len(CLASS_NAMES)):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                    color="white" if matrix[i, j] > matrix.max() / 2 else "black")
    ax.set_xticks(x, CLASS_NAMES)
    ax.set_yticks(x, CLASS_NAMES)
    ax.set_xlabel("Predicted class")
    ax.set_ylabel("True synthetic class")
    ax.set_title("All labeled valid test examples")
    fig.colorbar(display, ax=ax, label="Count", shrink=0.8)
    fig.suptitle("S0 synthetic geometry walkthrough | local XY metres | known seed replay", fontsize=13)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _check_destinations(out, inputs):
    workspace = ROOT.resolve()
    protected = [workspace / name for name in ("data", "tools", "fishing_demo", "docs", "tests", ".codex")]
    for target in (out / name for name in OUTPUT_NAMES):
        resolved = target.resolve()
        if resolved.parent != out:
            raise ValueError("analysis output must not alias a file outside its output directory")
        if resolved == workspace or any(resolved == directory or directory in resolved.parents for directory in protected):
            raise ValueError("analysis targets must be in a separate output directory")
        for source in inputs:
            if resolved == source.resolve() or (target.exists() and target.samefile(source)):
                raise ValueError("analysis output would overwrite a source input")


def analyze(output_dir):
    """Read six frozen inputs, assert agreement, emit exactly three audit artifacts."""
    out = Path(output_dir).resolve()
    paths = {name: out / name for name in INPUT_NAMES}
    if (out / "baseline_predictions.json").exists():
        paths["baseline_predictions.json"] = out / "baseline_predictions.json"
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError(f"missing frozen analysis inputs: {', '.join(missing)}")
    # Preserve the protocol, dashboard and run evidence as well as the six
    # numerical inputs. In particular, reject a hard link from a new output
    # name to any of those prior artifacts before rendering or writing.
    preserved = {p.name: p for p in out.iterdir() if p.is_file() and p.name not in OUTPUT_NAMES}
    _check_destinations(out, preserved.values())
    source_hashes = {name: _sha256(path) for name, path in preserved.items()}
    dataset = load_dataset(paths["sample_dataset.json"])
    bundle, baseline_bundle = load_model(paths["model.json"]), load_model(paths["baseline_model.json"])
    report, baseline_report = _read_json(paths["report.json"]), _read_json(paths["baseline_metrics.json"])
    saved = _read_json(paths["predictions.json"])
    for name, value in (("report", report), ("baseline metrics", baseline_report)):
        if value.get("source_type") != "synthetic":
            raise ValueError(f"{name} must be explicitly synthetic")
    if (baseline_bundle["classifier"]["hidden"] != 0
            or baseline_bundle["classifier"]["l2"] != 0.01):
        raise ValueError("baseline must be the declared fixed linear hidden=0, l2=0.01 model")
    for key, expected in (("class_names", CLASS_NAMES), ("feature_names", list(FEATURE_NAMES)),
                           ("feature_units", list(FEATURE_UNITS))):
        _same(report[key], expected, f"report {key}")
    if (baseline_report.get("model") != baseline_bundle["selected_model"]
            or baseline_report.get("hidden") != 0 or baseline_report.get("l2") != 0.01):
        raise AssertionError("baseline report/model identity differs")
    if (dataset["metadata"]["seed"] != 42 or bundle.get("seed") != 42
            or report.get("seed") != 42
            or baseline_report.get("evaluation_kind") != "known_seed42_replay"):
        raise ValueError("this guided audit requires the declared known-seed42 replay")
    if (report["audit"]["test_used_for_selection"] or report["audit"]["stress_used_for_selection"]
            or baseline_report["test_used_to_choose_baseline"]):
        raise ValueError("saved audit reports final-split use for model selection")
    _same(bundle["preprocessor"], baseline_bundle["preprocessor"], "shared frozen preprocessing")
    _same(bundle["anomaly_model"], baseline_bundle["anomaly_model"], "shared frozen anomaly model")
    digest = dataset_digest(dataset)
    for value in (bundle, baseline_bundle, report["audit"]):
        if value.get("dataset_sha256") != digest:
            raise AssertionError("saved dataset digest does not match frozen sample dataset")
    if report["selected_model"] != bundle["selected_model"]:
        raise AssertionError("report/model selected model differs")
    _close(report["temperature"], bundle["temperature"], "report/model temperature")
    _close(baseline_report["temperature"], baseline_bundle["temperature"], "baseline temperature")
    X, details = feature_matrix(dataset["records"])
    indices, groups = split_indices(dataset["records"], details)
    _check_training_statistics(X[indices["train"]], bundle)
    predictions = predict_records(dataset, bundle)
    _same(predictions, saved, "fresh/saved selected predictions")
    baseline_predictions = predict_records(dataset, baseline_bundle)
    if "baseline_predictions.json" in paths:
        _same(baseline_predictions, _read_json(paths["baseline_predictions.json"]), "fresh/saved baseline predictions")
    for name, model_bundle, expected in (("model.json", bundle, predictions),
                                         ("baseline_model.json", baseline_bundle, baseline_predictions)):
        _same(predict_records(dataset, load_model(paths[name])), expected, f"{name} serialized reload")
        unlabelled = copy.deepcopy(dataset)
        for row in unlabelled["records"]:
            row["label"] = None
        without_labels = predict_records(unlabelled, model_bundle)
        for a, b in zip(expected, without_labels):
            _same({k: v for k, v in a.items() if k != "true_label"},
                  {k: v for k, v in b.items() if k != "true_label"}, f"{name} label removal")
    preprocessor = Preprocessor.from_dict(bundle["preprocessor"])
    selected_model = Classifier.from_dict(bundle["classifier"])
    baseline_model = Classifier.from_dict(baseline_bundle["classifier"])
    split_metrics, preprocessing_summary = {}, {}
    for split, index in indices.items():
        z = preprocessor.transform(X[index])
        labels = [dataset["records"][int(i)]["label"] for i in index]
        selected_logits, _, _ = manual_forward(selected_model, z)
        baseline_logits, _, _ = manual_forward(baseline_model, z)
        split_metrics[split] = {}
        for name, logits, temperature in (("selected", selected_logits, bundle["temperature"]),
                                           ("baseline", baseline_logits, baseline_bundle["temperature"])):
            before = recompute_metrics(labels, softmax(logits))
            after = recompute_metrics(labels, softmax(logits, temperature))
            split_metrics[split][name] = {"before_calibration": before, "after_calibration": after}
            target_report = report if name == "selected" else baseline_report
            _check_metrics(after, target_report["metrics"][split], f"{name}.{split}.after")
            if name == "selected":
                _check_metrics(before, report["before_calibration"][split], f"selected.{split}.before")
            elif split == "validation":
                _check_metrics(before, baseline_report["validation_before_calibration"], "baseline.validation.before")
        preprocessing_summary[split] = {"missing_raw_values": int(np.isnan(X[index]).sum()),
                                        "max_absolute_scaled_feature": float(np.abs(z[:, :len(FEATURE_NAMES)]).max()),
                                        "rows_with_absolute_scaled_feature_gt_3": int(np.any(np.abs(z[:, :len(FEATURE_NAMES)]) > 3, axis=1).sum()),
                                        "meaning": "descriptive train-scale observation; not a fitted anomaly rule"}
    train_labels = [dataset["records"][int(i)]["label"] for i in indices["train"]]
    frequencies = np.bincount(train_labels, minlength=len(CLASS_NAMES)) / len(train_labels)
    for split in ("test", "stress"):
        labels = [dataset["records"][int(i)]["label"] for i in indices[split]]
        _check_metrics(recompute_metrics(labels, np.tile(frequencies, (len(labels), 1))),
                       report["majority_baseline"][split], f"majority baseline.{split}")
    baseline_lookup = {p["sample_id"]: p for p in baseline_predictions}
    cases = select_cases(predictions)
    lookup = {row["sample_id"]: (row, detail) for row, detail in zip(dataset["records"], details)}

    def trace_case(prediction):
        if prediction is None:
            return None
        row, detail = lookup[prediction["sample_id"]]
        return build_trace_case(row, detail, bundle, baseline_bundle, prediction,
                                baseline_lookup[prediction["sample_id"]])

    selected, comparison = trace_case(cases["selected"]), trace_case(cases["comparison"])
    selection = {"selected_kind": cases["selected_kind"], "selected_sample_id": selected["sample_id"],
                 "rule": "sort test misclassifications by sample_id; first correct only if none",
                 "comparison_rule": "first other correct test example with the same true class, sorted by sample_id",
                 "comparison_status": cases["comparison_status"],
                 "comparison_sample_id": comparison["sample_id"] if comparison else None}
    trace = {"schema_version": "guided_baseline_trace_v1", "source_type": "synthetic",
             "coordinate_system": "local_xy_m", "class_names": CLASS_NAMES,
             "feature_names": list(FEATURE_NAMES), "feature_units": list(FEATURE_UNITS),
             "comparison_tolerance": {"forward_absolute": ATOL, "forward_relative": 0,
                                      "geometry_absolute": ATOL, "geometry_relative": 1e-12},
             "selection": selection, "selected_case": selected,
             "same_class_correct_comparison": comparison,
             "comparison": _feature_comparison(selected, comparison),
             "meaning": "Synthetic raw_record is generated input, not real observational raw data."}
    final_splits = {s: _final_split_summary(s, predictions, baseline_lookup,
                    split_metrics[s]["selected"]["after_calibration"]) for s in ("test", "stress")}
    stress_case = cases["stress_misclassification"]
    stress_summary = _case_summary(stress_case, baseline_lookup[stress_case["sample_id"]]) if stress_case else None
    checks = {"frozen_source_hashes_preserved": True, "dataset_digest_matches": True,
              "dataset_and_model_contracts_pass": True, "group_overlap_zero": True,
              "train_statistics_match_frozen_values": True, "all_split_metrics_match_saved": True,
              "all_split_manual_logits_match_public": True, "saved_predictions_match_frozen_inference": True,
              "serialized_reload_predictions_match": True, "label_removal_predictions_invariant": True,
              "trace_geometry_matches_extractor": True, "trace_forward_matches_saved_atol_1e_10": True,
              "no_fit_called_by_analysis": True, "model_changed_after_test_review": False}
    analysis = {"schema_version": "guided_baseline_analysis_v1", "source_type": "synthetic",
                "evaluation_kind": "known_seed42_replay", "new_blind_test": False,
                "selected_model": bundle["selected_model"], "baseline_model": baseline_bundle["selected_model"],
                "class_names": CLASS_NAMES, "input_sha256": source_hashes,
                "dataset_sha256": digest, "checks": checks, "split_metrics": split_metrics,
                "preprocessing_observations": preprocessing_summary,
                "final_splits": final_splits, "trace_selection": selection,
                "stress_first_misclassification": stress_summary,
                "stress_case_rule": "first misclassified stress example sorted by sample_id; null if none",
                "comparison": trace["comparison"],
                "stress_interpretation": {"different_vessel_groups": True,
                    "simultaneous_generator_changes": dataset["metadata"]["assumptions"].get("stress_shift", {}),
                    "causal_decomposition_performed": False,
                    "reason": "Test and stress use different vessel groups and four simultaneous fixed generator changes; no paired intervention isolates any one cause."},
                "layers": _layers(dataset, details, final_splits, preprocessing_summary),
                "success": {"criterion": "contract, reproducibility and trace checks; no arbitrary accuracy target",
                            "technical_checks_passed": True, "learner_understanding": "not_assessed"},
                "limitations": ["Known seed replay is not a newly blinded final evaluation.",
                    "Feature contrasts are observations, not identified causes of errors.",
                    "Saved bootstrap CI intervals are not recalculated by this deterministic metric audit.",
                    "No real data evaluation, external collection, hardware experiment, operational trial, or learner assessment.",
                    "Anomaly distance and high confidence are not accident truth or accident probabilities.",
                    "No fitting, calibration fitting, retuning or model selection is performed by this analysis."]}
    # Render before publishing JSON, so a missing plotting dependency is an explicit error.
    _write_walkthrough(out / "walkthrough.png", trace, final_splits["test"]["metrics"]["confusion"])
    if source_hashes != {name: _sha256(path) for name, path in preserved.items()}:
        raise AssertionError("a frozen source changed during analysis")
    save_json(out / "trace.json", trace)
    save_json(out / "analysis.json", analysis)
    print(f"Frozen checks passed; trace={selected['sample_id']} ({cases['selected_kind']}).")
    print(f"Written: {', '.join(OUTPUT_NAMES)}")
    return analysis, trace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/guided_baseline_20261026",
                        help="existing directory containing frozen guided-baseline outputs")
    args = parser.parse_args(argv)
    try:
        analyze(args.out)
    except (ValueError, AssertionError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Frozen baseline analysis failed: {exc}\n")


if __name__ == "__main__":
    main()
