from __future__ import annotations

"""Independent metric/key audit of saved Round021 predictions; no model inference."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROUND = Path(__file__).resolve().parents[1]
PROJECT = ROUND.parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    cm = np.bincount(y * 4 + pred, minlength=16).reshape(4, 4)
    support = cm.sum(axis=1)
    predicted = cm.sum(axis=0)
    tp = np.diag(cm)
    precision = np.divide(tp, predicted, out=np.zeros(4, dtype=float), where=predicted > 0)
    recall = np.divide(tp, support, out=np.zeros(4, dtype=float), where=support > 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                    out=np.zeros(4, dtype=float), where=(precision + recall) > 0)
    correct = int(tp.sum())
    return {"n": int(len(y)), "correct": correct, "micro_f1": correct / len(y),
            "macro_f1": float(f1.mean()), "support": support.astype(int).tolist(),
            "tp": tp.astype(int).tolist(), "precision": precision.tolist(),
            "recall": recall.tolist(), "f1": f1.tolist(), "confusion_matrix": cm.tolist()}


def reference_diagnostics(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray) -> dict:
    cm = np.bincount(y * 4 + candidate, minlength=16).reshape(4, 4)
    trans = np.bincount(reference * 4 + candidate, minlength=16).reshape(4, 4)
    per_true = {}
    for c in range(4):
        mask = y == c
        per_true[str(c)] = np.bincount(reference[mask] * 4 + candidate[mask], minlength=16).reshape(4, 4).tolist()
    classes = []
    global_m = metrics(y, candidate)
    for c in range(4):
        mask = y == c
        gain = int(np.count_nonzero(mask & (reference != c) & (candidate == c)))
        loss = int(np.count_nonzero(mask & (reference == c) & (candidate != c)))
        tp = int(cm[c, c])
        fp = int(cm[:, c].sum() - tp)
        classes.append({"class": c, "reference_tp": int(np.count_nonzero(mask & (reference == c))),
                        "candidate_tp": tp, "gain": gain, "loss": loss, "net_tp": gain - loss,
                        "precision": global_m["precision"][c], "recall": global_m["recall"][c],
                        "f1": global_m["f1"][c], "false_positives": fp,
                        "false_positive_true_class_sources": {str(other): int(cm[other, c])
                                                               for other in range(4) if other != c}})
    return {"classes": classes, "prediction_transitions": {
        "overall_reference_rows_candidate_columns": trans.tolist(),
        "by_true_class_reference_rows_candidate_columns": per_true}}


def close(a: float, b: float, tol: float = 1e-12) -> bool:
    return abs(float(a) - float(b)) <= tol


def main() -> None:
    output_dir = ROUND / "artifacts"
    config = json.loads((ROUND / "configs" / "experiment.json").read_text(encoding="utf-8"))
    result_path = output_dir / "evaluation_round021.json"
    predictions_path = output_dir / "outer_predictions_round021_long.csv"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    rows = read_csv(predictions_path)
    models = ("LightGBM_sqrt_macro", "CatBoost", "TabICL_A_raw", "Stacker12_Baseline", "Stacker20_Spatial")
    by_model: dict[str, dict[str, dict]] = {m: {} for m in models}
    model_order: dict[str, list[str]] = {m: [] for m in models}
    order_ids: list[str] = []
    labels_by_id, fold_by_id, days_by_id = {}, {}, {}
    row_keys = set()
    max_sum_error = 0.0
    probability_bounds_ok = True
    for row in rows:
        vessel, model = row["id"], row["model"]
        fold, year = int(row["fold"]), int(row["year"])
        if model not in by_model or row["role"] != "OUTER" or year != config["dataset"]["cohort_year"]:
            raise ValueError(f"Unexpected saved row scope: {model}/{row['role']}/{year}")
        key = (vessel, fold, model)
        if key in row_keys:
            raise ValueError(f"Duplicate saved prediction key: {key}")
        row_keys.add(key)
        if vessel not in labels_by_id:
            order_ids.append(vessel)
        if vessel not in by_model[model]:
            model_order[model].append(vessel)
        y = int(row["y_true"])
        if y not in range(4):
            raise ValueError(f"Invalid saved label for id={vessel}")
        days = float(row["observed_days"]) if row["observed_days"] else float("nan")
        if vessel in labels_by_id and (labels_by_id[vessel] != y or fold_by_id[vessel] != fold):
            raise ValueError(f"Saved source/model rows disagree on y or fold for id={vessel}")
        labels_by_id[vessel], fold_by_id[vessel], days_by_id[vessel] = y, fold, days
        p = np.asarray([float(row[f"p{i}"]) for i in range(4)], dtype=np.float64)
        if not np.isfinite(p).all():
            raise ValueError(f"Nonfinite saved probability for {key}")
        probability_bounds_ok &= bool(np.all((p >= 0) & (p <= 1)))
        max_sum_error = max(max_sum_error, abs(float(p.sum()) - 1.0))
        by_model[model][vessel] = {"p": p, "pred": int(np.argmax(p)), "y": y,
                                   "fold": fold, "days": days}

    ids = order_ids
    if len(ids) != 5897 or any(len(by_model[m]) != 5897 for m in models):
        raise ValueError("Saved files do not contain exactly 5,897 rows per method")
    expected_folds = {0: 1966, 1: 1966, 2: 1965}
    fold_counts = {f: sum(v == f for v in fold_by_id.values()) for f in (0, 1, 2)}
    if fold_counts != expected_folds:
        raise ValueError(f"Unexpected OUTER fold counts: {fold_counts}")
    for model in models:
        if set(by_model[model]) != set(ids) or model_order[model] != ids:
            raise ValueError(f"ID set mismatch for {model}")

    y = np.asarray([labels_by_id[v] for v in ids], dtype=np.int64)
    folds = np.asarray([fold_by_id[v] for v in ids], dtype=np.int64)
    pred = {m: np.asarray([by_model[m][v]["pred"] for v in ids], dtype=np.int64) for m in models}
    computed = {m: metrics(y, pred[m]) for m in models}
    support = computed["Stacker20_Spatial"]["support"]
    if support != [2920, 2016, 835, 126]:
        raise ValueError(f"Unexpected class support: {support}")

    method_mapping = {"Stacker12_Baseline": "Stacker12_Baseline", "Stacker20_Spatial": "Stacker20_Spatial",
                      "Round002_seed42_LightGBM": "LightGBM_sqrt_macro"}
    checks = {"unique_id_fold_method_keys": len(row_keys) == 5897 * 5,
              "exact_outer_fold_counts": fold_counts == expected_folds,
              "class_support": support == [2920, 2016, 835, 126],
              "probability_bounds": probability_bounds_ok,
              "probability_row_sums_le_1e_6": max_sum_error <= 1e-6}
    for report_name, model in method_mapping.items():
        reported = result["methods"][report_name]
        cm = computed[model]
        checks[f"{report_name}_correct"] = cm["correct"] == reported["correct"]
        checks[f"{report_name}_micro_f1"] = close(cm["micro_f1"], reported["micro_f1"])
        checks[f"{report_name}_macro_f1"] = close(cm["macro_f1"], reported["macro_f1"])
        for c, rc in enumerate(reported["classes"]):
            checks[f"{report_name}_class{c}_metrics"] = checks.get(f"{report_name}_class{c}_metrics", True) and (
                cm["support"][c] == rc["support"] and close(cm["precision"][c], rc["precision"])
                and close(cm["recall"][c], rc["recall"]) and close(cm["f1"][c], rc["f1"]))

    baseline, candidate = pred["Stacker12_Baseline"], pred["Stacker20_Spatial"]
    base_ok, cand_ok = baseline == y, candidate == y
    paired = {"n": len(y), "baseline_correct": int(base_ok.sum()), "candidate_correct": int(cand_ok.sum()),
              "gain": int(np.count_nonzero(~base_ok & cand_ok)), "loss": int(np.count_nonzero(base_ok & ~cand_ok)),
              "net": int(np.count_nonzero(~base_ok & cand_ok) - np.count_nonzero(base_ok & ~cand_ok)),
              "micro_delta": float(cand_ok.mean() - base_ok.mean())}
    checks["baseline_candidate_paired_counts"] = (
        paired["baseline_correct"] == result["baseline12_vs_candidate20"]["reference_correct"]
        and paired["candidate_correct"] == result["baseline12_vs_candidate20"]["candidate_correct"]
        and paired["gain"] == result["baseline12_vs_candidate20"]["newly_correct"]
        and paired["loss"] == result["baseline12_vs_candidate20"]["newly_incorrect"]
        and paired["net"] == result["baseline12_vs_candidate20"]["net_additional_correct"]
        and close(paired["micro_delta"], result["baseline12_vs_candidate20"]["micro_delta"]))

    reps = config["evaluation"]["bootstrap"]["repetitions"]
    seed = config["evaluation"]["bootstrap"]["seed"]
    delta = (candidate == y).astype(np.int8) - (baseline == y).astype(np.int8)
    rng = np.random.default_rng(seed)
    draws = np.empty(reps, dtype=np.float64)
    for start in range(0, reps, 100):
        take = min(100, reps - start)
        index = rng.integers(0, len(y), size=(take, len(y)), dtype=np.int32)
        draws[start:start + take] = delta[index].mean(axis=1)
    ci = np.quantile(draws, [0.025, 0.975]).tolist()
    checks["paired_bootstrap_ci"] = all(close(a, b) for a, b in zip(ci, result["paired_bootstrap95"]["ci95_percentile"]))

    historical_path = Path(config["paths"]["historical_predictions"])
    if not historical_path.is_absolute():
        historical_path = PROJECT / historical_path
    historical_ref_path = Path(config["paths"]["historical_protection_reference"])
    if not historical_ref_path.is_absolute():
        historical_ref_path = PROJECT / historical_ref_path
    historical_ref = json.loads(historical_ref_path.read_text(encoding="utf-8-sig"))
    hist_sha = sha256(historical_path)
    hist_rows = read_csv(historical_path)
    hist_by_id = {r["rfid_id"]: r for r in hist_rows}
    if len(hist_by_id) != 5897 or set(hist_by_id) != set(ids):
        raise ValueError("Historical reference IDs do not match saved OUTER IDs")
    hist_pred = np.asarray([int(hist_by_id[v]["pred"]) for v in ids], dtype=np.int64)
    hist_y = np.asarray([int(hist_by_id[v]["y_true"]) for v in ids], dtype=np.int64)
    hist_fold = np.asarray([int(hist_by_id[v]["fold"]) for v in ids], dtype=np.int64)
    if not np.array_equal(hist_y, y) or not np.array_equal(hist_fold, folds):
        raise ValueError("Historical labels/folds do not align with saved OUTER rows")
    hist_metrics = metrics(y, hist_pred)
    seed_metrics = computed["LightGBM_sqrt_macro"]
    if hist_metrics["tp"] != historical_ref["tp"] or hist_metrics["support"] != historical_ref["support"]:
        raise ValueError("Historical TP/support differ from frozen reference metadata")
    if hist_sha.lower() != historical_ref["prediction_sha256"].lower():
        raise ValueError("Historical reference SHA mismatch")
    expected_seed_tp = [2389, 889, 108, 90]
    if seed_metrics["tp"] != expected_seed_tp:
        raise ValueError(f"Seed42 TP vector mismatch: {seed_metrics['tp']}")
    hist_reported = result["methods"]["Historical_sqrt_macro_5seed"]
    checks["historical_correct"] = hist_metrics["correct"] == hist_reported["correct"]
    checks["historical_micro_f1"] = close(hist_metrics["micro_f1"], hist_reported["micro_f1"])
    checks["historical_macro_f1"] = close(hist_metrics["macro_f1"], hist_reported["macro_f1"])
    checks["seed42_full_tp"] = seed_metrics["tp"] == [2389, 889, 108, 90]

    days = np.asarray([days_by_id[v] for v in ids], dtype=np.float64)
    day_masks = {"1-7": (days >= 1) & (days <= 7), "8-30": (days >= 8) & (days <= 30),
                 "31-90": (days >= 31) & (days <= 90), "91+": days >= 91,
                 "0_or_missing": (days < 1) | ~np.isfinite(days)}
    for name, mask in day_masks.items():
        report = result["observed_days"].get(name)
        if not mask.any():
            checks[f"days_{name}_empty"] = report is None
            continue
        if report is None:
            checks[f"days_{name}_present"] = False
            continue
        for model_name, pred_name in (("baseline12", "Stacker12_Baseline"), ("candidate20", "Stacker20_Spatial")):
            dm = metrics(y[mask], pred[pred_name][mask])
            reported_dm = report[model_name]
            checks[f"days_{name}_{model_name}"] = (dm["n"] == reported_dm["n"]
                and dm["correct"] == reported_dm["correct"]
                and close(dm["micro_f1"], reported_dm["micro_f1"])
                and close(dm["macro_f1"], reported_dm["macro_f1"]))

    protection = {}
    references = {"historical_sqrt_macro_5seed": hist_pred, "round002_seed42_lightgbm": pred["LightGBM_sqrt_macro"]}
    for name, ref in references.items():
        protection[name] = {}
        for model_name, model_pred in (("baseline12", baseline), ("candidate20", candidate)):
            diag = reference_diagnostics(y, model_pred, ref)
            protection[name][model_name] = diag
            reported = result["protected_reference_transitions"][name][model_name]
            checks[f"{name}_{model_name}_transitions_and_gainloss"] = diag == reported

    tp0, tp3 = computed["Stacker20_Spatial"]["tp"][0], computed["Stacker20_Spatial"]["tp"][3]
    checks["protected_candidate_tp0_report"] = tp0 == result["protected_true_positive_counts"]["candidate20"][0]
    checks["protected_candidate_tp3_report"] = tp3 == result["protected_true_positive_counts"]["candidate20"][3]
    checks["candidate_protection_gate_failure_matches_recomputed_tp"] = (
        (tp0 < 2389 or tp3 < 92) and result["candidate_gate"]["pass"] is False)
    checks["historical_hash_in_result"] = hist_sha == result["source_hashes"]["round002_seed42_historical_predictions_sha256"]
    checks["reported_candidate_gate"] = all(result["candidate_gate"]["checks"].values()) == result["candidate_gate"]["pass"]

    summary = {"round": "round_021", "passed": all(checks.values()),
               "verification": "saved_predictions_only_no_inference",
               "artifact_paths": {"result": str(result_path), "predictions": str(predictions_path),
                                  "historical_reference_predictions": str(historical_path),
                                  "historical_reference_metadata": str(historical_ref_path)},
               "result_status": result["status"], "saved_prediction_sha256": sha256(predictions_path),
               "historical_prediction_sha256": hist_sha, "rows_per_method": {m: len(by_model[m]) for m in models},
               "fold_counts": fold_counts, "class_support": support, "max_probability_row_sum_error": max_sum_error,
               "metrics": {"seed42_lightgbm": seed_metrics, "baseline12": computed["Stacker12_Baseline"],
                           "candidate20": computed["Stacker20_Spatial"], "historical5seed": hist_metrics},
               "baseline12_vs_candidate20": paired, "paired_bootstrap_ci95": ci,
               "protected_tp": {"candidate20": computed["Stacker20_Spatial"]["tp"],
                                "baseline12": computed["Stacker12_Baseline"]["tp"],
                                "historical5seed": hist_metrics["tp"], "seed42": seed_metrics["tp"]},
               "protected_reference_gain_loss_net": protection,
               "checks": checks, "all_checks_pass": all(checks.values()),
               "candidate_gate_pass": result["candidate_gate"]["pass"],
               "candidate_reached_0_7": result["candidate_gate"]["candidate_reached_0_7"],
               "candidate_protection_floors_met": {"class0_tp_at_least_2389": tp0 >= 2389,
                                                    "class3_tp_at_least_92": tp3 >= 92}}
    (ROUND / "review" / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": summary["passed"], "all_checks_pass": summary["all_checks_pass"], "checks": checks,
                      "seed42_correct": seed_metrics["correct"], "baseline12_correct": computed["Stacker12_Baseline"]["correct"],
                      "candidate20_correct": computed["Stacker20_Spatial"]["correct"],
                      "candidate_tp": computed["Stacker20_Spatial"]["tp"], "paired": paired, "bootstrap_ci95": ci,
                      "verification": str(ROUND / "review" / "verification.json")}, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
