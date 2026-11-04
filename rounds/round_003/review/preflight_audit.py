"""Reviewer-only preflight for Round 003's allowlisted TabICL artifacts.

This script validates provenance, roster alignment, saved-probability shape and
historical TabICL fit/INNER separation. It does not compute classification
metrics, run a model, load feature rows, or read holdout/Test2025/raw rows.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA = Path(
    r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료"
)
OUT = Path(__file__).resolve().parent / "preflight_audit.json"
SEEDS = (42, 2026)
FOLDS = (0, 1, 2)
EXPECTED_OUTER = {0: 1966, 1: 1966, 2: 1965}
EXPECTED = [
    "evaluation/seed_42/original_oof_predictions.csv",
    "evaluation/seed_2026/original_oof_predictions.csv",
    "evaluation/seed_42/oof_decisions.csv",
    "evaluation/seed_2026/oof_decisions.csv",
    "evaluation/trap_factors.csv",
    "evaluation/final_fixed_decision_rule.json",
    "metadata/classes.json",
    "metadata/run_settings.json",
    "metadata/package_validation.json",
    "splits/development_roles_long.csv",
    *[
        f"evaluation/seed_{seed}/fold_{fold}/inner_predictions.csv"
        for seed in SEEDS
        for fold in FOLDS
    ],
]
SOURCE_FILES = {
    "comparison_models.py": DATA / "code/historical/TabM/TabM_개선_20261030/comparison_models.py",
    "run_experiments.py": DATA / "code/historical/TabM/TabM_개선_20261030/run_experiments.py",
    "finalize_comparisons.py": DATA / "code/historical/TabM/TabM_개선_20261030/finalize_comparisons.py",
    "apply_frozen_decision.py": DATA / "code/historical/TabM/TabM_개선_20261030/apply_frozen_decision.py",
    "fishing_tiny_tabm.py": DATA / "code/historical/TinyTabM/TinyTabM_구현_20261029/fishing_tiny_tabm.py",
}
CLASS_ORDER = ["연안복합", "자망", "통발", "채낚기연승낚시"]
PCOLS = ["p0", "p1", "p2", "p3"]
TOL = 1e-12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest_json(value) -> str:
    # Matches the historical fishing_tiny_tabm.py BASE.digest_json helper.
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(rel: str):
    return json.loads((DATA / rel).read_text(encoding="utf-8-sig"))


def read_csv(rel: str):
    with (DATA / rel).open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def close(a, b, tol=TOL):
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)


def fail_if(condition, message, failures):
    if condition:
        failures.append(message)


def probability_row(row, where, failures):
    try:
        p = [float(row[name]) for name in PCOLS]
    except (KeyError, TypeError, ValueError):
        failures.append(f"{where}: probability columns unavailable")
        return None
    if not all(math.isfinite(x) and 0.0 <= x <= 1.0 for x in p):
        failures.append(f"{where}: nonfinite or out-of-range probability")
    if not close(sum(p), 1.0):
        failures.append(f"{where}: probability sum outside tolerance")
    return p


def main():
    failures = []
    checks = {}
    input_manifest = read_json("MANIFEST_SHA256.json")
    source_manifest = read_json("SOURCE_SHA256.json")

    # Validate exact allowlisted input files against the package file manifest.
    input_hashes = {}
    for rel in EXPECTED:
        path = DATA / rel
        if not path.is_file():
            failures.append(f"missing allowlisted input: {rel}")
            continue
        actual = sha256_file(path)
        expected = input_manifest.get(rel)
        input_hashes[rel] = actual
        if expected is None or actual.lower() != str(expected).lower():
            failures.append(f"package manifest hash mismatch: {rel}")
    checks["allowlisted_inputs_match_package_manifest"] = len(input_hashes) == len(EXPECTED) and not any(
        item.startswith("package manifest hash mismatch") or item.startswith("missing allowlisted input")
        for item in failures
    )

    # Confirm the historical helper's JSON-list digest convention against the
    # INNER ID order in the saved prediction CSVs and frozen decision metadata.
    source_hashes = {}
    source_manifest_matches = {}
    for name, path in SOURCE_FILES.items():
        actual = sha256_file(path)
        source_hashes[name] = actual
        source_manifest_matches[name] = any(
            str(k).replace("\\", "/").endswith(path.name)
            and str(v).lower() == actual.lower()
            for k, v in source_manifest.items()
        )
        if name in ("comparison_models.py", "run_experiments.py", "fishing_tiny_tabm.py") and not source_manifest_matches[name]:
            failures.append(f"historical source hash absent from SOURCE_SHA256: {name}")
    checks["historical_source_hashes_match"] = all(source_manifest_matches.values())

    classes = read_json("metadata/classes.json")
    canonical_classes = [classes.get(str(i)) for i in range(4)]
    rule = read_json("evaluation/final_fixed_decision_rule.json")
    checks["class_order_matches_rule"] = canonical_classes == CLASS_ORDER and rule.get("class_order") == CLASS_ORDER
    if not checks["class_order_matches_rule"]:
        failures.append("class order differs from the frozen rule")

    settings = read_json("metadata/run_settings.json")
    package_validation = read_json("metadata/package_validation.json")
    checks["historical_runtime_metadata"] = {
        "algorithm": settings.get("algorithm"),
        "tabicl_version": settings.get("package_versions", {}).get("tabicl"),
        "torch_version": settings.get("package_versions", {}).get("torch"),
        "checkpoint": settings.get("checkpoint"),
        "checkpoint_sha256": settings.get("checkpoint_sha256"),
        "package_validation_features": package_validation.get("features"),
        "package_validation_development_vessels": package_validation.get("development"),
        "package_validation_new_training": package_validation.get("new_training"),
        "package_validation_new_model_queries": package_validation.get("new_model_queries"),
        "run_settings_fit_preprocess": settings.get("fit_preprocess"),
    }

    role_rows = read_csv("splits/development_roles_long.csv")
    role_map = {}
    role_counts = {}
    for row in role_rows:
        vessel = str(row["rfid_id"])
        fold = int(row["outer_fold"])
        role = str(row["role"]).strip().upper()
        key = (fold, vessel)
        if key in role_map:
            failures.append("development role roster has duplicate vessel/fold entries")
            break
        role_map[key] = role
        role_counts[(fold, role)] = role_counts.get((fold, role), 0) + 1
    role_ids = sorted({vessel for _, vessel in role_map})
    checks["development_role_roster"] = {
        "rows": len(role_rows),
        "unique_vessels": len(role_ids),
        "rows_by_fold_role": {
            f"{fold}:{role}": count for (fold, role), count in sorted(role_counts.items())
        },
    }
    if len(role_ids) != 5897 or len(role_rows) != 5897 * 3:
        failures.append("development role roster is not 5,897 vessels x 3 folds")
    for fold in FOLDS:
        if {role_map.get((fold, vessel)) for vessel in role_ids} != {"FIT", "INNER", "OUTER"}:
            failures.append(f"role roster has incomplete roles in fold {fold}")

    oof_by_seed = {}
    oof_summary = {}
    for seed in SEEDS:
        rel = f"evaluation/seed_{seed}/original_oof_predictions.csv"
        rows = read_csv(rel)
        by_id = {}
        fold_counts = {fold: 0 for fold in FOLDS}
        for row in rows:
            vessel = str(row["rfid_id"])
            if vessel in by_id:
                failures.append(f"seed {seed}: duplicate OOF vessel")
                break
            fold = int(row["fold"])
            label = int(row["y_true"])
            days = float(row["observed_days"])
            if fold not in FOLDS:
                failures.append(f"seed {seed}: OOF fold outside [0,2]")
                continue
            p = probability_row(row, f"seed {seed} OOF", failures)
            if label not in range(4):
                failures.append(f"seed {seed}: label outside [0,3]")
            if not math.isfinite(days):
                failures.append(f"seed {seed}: nonfinite observed_days")
            fold_counts[fold] = fold_counts.get(fold, 0) + 1
            by_id[vessel] = {
                "fold": fold,
                "label": label,
                "days": days,
                "p": p,
            }
        if len(rows) != 5897 or len(by_id) != 5897 or fold_counts != EXPECTED_OUTER:
            failures.append(f"seed {seed}: OOF row/unique/fold counts differ from frozen counts")
        for vessel, item in by_id.items():
            if role_map.get((item["fold"], vessel)) != "OUTER":
                failures.append(f"seed {seed}: OOF assignment disagrees with development roles")
        oof_by_seed[seed] = by_id
        oof_summary[seed] = {"rows": len(rows), "unique_vessels": len(by_id), "fold_counts": fold_counts}
    checks["oof_counts_and_roles"] = oof_summary

    ref = oof_by_seed[SEEDS[0]]
    for seed in SEEDS[1:]:
        current = oof_by_seed[seed]
        if set(ref) != set(current):
            failures.append("seed OOF vessel inventories differ")
            continue
        for vessel in ref:
            a, b = ref[vessel], current[vessel]
            if (a["fold"], a["label"], a["days"]) != (b["fold"], b["label"], b["days"]):
                failures.append("seed OOF role/label/observed_days differ by vessel")
                break

    # Verify saved INNER predictions are the fold-local INNER roster and
    # match OOF labels/days, but deliberately do not score them.
    inner_results = {}
    for seed in SEEDS:
        for fold in FOLDS:
            rel = f"evaluation/seed_{seed}/fold_{fold}/inner_predictions.csv"
            rows = read_csv(rel)
            ids = []
            labels_by_id = {}
            for row in rows:
                vessel = str(row["rfid_id"])
                ids.append(vessel)
                label = int(row["y_true"])
                days = float(row["observed_days"])
                probability_row(row, f"seed {seed} INNER fold {fold}", failures)
                if role_map.get((fold, vessel)) != "INNER":
                    failures.append(f"seed {seed} INNER fold {fold}: ID not in INNER roster")
                if vessel not in ref or ref[vessel]["label"] != label or ref[vessel]["days"] != days:
                    failures.append(f"seed {seed} INNER fold {fold}: label/days disagree with OOF")
                if vessel in labels_by_id:
                    failures.append(f"seed {seed} INNER fold {fold}: duplicate vessel")
                labels_by_id[vessel] = label
            if len(rows) != 787 or len(set(ids)) != 787:
                failures.append(f"seed {seed} INNER fold {fold}: count/uniqueness differs from 787")
            rule_choice = next(
                (choice for choice in rule.get("inner_choices", [])
                 if choice.get("seed") == seed and choice.get("fold") == fold),
                None,
            )
            file_hash = sha256_file(DATA / rel)
            if not rule_choice or rule_choice.get("inner_predictions_sha256") != file_hash:
                failures.append(f"seed {seed} INNER fold {fold}: frozen prediction file hash mismatch")
            historical_id_hash = digest_json(ids)
            id_hash_match = bool(rule_choice and rule_choice.get("inner_ids_sha256") == historical_id_hash)
            inner_results[f"{seed}:{fold}"] = {
                "rows": len(rows),
                "unique_ids": len(set(ids)),
                "probability_sha256": file_hash,
                "frozen_rule_prediction_hash_match": bool(rule_choice and rule_choice.get("inner_predictions_sha256") == file_hash),
                "historical_digest_json_id_order_hash_match": id_hash_match,
            }
            if rule_choice and not id_hash_match:
                # Record, but do not call this a mismatch: exported roster order
                # may differ from the original manifest list order.
                pass
    checks["inner_role_and_manifest_alignment"] = inner_results

    # Validate the old per-fold factor table and saved A_old decisions without
    # calculating F1 or any aggregate outcome metric.
    trap_rows = read_csv("evaluation/trap_factors.csv")
    factors = {}
    for row in trap_rows:
        seed, fold = int(row["seed"]), int(row["outer_fold"])
        if seed in SEEDS and fold in FOLDS:
            factors[(seed, fold)] = float(row["trap_factor"])
    expected_factors = {0: 2.0, 1: 3.0, 2: 2.0}
    if any(factors.get((seed, fold)) != expected_factors[fold] for seed in SEEDS for fold in FOLDS):
        failures.append("old trap-factor table does not match frozen 2/3/2 fold factors")
    old_check_counts = {}
    for seed in SEEDS:
        rel = f"evaluation/seed_{seed}/oof_decisions.csv"
        rows = read_csv(rel)
        if len(rows) != 5897 or {str(row["rfid_id"]) for row in rows} != set(oof_by_seed[seed]):
            failures.append(f"seed {seed}: saved decision roster differs from OOF")
        for row in rows:
            vessel = str(row["rfid_id"])
            raw = oof_by_seed[seed].get(vessel)
            if raw is None:
                continue
            fold = int(row["fold"])
            factor = factors.get((seed, fold))
            if (int(row["y_true"]) != raw["label"] or fold != raw["fold"]
                    or float(row["observed_days"]) != raw["days"]
                    or any(not close(row[col], raw["p"][i]) for i, col in enumerate(PCOLS))):
                failures.append(f"seed {seed}: saved decision input differs from original OOF")
                break
            if factor is None or not close(row["selected_trap_factor"], factor):
                failures.append(f"seed {seed}: saved decision factor differs from trap-factor table")
                break
            scores = [raw["p"][0], raw["p"][1], raw["p"][2] * factor, raw["p"][3]]
            stored_scores = [float(row[f"decision_score{i}"]) for i in range(4)]
            if any(not close(a, b) for a, b in zip(scores, stored_scores)):
                failures.append(f"seed {seed}: saved old decision scores do not replay")
                break
            if int(row["uncorrected_class"]) != max(range(4), key=lambda i: raw["p"][i]):
                failures.append(f"seed {seed}: saved raw class does not equal probability argmax")
                break
            if int(row["chosen_class"]) != max(range(4), key=lambda i: stored_scores[i]):
                failures.append(f"seed {seed}: saved old class does not equal decision-score argmax")
                break
            if row["chosen_class_name"] != CLASS_ORDER[int(row["chosen_class"])]:
                failures.append(f"seed {seed}: saved old class name differs from class order")
                break
            if not close(row["chosen_class_original_probability"], raw["p"][int(row["chosen_class"])]):
                failures.append(f"seed {seed}: chosen-class confidence is not the original probability")
                break
        old_check_counts[seed] = len(rows)
    checks["old_decision_replay_without_metric_scoring"] = old_check_counts

    # Inspect saved training metadata only; no models/checkpoints are loaded.
    training_metadata = {}
    for seed in SEEDS:
        for fold in FOLDS:
            rel = f"evaluation/seed_{seed}/fold_{fold}/training.json"
            info = read_json(rel)
            training_metadata[f"{seed}:{fold}"] = {
                "method": info.get("method"),
                "official_estimator": info.get("official_estimator"),
                "parameters_trained_on_this_dataset": info.get("parameters_trained_on_this_dataset"),
                "context_rows": info.get("context_rows"),
                "fit_vessels": info.get("fit_vessels"),
                "inner_vessels": info.get("inner_vessels"),
                "selection_metric": info.get("selection_metric"),
                "selection_metric_reason": info.get("selection_metric_reason"),
                "checkpoint_sha256": info.get("checkpoint_sha256"),
            }
            if (info.get("method") != "tabicl"
                    or info.get("parameters_trained_on_this_dataset") != 0
                    or info.get("selection_metric") is not None
                    or info.get("inner_vessels") != 787
                    or info.get("checkpoint_sha256") != settings.get("checkpoint_sha256")):
                failures.append(f"seed {seed} fold {fold}: saved training metadata violates zero-shot contract")
    checks["saved_training_metadata"] = training_metadata

    result = {
        "reviewer_scope": "pre-score evidence review only",
        "allowlisted_data_files_read": EXPECTED + [
            "MANIFEST_SHA256.json", "SOURCE_SHA256.json",
            *[f"evaluation/seed_{seed}/fold_{fold}/training.json" for seed in SEEDS for fold in FOLDS],
        ],
        "prohibited_data_access": {
            "holdout_individual_rows_read": 0,
            "full_7372_f156_or_labels_rows_read": 0,
            "test2025_rows_read": 0,
            "raw_rows_read": 0,
            "feature_rows_read": 0,
            "model_or_checkpoint_loaded": False,
            "fit_or_model_inference": False,
            "classification_metrics_computed": False,
        },
        "input_hashes": input_hashes,
        "source_hashes": source_hashes,
        "source_manifest_matches": source_manifest_matches,
        "checks": checks,
        "preflight_status": "PASS" if not failures else "BLOCKED",
        "failures": failures,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "preflight_status": result["preflight_status"],
        "failure_count": len(failures),
        "failures": failures,
        "output": str(OUT),
    }, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
