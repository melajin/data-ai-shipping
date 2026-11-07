"""Compare independent Round 003 recomputation with the authorized artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from independent_recompute import metrics_from_cm


ROOT = Path(__file__).resolve().parents[3]
ROUND = ROOT / "rounds" / "round_003"
REVIEW = ROUND / "review"
DATA = Path(
    r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료"
)
SEEDS = (42, 2026)
FOLDS = (0, 1, 2)
POLICIES = ("A_raw", "A_old", "A_micro_select")
PCOLS = ("p0", "p1", "p2", "p3")
TOL = 1e-12
DAY_GROUPS = {
    "days_1_7": "1-7",
    "days_8_30": "8-30",
    "days_31_90": "31-90",
    "days_91_plus": "91+",
    "days_zero": "0",
    "days_unsupported": "unsupported_or_missing",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def close(a, b, tol=TOL):
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)


def policy_hash(policy):
    copy = dict(policy)
    saved = copy.pop("policy_sha256_before_hash_field", None)
    compact = json.dumps(copy, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return saved, hashlib.sha256(compact).hexdigest()


def load_development_inputs(independent):
    arrays = {}
    for seed in SEEDS:
        rows = read_csv(DATA / f"evaluation/seed_{seed}/original_oof_predictions.csv")
        rows.sort(key=lambda r: str(r["rfid_id"]))
        ids = [str(r["rfid_id"]) for r in rows]
        y = np.asarray([int(r["y_true"]) for r in rows], dtype=np.int64)
        p = np.asarray([[float(r[c]) for c in PCOLS] for r in rows], dtype=np.float64)
        days = np.asarray([float(r["observed_days"]) if r["observed_days"].strip() else math.nan for r in rows], dtype=np.float64)
        fold = np.asarray([int(r["fold"]) for r in rows], dtype=np.int64)
        factors = {int(k): float(v) for k, v in independent["policy_factors"][str(seed)]["A_micro_select"].items()}
        old_factors = {0: 2.0, 1: 3.0, 2: 2.0}
        pred = {"A_raw": p.argmax(axis=1)}
        for method, fm in (("A_old", old_factors), ("A_micro_select", factors)):
            selected = np.empty(len(y), dtype=np.int64)
            for f in FOLDS:
                mask = fold == f
                score = p[mask].copy()
                score[:, 2] *= fm[f]
                selected[mask] = score.argmax(axis=1)
            pred[method] = selected
        arrays[seed] = {"ids": ids, "y": y, "p": p, "days": days, "fold": fold, "pred": pred}
    return arrays


def main():
    independent = read_json(REVIEW / "independent_recompute.json")
    author = read_json(ROUND / "artifacts" / "result.json")
    policy = read_json(ROUND / "artifacts" / "decision_policy_frozen.json")
    precheck = read_json(REVIEW / "precheck.json")
    mismatches = []
    compared = {}

    # Verify source/config binding and the selected policy JSON digest.
    if author.get("runner_sha256") != precheck.get("runner_sha256"):
        mismatches.append("result runner SHA differs from precheck receipt")
    if author.get("config_sha256") != precheck.get("config_sha256"):
        mismatches.append("result config SHA differs from precheck receipt")
    if author.get("reviewer_precheck", {}).get("sha256") != sha256_file(REVIEW / "precheck.json"):
        mismatches.append("result reviewer-precheck SHA differs from current receipt file")
    saved_policy_digest, computed_policy_digest = policy_hash(policy)
    if saved_policy_digest != computed_policy_digest or author.get("policy_sha256") != computed_policy_digest:
        mismatches.append("frozen decision policy digest does not reproduce")
    compared["frozen_policy_digest"] = {
        "status": "PASS" if saved_policy_digest == computed_policy_digest == author.get("policy_sha256") else "FAIL",
        "saved": saved_policy_digest,
        "independent": computed_policy_digest,
    }

    # Compare all six independently selected factors and candidate grid values.
    policy_choices = {(int(c["seed"]), int(c["fold"])): c for c in policy["choices"]}
    selection_checks = {}
    for seed in SEEDS:
        for fold in FOLDS:
            key = (seed, fold)
            ours = independent["selection"][str(seed)][str(fold)]
            theirs = policy_choices.get(key)
            if theirs is None:
                mismatches.append(f"missing frozen policy choice {seed}/{fold}")
                continue
            ok = close(ours["factor"], theirs["selected_factor"])
            if not ok:
                mismatches.append(f"selected factor differs {seed}/{fold}")
            selection_checks[f"{seed}/{fold}"] = {
                "independent_factor": ours["factor"],
                "saved_factor": theirs["selected_factor"],
                "match": ok,
                "fallback": ours.get("fallback"),
            }
            if ours.get("grid"):
                by_factor = {float(c["factor"]): c for c in theirs.get("candidate_grid", [])}
                for item in ours["grid"]:
                    saved = by_factor.get(float(item["factor"]))
                    if saved is None:
                        mismatches.append(f"missing candidate grid factor {seed}/{fold}/{item['factor']}")
                        continue
                    for own_key, saved_key in (("eligible", "eligible"), ("inner_micro_f1", "micro_f1"),
                                               ("inner_macro_f1", "macro_f1"), ("natural_1_7_macro_f1", "days_1_7_macro_f1")):
                        if own_key == "eligible":
                            if item[own_key] != saved[saved_key]:
                                mismatches.append(f"candidate eligibility differs {seed}/{fold}/{item['factor']}")
                        elif not close(item[own_key], saved[saved_key]):
                            mismatches.append(f"candidate metric differs {seed}/{fold}/{item['factor']}/{own_key}")
    compared["selection"] = selection_checks

    # Compare full saved prediction rows to independently replayed decisions.
    arrays = load_development_inputs(independent)
    prediction_path = ROUND / "artifacts" / "predictions.csv"
    prediction_rows = read_csv(prediction_path)
    seen = set()
    prediction_mismatch_counts = {str(seed): 0 for seed in SEEDS}
    for row in prediction_rows:
        seed, vessel = int(row["seed"]), str(row["rfid_id"])
        if seed not in SEEDS or vessel not in set(arrays[seed]["ids"]) or (seed, vessel) in seen:
            mismatches.append("saved prediction artifact has invalid or duplicate seed/vessel inventory")
            continue
        seen.add((seed, vessel))
    if len(prediction_rows) != 5897 * 2 or len(seen) != 5897 * 2:
        mismatches.append("saved prediction artifact row inventory differs from 5,897 vessels per seed")
    row_map = {(int(r["seed"]), str(r["rfid_id"])): r for r in prediction_rows}
    for seed in SEEDS:
        d = arrays[seed]
        index_by_id = {v: i for i, v in enumerate(d["ids"])}
        for vessel in d["ids"]:
            row = row_map.get((seed, vessel))
            i = index_by_id[vessel]
            if row is None:
                prediction_mismatch_counts[str(seed)] += 1
                continue
            expected_days = d["days"][i]
            saved_days = float(row["observed_days"]) if row["observed_days"].strip() else math.nan
            bad = (
                int(row["fold"]) != int(d["fold"][i])
                or int(row["y_true"]) != int(d["y"][i])
                or not ((math.isnan(expected_days) and math.isnan(saved_days)) or expected_days == saved_days)
                or int(row["A_raw"]) != int(d["pred"]["A_raw"][i])
                or int(row["A_old"]) != int(d["pred"]["A_old"][i])
                or int(row["A_micro_select"]) != int(d["pred"]["A_micro_select"][i])
            )
            bad = bad or any(not close(row[c], d["p"][i, j]) for j, c in enumerate(PCOLS))
            if bad:
                prediction_mismatch_counts[str(seed)] += 1
    if any(prediction_mismatch_counts.values()):
        mismatches.append("saved per-vessel prediction decisions/probabilities differ from independent replay")
    compared["saved_predictions"] = {
        "rows": len(prediction_rows),
        "unique_seed_vessel_pairs": len(seen),
        "mismatch_count_by_seed": prediction_mismatch_counts,
        "status": "PASS" if not any(prediction_mismatch_counts.values()) else "FAIL",
        "artifact_sha256": sha256_file(prediction_path),
    }

    # Compare micro/macro/weighted F1, correct counts, per-class metrics and CMs
    # for every seed, fold, day stratum, and all-vessel scope.
    author_metric_checks = {"checked_metric_fields": ["micro_f1", "macro_f1", "weighted_f1", "class_precision", "class_recall", "class_f1", "class_support", "confusion_matrix"],
                            "total_fields": 0, "mismatches": []}
    group_mapping = {"all": ("overall", None), **{f"fold_{f}": ("by_fold", str(f)) for f in FOLDS}}
    group_mapping.update({name: ("by_observed_days", ours) for name, ours in DAY_GROUPS.items()})
    for seed in SEEDS:
        for author_group, ours_group in group_mapping.items():
            section, subsection = ours_group
            for method in POLICIES:
                method_result = independent["results"]["per_seed"][str(seed)][method]
                ours = method_result[section] if subsection is None else method_result[section][subsection]
                theirs = author["metrics"]["by_seed"][str(seed)][author_group][method]
                if not close(ours["micro_f1"], theirs["micro_f1"]):
                    author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/micro_f1")
                if not close(ours["macro_f1"], theirs["macro_f1"]):
                    author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/macro_f1")
                if not close(ours["weighted_f1"], theirs["weighted_f1"]):
                    author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/weighted_f1")
                if int(ours["n"]) != int(theirs["n_weighted"]):
                    author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/support_total")
                if int(ours["correct"]) != int(theirs["correct_weighted"]):
                    author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/correct")
                if ours["classes"]:
                    for name, saved_key in (("precision", "class_precision"), ("recall", "class_recall"), ("f1", "class_f1")):
                        for i, cls in enumerate(ours["classes"]):
                            author_metric_checks["total_fields"] += 1
                            if not close(cls[name], theirs[saved_key][i]):
                                author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/{saved_key}[{i}]")
                    support = [cls["support"] for cls in ours["classes"]]
                else:
                    # Empty strata have no observed classes in sklearn-style output;
                    # the runner deliberately serializes fixed-width all-zero class vectors.
                    support = [0, 0, 0, 0]
                    for saved_key in ("class_precision", "class_recall", "class_f1"):
                        author_metric_checks["total_fields"] += 4
                        if len(theirs[saved_key]) != 4 or any(v is not None for v in theirs[saved_key]):
                            author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/{saved_key}/empty_scope")
                author_metric_checks["total_fields"] += 4
                if support != [int(x) for x in theirs["class_support"]]:
                    author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/class_support")
                if ours["confusion_matrix_true_rows_predicted_columns"] != theirs["confusion_matrix"]:
                    author_metric_checks["mismatches"].append(f"{seed}/{author_group}/{method}/confusion_matrix")
    author_metric_checks["status"] = "PASS" if not author_metric_checks["mismatches"] else "FAIL"
    compared["metrics_all_scopes"] = author_metric_checks
    if author_metric_checks["mismatches"]:
        mismatches.extend("metric artifact mismatch: " + x for x in author_metric_checks["mismatches"])

    # Compare paired transition gains/losses and full predicted-label transitions.
    transition_checks = {"status": "PASS", "comparisons": {}}
    for a, b in (("A_old", "A_raw"), ("A_old", "A_micro_select"), ("A_raw", "A_micro_select")):
        key = f"{a}_to_{b}"
        transition_checks["comparisons"][key] = {}
        for seed in SEEDS:
            d = arrays[seed]
            own_a, own_b, y = d["pred"][a], d["pred"][b], d["y"]
            cm = np.bincount(own_a * 4 + own_b, minlength=16).reshape(4, 4)
            correct_a, correct_b = own_a == y, own_b == y
            own_gain = int((~correct_a & correct_b).sum())
            own_loss = int((correct_a & ~correct_b).sum())
            saved = author["paired_transition_counts"][key]["by_seed"][str(seed)]
            ok = (own_gain == saved["gain_new_correct"] and own_loss == saved["loss_new_wrong"]
                  and int(cm.sum()) == 5897
                  and cm.tolist() == saved["prediction_transition_matrix_source_rows_target_columns"])
            if not ok:
                mismatches.append(f"transition counts differ {key} seed {seed}")
                transition_checks["status"] = "FAIL"
            transition_checks["comparisons"][key][str(seed)] = {
                "gain": own_gain, "loss": own_loss, "net": own_gain - own_loss,
                "saved_gain": saved["gain_new_correct"], "saved_loss": saved["loss_new_wrong"],
                "prediction_transition_matrix_match": cm.tolist() == saved["prediction_transition_matrix_source_rows_target_columns"],
                "match": ok,
            }
    compared["paired_transition_counts"] = transition_checks

    # Confirm the author summary is backed by its saved numeric bootstrap draws
    # and that the independent CI matches the author output for all comparisons.
    bootstrap_meta = author["paired_bootstrap"]["raw_numeric_draws_artifact"]
    bootstrap_path = Path(bootstrap_meta["path"])
    if not bootstrap_path.is_absolute():
        bootstrap_path = ROOT / bootstrap_path
    draws = np.load(bootstrap_path, allow_pickle=False)
    pairs = (("A_old", "A_raw"), ("A_old", "A_micro_select"), ("A_raw", "A_micro_select"))
    # Independently recreate the runner's fixed vessel-resampling stream from
    # aligned development OOF labels and replayed predictions, then compare every
    # saved per-seed numeric draw cell (not just interval summaries).
    independent_draws = {
        (a, b, metric): np.empty((5000, 2), dtype=np.float64)
        for a, b in pairs for metric in ("micro_f1", "macro_f1")
    }
    rng = np.random.default_rng(20261105)
    for start in range(0, 5000, 40):
        stop = min(start + 40, 5000)
        sampled_indices = rng.integers(0, 5897, size=(stop - start, 5897), endpoint=False)
        for local_rep, indices in enumerate(sampled_indices):
            replicate = start + local_rep
            for seed_index, seed in enumerate(SEEDS):
                y_sample = arrays[seed]["y"][indices]
                metric_by_policy = {}
                for method in POLICIES:
                    pred = arrays[seed]["pred"][method][indices]
                    cm = np.bincount(y_sample * 4 + pred, minlength=16).reshape(4, 4)
                    metric_by_policy[method] = metrics_from_cm(cm)
                for a, b in pairs:
                    for metric in ("micro_f1", "macro_f1"):
                        independent_draws[(a, b, metric)][replicate, seed_index] = (
                            metric_by_policy[b][metric] - metric_by_policy[a][metric]
                        )
    bootstrap_checks = {"status": "PASS", "artifact_sha256": sha256_file(bootstrap_path), "pairs": {}}
    for a, b in pairs:
        key = f"{a}_to_{b}"
        bootstrap_checks["pairs"][key] = {}
        for metric in ("micro_f1", "macro_f1"):
            draw_key = f"{key}__all__{metric}"
            raw = draws[draw_key]
            own_raw = independent_draws[(a, b, metric)]
            raw_exact_match = np.array_equal(own_raw, raw)
            mean_draw = raw.mean(axis=1)
            raw_ci = [float(x) for x in np.quantile(mean_draw, [0.025, 0.975])]
            own_key = f"{b}_to_{a}" if key == "A_old_to_A_raw" else key
            own = independent["paired_bootstrap"]["pairs"][own_key][metric]
            saved = author["paired_bootstrap"]["by_comparison"][key]["all"][metric]
            if own_key != key:
                own_ci = [-own["percentile_95_ci"][1], -own["percentile_95_ci"][0]]
                own_point = -own["point_delta_mean_across_seeds"]
            else:
                own_ci = own["percentile_95_ci"]
                own_point = own["point_delta_mean_across_seeds"]
            ok = (raw.shape == (5000, 2)
                  and close(raw_ci[0], saved["ci95_percentile_mean_across_seeds"][0])
                  and close(raw_ci[1], saved["ci95_percentile_mean_across_seeds"][1])
                  and close(raw_ci[0], own_ci[0])
                  and close(raw_ci[1], own_ci[1])
                  and close(own_point, saved["point_delta_mean_across_seeds"])
                  and raw_exact_match)
            if not ok:
                mismatches.append(f"bootstrap draw/summary mismatch {key}/{metric}")
                bootstrap_checks["status"] = "FAIL"
            bootstrap_checks["pairs"][key][metric] = {
                "raw_draw_shape": list(raw.shape),
                "independent_ci": own_ci,
                "saved_summary_ci": saved["ci95_percentile_mean_across_seeds"],
                "ci_from_saved_draws": raw_ci,
                "independently_recomputed_draws_exact_match": raw_exact_match,
                "independent_draw_max_absolute_difference": float(np.max(np.abs(own_raw - raw))),
                "match": ok,
            }
    compared["paired_bootstrap"] = bootstrap_checks

    # Recompute the original-p probability quality summary independently.
    probability_checks = {"status": "PASS", "by_seed": {}}
    for seed in SEEDS:
        own = independent["probability_diagnostics_by_seed"][str(seed)]
        saved = author["original_probability_quality_by_seed_and_scope"][str(seed)]["all"]
        pairs = (("log_loss_original_probabilities", "logloss"),
                 ("multiclass_brier_sum_per_row", "multiclass_brier_sum_squared_mean"),
                 ("ece_10_equal_width_bins", "ece_10_equal_width"))
        ok = all(close(own[a], saved[b]) for a, b in pairs)
        high = own["high_confidence_errors_max_probability_ge_0_9"] == saved["high_confidence_raw_max_ge_0_9_errors"]
        ok = ok and high
        if not ok:
            mismatches.append(f"original probability quality diagnostics differ for seed {seed}")
            probability_checks["status"] = "FAIL"
        probability_checks["by_seed"][str(seed)] = {"match": ok}
    compared["original_probability_quality"] = probability_checks

    independent_gate = independent["selected_vs_raw_acceptance_gate"]
    author_gate = author["selected_vs_raw_progress_gate"]["criteria"]
    gate_key_map = {
        "paired_micro_ci_lower_above_zero": "paired_5000_vessel_bootstrap_ci_lower_above_zero",
        "mean_macro_not_lower": "mean_macro_f1_not_decreased",
        "each_seed_natural_1_7_macro_drop_no_more_than_0_01": "each_seed_natural_1_7_macro_f1_drop_no_more_than_0_01",
    }
    gates_match = all(
        independent_gate[k] == author_gate.get(gate_key_map.get(k, k))
        for k in independent_gate if k != "all_conditions"
    )
    if not gates_match:
        mismatches.append("selected-vs-raw progress gate differs")
    compared["selected_vs_raw_progress_gate"] = {
        "independent": independent_gate,
        "saved": author["selected_vs_raw_progress_gate"],
        "match": gates_match,
    }

    result = {
        "review_status": "PASS" if not mismatches else "MISMATCHES_FOUND",
        "scope": "independent verification of saved development probability decisions and output artifacts only",
        "holdout_individual_rows_read": 0,
        "full7372_f156_rows_or_labels_read": 0,
        "test2025_rows_read": 0,
        "raw_rows_read": 0,
        "feature_rows_read": 0,
        "model_fit_or_inference": False,
        "runner_sha256": author.get("runner_sha256"),
        "config_sha256": author.get("config_sha256"),
        "precheck_sha256": author.get("reviewer_precheck", {}).get("sha256"),
        "comparisons": compared,
        "mismatches": mismatches,
        "limitations": [
            "Evaluation is the previously exposed development OUTER population, not independent validation.",
            "Bootstrap intervals do not remove repeated-development selection bias or geographic dependence.",
            "The archived generation lineage is verified from source and metadata; no model re-inference or checkpoint validation was performed.",
            "F156 versus missing-flag/312-column input discrepancy remains unresolved for M4; no feature rows were read.",
        ],
    }
    out = REVIEW / "artifact_comparison.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "review_status": result["review_status"],
        "metric_scope_status": author_metric_checks["status"],
        "prediction_status": compared["saved_predictions"]["status"],
        "bootstrap_status": bootstrap_checks["status"],
        "probability_quality_status": probability_checks["status"],
        "mismatch_count": len(mismatches),
        "output": str(out),
    }, ensure_ascii=False, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
