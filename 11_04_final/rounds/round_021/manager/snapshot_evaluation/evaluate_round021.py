from __future__ import annotations

"""Final Round021 OUTER evaluation after all six fold models are frozen/reloaded."""
import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import psutil
from threadpoolctl import threadpool_limits

CODE_DIR = Path(__file__).resolve().parent
ROOT = CODE_DIR.parents[2]
sys.path.insert(0, str(CODE_DIR))
import run_performance as rp  # noqa: E402


def json_rows(path: Path, header: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != header:
            raise ValueError(f"Unexpected CSV columns: {path}: {reader.fieldnames}")
        return list(reader)


def metrics_for_days(y: np.ndarray, baseline: np.ndarray, candidate: np.ndarray, days: np.ndarray) -> dict:
    out = {}
    for name, mask in rp.day_masks(days).items():
        if mask.any():
            out[name] = {"rows": int(mask.sum()), "baseline12": rp.score_metrics(y[mask], baseline[mask]),
                         "candidate20": rp.score_metrics(y[mask], candidate[mask])}
    return out


def bootstrap_micro(y: np.ndarray, baseline: np.ndarray, candidate: np.ndarray,
                    repetitions: int, seed: int) -> dict:
    delta = (candidate == y).astype(np.int8) - (baseline == y).astype(np.int8)
    rng = np.random.default_rng(seed)
    draws = np.empty(repetitions, dtype=np.float64)
    n = len(y)
    for start in range(0, repetitions, 100):
        take = min(100, repetitions - start)
        index = rng.integers(0, n, size=(take, n), dtype=np.int32)
        draws[start:start + take] = delta[index].mean(axis=1)
    return {"unit": "vessel", "repetitions": repetitions, "seed": seed, "confidence": 0.95,
            "point_delta_micro_f1": float(delta.mean()),
            "ci95_percentile": np.quantile(draws, [0.025, 0.975]).tolist(),
            "limitation": "Repeated development OUTER rows do not establish independent performance."}


def class_transitions(y: np.ndarray, reference: np.ndarray, candidate: np.ndarray) -> dict:
    per_true = {}
    for c in range(4):
        mask = y == c
        per_true[str(c)] = np.bincount(reference[mask] * 4 + candidate[mask], minlength=16).reshape(4, 4).tolist()
    return {"overall_reference_rows_candidate_columns":
            np.bincount(reference * 4 + candidate, minlength=16).reshape(4, 4).tolist(),
            "by_true_class_reference_rows_candidate_columns": per_true}


def reference_diagnostics(y: np.ndarray, candidate: np.ndarray, reference: np.ndarray) -> dict:
    transitions = class_transitions(y, reference, candidate)
    class_rows = []
    cm = np.bincount(y * 4 + candidate, minlength=16).reshape(4, 4)
    global_metrics = rp.score_metrics(y, candidate)
    for c in range(4):
        mask = y == c
        gain = int(np.count_nonzero(mask & (reference != c) & (candidate == c)))
        loss = int(np.count_nonzero(mask & (reference == c) & (candidate != c)))
        tp = int(np.count_nonzero(mask & (candidate == c)))
        fp = int(np.count_nonzero((y != c) & (candidate == c)))
        class_rows.append({"class": c, "reference_tp": int(np.count_nonzero(mask & (reference == c))),
                           "candidate_tp": tp, "gain": gain, "loss": loss, "net_tp": gain - loss,
                           "precision": float(tp / (tp + fp)) if tp + fp else 0.0,
                           "recall": float(tp / int(mask.sum())) if mask.any() else 0.0,
                           "f1": global_metrics["classes"][c]["f1"],
                           "false_positives": fp,
                           "false_positive_true_class_sources": {str(other): int(cm[other, c]) for other in range(4) if other != c}})
    return {"classes": class_rows, "prediction_transitions": transitions}


def load_outer_spatial(path: Path, expected: dict[int, dict], cfg: dict) -> dict[int, np.ndarray]:
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    manifest = rp.read_json(manifest_path)
    if manifest.get("role") != "OUTER" or manifest.get("columns") != list(rp.SPATIAL_COLUMNS):
        raise ValueError("OUTER spatial feature manifest has an unexpected role/column schema")
    if rp.sha256_file(path) != manifest.get("output_sha256"):
        raise ValueError("OUTER spatial feature file hash differs from its manifest")
    output_dir = rp.path_from_config(cfg["paths"]["output_dir"])
    proof = manifest.get("fit_artifact_proof") or {}
    if proof.get("baseline_fit_sha256") != rp.sha256_file(output_dir / "baseline_fit.json") or proof.get("candidate_fit_sha256") != rp.sha256_file(output_dir / "candidate_fit.json"):
        raise PermissionError("OUTER spatial feature manifest is not bound to both saved/reloaded fit stages")
    rows = json_rows(path, ("id", "year", "fold", "role", *rp.SPATIAL_COLUMNS))
    by_fold = {f: {} for f in rp.FOLDS}
    for row in rows:
        fold = rp.integer(row["fold"], "spatial OUTER fold")
        vessel = row["id"]
        if fold not in rp.FOLDS or row["role"] != "OUTER" or rp.integer(row["year"], "spatial OUTER year") != cfg["dataset"]["cohort_year"]:
            raise ValueError(f"OUTER spatial row key mismatch: {row}")
        if vessel in by_fold[fold]:
            raise ValueError(f"Duplicate OUTER spatial key: {fold}/{vessel}")
        vals = np.asarray([rp.numeric(row[c], f"spatial {c}", blank_nan=True) for c in rp.SPATIAL_COLUMNS], dtype=np.float64)
        finite = np.isfinite(vals)
        if np.isinf(vals).any() or np.any((vals[finite] < -1e-12) | (vals[finite] > 1.0 + 1e-12)):
            raise ValueError(f"Invalid OUTER spatial feature: {fold}/{vessel}")
        by_fold[fold][vessel] = vals
    output = {}
    for fold in rp.FOLDS:
        ids = expected[fold]["ids"]
        if set(by_fold[fold]) != set(ids) or len(by_fold[fold]) != len(ids):
            raise ValueError(f"OUTER spatial rowkeys do not match exact OUTER IDs fold={fold}")
        output[fold] = np.vstack([by_fold[fold][v] for v in ids])
    return output


def verify_six_models(output_dir: Path, config_sha256: str) -> tuple[dict, dict, dict[int, object], dict[int, object]]:
    import joblib

    baseline = rp.read_json(output_dir / "baseline_fit.json")
    candidate = rp.read_json(output_dir / "candidate_fit.json")
    if baseline.get("status") != "baseline_12_fit_reloaded_select_only" or candidate.get("status") != "candidate_20_fit_reloaded_select_only":
        raise PermissionError("Evaluation requires completed baseline and candidate stages")
    if baseline.get("config_sha256") != config_sha256 or candidate.get("config_sha256") != config_sha256:
        raise ValueError("Frozen model stages use a different config SHA")
    if baseline.get("fits", {}).get("meta_fits") != 3 or candidate.get("fits", {}).get("meta_fits") != 3:
        raise ValueError("All six meta fits are required before OUTER access")
    if candidate.get("baseline_fit_sha256") != rp.sha256_file(output_dir / "baseline_fit.json"):
        raise ValueError("Candidate stage is not bound to the completed baseline fit artifact")
    base_models, cand_models = {}, {}
    for result, variant, target in ((baseline, "baseline12", base_models), (candidate, "candidate20", cand_models)):
        records = result.get("fit_records", [])
        if len(records) != 3 or {int(r["fold"]) for r in records} != set(rp.FOLDS):
            raise ValueError(f"Incomplete {variant} fold fit records")
        for record in records:
            fold = int(record["fold"])
            if record.get("features") != (12 if variant == "baseline12" else 20) or not record.get("reload_check_pass"):
                raise ValueError(f"Invalid {variant} fit/reload record fold={fold}")
            model_path = Path(record["model_path"])
            if not model_path.is_file() or rp.sha256_file(model_path) != record["model_sha256"]:
                raise ValueError(f"Frozen {variant} model hash mismatch fold={fold}")
            target[fold] = joblib.load(model_path)
            classes = target[fold].named_steps["logistic"].classes_.astype(int).tolist()
            if classes != [0, 1, 2, 3] or classes != record.get("classes"):
                raise ValueError(f"Frozen {variant} class order mismatch fold={fold}: {classes}")
    return baseline, candidate, base_models, cand_models


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=rp.DEFAULT_CONFIG)
    parser.add_argument("--outer-spatial", type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config.resolve()
    cfg = rp.read_json(config_path)
    output_dir = rp.path_from_config(cfg["paths"]["output_dir"])
    result_path = output_dir / "evaluation_round021.json"
    predictions_path = output_dir / "outer_predictions_round021_long.csv"
    core_path = output_dir / "evaluation_core_round021.json"
    claim_path = output_dir / "outer_eval_claim.json"
    if claim_path.exists() or result_path.exists() or predictions_path.exists() or core_path.exists():
        raise FileExistsError("Refusing a second OUTER scoring/evaluation run")
    start = time.perf_counter()
    available = int(psutil.virtual_memory().available)
    if available < int(cfg["execution"]["minimum_free_ram_before_fit_bytes"]):
        raise MemoryError(f"Evaluation RAM gate failed before reads: {available} bytes available")
    current = rp.build_input_manifest(cfg, config_path)
    # Manager must write approval for the exact current code/config/input snapshot.
    approval = rp.load_approval(cfg, current, config_path)
    approval_path = rp.path_from_config(cfg["paths"]["approval_file"])
    approval_record = rp.read_json(approval_path)
    evaluator_sha = rp.sha256_file(Path(__file__).resolve())
    approved_evaluator_sha = approval_record.get("evaluation_sha256") or approval_record.get("evaluation_script_sha256")
    if approved_evaluator_sha != evaluator_sha:
        raise PermissionError("Manager approval does not bind this exact final evaluator source")
    if approval_record.get("allowed_stage") != "evaluation":
        raise PermissionError(f"Manager approval stage is not OUTER evaluation: {approval_record.get('allowed_stage')}")
    outer_spatial_path = args.outer_spatial.resolve()
    outer_spatial_manifest_path = outer_spatial_path.with_suffix(outer_spatial_path.suffix + ".manifest.json")
    outer_spatial_sha = rp.sha256_file(outer_spatial_path)
    outer_spatial_manifest_sha = rp.sha256_file(outer_spatial_manifest_path)
    if approval_record.get("outer_spatial_features_sha256") != outer_spatial_sha or approval_record.get("outer_spatial_manifest_sha256") != outer_spatial_manifest_sha:
        additional = approval_record.get("additional_input_hashes", {})
        if (additional.get(str(outer_spatial_path)) != outer_spatial_sha
                or additional.get(str(outer_spatial_manifest_path.resolve())) != outer_spatial_manifest_sha):
            raise PermissionError("Manager approval does not bind this exact OUTER spatial feature CSV and manifest")
    additional = approval_record.get("additional_input_hashes", {})
    output_dir_for_approval = rp.path_from_config(cfg["paths"]["output_dir"])
    required_additional = {
        output_dir_for_approval / "baseline_fit.json",
        output_dir_for_approval / "candidate_fit.json",
        outer_spatial_path,
        outer_spatial_manifest_path.resolve(),
    }
    for fit_file in (output_dir_for_approval / "baseline_fit.json", output_dir_for_approval / "candidate_fit.json"):
        fit_record = rp.read_json(fit_file)
        for model_record in fit_record.get("fit_records", []):
            required_additional.add(Path(model_record["model_path"]).resolve())
    for path in required_additional:
        expected_hash = additional.get(str(path.resolve()))
        if not expected_hash or rp.sha256_file(path) != expected_hash:
            raise PermissionError(f"Final evaluation approval lacks or mismatches input hash: {path}")
    if current["config_sha256"] != rp.sha256_file(config_path):
        raise ValueError("Configuration changed during evaluation authorization")
    baseline_fit, candidate_fit, base_models, candidate_models = verify_six_models(output_dir, current["config_sha256"])

    # No OUTER probability values or per-vessel prediction rows are read before this point.
    # Feature metadata labels were previously loaded only for role alignment/prototype FIT labels.
    paths = rp.source_paths(cfg)
    source_meta = rp.validate_round002_sources(cfg, paths)
    state, prep_audit = rp.prepare_select_state(cfg, paths, source_meta)
    rp.ensure_select_only_probabilities_ready(state)
    baseline_verified = verify_baseline_select_models(cfg, state, output_dir, base_models)
    spatial_select_manifest = rp.attach_spatial_select_features(cfg, state)
    candidate_verified = verify_candidate_select_models(cfg, state, output_dir, candidate_models)
    for fold in rp.FOLDS:
        state["metadata"][fold]["package_roles"] = source_meta["package_roles"]
    rp.write_json(claim_path, {"round": "round_021", "status": "outer_evaluation_started_no_retry",
                               "started_at_utc": rp.utc_now(), "pid": os.getpid(),
                               "approval_sha256": rp.sha256_file(approval_path),
                               "evaluator_sha256": evaluator_sha,
                               "outer_spatial_features_sha256": outer_spatial_sha,
                               "outer_spatial_manifest_sha256": outer_spatial_manifest_sha,
                               "baseline_fit_sha256": rp.sha256_file(output_dir / "baseline_fit.json"),
                               "candidate_fit_sha256": rp.sha256_file(output_dir / "candidate_fit.json"),
                               "all_six_models_reload_verified": True,
                               "outer_probability_values_read_yet": False})
    outer = rp.load_outer_after_reload(cfg, paths, state)
    outer_spatial = load_outer_spatial(outer_spatial_path, outer, cfg)

    ids, folds, labels, days = [], [], [], []
    probs_base, probs_candidate = [], []
    predictions_base, predictions_candidate = [], []
    raw_by_model = {name: [] for name in rp.BASE_MODELS}
    outer_rows = []
    for fold in rp.FOLDS:
        d = outer[fold]
        ids.extend(d["ids"]); folds.extend([fold] * len(d["ids"]))
        labels.extend(d["y"].tolist()); days.extend(d["days"].tolist())
        for name in rp.BASE_MODELS:
            raw_by_model[name].append(d["base_probabilities"][name])
        x12 = np.concatenate([np.log(np.clip(d["base_probabilities"][name], cfg["probabilities"]["clip_min"], cfg["probabilities"]["clip_max"])) for name in rp.BASE_MODELS], axis=1)
        x20 = np.concatenate((x12, outer_spatial[fold]), axis=1)
        if x20.shape != (len(d["ids"]), 20) or np.isinf(x20).any():
            raise ValueError(f"Invalid OUTER candidate matrix fold={fold}")
        with threadpool_limits(limits=3):
            p12 = base_models[fold].predict_proba(x12)
            p20 = candidate_models[fold].predict_proba(x20)
        rp.assert_probability(p12, len(d["ids"]), 1e-12, f"baseline12 reload OUTER fold={fold}")
        rp.assert_probability(p20, len(d["ids"]), 1e-12, f"candidate20 reload OUTER fold={fold}")
        probs_base.append(p12); probs_candidate.append(p20)
        predictions_base.append(p12.argmax(axis=1)); predictions_candidate.append(p20.argmax(axis=1))
    y = np.asarray(labels, dtype=np.int64)
    days_array = np.asarray(days, dtype=np.float64)
    fold_array = np.asarray(folds, dtype=np.int64)
    pred12 = np.concatenate(predictions_base)
    pred20 = np.concatenate(predictions_candidate)
    p12_all = np.concatenate(probs_base); p20_all = np.concatenate(probs_candidate)
    if len(ids) != 5897 or len(set(ids)) != 5897:
        raise ValueError("OUTER rowkeys do not contain the 5,897 development vessels exactly once")

    metric12, metric20 = rp.score_metrics(y, pred12), rp.score_metrics(y, pred20)
    paired = rp.paired_correctness(y, pred12, pred20)
    boot = bootstrap_micro(y, pred12, pred20, cfg["evaluation"]["bootstrap"]["repetitions"], cfg["evaluation"]["bootstrap"]["seed"])
    base_all = {name: np.concatenate(parts) for name, parts in raw_by_model.items()}
    years = np.full(len(ids), int(cfg["dataset"]["cohort_year"]), dtype=np.int16)
    rows = []
    model_probs = {**base_all, "Stacker12_Baseline": p12_all, "Stacker20_Spatial": p20_all}
    for i, vessel in enumerate(ids):
        for name, p in model_probs.items():
            rows.append({"id": vessel, "year": int(years[i]), "fold": int(fold_array[i]), "role": "OUTER",
                         "model": name, "p0": float(p[i, 0]), "p1": float(p[i, 1]),
                         "p2": float(p[i, 2]), "p3": float(p[i, 3]), "y_true": int(y[i]),
                         "observed_days": float(days_array[i]) if math.isfinite(float(days_array[i])) else None})
    rp.write_predictions_csv(predictions_path, rows)
    rp.write_json(core_path, {"round": "round_021", "status": "core_outer_metrics_saved",
                              "evaluated_at_utc": rp.utc_now(), "rows": len(y),
                              "baseline12": metric12, "candidate20": metric20,
                              "paired": paired, "paired_bootstrap95": boot,
                              "outer_predictions_long_csv": str(predictions_path),
                              "independent_verified_performance": None, "official_score": None})

    # Six model fit/reload checks have completed before opening the historical per-vessel CSV.
    hist_path = rp.path_from_config(cfg["paths"]["historical_predictions"])
    historical_ref = rp.read_json(rp.path_from_config(cfg["paths"]["historical_protection_reference"]))
    expected_hist_sha = str(historical_ref["prediction_sha256"]).lower()
    gate = cfg["evaluation"]["gate"]
    if (expected_hist_sha != str(gate["historical_prediction_sha256"]).lower()
            or historical_ref["tp"] != gate["historical_true_positives"]
            or historical_ref["support"] != gate["historical_support"]):
        raise ValueError("Historical protection JSON differs from the frozen config reference values")
    if rp.sha256_file(hist_path).lower() != expected_hist_sha:
        raise ValueError("Historical protection prediction SHA differs from archived reference")
    hist_rows = json_rows(hist_path, ("rfid_id", "fold", "role", "y_true", "p0", "p1", "p2", "p3", "pred"))
    hist_by_id = {}
    for row in hist_rows:
        vessel = row["rfid_id"]
        if vessel in hist_by_id or row["role"] != "OUTER":
            raise ValueError(f"Duplicate/non-OUTER historical prediction row: {vessel}")
        hist_by_id[vessel] = row
    if set(hist_by_id) != set(ids) or len(hist_rows) != 5897:
        raise ValueError("Historical row IDs do not match the exact OUTER development roster")
    if any(int(hist_by_id[v]["fold"]) != int(folds[i]) or int(hist_by_id[v]["y_true"]) != int(y[i]) for i, v in enumerate(ids)):
        raise ValueError("Historical per-vessel fold/label alignment differs from current OUTER rows")
    pred_hist = np.asarray([int(hist_by_id[v]["pred"]) for v in ids], dtype=np.int64)
    if np.any((pred_hist < 0) | (pred_hist > 3)):
        raise ValueError("Historical class prediction outside [0,3]")
    hist_metrics = rp.score_metrics(y, pred_hist)
    hist_support = [c["support"] for c in hist_metrics["classes"]]
    if hist_support != historical_ref["support"]:
        raise ValueError("Historical class support differs from protected reference metadata")
    hist_tp = [int(np.count_nonzero((y == c) & (pred_hist == c))) for c in range(4)]
    if hist_tp != historical_ref["tp"]:
        raise ValueError(f"Historical per-vessel TP counts differ from archive: {hist_tp}")
    base_lightgbm_p = np.concatenate(raw_by_model["LightGBM_sqrt_macro"])
    pred_seed42 = base_lightgbm_p.argmax(axis=1)
    seed42_tp = [int(np.count_nonzero((y == c) & (pred_seed42 == c))) for c in range(4)]
    expected_seed42 = cfg["evaluation"]["gate"]["same_condition_baseline_true_positives"]
    if seed42_tp != [2389, 889, 108, 90] or seed42_tp[0] != expected_seed42["0"] or seed42_tp[3] != expected_seed42["3"]:
        raise ValueError(f"Round002 same-condition TP0/TP3 mismatch: {seed42_tp}")
    raw_lgbm_metrics = rp.score_metrics(y, pred_seed42)
    expected_raw = cfg["evaluation"]["baseline_expected"]
    if (raw_lgbm_metrics["correct"] != expected_raw["correct"]
            or abs(raw_lgbm_metrics["micro_f1"] - expected_raw["micro_f1"]) > 1e-12
            or abs(raw_lgbm_metrics["macro_f1"] - expected_raw["macro_f1"]) > 1e-12):
        raise ValueError("Raw round002 LightGBM seed42 reference no longer matches its saved expected metrics")

    metric12, metric20 = rp.score_metrics(y, pred12), rp.score_metrics(y, pred20)
    paired = rp.paired_correctness(y, pred12, pred20)
    boot = bootstrap_micro(y, pred12, pred20, cfg["evaluation"]["bootstrap"]["repetitions"], cfg["evaluation"]["bootstrap"]["seed"])
    day_report = metrics_for_days(y, pred12, pred20, days_array)
    fold_report = {}
    for fold in rp.FOLDS:
        mask = fold_array == fold
        fold_report[str(fold)] = {"rows": int(mask.sum()), "baseline12": rp.score_metrics(y[mask], pred12[mask]),
                                  "candidate20": rp.score_metrics(y[mask], pred20[mask]),
                                  "paired": rp.paired_correctness(y[mask], pred12[mask], pred20[mask])}
    references = {"historical_sqrt_macro_5seed": pred_hist, "round002_seed42_lightgbm": pred_seed42}
    reference_report = {name: {"baseline12": reference_diagnostics(y, pred12, ref),
                               "candidate20": reference_diagnostics(y, pred20, ref)}
                        for name, ref in references.items()}
    class_deltas = [{"class": c,
                     "recall_delta": metric20["classes"][c]["recall"] - metric12["classes"][c]["recall"],
                     "f1_delta": metric20["classes"][c]["f1"] - metric12["classes"][c]["f1"]} for c in range(4)]
    day_deltas = {name: report["candidate20"]["micro_f1"] - report["baseline12"]["micro_f1"]
                  for name, report in day_report.items() if name != "0_or_missing"}
    ci_low = boot["ci95_percentile"][0]
    tp20 = [int(np.count_nonzero((y == c) & (pred20 == c))) for c in range(4)]
    tp12 = [int(np.count_nonzero((y == c) & (pred12 == c))) for c in range(4)]
    checks = {
        "candidate_micro_delta_ge_0_005": paired["micro_delta"] >= gate["candidate_micro_delta_min"],
        "paired_vessel_bootstrap_ci_lower_gt_0": ci_low > gate["paired_ci_lower_gt"],
        "candidate_macro_drop_le_0_03": metric20["macro_f1"] - metric12["macro_f1"] >= gate["macro_f1_delta_min"],
        "every_class_recall_drop_le_0_03": all(x["recall_delta"] >= gate["each_class_recall_delta_min"] for x in class_deltas),
        "protected_class_0_recall_not_below_baseline12": class_deltas[0]["recall_delta"] >= 0.0,
        "protected_class_3_recall_not_below_baseline12": class_deltas[3]["recall_delta"] >= 0.0,
        "every_class_f1_drop_le_0_03": all(x["f1_delta"] >= gate["each_class_f1_delta_min"] for x in class_deltas),
        "observed_days_micro_drop_le_0_03": len(day_deltas) == 4 and all(v >= gate["each_observed_days_micro_delta_min"] for v in day_deltas.values()),
        "protected_tp0_at_least_2389": tp20[0] >= 2389,
        "protected_tp3_at_least_92": tp20[3] >= 92,
        "nondecrease_vs_both_protection_references": all(reference_report[name]["candidate20"]["classes"][c]["net_tp"] >= 0 for name in references for c in (0, 3)),
        "model_hashes_and_reload_checks_pass": True,
        "source_alignment_pass": True,
    }
    pass_gate = all(checks.values())

    result = {
        "round": "round_021", "status": "evaluated_development_outer",
        "evaluated_at_utc": rp.utc_now(),
        "scope": "Repeated 5,897-row development OUTER; no 2025/Test2025/holdout rows",
        "rows": len(y), "class_order": cfg["dataset"]["class_order"],
        "cohort_year": cfg["dataset"]["cohort_year"], "year_is_rowwise_measured": False,
        "methods": {"Stacker12_Baseline": metric12, "Stacker20_Spatial": metric20,
                    "Historical_sqrt_macro_5seed": hist_metrics,
                    "Round002_seed42_LightGBM": raw_lgbm_metrics},
        "baseline12_vs_candidate20": paired, "paired_bootstrap95": boot,
        "observed_days": day_report, "observed_days_micro_deltas_candidate_minus_baseline": day_deltas,
        "folds": fold_report, "class_recall_f1_deltas": class_deltas,
        "protected_reference_transitions": reference_report,
        "protected_true_positive_counts": {"baseline12": tp12, "candidate20": tp20,
                                            "historical5seed": hist_tp, "round002_seed42": seed42_tp},
        "candidate_gate": {"checks": checks, "pass": pass_gate,
                           "development_goal_micro_f1": cfg["evaluation"]["development_goal_micro_f1"],
                           "candidate_reached_0_7": metric20["micro_f1"] >= cfg["evaluation"]["development_goal_micro_f1"],
                           "candidate_adopted": False},
        "fit_accounting": {"base_fits": 0, "meta_fits": 6, "grid_searches": 0, "retries": 0,
                           "baseline_fit_sha256": rp.sha256_file(output_dir / "baseline_fit.json"),
                           "candidate_fit_sha256": rp.sha256_file(output_dir / "candidate_fit.json")},
        "source_hashes": {"round002_seed42_historical_predictions_sha256": rp.sha256_file(hist_path),
                          "outer_spatial_features_sha256": rp.sha256_file(args.outer_spatial.resolve()),
                          "evaluator_sha256": rp.sha256_file(Path(__file__).resolve()),
                          "runner_sha256": current["runner_sha256"], "config_sha256": current["config_sha256"]},
        "manager_approval": approval, "select_verify": {"baseline_model_reproduces_select": baseline_verified,
                                                            "candidate_model_reproduces_select": candidate_verified,
                                                            "spatial_select_manifest": spatial_select_manifest},
        "outer_predictions_long_csv": str(predictions_path),
        "independent_verified_performance": None, "official_score": None,
        "hardware_test": None, "elapsed_seconds": time.perf_counter() - start,
        "note": "F1 values are development OUTER results only; no independent or official result is claimed."}
    rp.write_json(result_path, result)
    print(json.dumps({"status": result["status"], "evaluated_at_utc": result["evaluated_at_utc"], "candidate_micro_f1": metric20["micro_f1"],
                      "baseline12_micro_f1": metric12["micro_f1"], "progress_gate_pass": pass_gate,
                      "candidate_reached_0_7": result["candidate_gate"]["candidate_reached_0_7"],
                      "result": str(result_path), "predictions": str(predictions_path)}, ensure_ascii=False))
    return 0


def verify_baseline_select_models(cfg: dict, state: dict, output_dir: Path, models: dict[int, object]) -> bool:
    for fold in rp.FOLDS:
        with threadpool_limits(limits=3):
            p = models[fold].predict_proba(state["select"][fold]["stacker_x"])
        file = output_dir / "select_probabilities" / f"fold_{fold}_baseline12_inner_select.npz"
        with np.load(file, allow_pickle=False) as z:
            before = z["probabilities"]
        if not np.allclose(p, before, atol=1e-12, rtol=0.0):
            raise ValueError(f"Baseline SELECT reload verification failed again fold={fold}")
    return True


def verify_candidate_select_models(cfg: dict, state: dict, output_dir: Path, models: dict[int, object]) -> bool:
    for fold in rp.FOLDS:
        with threadpool_limits(limits=3):
            p = models[fold].predict_proba(state["select"][fold]["candidate_x"])
        file = output_dir / "select_probabilities" / f"fold_{fold}_candidate20_inner_select.npz"
        with np.load(file, allow_pickle=False) as z:
            before = z["probabilities"]
        if not np.allclose(p, before, atol=1e-12, rtol=0.0):
            raise ValueError(f"Candidate SELECT reload verification failed again fold={fold}")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
