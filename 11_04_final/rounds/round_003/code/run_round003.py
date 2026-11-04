#!/usr/bin/env python
"""Round 003 R0: audit saved TabICLv2 probabilities and fold-local decisions.

This runner never reads raw feature tables, holdout rows, the 7,372-row F156
tables, or Test2025. It uses only the explicit development-probability and
metadata whitelist below. Default mode is preflight only. Scoring requires an
explicit manager-go token and a reviewer receipt bound to the exact source and
frozen configuration hashes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
ROUND = ROOT / "rounds" / "round_003"
CONFIG_PATH = ROUND / "configs" / "experiment.json"
PLAN_PATH = ROUND / "ROUND_PLAN.md"
INPUT_ROOT = Path(
    r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료"
)
SEEDS = (42, 2026)
FOLDS = (0, 1, 2)
LABELS = (0, 1, 2, 3)
CLASS_NAMES = ("연안복합", "자망", "통발", "채낚기연승낚시")
P_COLS = ("p0", "p1", "p2", "p3")
EXPECTED_N = 5897
EXPECTED_FOLD_COUNTS = {0: 1966, 1: 1966, 2: 1965}
EXPECTED_INNER = 787
EXPECTED_FIT = {0: 3144, 1: 3144, 2: 3145}
DAY_SCOPES = ("days_1_7", "days_8_30", "days_31_90", "days_91_plus", "days_zero", "days_unsupported")
METHODS = ("A_raw", "A_old", "A_micro_select")
PAIRS = (("A_old", "A_raw"), ("A_old", "A_micro_select"), ("A_raw", "A_micro_select"))
METRIC_TOLERANCE = 1e-12
PROBABILITY_SUM_TOLERANCE = 1e-12
PROBABILITY_BOUND_TOLERANCE = 1e-12
LOGLOSS_EPSILON = 1e-15
BOOTSTRAP_BATCH = 40


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def json_compact_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(json_bytes(value))
    temp_path.replace(path)


def to_builtin(value):
    if isinstance(value, dict):
        return {str(k): to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(v) for v in value]
    if isinstance(value, np.ndarray):
        return to_builtin(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def historical_digest_json(value: object) -> str:
    """Match the copied source helper's json.dumps(sort_keys=True, ensure_ascii=False)."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def rel_package(path: str) -> Path:
    return INPUT_ROOT / Path(path)


def allowed_package_paths() -> list[str]:
    paths = [
        "README_먼저읽기.md",
        "MANIFEST_SHA256.json",
        "SOURCE_SHA256.json",
        "evaluation/trap_factors.csv",
        "evaluation/final_fixed_decision_rule.json",
        "metadata/classes.json",
        "metadata/run_settings.json",
        "metadata/package_validation.json",
        "metadata/software_environment.json",
        "splits/development_roles_long.csv",
        "code/historical/TabM/TabM_개선_20261030/comparison_models.py",
        "code/historical/TabM/TabM_개선_20261030/run_experiments.py",
        "code/historical/TabM/TabM_개선_20261030/refinement_features.py",
        "code/historical/TabM/TabM_개선_20261030/finalize_comparisons.py",
        "code/historical/TabM/TabM_개선_20261030/apply_frozen_decision.py",
        "code/historical/TabM/TabM_개선_20261030/검증/audit_experiments.py",
        "code/historical/TinyTabM/TinyTabM_구현_20261029/fishing_tiny_tabm.py",
    ]
    for seed in SEEDS:
        base = f"evaluation/seed_{seed}"
        paths.extend((f"{base}/original_oof_predictions.csv", f"{base}/oof_decisions.csv"))
        for fold in FOLDS:
            paths.extend((
                f"{base}/fold_{fold}/inner_predictions.csv",
                f"{base}/fold_{fold}/training.json",
            ))
    return paths


SOURCE_MANIFEST_LINKS = {
    "code/historical/TabM/TabM_개선_20261030/comparison_models.py": r"TabM 총정리\TabM\TabM_개선_20261030\comparison_models.py",
    "code/historical/TabM/TabM_개선_20261030/run_experiments.py": r"TabM 총정리\TabM\TabM_개선_20261030\run_experiments.py",
    "code/historical/TabM/TabM_개선_20261030/refinement_features.py": r"TabM 총정리\TabM\TabM_개선_20261030\refinement_features.py",
    "code/historical/TabM/TabM_개선_20261030/finalize_comparisons.py": r"TabM 총정리\TabM\TabM_개선_20261030\finalize_comparisons.py",
    "code/historical/TabM/TabM_개선_20261030/apply_frozen_decision.py": r"TabM 총정리\TabM\TabM_개선_20261030\apply_frozen_decision.py",
    "code/historical/TabM/TabM_개선_20261030/검증/audit_experiments.py": r"TabM 총정리\TabM\TabM_개선_20261030\검증\audit_experiments.py",
    "code/historical/TinyTabM/TinyTabM_구현_20261029/fishing_tiny_tabm.py": r"TabM 총정리\TinyTabM\TinyTabM_구현_20261029\fishing_tiny_tabm.py",
}


def verify_frozen_config(config: dict) -> dict:
    if config.get("experiment") != "round_003_tabicl_saved_probability_decisions":
        raise ValueError("Unexpected experiment identity in frozen config")
    if config.get("frozen_before_scoring") is not True:
        raise ValueError("Configuration is not frozen before scoring")
    if tuple(config.get("seeds", ())) != SEEDS or tuple(config.get("folds", ())) != FOLDS:
        raise ValueError("Seed/fold inventory differs from frozen configuration")
    if tuple(config.get("class_labels", ())) != LABELS:
        raise ValueError("Class label order differs from the frozen configuration")
    if tuple(float(x) for x in config.get("grid", ())) != (1.0, 1.5, 2.0, 2.5, 3.0):
        raise ValueError("Multiplier grid differs from the frozen configuration")
    if tuple(float(x) for x in config.get("old_factors", ())) != (2.0, 3.0, 2.0):
        raise ValueError("Historical fold factors differ from the frozen configuration")
    if config.get("numeric_tolerance") != METRIC_TOLERANCE:
        raise ValueError("Numeric tolerance differs from the frozen configuration")
    if config.get("support_fallback") != "raw if any true class absent in full INNER or natural 1-7 day INNER":
        raise ValueError("Support fallback differs from the frozen configuration")
    bootstrap = config.get("bootstrap", {})
    if (bootstrap.get("method") != "percentile" or bootstrap.get("repetitions") != 5000
            or bootstrap.get("seed") != 20261105
            or bootstrap.get("unit") != "same vessel jointly across both seeds"):
        raise ValueError("Bootstrap settings differ from the frozen configuration")
    return config


def build_hash_manifest(config: dict) -> dict:
    if not INPUT_ROOT.is_dir():
        raise FileNotFoundError(f"Whitelisted saved-probability package missing: {INPUT_ROOT}")
    package_manifest_path = rel_package("MANIFEST_SHA256.json")
    source_manifest_path = rel_package("SOURCE_SHA256.json")
    package_manifest = read_json(package_manifest_path)
    upstream_manifest = read_json(source_manifest_path)
    files = {}
    for rel in allowed_package_paths():
        path = rel_package(rel)
        if not path.is_file():
            raise FileNotFoundError(f"Whitelisted input/source is missing: {path}")
        actual = sha256_file(path)
        expected = package_manifest.get(rel)
        if expected is not None and actual.lower() != str(expected).lower():
            raise ValueError(f"Package manifest SHA256 mismatch for {rel}")
        files[rel] = {"sha256": actual, "bytes": path.stat().st_size,
                      "manifest_sha256": expected,
                      "manifest_match": None if expected is None else actual.lower() == str(expected).lower(),
                      "manifest_note": "manifest file is not self-listed" if expected is None else None}
    upstream_code = {}
    for local_rel, source_rel in SOURCE_MANIFEST_LINKS.items():
        actual = files[local_rel]["sha256"]
        expected = upstream_manifest.get(source_rel)
        if expected is not None and actual.lower() != str(expected).lower():
            raise ValueError(f"Source manifest SHA256 mismatch for {local_rel}")
        upstream_code[local_rel] = {"source_manifest_key": source_rel, "sha256": actual,
                                     "source_manifest_sha256": expected,
                                     "source_manifest_match": expected is not None and actual.lower() == str(expected).lower()}
    local_files = {
        "runner": Path(__file__),
        "launcher": ROUND / "code" / "launch_round003.ps1",
        "configuration": CONFIG_PATH,
        "plan": PLAN_PATH,
    }
    local = {}
    for name, path in local_files.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required local source/config missing: {path}")
        local[name] = {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
    return {
        "created_at_utc": utc_now(),
        "round": "round_003",
        "scope": "saved development OOF and INNER probabilities, decision files, role roster, selected package metadata and copied source code only",
        "input_root": str(INPUT_ROOT),
        "local": local,
        "package_manifest_sha256": sha256_file(package_manifest_path),
        "source_manifest_sha256": sha256_file(source_manifest_path),
        "whitelisted_files": files,
        "upstream_source_code": upstream_code,
        "excluded_from_opening_or_hashing": [
            "data/F156_train.csv", "data/F156_test.csv", "data/train_labels.csv",
            "data/cv/*/F156_train.csv", "data/cv/*/F156_test.csv",
            "evaluation/holdout/*", "splits/holdout_ids.csv", "Test2025", "raw source tables",
        ],
        "feature_shape_ambiguity": {
            "status": "unresolved for M4",
            "readme_and_run_settings": "describe F156 and state no missing-flag columns",
            "copied_generation_code": "FitMedianImputer.transform appends one missing-indicator column per input column, which would double the width if applied to all 156 columns",
            "scope_limit": "R0 does not load feature rows or model tensors and cannot establish which exact transformed width was used by every saved query",
        },
        "config_sha256": local["configuration"]["sha256"],
        "plan_sha256": local["plan"]["sha256"],
        "config_frozen_before_scoring": bool(config.get("frozen_before_scoring")),
        "id_hash_serialization": {
            "historical_serializer": "json.dumps(sort_keys=True, ensure_ascii=False) from the copied helper",
            "csv_row_order_digest_is_only_diagnostic": True,
            "fixed_rule_id_hash_validation": "unverified because the original producer's ID list order is unavailable; do not treat a CSV-order digest difference as an ID mismatch",
            "primary_checks": "exact INNER file SHA256 against final_fixed_decision_rule plus ID uniqueness, role, y_true and observed_days alignment",
        },
    }


def read_csv_rows(path: Path, required_columns: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        if required_columns is not None and tuple(reader.fieldnames) != required_columns:
            raise ValueError(f"Unexpected CSV header for {path}: {reader.fieldnames}")
        rows = list(reader)
    return rows


def as_int(value: str, name: str) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer in {name}: {value!r}") from exc
    if not math.isfinite(numeric) or numeric != int(numeric):
        raise ValueError(f"Invalid integer in {name}: {value!r}")
    return int(numeric)


def as_float(value: str, name: str, allow_blank: bool = False) -> float:
    if allow_blank and (value is None or value.strip() == ""):
        return float("nan")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value in {name}: {value!r}") from exc
    return numeric


def load_roster_and_metadata() -> tuple[dict, dict, dict, dict]:
    class_meta = read_json(rel_package("metadata/classes.json"))
    expected_classes = {str(i): CLASS_NAMES[i] for i in LABELS}
    if class_meta != expected_classes:
        raise ValueError("Class label order/names disagree with metadata/classes.json")
    settings = read_json(rel_package("metadata/run_settings.json"))
    package_validation = read_json(rel_package("metadata/package_validation.json"))
    decision_rule = read_json(rel_package("evaluation/final_fixed_decision_rule.json"))
    roster_rows = read_csv_rows(rel_package("splits/development_roles_long.csv"),
                                ("rfid_id", "outer_fold", "role"))
    roster: dict[str, dict[int, str]] = defaultdict(dict)
    roster_counts: dict[str, Counter] = {str(f): Counter() for f in FOLDS}
    for row in roster_rows:
        vessel = row["rfid_id"]
        fold = as_int(row["outer_fold"], "outer_fold")
        role = row["role"]
        if fold not in FOLDS or role not in {"FIT", "INNER", "OUTER"}:
            raise ValueError(f"Invalid development role record: {row}")
        if fold in roster[vessel]:
            raise ValueError(f"Duplicate development role for vessel/fold: {vessel}/{fold}")
        roster[vessel][fold] = role
        roster_counts[str(fold)][role] += 1
    if len(roster) != EXPECTED_N or any(len(v) != 3 for v in roster.values()):
        raise ValueError("Development roster is not exactly 5,897 vessels across three folds")
    for fold in FOLDS:
        counts = roster_counts[str(fold)]
        if counts["INNER"] != EXPECTED_INNER or counts["OUTER"] != EXPECTED_FOLD_COUNTS[fold] or counts["FIT"] != EXPECTED_FIT[fold]:
            raise ValueError(f"Unexpected role counts for fold {fold}: {counts}")
    if settings.get("algorithm") != "TabICLv2" or settings.get("seeds") != list(SEEDS):
        raise ValueError("TabICL metadata identity/seeds are unexpected")
    if settings.get("checkpoint_sha256") != "bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0":
        raise ValueError("Checkpoint SHA in run_settings differs from NEXT_SESSION")
    if (package_validation.get("development") != EXPECTED_N
            or package_validation.get("features") != 156
            or package_validation.get("new_training") is not False
            or package_validation.get("new_model_queries") is not False):
        raise ValueError("Package validation metadata differs from expected development-only saved run")
    if decision_rule.get("class_order") != list(CLASS_NAMES):
        raise ValueError("Frozen decision rule class order differs")
    if decision_rule.get("outer_used_for_factor_choice") is not False:
        raise ValueError("Historical decision metadata does not rule out OUTER factor selection")
    training_meta = {}
    lineage_checks = []
    code_path = rel_package("code/historical/TabM/TabM_개선_20261030/comparison_models.py")
    code_text = code_path.read_text(encoding="utf-8-sig")
    required_code_fragments = (
        "model.fit(fit_x, fit_y)",
        "'parameters_trained_on_this_dataset': 0",
        "'selection_metric': None",
        "'fixed zero-shot in-context model; inner split unused'",
    )
    code_ok = all(fragment in code_text for fragment in required_code_fragments)
    if not code_ok:
        raise ValueError("Copied TabICL generation code no longer confirms FIT-only, fixed zero-shot lineage")
    for seed in SEEDS:
        for fold in FOLDS:
            key = f"{seed}/{fold}"
            path = rel_package(f"evaluation/seed_{seed}/fold_{fold}/training.json")
            training = read_json(path)
            expected_context = EXPECTED_FIT[fold]
            if (training.get("method") != "tabicl"
                    or training.get("parameters_trained_on_this_dataset") != 0
                    or training.get("selection_metric") is not None
                    or training.get("selection_metric_reason") != "fixed zero-shot in-context model; inner split unused"
                    or training.get("fit_vessels") != expected_context
                    or training.get("context_rows") != expected_context
                    or training.get("inner_vessels") != EXPECTED_INNER
                    or training.get("checkpoint_sha256") != settings.get("checkpoint_sha256")):
                raise ValueError(f"Saved training lineage metadata failed for seed/fold {key}")
            training_meta[key] = training
            lineage_checks.append({"seed": seed, "fold": fold, "fit_vessels": training["fit_vessels"],
                                   "inner_vessels": training["inner_vessels"], "trained_parameters": training["parameters_trained_on_this_dataset"],
                                   "selection_metric": training["selection_metric"], "inner_used_for_training_or_early_stopping": False})
    lineage = {
        "status": "confirmed_for_saved TabICLv2 generation based on archived source and six fold training records",
        "source_path": str(code_path),
        "source_sha256": sha256_file(code_path),
        "fit_estimator_tabicl_branch": "model.fit(fit_x, fit_y); INNER arguments are not passed to TabICL fit",
        "training_metadata": lineage_checks,
        "limitation": "This confirms the archived saved run's documented code/metadata lineage; no model re-fit or query replay is performed in R0.",
    }
    return roster, settings, decision_rule, {"package_validation": package_validation, "training_meta": training_meta, "lineage": lineage}


def validate_oof_inventory(roster: dict) -> dict:
    inventory = {}
    probability_checks = {}
    for seed in SEEDS:
        path = rel_package(f"evaluation/seed_{seed}/original_oof_predictions.csv")
        rows = read_csv_rows(path, ("rfid_id", "p0", "p1", "p2", "p3", "y_true", "observed_days", "fold"))
        ids = []
        by_id = {}
        fold_counts = Counter()
        max_probability_sum_error = 0.0
        for row in rows:
            vessel = row["rfid_id"]
            if not vessel or vessel in by_id:
                raise ValueError(f"Missing/duplicate OOF vessel in seed {seed}: {vessel!r}")
            y = as_int(row["y_true"], "y_true")
            fold = as_int(row["fold"], "fold")
            days = as_float(row["observed_days"], "observed_days", allow_blank=True)
            p = [as_float(row[c], f"OOF {c}") for c in P_COLS]
            if not all(math.isfinite(x) for x in p) or min(p) < -PROBABILITY_BOUND_TOLERANCE or max(p) > 1 + PROBABILITY_BOUND_TOLERANCE:
                raise ValueError(f"Invalid saved OOF probability in preflight for seed {seed}, vessel {vessel}")
            sum_error = abs(sum(p) - 1.0)
            max_probability_sum_error = max(max_probability_sum_error, sum_error)
            if sum_error > PROBABILITY_SUM_TOLERANCE:
                raise ValueError(f"Saved OOF probability row fails preflight sum tolerance {PROBABILITY_SUM_TOLERANCE}")
            if y not in LABELS or fold not in FOLDS:
                raise ValueError(f"Invalid OOF label/fold for seed {seed}, vessel {vessel}")
            if vessel not in roster or roster[vessel].get(fold) != "OUTER":
                raise ValueError(f"OOF vessel/fold is not OUTER in role roster: {seed}/{vessel}/{fold}")
            ids.append(vessel)
            by_id[vessel] = {"y": y, "days": days, "fold": fold}
            fold_counts[fold] += 1
        if len(rows) != EXPECTED_N or set(by_id) != set(roster):
            raise ValueError(f"OOF inventory differs from 5,897-vessel development roster for seed {seed}")
        if dict(fold_counts) != EXPECTED_FOLD_COUNTS:
            raise ValueError(f"Unexpected OOF fold counts for seed {seed}: {dict(fold_counts)}")
        inventory[seed] = {"ids": ids, "by_id": by_id, "fold_counts": dict(fold_counts)}
        probability_checks[str(seed)] = {"finite_and_in_range": True, "max_abs_sum_to_one": max_probability_sum_error,
                                         "sum_tolerance": PROBABILITY_SUM_TOLERANCE}
    ids42 = set(inventory[42]["by_id"])
    ids26 = set(inventory[2026]["by_id"])
    if ids42 != ids26:
        raise ValueError("Saved OOF seed vessel ID inventories differ")
    for vessel in ids42:
        left, right = inventory[42]["by_id"][vessel], inventory[2026]["by_id"][vessel]
        if left["y"] != right["y"] or left["fold"] != right["fold"]:
            raise ValueError(f"Saved OOF seed label/fold differs for vessel {vessel}")
        if not (math.isnan(left["days"]) and math.isnan(right["days"])) and left["days"] != right["days"]:
            raise ValueError(f"Saved OOF seed observed_days differs for vessel {vessel}")
    inventory["probability_checks"] = probability_checks
    return inventory


def load_inner_data(roster: dict, oof_inventory: dict, decision_rule: dict) -> dict:
    rule_choices = {(entry.get("seed"), entry.get("fold")): entry for entry in decision_rule.get("inner_choices", [])}
    if len(rule_choices) != 6 or set(rule_choices) != {(seed, fold) for seed in SEEDS for fold in FOLDS}:
        raise ValueError("Frozen rule lacks exactly six seed/fold INNER records")
    inner_all = {}
    hashes = {}
    for seed in SEEDS:
        for fold in FOLDS:
            rel = f"evaluation/seed_{seed}/fold_{fold}/inner_predictions.csv"
            path = rel_package(rel)
            file_hash = sha256_file(path)
            choice = rule_choices[(seed, fold)]
            if file_hash.lower() != str(choice.get("inner_predictions_sha256", "")).lower():
                raise ValueError(f"INNER probability file SHA differs from frozen decision rule: {seed}/{fold}")
            rows = read_csv_rows(path, ("rfid_id", "p0", "p1", "p2", "p3", "y_true", "observed_days"))
            ids, p_rows, ys, days_rows = [], [], [], []
            for row in rows:
                vessel = row["rfid_id"]
                y = as_int(row["y_true"], "INNER y_true")
                days = as_float(row["observed_days"], "INNER observed_days", allow_blank=True)
                if not vessel or vessel in ids or y not in LABELS:
                    raise ValueError(f"Invalid or duplicate INNER vessel/label: {seed}/{fold}/{vessel}")
                if vessel not in roster or roster[vessel].get(fold) != "INNER":
                    raise ValueError(f"INNER prediction vessel absent from INNER role: {seed}/{fold}/{vessel}")
                outer_record = oof_inventory[seed]["by_id"].get(vessel)
                if outer_record is None or outer_record["y"] != y or outer_record["fold"] == fold:
                    raise ValueError(f"INNER label/ID cannot be reconciled to development OOF roster: {seed}/{fold}/{vessel}")
                if not (math.isnan(days) and math.isnan(outer_record["days"])) and days != outer_record["days"]:
                    raise ValueError(f"INNER observed_days differs from development roster OOF record: {seed}/{fold}/{vessel}")
                p = [as_float(row[c], f"INNER {c}") for c in P_COLS]
                if not all(math.isfinite(x) for x in p) or min(p) < -PROBABILITY_BOUND_TOLERANCE or max(p) > 1 + PROBABILITY_BOUND_TOLERANCE:
                    raise ValueError(f"Invalid saved INNER probability for {seed}/{fold}/{vessel}")
                if abs(sum(p) - 1.0) > PROBABILITY_SUM_TOLERANCE:
                    raise ValueError(f"Saved INNER probability row does not sum to one within {PROBABILITY_SUM_TOLERANCE}")
                ids.append(vessel); p_rows.append(p); ys.append(y); days_rows.append(days)
            if len(ids) != EXPECTED_INNER or len(set(ids)) != EXPECTED_INNER:
                raise ValueError(f"INNER inventory is not exactly {EXPECTED_INNER}: {seed}/{fold}")
            computed_id_hash = historical_digest_json(ids)
            fixed_rule_id_hash = str(choice.get("inner_ids_sha256", ""))
            inner_all[(seed, fold)] = {
                "ids": ids, "p": np.asarray(p_rows, dtype=np.float64), "y": np.asarray(ys, dtype=np.int64),
                "days": np.asarray(days_rows, dtype=np.float64), "fold": np.full(len(ids), fold, dtype=np.int64),
            }
            hashes[f"{seed}/{fold}"] = {
                "inner_predictions_sha256": file_hash,
                "fixed_rule_inner_predictions_sha256": choice.get("inner_predictions_sha256"),
                "inner_predictions_hash_matches_fixed_rule": True,
                "historical_serializer_csv_row_order_digest": computed_id_hash,
                "fixed_rule_inner_ids_sha256": fixed_rule_id_hash,
                "historical_id_hash_matches_csv_row_order": computed_id_hash.lower() == fixed_rule_id_hash.lower(),
                "id_hash_status": "unverified_original_list_order_unavailable; CSV-order digest is diagnostic only",
            }
    # Verify old factor table independently of stored decisions.
    factor_rows = read_csv_rows(rel_package("evaluation/trap_factors.csv"), ("seed", "outer_fold", "trap_factor", "selection_scope"))
    factors = {}
    for row in factor_rows:
        seed, fold = as_int(row["seed"], "trap_factors.seed"), as_int(row["outer_fold"], "trap_factors.outer_fold")
        factor = as_float(row["trap_factor"], "trap_factors.trap_factor")
        if seed not in SEEDS or fold not in FOLDS or row["selection_scope"] != "INNER only" or (seed, fold) in factors:
            raise ValueError(f"Invalid historical factor record: {row}")
        factors[(seed, fold)] = factor
    expected_factors = {(seed, fold): (2.0, 3.0, 2.0)[fold] for seed in SEEDS for fold in FOLDS}
    if factors != expected_factors:
        raise ValueError("Historical trap factor table differs from frozen old 2/3/2 comparison")
    return {"inner": inner_all, "old_factors": factors, "inner_hashes": hashes}


def confusion_matrix(y: np.ndarray, pred: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    if not len(y):
        return np.zeros((4, 4), dtype=np.float64)
    codes = y.astype(np.int64, copy=False) * 4 + pred.astype(np.int64, copy=False)
    if weights is None:
        return np.bincount(codes, minlength=16).reshape(4, 4).astype(np.float64)
    return np.bincount(codes, weights=weights, minlength=16).reshape(4, 4).astype(np.float64)


def metrics_from_cm(cm: np.ndarray) -> dict:
    support = cm.sum(axis=1)
    predicted = cm.sum(axis=0)
    tp = np.diag(cm)
    precision = np.divide(tp, predicted, out=np.zeros(4, dtype=np.float64), where=predicted > 0)
    recall = np.divide(tp, support, out=np.zeros(4, dtype=np.float64), where=support > 0)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros(4, dtype=np.float64), where=denom > 0)
    total = float(cm.sum())
    result = {
        "n_weighted": total,
        "correct_weighted": float(tp.sum()),
        "micro_f1": float(tp.sum() / total) if total else None,
        "macro_f1": float(f1.mean()) if total else None,
        "weighted_f1": float(np.dot(f1, support) / total) if total else None,
        "class_precision": precision.tolist() if total else [None] * 4,
        "class_recall": recall.tolist() if total else [None] * 4,
        "class_f1": f1.tolist() if total else [None] * 4,
        "class_support": support.tolist(),
        "confusion_matrix": cm.tolist(),
    }
    return result


def prediction_for(p: np.ndarray, factor: float) -> np.ndarray:
    scores = p.copy()
    scores[:, 2] *= factor
    return scores.argmax(axis=1)


def choose_inner_policies(inner: dict, config: dict) -> dict:
    grid = [float(v) for v in config["grid"]]
    tolerance = float(config["numeric_tolerance"])
    result = {
        "schema_version": 1,
        "policy": "A_micro_select",
        "selection_source": "same seed/fold full INNER only; no pooling across folds; no OUTER score used",
        "probabilities_changed": False,
        "class_order": list(CLASS_NAMES),
        "grid": grid,
        "eligibility": {
            "macro_f1_drop_max": 0.0,
            "per_class_f1_drop_max": 0.01,
            "natural_1_7_day_macro_f1_drop_max": 0.01,
            "support_fallback": config["support_fallback"],
            "zero_division": 0,
            "numeric_tolerance": tolerance,
        },
        "tie_break": "highest micro_f1; within tolerance choose factor closest to 1, then smaller factor",
        "choices": [],
        "created_at_utc": utc_now(),
    }
    for seed in SEEDS:
        for fold in FOLDS:
            data = inner[(seed, fold)]
            p, y, days = data["p"], data["y"], data["days"]
            raw_pred = p.argmax(axis=1)
            day_mask = np.isfinite(days) & (days >= 1) & (days <= 7)
            raw_cm = confusion_matrix(y, raw_pred)
            raw_metrics = metrics_from_cm(raw_cm)
            raw_day_metrics = metrics_from_cm(confusion_matrix(y[day_mask], raw_pred[day_mask]))
            support_full = np.bincount(y, minlength=4)
            support_short = np.bincount(y[day_mask], minlength=4)
            unsupported_full = np.flatnonzero(support_full == 0).tolist()
            unsupported_short = np.flatnonzero(support_short == 0).tolist()
            candidates = []
            for factor in grid:
                pred = prediction_for(p, factor)
                metrics = metrics_from_cm(confusion_matrix(y, pred))
                short_metrics = metrics_from_cm(confusion_matrix(y[day_mask], pred[day_mask]))
                eligible = (
                    metrics["macro_f1"] + tolerance >= raw_metrics["macro_f1"]
                    and all(metrics["class_f1"][c] + tolerance >= raw_metrics["class_f1"][c] - 0.01 for c in LABELS)
                    and short_metrics["macro_f1"] is not None
                    and raw_day_metrics["macro_f1"] is not None
                    and short_metrics["macro_f1"] + tolerance >= raw_day_metrics["macro_f1"] - 0.01
                )
                candidates.append({"factor": factor, "eligible": bool(eligible),
                                   "micro_f1": metrics["micro_f1"], "macro_f1": metrics["macro_f1"],
                                   "class_f1": metrics["class_f1"], "days_1_7_macro_f1": short_metrics["macro_f1"],
                                   "correct": metrics["correct_weighted"], "n": metrics["n_weighted"]})
            support_fallback = bool(unsupported_full or unsupported_short)
            if support_fallback:
                selected = 1.0
                reason = "raw fallback: at least one true class has zero support in full INNER or natural 1-7 day INNER"
            else:
                eligible_candidates = [c for c in candidates if c["eligible"]]
                if not eligible_candidates:
                    # A_raw is specified as the always-available default; protect against numerical edge cases.
                    selected = 1.0
                    reason = "raw fallback: no candidate remained eligible; A_raw retained as default"
                else:
                    top_micro = max(float(c["micro_f1"]) for c in eligible_candidates)
                    tied = [c for c in eligible_candidates if float(c["micro_f1"]) >= top_micro - tolerance]
                    best = min(tied, key=lambda c: (abs(float(c["factor"]) - 1.0), float(c["factor"])))
                    selected = float(best["factor"])
                    reason = "highest eligible INNER micro_f1 with frozen tie break"
            result["choices"].append({
                "seed": seed, "fold": fold, "selected_factor": selected, "reason": reason,
                "support_fallback": support_fallback,
                "support_full_inner": support_full.tolist(), "support_natural_1_7_inner": support_short.tolist(),
                "unsupported_classes_full_inner": unsupported_full,
                "unsupported_classes_natural_1_7_inner": unsupported_short,
                "inner_ids_sha256_csv_row_order_diagnostic": historical_digest_json(data["ids"]),
                "raw_inner_metrics": raw_metrics,
                "raw_inner_days_1_7_metrics": raw_day_metrics,
                "candidate_grid": candidates,
            })
    if len(result["choices"]) != 6:
        raise AssertionError("Expected six frozen seed/fold choices")
    return result


def create_policy_artifact(config: dict, hash_manifest: dict, inner_inputs: dict) -> tuple[dict, str]:
    policy = choose_inner_policies(inner_inputs["inner"], config)
    policy["plan_sha256"] = hash_manifest["plan_sha256"]
    policy["config_sha256"] = hash_manifest["config_sha256"]
    policy["input_hashes"] = {
        "inner_files": inner_inputs["inner_hashes"],
        "trap_factors_sha256": hash_manifest["whitelisted_files"]["evaluation/trap_factors.csv"]["sha256"],
        "decision_rule_sha256": hash_manifest["whitelisted_files"]["evaluation/final_fixed_decision_rule.json"]["sha256"],
    }
    payload = json_compact_bytes(policy)
    policy_sha = sha256_bytes(payload)
    policy["policy_sha256_before_hash_field"] = policy_sha
    path = ROUND / "artifacts" / "decision_policy_frozen.json"
    write_json(path, policy)
    reread = read_json(path)
    saved_hash = reread.pop("policy_sha256_before_hash_field", None)
    if saved_hash != sha256_bytes(json_compact_bytes(reread)):
        raise ValueError("Frozen decision policy JSON hash did not reproduce after serialization")
    return policy, saved_hash


def load_oof_for_scoring(seed: int, roster: dict, inventory: dict, old_factors: dict) -> dict:
    original_path = rel_package(f"evaluation/seed_{seed}/original_oof_predictions.csv")
    decision_path = rel_package(f"evaluation/seed_{seed}/oof_decisions.csv")
    rows = read_csv_rows(original_path, ("rfid_id", "p0", "p1", "p2", "p3", "y_true", "observed_days", "fold"))
    if len(rows) != EXPECTED_N:
        raise ValueError(f"OOF row count changed after preflight for seed {seed}")
    data_by_id = {}
    for row in rows:
        vessel = row["rfid_id"]
        if vessel in data_by_id:
            raise ValueError(f"Duplicate OOF ID after frozen policy for seed {seed}: {vessel}")
        y = as_int(row["y_true"], "OOF y_true")
        days = as_float(row["observed_days"], "OOF observed_days", allow_blank=True)
        fold = as_int(row["fold"], "OOF fold")
        if inventory[seed]["by_id"].get(vessel) != {"y": y, "days": days, "fold": fold}:
            # NaN equality needs special treatment.
            expected = inventory[seed]["by_id"].get(vessel)
            if expected is None or expected["y"] != y or expected["fold"] != fold or not ((math.isnan(expected["days"]) and math.isnan(days)) or expected["days"] == days):
                raise ValueError(f"OOF metadata changed after preflight for seed {seed}, vessel {vessel}")
        if roster.get(vessel, {}).get(fold) != "OUTER":
            raise ValueError(f"OOF role changed for seed {seed}, vessel {vessel}")
        p = np.asarray([as_float(row[c], f"OOF {c}") for c in P_COLS], dtype=np.float64)
        if not np.isfinite(p).all() or p.min() < -PROBABILITY_BOUND_TOLERANCE or p.max() > 1 + PROBABILITY_BOUND_TOLERANCE:
            raise ValueError(f"Invalid saved OOF probability for {seed}/{vessel}")
        if abs(float(p.sum()) - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise ValueError(f"Saved OOF probability row fails sum tolerance {PROBABILITY_SUM_TOLERANCE}")
        data_by_id[vessel] = {"p": p, "y": y, "days": days, "fold": fold}
    ordered_ids = sorted(data_by_id)
    if set(ordered_ids) != set(roster):
        raise ValueError(f"OOF vessel IDs differ from roster after policy freeze for seed {seed}")
    p = np.stack([data_by_id[v]["p"] for v in ordered_ids])
    y = np.asarray([data_by_id[v]["y"] for v in ordered_ids], dtype=np.int64)
    days = np.asarray([data_by_id[v]["days"] for v in ordered_ids], dtype=np.float64)
    fold = np.asarray([data_by_id[v]["fold"] for v in ordered_ids], dtype=np.int64)
    raw = p.argmax(axis=1)
    old_factor = np.asarray([old_factors[(seed, int(f))] for f in fold], dtype=np.float64)
    old = np.empty(len(y), dtype=np.int64)
    for factor in sorted(set(old_factor)):
        mask = old_factor == factor
        old[mask] = prediction_for(p[mask], float(factor))
    decisions = read_csv_rows(decision_path,
        ("rfid_id", "y_true", "p0", "p1", "p2", "p3", "observed_days", "fold", "selected_trap_factor",
         "uncorrected_class", "chosen_class", "chosen_class_name", "chosen_class_original_probability",
         "uncorrected_class_original_probability", "decision_score0", "decision_score1", "decision_score2", "decision_score3"))
    decision_map = {}
    for row in decisions:
        vessel = row["rfid_id"]
        if vessel in decision_map:
            raise ValueError(f"Duplicate saved old decision for seed {seed}: {vessel}")
        decision_map[vessel] = row
    if set(decision_map) != set(ordered_ids) or len(decisions) != EXPECTED_N:
        raise ValueError(f"Saved decision OOF inventory differs from probabilities for seed {seed}")
    for i, vessel in enumerate(ordered_ids):
        row = decision_map[vessel]
        if as_int(row["y_true"], "decision y_true") != int(y[i]) or as_int(row["fold"], "decision fold") != int(fold[i]):
            raise ValueError(f"Saved decision label/fold mismatch for seed {seed}, vessel {vessel}")
        saved_days = as_float(row["observed_days"], "decision observed_days", allow_blank=True)
        if not ((math.isnan(saved_days) and math.isnan(days[i])) or saved_days == days[i]):
            raise ValueError(f"Saved decision observed_days mismatch for seed {seed}, vessel {vessel}")
        stored_p = np.asarray([as_float(row[c], f"decision {c}") for c in P_COLS], dtype=np.float64)
        if np.max(np.abs(stored_p - p[i])) > METRIC_TOLERANCE:
            raise ValueError(f"Saved decision probability values differ from original OOF for seed {seed}, vessel {vessel}")
        if as_float(row["selected_trap_factor"], "selected_trap_factor") != old_factor[i]:
            raise ValueError(f"Saved decision old factor mismatch for seed {seed}, vessel {vessel}")
        if as_int(row["uncorrected_class"], "uncorrected_class") != int(raw[i]):
            raise ValueError(f"Saved raw argmax mismatch for seed {seed}, vessel {vessel}")
        if as_int(row["chosen_class"], "chosen_class") != int(old[i]):
            raise ValueError(f"Saved old selected class mismatch for seed {seed}, vessel {vessel}")
        if row["chosen_class_name"] != CLASS_NAMES[int(old[i])]:
            raise ValueError(f"Saved old selected class name mismatch for seed {seed}, vessel {vessel}")
        conf = as_float(row["chosen_class_original_probability"], "chosen_class_original_probability")
        raw_conf = as_float(row["uncorrected_class_original_probability"], "uncorrected_class_original_probability")
        if abs(conf - float(p[i, old[i]])) > METRIC_TOLERANCE or abs(raw_conf - float(p[i, raw[i]])) > METRIC_TOLERANCE:
            raise ValueError(f"Saved original-probability confidence field mismatch for seed {seed}, vessel {vessel}")
        saved_scores = np.asarray([as_float(row[f"decision_score{j}"], f"decision_score{j}") for j in LABELS], dtype=np.float64)
        scaled_scores = p[i].copy()
        scaled_scores[2] *= old_factor[i]
        normalized_scaled_scores = scaled_scores / scaled_scores.sum()
        if np.max(np.abs(saved_scores - normalized_scaled_scores)) > METRIC_TOLERANCE:
            raise ValueError(f"Saved decision_score values do not match normalized p2-scaled scores for seed {seed}, vessel {vessel}")
    return {"ids": ordered_ids, "p": p, "y": y, "days": days, "fold": fold,
            "raw": raw, "old": old, "old_factor": old_factor, "saved_decision_rows": decision_map,
            "decision_score_representation": {
                "saved_csv": "decision_score columns equal the p2-multiplied scores normalized to sum to one",
                "copied_helper": "apply_frozen_decision.py scores_for returns unnormalized p with p2 multiplied",
                "prediction_invariant": "normalization is by a positive row constant; argmax and chosen class are unchanged",
                "probability_interpretation": "neither scaled representation is a calibrated probability; original p0-p3 remain the probability inputs",
            }}


def policy_factor_map(policy: dict) -> dict:
    mapping = {(int(c["seed"]), int(c["fold"])): float(c["selected_factor"]) for c in policy["choices"]}
    if set(mapping) != {(seed, fold) for seed in SEEDS for fold in FOLDS}:
        raise ValueError("Frozen policy does not contain exactly six seed/fold choices")
    return mapping


def day_group_masks(days: np.ndarray, fold: np.ndarray) -> dict[str, np.ndarray]:
    finite = np.isfinite(days)
    integer = finite & (days == np.floor(days))
    groups = {
        "all": np.ones(len(days), dtype=bool),
        **{f"fold_{f}": fold == f for f in FOLDS},
        "days_1_7": integer & (days >= 1) & (days <= 7),
        "days_8_30": integer & (days >= 8) & (days <= 30),
        "days_31_90": integer & (days >= 31) & (days <= 90),
        "days_91_plus": integer & (days >= 91),
        "days_zero": integer & (days == 0),
        "days_unsupported": ~(integer & (days >= 0)),
    }
    return groups


def probability_quality(p: np.ndarray, y: np.ndarray, pred: np.ndarray, mask: np.ndarray) -> dict:
    if not mask.any():
        return {"n": 0, "logloss": None, "multiclass_brier_sum_squared_mean": None,
                "ece_10_equal_width": None, "high_confidence_raw_max_ge_0_9_errors": 0,
                "ece_bins": []}
    pp, yy, pr = p[mask], y[mask], pred[mask]
    selected = np.clip(pp[np.arange(len(yy)), yy], LOGLOSS_EPSILON, 1.0)
    onehot = np.eye(4, dtype=np.float64)[yy]
    confidence = pp.max(axis=1)
    raw_correct = pr == yy
    edges = np.linspace(0.0, 1.0, 11)
    bin_index = np.minimum(np.floor(confidence * 10).astype(int), 9)
    bins = []
    ece = 0.0
    for b in range(10):
        active = bin_index == b
        count = int(active.sum())
        if count:
            acc = float(raw_correct[active].mean())
            conf = float(confidence[active].mean())
            ece += count / len(yy) * abs(acc - conf)
        else:
            acc, conf = None, None
        bins.append({"bin": b, "left": float(edges[b]), "right": float(edges[b + 1]),
                     "right_inclusive": b == 9, "count": count,
                     "mean_confidence": conf, "accuracy": acc})
    return {
        "n": int(len(yy)),
        "logloss": float(-np.log(selected).mean()),
        "multiclass_brier_sum_squared_mean": float(np.square(pp - onehot).sum(axis=1).mean()),
        "brier_convention": "mean per-vessel sum over four class squared errors (not divided by 4)",
        "ece_10_equal_width": float(ece),
        "high_confidence_raw_max_ge_0_9_errors": int(((confidence >= 0.9) & (~raw_correct)).sum()),
        "ece_bins": bins,
    }


def make_point_metrics(data: dict, policy_factors: dict) -> tuple[dict, dict, dict]:
    points = {}
    arrays = {}
    qualities = {}
    for seed in SEEDS:
        d = data[seed]
        selected_factor = np.asarray([policy_factors[(seed, int(f))] for f in d["fold"]], dtype=np.float64)
        selected = np.empty(len(d["y"]), dtype=np.int64)
        for factor in sorted(set(selected_factor)):
            mask_factor = selected_factor == factor
            selected[mask_factor] = prediction_for(d["p"][mask_factor], float(factor))
        pred_map = {"A_raw": d["raw"], "A_old": d["old"], "A_micro_select": selected}
        arrays[seed] = {"p": d["p"], "y": d["y"], "days": d["days"], "fold": d["fold"],
                        "ids": d["ids"], "pred": pred_map, "selected_factor": selected_factor,
                        "old_factor": d["old_factor"]}
        groups = day_group_masks(d["days"], d["fold"])
        points[str(seed)] = {}
        qualities[str(seed)] = {}
        for group_name, mask in groups.items():
            points[str(seed)][group_name] = {}
            qualities[str(seed)][group_name] = probability_quality(d["p"], d["y"], d["raw"], mask)
            for method, pred in pred_map.items():
                cm = confusion_matrix(d["y"][mask], pred[mask])
                metrics = metrics_from_cm(cm)
                if mask.any():
                    metrics["mean_assigned_class_original_probability"] = float(d["p"][mask, pred[mask]].mean())
                else:
                    metrics["mean_assigned_class_original_probability"] = None
                points[str(seed)][group_name][method] = metrics
    # The arithmetic mean across seeds is calculated over metrics, never over probabilities or predictions.
    averaged = {}
    for group in points["42"]:
        averaged[group] = {}
        for method in METHODS:
            left, right = points["42"][group][method], points["2026"][group][method]
            record = {"vessels_per_seed": left["n_weighted"], "not_summed_across_seeds": True}
            for key in ("micro_f1", "macro_f1", "weighted_f1", "mean_assigned_class_original_probability"):
                record[key] = None if left[key] is None or right[key] is None else (left[key] + right[key]) / 2.0
            for key in ("class_precision", "class_recall", "class_f1"):
                record[key] = [None if left[key][i] is None or right[key][i] is None else (left[key][i] + right[key][i]) / 2.0 for i in LABELS]
            averaged[group][method] = record
    return {"by_seed": points, "arithmetic_mean_across_seeds": averaged}, arrays, qualities


def compare_transitions(arrays: dict) -> dict:
    out = {}
    for a, b in PAIRS:
        per_seed = {}
        for seed in SEEDS:
            d = arrays[seed]
            pa, pb = d["pred"][a], d["pred"][b]
            ya = d["y"]
            ca, cb = pa == ya, pb == ya
            gain = int((~ca & cb).sum())
            loss = int((ca & ~cb).sum())
            confusion = np.zeros((4, 4), dtype=np.int64)
            np.add.at(confusion, (pa, pb), 1)
            specific = {}
            for left, right, label in ((0, 1, "coastal_vs_gillnet"), (0, 2, "coastal_vs_trap"), (1, 2, "gillnet_vs_trap")):
                specific[label] = {
                    f"{CLASS_NAMES[left]}_to_{CLASS_NAMES[right]}": int(((pa == left) & (pb == right)).sum()),
                    f"{CLASS_NAMES[right]}_to_{CLASS_NAMES[left]}": int(((pa == right) & (pb == left)).sum()),
                }
            per_seed[str(seed)] = {
                "source_method": a, "target_method": b,
                "source_correct_target_correct": int((ca & cb).sum()),
                "gain_new_correct": gain, "loss_new_wrong": loss, "net_correct": gain - loss,
                "prediction_transition_matrix_source_rows_target_columns": confusion.tolist(),
                "bidirectional_prediction_changes": specific,
            }
        out[f"{a}_to_{b}"] = {"by_seed": per_seed,
            "arithmetic_mean_gain": sum(per_seed[str(s)]["gain_new_correct"] for s in SEEDS) / 2.0,
            "arithmetic_mean_loss": sum(per_seed[str(s)]["loss_new_wrong"] for s in SEEDS) / 2.0,
            "arithmetic_mean_net": sum(per_seed[str(s)]["net_correct"] for s in SEEDS) / 2.0,
            "note": "Mean counts are per-seed averages; the same 5,897 vessel IDs are not counted as 11,794 distinct vessels."}
    return out


BOOT_METRICS = ("micro_f1", "macro_f1", "weighted_f1") + tuple(
    f"class_{metric}_{label}" for metric in ("precision", "recall", "f1") for label in range(4)
)


def metric_vector_from_cm(cm: np.ndarray) -> np.ndarray:
    m = metrics_from_cm(cm)
    values = [m["micro_f1"], m["macro_f1"], m["weighted_f1"]]
    for metric in ("class_precision", "class_recall", "class_f1"):
        values.extend(m[metric])
    return np.asarray([np.nan if x is None else x for x in values], dtype=np.float64)


def bootstrap_differences(arrays: dict, config: dict) -> dict:
    n = EXPECTED_N
    reps = int(config["bootstrap"]["repetitions"])
    seed_value = int(config["bootstrap"]["seed"])
    rng = np.random.default_rng(seed_value)
    scopes = day_group_masks(arrays[42]["days"], arrays[42]["fold"])
    code = {s: {m: arrays[s]["y"] * 4 + arrays[s]["pred"][m] for m in METHODS} for s in SEEDS}
    dists = {}
    for a, b in PAIRS:
        dists[f"{a}_to_{b}"] = {
            scope: {metric: np.full((reps, 2), np.nan, dtype=np.float64) for metric in BOOT_METRICS}
            for scope in scopes
        }
    for start in range(0, reps, BOOTSTRAP_BATCH):
        stop = min(start + BOOTSTRAP_BATCH, reps)
        draws = rng.integers(0, n, size=(stop - start, n), endpoint=False)
        frequencies = np.zeros((stop - start, n), dtype=np.int32)
        for r, sample in enumerate(draws):
            frequencies[r] = np.bincount(sample, minlength=n)
        for r in range(stop - start):
            weights_full = frequencies[r]
            for scope, scope_mask in scopes.items():
                idx = np.flatnonzero(scope_mask)
                if not len(idx):
                    continue
                w = weights_full[idx]
                values = {}
                for s in SEEDS:
                    values[s] = {}
                    for method in METHODS:
                        cm = np.bincount(code[s][method][idx], weights=w, minlength=16).reshape(4, 4)
                        values[s][method] = metric_vector_from_cm(cm)
                replicate = start + r
                for a, b in PAIRS:
                    contrast = f"{a}_to_{b}"
                    for si, s in enumerate(SEEDS):
                        diff = values[s][b] - values[s][a]
                        for mi, metric in enumerate(BOOT_METRICS):
                            dists[contrast][scope][metric][replicate, si] = diff[mi]
    result = {
        "method": "paired percentile vessel bootstrap",
        "unit": "same sorted rfid_id index drawn once per replicate and applied to both seeds",
        "repetitions": reps,
        "seed": seed_value,
        "percentiles": [2.5, 97.5],
        "seed_mean_definition": "metric difference is computed per seed and then averaged across the two seeds in each replicate",
        "includes": list(BOOT_METRICS),
        "by_comparison": {},
        "limitations": ["Previously exposed development OUTER; interval does not remove repeated-development selection bias or geographic dependence."],
    }
    raw_draws_path = ROUND / "artifacts" / "paired_bootstrap_draws.npz"
    draw_arrays = {
        f"{comparison}__{scope}__{metric}": values
        for comparison, scopes_dist in dists.items()
        for scope, metrics in scopes_dist.items()
        for metric, values in metrics.items()
    }
    np.savez_compressed(raw_draws_path, **draw_arrays)
    result["raw_numeric_draws_artifact"] = {
        "path": str(raw_draws_path), "sha256": sha256_file(raw_draws_path),
        "keys": len(draw_arrays), "shape_per_key": [reps, len(SEEDS)],
        "columns": [str(seed) for seed in SEEDS],
        "note": "Each numeric cell is the paired metric delta (target minus source) for that bootstrap replicate and seed; source/target pairs share the same resampled vessel IDs.",
    }
    for comparison, scopes_dist in dists.items():
        result["by_comparison"][comparison] = {}
        for scope, metrics in scopes_dist.items():
            result["by_comparison"][comparison][scope] = {}
            for metric, values in metrics.items():
                by_seed = {}
                for si, seed in enumerate(SEEDS):
                    vals = values[:, si]
                    vals = vals[np.isfinite(vals)]
                    by_seed[str(seed)] = {"bootstrap_mean": float(vals.mean()) if len(vals) else None,
                                          "ci95_percentile": [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if len(vals) else None}
                valid_rows = np.isfinite(values).any(axis=1)
                paired_mean_all = np.full(reps, np.nan, dtype=np.float64)
                paired_mean_all[valid_rows] = np.nanmean(values[valid_rows], axis=1)
                paired_mean = paired_mean_all[np.isfinite(paired_mean_all)]
                point_delta = None
                if scopes[scope].any():
                    # Point delta is recomputed from the same per-seed estimates used in the report.
                    point_deltas = []
                    source_method, target_method = comparison.split("_to_")
                    for seed in SEEDS:
                        d = arrays[seed]
                        mask = scopes[scope]
                        c_a = confusion_matrix(d["y"][mask], d["pred"][source_method][mask])
                        c_b = confusion_matrix(d["y"][mask], d["pred"][target_method][mask])
                        va, vb = metric_vector_from_cm(c_a), metric_vector_from_cm(c_b)
                        point_deltas.append(vb[BOOT_METRICS.index(metric)] - va[BOOT_METRICS.index(metric)])
                    point_delta = float(np.mean(point_deltas))
                result["by_comparison"][comparison][scope][metric] = {
                    "point_delta_mean_across_seeds": point_delta,
                    "bootstrap_mean_delta_mean_across_seeds": float(paired_mean.mean()) if len(paired_mean) else None,
                    "ci95_percentile_mean_across_seeds": [float(np.percentile(paired_mean, 2.5)), float(np.percentile(paired_mean, 97.5))] if len(paired_mean) else None,
                    "by_seed": by_seed,
                }
    return result


def save_predictions(arrays: dict) -> dict:
    path = ROUND / "artifacts" / "predictions.csv"
    fields = ("seed", "rfid_id", "fold", "observed_days", "y_true", "p0", "p1", "p2", "p3",
              "old_factor", "selected_factor", "A_raw", "A_old", "A_micro_select",
              "raw_confidence", "old_assigned_original_probability", "selected_assigned_original_probability")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".csv.tmp")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for seed in SEEDS:
            d = arrays[seed]
            for i, vessel in enumerate(d["ids"]):
                row = {"seed": seed, "rfid_id": vessel, "fold": int(d["fold"][i]),
                       "observed_days": "" if not math.isfinite(float(d["days"][i])) else float(d["days"][i]),
                       "y_true": int(d["y"][i]), "old_factor": float(d["old_factor"][i]),
                       "selected_factor": float(d["selected_factor"][i]),
                       "A_raw": int(d["pred"]["A_raw"][i]), "A_old": int(d["pred"]["A_old"][i]),
                       "A_micro_select": int(d["pred"]["A_micro_select"][i]),
                       "raw_confidence": float(d["p"][i].max()),
                       "old_assigned_original_probability": float(d["p"][i, d["pred"]["A_old"][i]]),
                       "selected_assigned_original_probability": float(d["p"][i, d["pred"]["A_micro_select"][i]])}
                row.update({f"p{j}": float(d["p"][i, j]) for j in LABELS})
                writer.writerow(row)
    temp_path.replace(path)
    return {"path": str(path), "sha256": sha256_file(path), "rows": EXPECTED_N * len(SEEDS),
            "unique_vessels_per_seed": EXPECTED_N}


def preflight(config: dict, hash_manifest: dict) -> tuple[dict, dict, dict, dict, dict]:
    roster, settings, decision_rule, meta = load_roster_and_metadata()
    inventory = validate_oof_inventory(roster)
    inner_inputs = load_inner_data(roster, inventory, decision_rule)
    validation = {
        "status": "PASS",
        "performed_at_utc": utc_now(),
        "execution_mode": "preflight_only_no_outer_metrics",
        "scope": "whitelisted saved development probability files, label/role metadata, source-code copies and package manifests",
        "counts": {
            "development_vessels": EXPECTED_N,
            "oof_per_seed": {str(seed): EXPECTED_N for seed in SEEDS},
            "oof_fold_counts": {str(seed): inventory[seed]["fold_counts"] for seed in SEEDS},
            "oof_probability_checks": inventory["probability_checks"],
            "inner_per_seed_fold": {f"{seed}/{fold}": EXPECTED_INNER for seed in SEEDS for fold in FOLDS},
            "roster_rows": sum(len(x) for x in roster.values()),
            "roster_role_counts_by_fold": {str(fold): {role: sum(1 for roles in roster.values() if roles[fold] == role) for role in ("FIT", "INNER", "OUTER")} for fold in FOLDS},
        },
        "checks": {
            "classes_match_frozen_order": True,
            "oof_unique_ids_and_roles_match_roster": True,
            "seed_id_label_fold_observed_day_alignment": True,
            "inner_ids_labels_observed_days_match_role_and_development_roster": True,
            "inner_prediction_file_hashes_match_fixed_rule_and_role_membership": True,
            "historical_inner_id_hash_list_order": "unverified; CSV-order digest recorded without treating difference as an ID mismatch",
            "TabICL_fit_only_zero_shot_generation_lineage": meta["lineage"]["status"],
            "old_factor_table_matches_frozen_2_3_2": True,
        },
        "historical_inner_hashes": inner_inputs["inner_hashes"],
        "model_lineage": meta["lineage"],
        "feature_input_ambiguity": hash_manifest["feature_shape_ambiguity"],
        "no_oof_metrics_computed": True,
        "no_raw_or_holdout_or_7372_rows_opened": True,
    }
    return validation, roster, inventory, inner_inputs, {"settings": settings, "decision_rule": decision_rule, **meta}


def reviewer_receipt_check(runner_hash: str, config_hash: str) -> dict:
    path = ROUND / "review" / "precheck.json"
    if not path.is_file():
        raise RuntimeError("Scoring blocked: rounds/round_003/review/precheck.json is missing")
    receipt = read_json(path)
    status = receipt.get("precheck_status", receipt.get("status"))
    reviewed_runner = receipt.get("runner_sha256", receipt.get("reviewed_runner_sha256"))
    reviewed_config = receipt.get("config_sha256", receipt.get("reviewed_config_sha256"))
    if status not in {"PASS", "CONDITIONAL_PASS"}:
        raise RuntimeError(f"Scoring blocked: reviewer precheck status is {status!r}")
    if str(reviewed_runner).lower() != runner_hash.lower() or str(reviewed_config).lower() != config_hash.lower():
        raise RuntimeError("Scoring blocked: reviewer receipt is not bound to current runner/config SHA256")
    return {"path": str(path), "sha256": sha256_file(path), "status": status,
            "runner_sha256": reviewed_runner, "config_sha256": reviewed_config}


def execute(args) -> int:
    ROUND.joinpath("logs", "pycache").mkdir(parents=True, exist_ok=True)
    config = verify_frozen_config(read_json(Path(args.config).resolve()))
    hash_manifest = build_hash_manifest(config)
    write_json(ROUND / "artifacts" / "source_hash_manifest.json", hash_manifest)
    validation, roster, inventory, inner_inputs, meta = preflight(config, hash_manifest)
    write_json(ROUND / "artifacts" / "preflight_validation.json", validation)
    print(json.dumps({"mode": args.mode, "preflight": validation["status"],
                      "development_vessels": EXPECTED_N, "oof_metrics_computed": False}, ensure_ascii=False))
    if args.mode == "preflight":
        return 0
    if not args.manager_go or not os.environ.get("ROUND003_MANAGER_GO"):
        raise RuntimeError("Scoring blocked: explicit manager go is required in both CLI and launcher environment")
    current_runner_hash = sha256_file(Path(__file__))
    current_config_hash = sha256_file(Path(args.config).resolve())
    review_receipt = reviewer_receipt_check(current_runner_hash, current_config_hash)
    if meta["lineage"]["status"].startswith("confirmed") is False:
        raise RuntimeError("Scoring blocked: saved TabICL FIT-only/INNER-unused generation lineage is not confirmed")

    policy, policy_hash = create_policy_artifact(config, hash_manifest, inner_inputs)
    # Re-open and verify the frozen choice file before any OOF prediction metrics are calculated.
    policy_path = ROUND / "artifacts" / "decision_policy_frozen.json"
    frozen = read_json(policy_path)
    frozen_hash = frozen.pop("policy_sha256_before_hash_field", None)
    if frozen_hash != policy_hash or frozen_hash != sha256_bytes(json_compact_bytes(frozen)):
        raise ValueError("Frozen policy hash verification failed before OUTER scoring")
    factors = policy_factor_map(policy)

    # This is the first stage that reads OOF probability values for decisions or metrics.
    data = {seed: load_oof_for_scoring(seed, roster, inventory, inner_inputs["old_factors"]) for seed in SEEDS}
    points, arrays, quality = make_point_metrics(data, factors)
    transitions = compare_transitions(arrays)
    prediction_artifact = save_predictions(arrays)
    # The plan's bootstrap uses the same sampled vessel indices for both seeds.
    bootstrap = bootstrap_differences(arrays, config)

    # Compute fixed progress gates from the arithmetic mean across two seeds.
    raw_mean = points["arithmetic_mean_across_seeds"]["all"]["A_raw"]
    selected_mean = points["arithmetic_mean_across_seeds"]["all"]["A_micro_select"]
    selected_vs_raw = bootstrap["by_comparison"]["A_raw_to_A_micro_select"]["all"]["micro_f1"]
    micro_delta_by_seed = {str(seed): points["by_seed"][str(seed)]["all"]["A_micro_select"]["micro_f1"] - points["by_seed"][str(seed)]["all"]["A_raw"]["micro_f1"] for seed in SEEDS}
    macro_delta_mean = selected_mean["macro_f1"] - raw_mean["macro_f1"]
    class_f1_delta = {
        str(seed): [points["by_seed"][str(seed)]["all"]["A_micro_select"]["class_f1"][c]
                    - points["by_seed"][str(seed)]["all"]["A_raw"]["class_f1"][c] for c in LABELS]
        for seed in SEEDS
    }
    day_macro_delta = {}
    for seed in SEEDS:
        selected_day_macro = points["by_seed"][str(seed)]["days_1_7"]["A_micro_select"]["macro_f1"]
        raw_day_macro = points["by_seed"][str(seed)]["days_1_7"]["A_raw"]["macro_f1"]
        day_macro_delta[str(seed)] = None if selected_day_macro is None or raw_day_macro is None else selected_day_macro - raw_day_macro
    ci_lower = selected_vs_raw["ci95_percentile_mean_across_seeds"][0]
    gates = {
        "mean_micro_delta_at_least_0_005": float(selected_mean["micro_f1"] - raw_mean["micro_f1"]) >= 0.005,
        "both_seed_micro_deltas_positive": all(v > 0 for v in micro_delta_by_seed.values()),
        "paired_5000_vessel_bootstrap_ci_lower_above_zero": ci_lower is not None and ci_lower > 0,
        "mean_macro_f1_not_decreased": macro_delta_mean >= 0,
        "each_seed_class_f1_drop_no_more_than_0_01": all(v >= -0.01 for values in class_f1_delta.values() for v in values),
        "each_seed_natural_1_7_macro_f1_drop_no_more_than_0_01": all(v is not None and v >= -0.01 for v in day_macro_delta.values()),
    }
    gate_result = {"criteria": gates, "all_criteria_met": all(gates.values()),
                   "micro_delta_by_seed": micro_delta_by_seed, "macro_delta_mean": macro_delta_mean,
                   "class_f1_delta_by_seed": class_f1_delta, "natural_1_7_macro_delta_by_seed": day_macro_delta,
                   "paired_ci95_mean_micro_delta_vs_raw": selected_vs_raw["ci95_percentile_mean_across_seeds"],
                   "interpretation": "development confirmation candidate gate only; not independent or official performance"}
    result = {
        "round": "round_003", "status": "completed_with_limitations",
        "completed_at_utc": utc_now(), "evaluation_population": "repeatedly exposed development OUTER, 5,897 unique vessels",
        "comparison": "A_raw vs A_old vs A_micro_select on unchanged saved probability rows",
        "policy_sha256": policy_hash,
        "reviewer_precheck": review_receipt,
        "runner_sha256": current_runner_hash, "config_sha256": current_config_hash,
        "source_hash_manifest_sha256": sha256_file(ROUND / "artifacts" / "source_hash_manifest.json"),
        "prediction_artifact": prediction_artifact,
        "metrics": points,
        "original_probability_quality_by_seed_and_scope": quality,
        "paired_transition_counts": transitions,
        "paired_bootstrap": bootstrap,
        "selected_vs_raw_progress_gate": gate_result,
        "model_generation_lineage": meta["lineage"],
        "saved_decision_score_representation": {str(seed): data[seed]["decision_score_representation"] for seed in SEEDS},
        "limitations": [
            "Development OUTER results were previously exposed; this is not independent validation.",
            "Decision factors change argmax only. Original probabilities are unchanged; scaled decision scores are not calibrated probabilities.",
            "Bootstrap does not remove repeated-development selection bias or geographic dependence.",
            "F156/no-missing-flags documentation conflicts with copied transformation code that appends missing flags; exact M4 query width remains unresolved.",
            "No raw/holdout/full-7,372 feature rows, Test2025 rows, model binary, or new model queries were used.",
            "No model was fitted and no new original model inference was run.",
        ],
    }
    write_json(ROUND / "artifacts" / "result.json", result)
    print(json.dumps({"mode": args.mode, "status": result["status"],
                      "policy_sha256": policy_hash, "prediction_sha256": prediction_artifact["sha256"],
                      "selected_progress_gate": gates}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "score"), default="preflight")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--manager-go", default="")
    args = parser.parse_args()
    started_at = utc_now()
    started = time.monotonic()
    try:
        exit_code = execute(args)
    except Exception as exc:
        failure = {"status": "FAILED", "mode": args.mode, "failed_at_utc": utc_now(),
                   "error_type": type(exc).__name__, "error": str(exc),
                   "pid": os.getpid(), "runner_sha256": sha256_file(Path(__file__))}
        write_json(ROUND / "logs" / f"failure_{args.mode}.json", failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1
    runtime = {"mode": args.mode, "pid": os.getpid(), "started_at_utc": started_at,
               "elapsed_seconds": time.monotonic() - started, "exit_code": exit_code,
               "python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
               "thread_environment": {key: os.environ.get(key) for key in
                   ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")},
               "temporary_directories": {key: os.environ.get(key) for key in ("TEMP", "TMP", "TMPDIR", "PYTHONPYCACHEPREFIX")}}
    write_json(ROUND / "logs" / f"runner_runtime_{args.mode}.json", runtime)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
