from __future__ import annotations

"""Round021: baseline 12-feature stacker vs 20-feature spatial stacker.

--prepare inventories and hashes inputs, validates role/label alignment, and
reads INNER_SELECT probabilities only. It never fits or reads OUTER probability
values. --run requires manager/outer_read_approval.json bound to that prepared
snapshot, fits exactly three fold-local meta models, saves/reloads them, checks
reload equivalence on INNER_SELECT, then and only then loads OUTER probabilities.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUND = ROOT / "rounds" / "round_021"
DEFAULT_CONFIG = ROUND / "configs" / "experiment.json"

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"):
    os.environ[key] = "3"

import numpy as np
import psutil
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


PHASE = "startup"
FOLDS = (0, 1, 2)
BASE_MODELS = ("LightGBM_sqrt_macro", "CatBoost", "TabICL_A_raw")
METHODS = (*BASE_MODELS, "Fixed_mean_3model", "Stacker_Logistic_C1")
ROUND2_MODELS = {
    "LightGBM_sqrt_macro": "baseline_lightgbm",
    "CatBoost": "candidate_catboost",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path_from_config(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(to_builtin(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path, expected_header: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        if expected_header is not None and tuple(reader.fieldnames) != expected_header:
            raise ValueError(f"Unexpected CSV columns for {path}: {reader.fieldnames}")
        return list(reader)


def csv_header(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), None)
    if header is None:
        raise ValueError(f"CSV has no header: {path}")
    return tuple(header)


def input_paths(cfg: dict, config_path: Path) -> list[Path]:
    p = cfg["paths"]
    r2_prob = path_from_config(p["round002_probability_dir"])
    feature_root = path_from_config(p["round002_feature_root"])
    package = path_from_config(p["tabicl_package_root"])
    files = [
        Path(__file__).resolve(), Path(__file__).with_name("fit_meta_worker.py").resolve(), config_path.resolve(),
        path_from_config(p["round002_config"]), path_from_config(p["round002_result"]),
        path_from_config(p["round002_roster"]), path_from_config(p["round002_split_manifest"]),
        path_from_config(p["tabicl_source_hash_manifest"]), path_from_config(p["tabicl_preflight_validation"]),
        path_from_config(p["tabicl_runner"]), path_from_config(p["year_provenance_source"]),
        feature_root / "fold_0_features.npz", feature_root / "fold_1_features.npz", feature_root / "fold_2_features.npz",
        package / "MANIFEST_SHA256.json", package / "SOURCE_SHA256.json",
        package / "splits" / "development_roles_long.csv",
        package / "metadata" / "classes.json", package / "metadata" / "run_settings.json",
        package / "metadata" / "package_validation.json",
        package / "evaluation" / "final_fixed_decision_rule.json",
        package / "evaluation" / "seed_42" / "original_oof_predictions.csv",
        path_from_config(p["historical_predictions"]),
        path_from_config(p["historical_protection_reference"]),
        path_from_config(p["spatial_parquet"]),
    ]
    for fold in FOLDS:
        files.append(package / "evaluation" / "seed_42" / f"fold_{fold}" / "inner_predictions.csv")
        files.append(package / "evaluation" / "seed_42" / f"fold_{fold}" / "training.json")
        for source_name in ROUND2_MODELS.values():
            for role in ("inner_es", "inner_select", "outer"):
                files.append(r2_prob / f"fold_{fold}_{source_name}_{role}.npz")
    # Preserve first occurrence while keeping the manifest path ordering fixed.
    unique = []
    seen = set()
    for path in files:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    return unique


def build_input_manifest(cfg: dict, config_path: Path) -> dict:
    files = input_paths(cfg, config_path)
    rows = []
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"Required source file missing: {path}")
        rows.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    core = {
        "round": "round_021",
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "config_sha256": sha256_file(config_path.resolve()),
        "files": rows,
        "outer_probability_file_policy": "byte hashes recorded; no OUTER probability arrays loaded in prepare",
        "excluded": ["raw F drive files", "holdout individual rows", "Test2025", "OUTER probability values during prepare"],
    }
    return {**core, "fingerprint_sha256": canonical_hash(core), "created_at_utc": utc_now()}


def source_paths(cfg: dict) -> dict:
    p = cfg["paths"]
    package = path_from_config(p["tabicl_package_root"])
    return {
        "round002_config": path_from_config(p["round002_config"]),
        "round002_result": path_from_config(p["round002_result"]),
        "round002_roster": path_from_config(p["round002_roster"]),
        "round002_split_manifest": path_from_config(p["round002_split_manifest"]),
        "round002_feature_root": path_from_config(p["round002_feature_root"]),
        "round002_probability_dir": path_from_config(p["round002_probability_dir"]),
        "tabicl_package": package,
        "tabicl_source_manifest": path_from_config(p["tabicl_source_hash_manifest"]),
        "tabicl_preflight": path_from_config(p["tabicl_preflight_validation"]),
        "year_source": path_from_config(p["year_provenance_source"]),
    }


def assert_probability(p: np.ndarray, expected_rows: int, sum_tolerance: float, label: str) -> float:
    p = np.asarray(p, dtype=np.float64)
    if p.shape != (expected_rows, 4) or not np.isfinite(p).all():
        raise ValueError(f"{label}: expected finite ({expected_rows},4) probabilities, got {p.shape}")
    if np.any(p < -1e-12) or np.any(p > 1 + 1e-12):
        raise ValueError(f"{label}: probability outside [0,1]")
    max_sum_error = float(np.max(np.abs(p.sum(axis=1) - 1.0)))
    if max_sum_error > sum_tolerance:
        raise ValueError(f"{label}: row sum error {max_sum_error} exceeds {sum_tolerance}")
    return max_sum_error


def integer(value: str, name: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer {name}={value!r}") from exc
    if not math.isfinite(number) or number != int(number):
        raise ValueError(f"Invalid integer {name}={value!r}")
    return int(number)


def numeric(value: str, name: str, blank_nan: bool = False) -> float:
    if blank_nan and (value is None or value.strip() == ""):
        return float("nan")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric {name}={value!r}") from exc
    return result


def same_days(left: float, right: float) -> bool:
    return (math.isnan(left) and math.isnan(right)) or left == right


def validate_round002_sources(cfg: dict, paths: dict) -> dict:
    round2_cfg = read_json(paths["round002_config"])
    if round2_cfg.get("experiment") != "round_002_catboost_vs_refit_sqrt_macro_seed42":
        raise ValueError("Round002 config identity differs from the frozen source")
    if round2_cfg.get("input", {}).get("class_order") != cfg["dataset"]["class_order"]:
        raise ValueError("Round002 class order differs from Round020 config")
    if round2_cfg.get("split", {}).get("train_role") != "INNER_ES" or round2_cfg.get("split", {}).get("test_role") != "INNER_SELECT":
        raise ValueError("Round002 ES/SELECT split role semantics differ")
    result = read_json(paths["round002_result"])
    if result.get("status") != "completed" or result.get("scope", {}).get("holdout_individual_rows_read") != 0:
        raise ValueError("Round002 archived result is not the expected completed development-only run")
    split_manifest = read_json(paths["round002_split_manifest"])
    roster_hash = sha256_file(paths["round002_roster"])
    if str(split_manifest.get("roster_sha256", "")).lower() != roster_hash.lower():
        raise ValueError("Round002 inner roster differs from inner_split_manifest.json")
    if split_manifest.get("class_order") not in (None, cfg["dataset"]["class_order"]):
        raise ValueError("Round002 split manifest class order mismatch")

    r2_roster_rows = read_csv(paths["round002_roster"], ("fold", "role", "rfid_id", "y_true"))
    split_ids: dict[int, dict[str, dict[str, int]]] = {f: {"INNER_ES": {}, "INNER_SELECT": {}} for f in FOLDS}
    for row in r2_roster_rows:
        fold = integer(row["fold"], "round002 roster fold")
        role = row["role"]
        vessel = row["rfid_id"]
        y = integer(row["y_true"], "round002 roster y_true")
        if fold not in FOLDS or role not in {"INNER_ES", "INNER_SELECT"} or not vessel or y not in (0, 1, 2, 3):
            raise ValueError(f"Invalid round002 INNER split row: {row}")
        if vessel in split_ids[fold][role]:
            raise ValueError(f"Duplicate round002 split ID: fold={fold} role={role} id={vessel}")
        split_ids[fold][role][vessel] = y

    package = paths["tabicl_package"]
    source_manifest = read_json(paths["tabicl_source_manifest"])
    whitelist = source_manifest.get("whitelisted_files", {})
    needed_package_files = [
        "MANIFEST_SHA256.json", "SOURCE_SHA256.json", "splits/development_roles_long.csv",
        "metadata/classes.json", "metadata/run_settings.json", "metadata/package_validation.json",
        "evaluation/final_fixed_decision_rule.json", "evaluation/seed_42/original_oof_predictions.csv",
        "code/historical/TinyTabM/TinyTabM_구현_20261029/fishing_tiny_tabm.py",
    ]
    for fold in FOLDS:
        needed_package_files.extend((
            f"evaluation/seed_42/fold_{fold}/inner_predictions.csv",
            f"evaluation/seed_42/fold_{fold}/training.json",
        ))
    package_hash_checks = {}
    for rel in needed_package_files:
        record = whitelist.get(rel)
        path = package / Path(rel)
        if not isinstance(record, dict) or not path.is_file():
            raise ValueError(f"TabICL source manifest lacks required whitelisted file: {rel}")
        actual = sha256_file(path)
        expected = str(record.get("sha256", "")).lower()
        if actual.lower() != expected or record.get("manifest_match") is False:
            raise ValueError(f"TabICL package whitelist SHA mismatch: {rel}")
        package_hash_checks[rel] = {"sha256": actual, "bytes": path.stat().st_size, "manifest_match": True}

    expected_classes = {str(i): name for i, name in enumerate(cfg["dataset"]["class_order"])}
    if read_json(package / "metadata" / "classes.json") != expected_classes:
        raise ValueError("TabICL metadata class mapping/order differs")
    package_validation = read_json(package / "metadata" / "package_validation.json")
    if (package_validation.get("development") != 5897 or package_validation.get("holdout") != 1475
            or package_validation.get("new_training") is not False or package_validation.get("new_model_queries") is not False):
        raise ValueError("TabICL package metadata no longer confirms the archived saved-probability scope")
    settings = read_json(package / "metadata" / "run_settings.json")
    if settings.get("algorithm") != "TabICLv2" or settings.get("seeds") != [42, 2026]:
        raise ValueError("TabICL archived seed/model identity differs")
    lineage_source = (package / "code" / "historical" / "TinyTabM" / "TinyTabM_구현_20261029" / "fishing_tiny_tabm.py").read_text(encoding="utf-8-sig")
    if "expected_year = int(source.get('year', 2026 if split == 'train' else 2025))" not in lineage_source or "date.year != expected_year" not in lineage_source:
        raise ValueError("Year cohort provenance source no longer contains the documented Train2026 default/check")

    package_roster_rows = read_csv(package / "splits" / "development_roles_long.csv", ("rfid_id", "outer_fold", "role"))
    package_roles: dict[str, dict[int, str]] = {}
    for row in package_roster_rows:
        vessel = row["rfid_id"]
        fold = integer(row["outer_fold"], "TabICL roster outer_fold")
        role = row["role"]
        if fold not in FOLDS or role not in {"FIT", "INNER", "OUTER"}:
            raise ValueError(f"Invalid TabICL development role: {row}")
        if fold in package_roles.setdefault(vessel, {}):
            raise ValueError(f"Duplicate TabICL role row: {vessel}/{fold}")
        package_roles[vessel][fold] = role
    if len(package_roles) != cfg["dataset"]["development_rows"] or any(len(roles) != 3 for roles in package_roles.values()):
        raise ValueError("TabICL role roster is not exactly one record per vessel/fold")

    tabicl_rule = read_json(package / "evaluation" / "final_fixed_decision_rule.json")
    if tabicl_rule.get("class_order") != cfg["dataset"]["class_order"] or tabicl_rule.get("outer_used_for_factor_choice") is not False:
        raise ValueError("TabICL historical frozen-rule metadata differs")
    choices = {(int(c.get("seed", -1)), int(c.get("fold", -1))): c for c in tabicl_rule.get("inner_choices", [])}
    for fold in FOLDS:
        choice = choices.get((42, fold))
        inner_path = package / "evaluation" / "seed_42" / f"fold_{fold}" / "inner_predictions.csv"
        if choice is None or str(choice.get("inner_predictions_sha256", "")).lower() != sha256_file(inner_path).lower():
            raise ValueError(f"TabICL INNER file does not match its frozen rule: fold={fold}")
        training = read_json(package / "evaluation" / "seed_42" / f"fold_{fold}" / "training.json")
        expected_fit = cfg["dataset"]["folds"][str(fold)]["FIT"]
        if (training.get("method") != "tabicl" or training.get("fit_vessels") != expected_fit
                or training.get("inner_vessels") != 787 or training.get("parameters_trained_on_this_dataset") != 0
                or training.get("selection_metric") is not None):
            raise ValueError(f"TabICL saved training record has unexpected lineage for fold={fold}")
    oof = package / "evaluation" / "seed_42" / "original_oof_predictions.csv"
    if csv_header(oof) != tuple(cfg["probabilities"]["tabicl_oof_csv_columns"]):
        raise ValueError("TabICL OOF CSV columns differ; header inspected only in prepare")
    return {"split_ids": split_ids, "package_roles": package_roles,
            "package_hash_checks": package_hash_checks, "tabicl_rule": tabicl_rule,
            "round002_result": result, "split_manifest": split_manifest,
            "roster_sha256": roster_hash, "source_manifest_sha256": sha256_file(paths["tabicl_source_manifest"])}


def validate_feature_metadata(cfg: dict, paths: dict, source_meta: dict) -> dict:
    """Read only IDs/roles/labels/days from saved fold NPZs; never access X."""
    round2_cfg = read_json(paths["round002_config"])
    feature_hashes = round2_cfg["input"]["fold_sha256"]
    out: dict[int, dict] = {}
    role_code = {"FIT": "FIT", "INNER": "INNER", "OUTER": "OUTER"}
    for fold in FOLDS:
        path = paths["round002_feature_root"] / f"fold_{fold}_features.npz"
        if sha256_file(path).lower() != str(feature_hashes[str(fold)]).lower():
            raise ValueError(f"Round002 saved fold metadata source SHA mismatch: fold={fold}")
        with np.load(path, allow_pickle=False) as archive:
            expected_keys = {"fold", "rfid_ids", "y", "roles", "X", "feature_names", "obs_days"}
            if set(archive.files) != expected_keys:
                raise ValueError(f"Unexpected round002 feature NPZ keys at fold={fold}: {archive.files}")
            stored_fold = int(np.asarray(archive["fold"]).item())
            # Deliberately access no X or feature_names array.
            ids = archive["rfid_ids"].astype(str)
            y = archive["y"].astype(np.int64)
            roles = archive["roles"].astype(str)
            days = archive["obs_days"].astype(np.float64)
        if stored_fold != fold or len(ids) != 5897 or len(set(ids.tolist())) != 5897:
            raise ValueError(f"Invalid source ID/fold inventory for fold={fold}")
        if y.shape != (len(ids),) or roles.shape != (len(ids),) or days.shape != (len(ids),):
            raise ValueError(f"Round002 metadata vector shape mismatch at fold={fold}")
        if np.any((y < 0) | (y > 3)) or np.isinf(days).any():
            raise ValueError(f"Round002 metadata labels/days invalid at fold={fold}")
        role_ids = {role: [str(ids[i]) for i in range(len(ids)) if roles[i] == role] for role in ("FIT", "INNER", "OUTER")}
        if set(np.unique(roles).tolist()) != set(role_code):
            raise ValueError(f"Round002 feature metadata role vocabulary mismatch at fold={fold}")
        expected_counts = cfg["dataset"]["folds"][str(fold)]
        split = source_meta["split_ids"][fold]
        if len(role_ids["FIT"]) != expected_counts["FIT"] or len(role_ids["INNER"]) != 787 or len(role_ids["OUTER"]) != expected_counts["OUTER"]:
            raise ValueError(f"Round002 FIT/INNER/OUTER counts mismatch at fold={fold}")
        if set(split["INNER_ES"]) | set(split["INNER_SELECT"]) != set(role_ids["INNER"]):
            raise ValueError(f"Round002 ES/SELECT does not partition INNER at fold={fold}")
        if set(split["INNER_ES"]) & set(split["INNER_SELECT"]):
            raise ValueError(f"Round002 ES and SELECT overlap at fold={fold}")
        if len(split["INNER_ES"]) != expected_counts["INNER_ES"] or len(split["INNER_SELECT"]) != expected_counts["INNER_SELECT"]:
            raise ValueError(f"Round002 ES/SELECT counts mismatch at fold={fold}")
        index = {str(v): i for i, v in enumerate(ids)}
        for i, vessel in enumerate(ids):
            package_role = source_meta["package_roles"].get(str(vessel), {}).get(fold)
            if package_role is None or package_role != str(roles[i]):
                raise ValueError(f"Round002/TabICL role mismatch fold={fold} id={vessel}")
        for role in ("INNER_ES", "INNER_SELECT"):
            for vessel, expected_y in split[role].items():
                if int(y[index[vessel]]) != expected_y:
                    raise ValueError(f"Round002 split label mismatch fold={fold} role={role} id={vessel}")

        entry = source_meta["split_manifest"].get("folds", {}).get(str(fold))
        if not isinstance(entry, dict):
            raise ValueError(f"Round002 split manifest missing fold={fold}")
        for role, key in (("INNER_ES", "inner_es"), ("INNER_SELECT", "inner_select")):
            ordered = [v for v in role_ids["INNER"] if v in split[role]]
            id_digest = sha256_text("\n".join(ordered))
            label_digest = sha256_text("\n".join(f"{v}:{split[role][v]}" for v in ordered))
            if entry.get(f"{key}_ids_sha256") != id_digest or entry.get(f"{key}_label_sha256") != label_digest:
                raise ValueError(f"Round002 roster ID/label digest differs from manifest: fold={fold} role={role}")
        out[fold] = {"ids": ids, "y": y, "roles": roles, "days": days,
                     "index": index, "role_ids": role_ids,
                     "role_counts": {r: len(v) for r, v in role_ids.items()},
                     "feature_npz_sha256": sha256_file(path),
                     "note": "IDs, role codes, labels and observed days read; X and feature_names arrays not loaded"}
    return out


def load_round002_probability_metadata(path: Path, fold: int, role: str, expected: dict[str, int],
                                       sum_tolerance: float, load_probabilities: bool) -> tuple[list[str], np.ndarray, np.ndarray | None, float | None]:
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {"fold", "role", "ids", "y_true", "probabilities", "predictions"}:
            raise ValueError(f"Unexpected saved probability keys: {path}")
        stored_fold = int(np.asarray(archive["fold"]).item())
        stored_role = str(np.asarray(archive["role"]).item())
        ids = archive["ids"].astype(str).tolist()
        y = archive["y_true"].astype(np.int64)
        p = archive["probabilities"].astype(np.float64) if load_probabilities else None
    if stored_fold != fold or stored_role != role:
        raise ValueError(f"Probability role/fold mismatch in {path}: {stored_fold}/{stored_role}")
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError(f"Probability IDs do not match expected {role} set: {path}")
    row = dict(zip(ids, y.tolist()))
    if row != expected:
        raise ValueError(f"Probability labels differ from expected {role} labels: {path}")
    if p is None:
        return ids, y, None, None
    max_sum_error = assert_probability(p, len(ids), sum_tolerance, str(path))
    return ids, y, p, max_sum_error


def load_tabicl_inner(path: Path, fold: int, expected_select: dict[str, int], metadata: dict[int, dict],
                      cfg: dict) -> tuple[list[str], np.ndarray, np.ndarray, float]:
    rows = read_csv(path, tuple(cfg["probabilities"]["tabicl_inner_csv_columns"]))
    source = metadata[fold]
    inner_ids = set(source["role_ids"]["INNER"])
    if len(rows) != len(inner_ids):
        raise ValueError(f"TabICL fold-local INNER row count mismatch at fold={fold}: {len(rows)} != {len(inner_ids)}")
    by_id = {}
    selected_p = {}
    for row in rows:
        vessel = row["rfid_id"]
        if not vessel or vessel in by_id:
            raise ValueError(f"TabICL INNER duplicate/missing ID fold={fold}: {vessel!r}")
        y = integer(row["y_true"], "TabICL INNER y_true")
        days = numeric(row["observed_days"], "TabICL INNER observed_days", blank_nan=True)
        if vessel not in inner_ids:
            raise ValueError(f"TabICL fold-local CSV contains a non-INNER ID fold={fold}: {vessel}")
        row_i = source["index"][vessel]
        if y != int(source["y"][row_i]) or not same_days(days, float(source["days"][row_i])):
            raise ValueError(f"TabICL INNER label/days mismatch fold={fold} id={vessel}")
        by_id[vessel] = (y, days)
        if vessel in expected_select:
            selected_p[vessel] = [numeric(row[c], f"TabICL INNER_SELECT {c}") for c in cfg["probabilities"]["class_columns"]]
    if set(by_id) != inner_ids:
        raise ValueError(f"TabICL fold-local INNER IDs do not match all INNER IDs for fold={fold}")
    if set(expected_select) - set(selected_p):
        raise ValueError(f"TabICL fold-local CSV misses INNER_SELECT probability rows fold={fold}")
    out_ids = [v for v in source["role_ids"]["INNER"] if v in expected_select]
    if set(out_ids) != set(expected_select) or len(out_ids) != len(expected_select):
        raise ValueError(f"Round002 INNER_SELECT not projected from TabICL INNER fold={fold}")
    ys = np.asarray([expected_select[v] for v in out_ids], dtype=np.int64)
    pp = np.asarray([selected_p[v] for v in out_ids], dtype=np.float64)
    for i, vessel in enumerate(out_ids):
        y, days = by_id[vessel]
        row_i = source["index"][vessel]
        if y != int(ys[i]) or source["roles"][row_i] != "INNER":
            raise ValueError(f"TabICL INNER file has non-INNER ID fold={fold} id={vessel}")
    max_sum_error = assert_probability(pp, len(out_ids), cfg["probabilities"]["sum_tolerance_tabicl"], f"TabICL INNER fold={fold}")
    return out_ids, ys, pp, max_sum_error


def prepare_select_state(cfg: dict, paths: dict, source_meta: dict) -> tuple[dict, dict]:
    metadata = validate_feature_metadata(cfg, paths, source_meta)
    data = {}
    split_audit = {}
    for fold in FOLDS:
        split = source_meta["split_ids"][fold]
        expected = split["INNER_SELECT"]
        # The saved roster sequence is the canonical SELECT row order.
        roster_rows = read_csv(paths["round002_roster"], ("fold", "role", "rfid_id", "y_true"))
        ids = [row["rfid_id"] for row in roster_rows
               if integer(row["fold"], "round002 roster fold") == fold and row["role"] == "INNER_SELECT"]
        if len(ids) != len(set(ids)) or set(ids) != set(expected):
            raise ValueError(f"Round002 SELECT roster order/inventory mismatch fold={fold}")
        base = {}
        sum_errors = {}
        for model, source_name in ROUND2_MODELS.items():
            for role, role_key in (("INNER_ES", "inner_es"), ("INNER_SELECT", "inner_select"), ("OUTER", "outer")):
                file_path = paths["round002_probability_dir"] / f"fold_{fold}_{source_name}_{role_key}.npz"
                expected_labels = split[role] if role in split else {
                    vessel: int(metadata[fold]["y"][metadata[fold]["index"][vessel]])
                    for vessel in metadata[fold]["role_ids"]["OUTER"]
                }
                load_p = role == "INNER_SELECT"
                _, _, p, max_error = load_round002_probability_metadata(
                    file_path, fold, role, expected_labels,
                    cfg["probabilities"]["sum_tolerance_round002"], load_p)
                if load_p:
                    with np.load(file_path, allow_pickle=False) as archive:
                        source_ids = archive["ids"].astype(str).tolist()
                    by_id = {v: p[i] for i, v in enumerate(source_ids)}
                    base[model] = np.asarray([by_id[v] for v in ids], dtype=np.float64)
                    sum_errors[f"{model}_INNER_SELECT"] = max_error
        tabicl_path = paths["tabicl_package"] / "evaluation" / "seed_42" / f"fold_{fold}" / "inner_predictions.csv"
        tab_ids, tab_y, tab_p, tab_sum_error = load_tabicl_inner(tabicl_path, fold, expected, metadata, cfg)
        if len(tab_ids) != len(set(tab_ids)) or set(tab_ids) != set(ids):
            raise ValueError(f"TabICL INNER_SELECT IDs do not match the canonical split roster fold={fold}")
        tab_index = {v: i for i, v in enumerate(tab_ids)}
        tab_p = np.asarray([tab_p[tab_index[v]] for v in ids], dtype=np.float64)
        tab_y = np.asarray([tab_y[tab_index[v]] for v in ids], dtype=np.int64)
        if not np.array_equal(tab_y, np.asarray([expected[v] for v in ids], dtype=np.int64)):
            raise ValueError(f"TabICL INNER labels/order mismatch against split roster fold={fold}")
        base["TabICL_A_raw"] = tab_p
        if set(base) != set(BASE_MODELS):
            raise AssertionError(f"Unexpected base model inventory fold={fold}: {sorted(base)}")
        x = np.concatenate([np.log(np.clip(base[name], cfg["probabilities"]["clip_min"], cfg["probabilities"]["clip_max"])) for name in BASE_MODELS], axis=1)
        y = np.asarray([expected[v] for v in ids], dtype=np.int64)
        data[fold] = {"ids": ids, "y": y, "days": np.asarray([metadata[fold]["days"][metadata[fold]["index"][v]] for v in ids], dtype=np.float64),
                      "base_probabilities": base, "stacker_x": x}
        split_audit[str(fold)] = {
            "counts": {"FIT": metadata[fold]["role_counts"]["FIT"], "INNER_ES": len(split["INNER_ES"]),
                       "INNER_SELECT": len(ids), "OUTER": metadata[fold]["role_counts"]["OUTER"]},
            "source_role_codes": {r: len(metadata[fold]["role_ids"][r]) for r in ("FIT", "INNER", "OUTER")},
            "role_id_sets_disjoint": not (set(split["INNER_ES"]) & set(split["INNER_SELECT"])),
            "inner_partition_matches_source_inner": True,
            "labels_match_round002_source_and_split_manifest": True,
            "TabICL_inner_source": str(tabicl_path),
            "TabICL_inner_max_probability_row_sum_error": tab_sum_error,
            "round002_select_probability_max_sum_error": sum_errors,
            "OUTER_probability_values_loaded": False,
            "FIT_feature_matrix_loaded": False,
        }
    return {"metadata": metadata, "select": data}, {"folds": split_audit, "fits": 0,
        "base_fits": 0, "meta_fits": 0, "grid_searches": 0, "retries": 0,
        "outer_probability_values_loaded": False, "outer_label_values_read": True,
        "outer_label_source": "round002 fold NPZ y vector; used only for exact role/label alignment before freeze",
        "feature_matrices_loaded": False}


def select_diagnostics(cfg: dict, select: dict) -> dict:
    out = {}
    for fold, d in select.items():
        y = d["y"]
        predictions = {name: p.argmax(axis=1) for name, p in d["base_probabilities"].items()}
        by_model = {name: {"correct": int(np.count_nonzero(pred == y)), "micro_f1": float(np.mean(pred == y))}
                    for name, pred in predictions.items()}
        pairwise = {}
        names = list(BASE_MODELS)
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                lc, rc = predictions[left] == y, predictions[right] == y
                pairwise[f"{left}_to_{right}"] = {
                    "left_wrong_right_correct": int(np.count_nonzero(~lc & rc)),
                    "left_correct_right_wrong": int(np.count_nonzero(lc & ~rc)),
                }
        correct = np.vstack([predictions[name] == y for name in BASE_MODELS])
        out[str(fold)] = {"n": len(y), "models": by_model, "pairwise_complementarity": pairwise,
            "all_three_correct": int(np.count_nonzero(correct.all(axis=0))),
            "all_three_wrong": int(np.count_nonzero(~correct.any(axis=0))),
            "top1_correct_union": int(np.count_nonzero(correct.any(axis=0))),
            "top1_union_note": "Hard-selector descriptive ceiling on INNER_SELECT, not a logistic-stack generalization bound."}
    return out


def ensure_select_only_probabilities_ready(state: dict) -> None:
    for fold, d in state["select"].items():
        if d["stacker_x"].shape != (394, 12) or len(d["y"]) != 394:
            raise ValueError(f"Unexpected fixed meta-fit dimensions fold={fold}")
        if set(np.unique(d["y"]).tolist()) != {0, 1, 2, 3}:
            raise ValueError(f"INNER_SELECT lacks one or more classes fold={fold}")


def prepare(cfg: dict, config_path: Path) -> None:
    global PHASE
    PHASE = "prepare_manifest"
    paths = source_paths(cfg)
    manifest = build_input_manifest(cfg, config_path)
    PHASE = "prepare_select_alignment"
    source_meta = validate_round002_sources(cfg, paths)
    state, audit = prepare_select_state(cfg, paths, source_meta)
    ensure_select_only_probabilities_ready(state)
    audit["select_diagnostics"] = select_diagnostics(cfg, state["select"])
    audit["alignment"] = {str(f): {
        "selected_ids_sha256": sha256_text("\n".join(state["select"][f]["ids"])),
        "selected_label_sha256": sha256_text("\n".join(f"{v}:{int(y)}" for v, y in zip(state["select"][f]["ids"], state["select"][f]["y"]))),
        "selected_rows": len(state["select"][f]["ids"]),
        "class_order": cfg["dataset"]["class_order"],
        "cohort_year": cfg["dataset"]["cohort_year"],
        "year_source": cfg["dataset"]["cohort_year_source"],
        "year_is_rowwise_measured": False,
    } for f in FOLDS}
    audit.update({"round": "round_021", "status": "SELECT_ONLY_PREPARED", "prepared_at_utc": utc_now(),
                  "input_manifest_fingerprint_sha256": manifest["fingerprint_sha256"],
                  "runner_sha256": manifest["runner_sha256"], "config_sha256": manifest["config_sha256"],
                  "source_hashes": {row["path"]: row["sha256"] for row in manifest["files"]}})
    out = path_from_config(cfg["paths"]["output_dir"])
    write_json(out / "input_manifest.json", manifest)
    write_json(out / "select_audit.json", audit)
    print(json.dumps({"status": "SELECT_ONLY_PREPARED", "input_manifest_fingerprint_sha256": manifest["fingerprint_sha256"],
                      "fits": 0, "outer_probability_values_loaded": False,
                      "input_manifest": str(out / "input_manifest.json"), "select_audit": str(out / "select_audit.json")}, ensure_ascii=False))


def load_approval(cfg: dict, manifest: dict, config_path: Path) -> dict:
    path = path_from_config(cfg["paths"]["approval_file"])
    if not path.is_file():
        raise PermissionError(f"Manager approval file is required before model fitting/OUTER read: {path}")
    approval = read_json(path)
    expected = {
        "round": "round_021", "status": "approved",
        "runner_sha256": manifest["runner_sha256"],
        "config_sha256": manifest["config_sha256"],
        "input_manifest_sha256": manifest["fingerprint_sha256"],
    }
    for key, value in expected.items():
        if approval.get(key) != value:
            raise PermissionError(f"Manager approval mismatch for {key}: expected {value!r}")
    return {"path": str(path), "sha256": sha256_file(path), "fields": expected}


def resource_snapshot(cfg: dict, stage: str) -> dict:
    available = int(psutil.virtual_memory().available)
    rss = int(psutil.Process(os.getpid()).memory_info().rss)
    limits = cfg["execution"]
    snapshot = {"time_utc": utc_now(), "stage": stage, "available_ram_bytes": available,
                "process_rss_bytes": rss, "pid": os.getpid()}
    if available < limits["minimum_free_ram_before_fit_bytes"]:
        raise MemoryError(f"Free RAM below pre-fit guard at {stage}: {available}")
    if rss > limits["max_owned_process_rss_bytes"]:
        raise MemoryError(f"Owned process RSS above guard at {stage}: {rss}")
    return snapshot


def fit_and_reload(cfg: dict, state: dict, output_dir: Path, start_clock: float) -> tuple[dict, list[dict]]:
    global PHASE
    import joblib

    fitted = {}
    records = []
    if len(FOLDS) != 3:
        raise AssertionError("Round021 baseline fit count must remain exactly three")
    for fold in FOLDS:
        PHASE = f"meta_fit_fold_{fold}"
        snap = resource_snapshot(cfg, PHASE)
        d = state["select"][fold]
        x = d["stacker_x"]
        if x.shape != (394, 12):
            raise ValueError(f"Fixed stacker input shape mismatch at fold={fold}")
        path = output_dir / "models" / f"fold_{fold}_baseline12_stackerc1.joblib"
        if path.exists():
            raise FileExistsError(f"Refusing an implicit fit retry or overwrite: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        fit_input = output_dir / "tmp" / f"baseline12_fold_{fold}_select.npz"
        fit_input.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(fit_input, x=x, y=d["y"])
        select_path = output_dir / "select_probabilities" / f"fold_{fold}_baseline12_inner_select.npz"
        if select_path.exists():
            raise FileExistsError(f"Refusing an implicit fit retry or overwrite: {select_path}")
        worker = Path(__file__).with_name("fit_meta_worker.py").resolve()
        cmd = [sys.executable, str(worker), "--input", str(fit_input), "--output", str(path),
               "--select-output", str(select_path), "--features", "12"]
        fit_start = time.perf_counter()
        try:
            completed = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                                       timeout=cfg["execution"]["max_fit_seconds_each"], check=True)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Baseline meta fit forcibly stopped after {cfg['execution']['max_fit_seconds_each']}s at fold={fold}") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Baseline meta fit failed fold={fold}; warnings/errors are fatal: {exc.stderr[-2000:]}") from exc
        fit_wall = time.perf_counter() - fit_start
        worker_record = json.loads(completed.stdout.strip().splitlines()[-1])
        fit_seconds = float(worker_record["fit_seconds"])
        if fit_wall > cfg["execution"]["max_fit_seconds_each"] or fit_seconds > cfg["execution"]["max_fit_seconds_each"]:
            raise TimeoutError(f"Baseline meta fit exceeded {cfg['execution']['max_fit_seconds_each']}s at fold={fold}")
        if time.perf_counter() - start_clock > cfg["execution"]["max_job_seconds"]:
            raise TimeoutError("Round021 total compute budget exceeded after meta fit")
        reloaded = joblib.load(path)
        classes = reloaded.named_steps["logistic"].classes_.astype(int)
        if not np.array_equal(classes, np.asarray(cfg["stacker"]["classes"], dtype=np.int64)):
            raise ValueError(f"Meta model class order mismatch fold={fold}: {classes.tolist()}")
        model_hash = sha256_file(path)
        with threadpool_limits(limits=3):
            after = reloaded.predict_proba(x)
        with np.load(select_path, allow_pickle=False) as z:
            before = np.asarray(z["probabilities"], dtype=np.float64)
        reload_delta = float(np.max(np.abs(before - after)))
        if reload_delta > cfg["stacker"]["reload_tolerance_abs"]:
            raise ValueError(f"Meta model reload check failed fold={fold}: max abs delta={reload_delta}")
        scaler = reloaded.named_steps["scaler"]
        lr = reloaded.named_steps["logistic"]
        fitted[fold] = reloaded
        records.append({
            "fold": fold, "fit_role": "INNER_SELECT", "fit_rows": len(d["y"]),
            "features": 12, "base_fits": 0, "meta_fits": 1,
            "fit_seconds": fit_seconds, "fit_process_wall_seconds": fit_wall, "threads": 3, "pre_fit_resource": snap,
            "model_path": str(path), "model_sha256": model_hash,
            "reload_max_abs_select_probability_delta": reload_delta,
            "reload_check_pass": True, "classes": classes.tolist(),
            "coef": lr.coef_.tolist(), "intercept": lr.intercept_.tolist(),
            "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
            "scaler_fit_role": "INNER_SELECT only",
        })
    if len(records) != 3 or sum(r["meta_fits"] for r in records) != 3:
        raise AssertionError("Round021 baseline stage must finish with exactly three meta fits")
    return fitted, records


def load_outer_after_reload(cfg: dict, paths: dict, state: dict) -> dict:
    """This function is called only after all three meta models passed reload checks."""
    global PHASE
    PHASE = "outer_probability_load_after_meta_reload"
    metadata = state["metadata"]
    out: dict[int, dict] = {}
    package = paths["tabicl_package"]
    oof_path = package / "evaluation" / "seed_42" / "original_oof_predictions.csv"
    oof_rows = read_csv(oof_path, tuple(cfg["probabilities"]["tabicl_oof_csv_columns"]))
    if len(oof_rows) != cfg["dataset"]["development_rows"]:
        raise ValueError("TabICL seed42 original OOF row count differs from 5,897")
    oof_by_fold: dict[int, dict[str, tuple[int, list[float], float]]] = {f: {} for f in FOLDS}
    for row in oof_rows:
        vessel = row["rfid_id"]
        fold = integer(row["fold"], "TabICL OOF fold")
        if fold not in FOLDS or vessel in oof_by_fold[fold]:
            raise ValueError(f"TabICL OOF duplicate/invalid fold id: {fold}/{vessel}")
        y = integer(row["y_true"], "TabICL OOF y_true")
        p = [numeric(row[c], f"TabICL OOF {c}") for c in cfg["probabilities"]["class_columns"]]
        days = numeric(row["observed_days"], "TabICL OOF observed_days", blank_nan=True)
        oof_by_fold[fold][vessel] = (y, p, days)
    for fold in FOLDS:
        d = metadata[fold]
        ids = d["role_ids"]["OUTER"]
        expected = {v: int(d["y"][d["index"][v]]) for v in ids}
        models = {}
        sums = {}
        for model_name, source_name in ROUND2_MODELS.items():
            file_path = paths["round002_probability_dir"] / f"fold_{fold}_{source_name}_outer.npz"
            saved_ids, _, p, sum_error = load_round002_probability_metadata(
                file_path, fold, "OUTER", expected,
                cfg["probabilities"]["sum_tolerance_round002"], True)
            with np.load(file_path, allow_pickle=False) as archive:
                by_id = {v: archive["probabilities"][i].astype(np.float64) for i, v in enumerate(saved_ids)}
            models[model_name] = np.asarray([by_id[v] for v in ids], dtype=np.float64)
            sums[model_name] = sum_error
        tab = oof_by_fold[fold]
        if set(tab) != set(ids):
            raise ValueError(f"TabICL OOF fold={fold} IDs do not equal round002 OUTER IDs")
        tab_y, tab_days, tab_p = [], [], []
        for vessel in ids:
            y, p, days = tab[vessel]
            idx = d["index"][vessel]
            if y != int(d["y"][idx]) or not same_days(days, float(d["days"][idx])):
                raise ValueError(f"TabICL OOF label/days mismatch fold={fold} id={vessel}")
            if d["roles"][idx] != "OUTER" or d["package_roles"][vessel][fold] != "OUTER":
                raise ValueError(f"TabICL OOF row is not in the exact OUTER role fold={fold} id={vessel}")
            tab_y.append(y); tab_days.append(days); tab_p.append(p)
        tab_arr = np.asarray(tab_p, dtype=np.float64)
        sums["TabICL_A_raw"] = assert_probability(tab_arr, len(ids), cfg["probabilities"]["sum_tolerance_tabicl"], f"TabICL OUTER fold={fold}")
        labels = np.asarray([expected[v] for v in ids], dtype=np.int64)
        days = np.asarray([d["days"][d["index"][v]] for v in ids], dtype=np.float64)
        if not np.array_equal(np.asarray(tab_y, dtype=np.int64), labels) or not np.array_equal(np.asarray(tab_days), days, equal_nan=True):
            raise ValueError(f"TabICL OUTER metadata row alignment failed fold={fold}")
        models["TabICL_A_raw"] = tab_arr
        out[fold] = {"ids": ids, "y": labels, "days": days, "base_probabilities": models,
                     "max_probability_row_sum_errors": sums,
                     "year": np.full(len(ids), int(cfg["dataset"]["cohort_year"]), dtype=np.int16)}
    all_ids = [v for f in FOLDS for v in out[f]["ids"]]
    if len(all_ids) != cfg["dataset"]["development_rows"] or len(set(all_ids)) != len(all_ids):
        raise ValueError("Combined OUTER rows do not contain each development ID exactly once")
    return out


def score_metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    y = np.asarray(y, dtype=np.int64)
    pred = np.asarray(pred, dtype=np.int64)
    if y.shape != pred.shape or y.ndim != 1:
        raise ValueError("Metric label/prediction shape mismatch")
    cm = np.bincount(y * 4 + pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(np.float64)
    support = cm.sum(axis=1).astype(np.int64)
    predicted = cm.sum(axis=0).astype(np.int64)
    recall = np.divide(tp, support, out=np.zeros(4), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros(4), where=predicted > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros(4), where=(precision + recall) > 0)
    correct = int(np.count_nonzero(y == pred))
    return {"n": len(y), "correct": correct, "micro_f1": correct / len(y) if len(y) else None,
            "macro_f1": float(f1.mean()), "classes": [
                {"label": i, "precision": float(precision[i]), "recall": float(recall[i]),
                 "f1": float(f1[i]), "support": int(support[i]), "predicted": int(predicted[i])}
                for i in range(4)], "confusion_matrix": cm.tolist()}


def paired_correctness(y: np.ndarray, reference: np.ndarray, candidate: np.ndarray) -> dict:
    ref_ok, cand_ok = reference == y, candidate == y
    gain = int(np.count_nonzero(~ref_ok & cand_ok))
    loss = int(np.count_nonzero(ref_ok & ~cand_ok))
    return {"n": len(y), "reference_correct": int(ref_ok.sum()), "candidate_correct": int(cand_ok.sum()),
            "newly_correct": gain, "newly_incorrect": loss, "net_additional_correct": gain - loss,
            "micro_delta": float(cand_ok.mean() - ref_ok.mean())}


def day_masks(days: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "1-7": (days >= 1) & (days <= 7),
        "8-30": (days >= 8) & (days <= 30),
        "31-90": (days >= 31) & (days <= 90),
        "91+": days >= 91,
        "0_or_missing": (~np.isfinite(days)) | (days <= 0),
    }


def bootstrap_paired(y: np.ndarray, baseline: np.ndarray, candidate: np.ndarray, fixed_mean: np.ndarray,
                     reps: int, seed: int) -> dict:
    diff_c = ((candidate == y).astype(np.int8) - (baseline == y).astype(np.int8))
    diff_m = ((fixed_mean == y).astype(np.int8) - (baseline == y).astype(np.int8))
    rng = np.random.default_rng(seed)
    draws_c = np.empty(reps, dtype=np.float64)
    draws_m = np.empty(reps, dtype=np.float64)
    n = len(y)
    for start in range(0, reps, 100):
        count = min(100, reps - start)
        index = rng.integers(0, n, size=(count, n), dtype=np.int32)
        draws_c[start:start + count] = diff_c[index].mean(axis=1)
        draws_m[start:start + count] = diff_m[index].mean(axis=1)
    return {"unit": "vessel", "repetitions": reps, "seed": seed, "confidence": 0.95,
            "same_resamples_for_candidate_and_fixed_mean": True,
            "Stacker_Logistic_C1_vs_LightGBM_sqrt_macro": {
                "point_delta_micro_f1": float(diff_c.mean()),
                "ci95_percentile": np.quantile(draws_c, [0.025, 0.975]).tolist()},
            "Fixed_mean_3model_vs_LightGBM_sqrt_macro": {
                "point_delta_micro_f1": float(diff_m.mean()),
                "ci95_percentile": np.quantile(draws_m, [0.025, 0.975]).tolist()},
            "limitation": "Repeated development OUTER data; the interval does not remove selection bias, geographic dependence, or establish independent performance."}


def evaluate(cfg: dict, outer: dict, fitted: dict) -> tuple[dict, list[dict]]:
    ids, years, folds, labels, days = [], [], [], [], []
    probs = {name: [] for name in BASE_MODELS}
    cand_p = []
    for fold in FOLDS:
        d = outer[fold]
        ids.extend(d["ids"]); years.extend(d["year"].tolist()); folds.extend([fold] * len(d["ids"]))
        labels.extend(d["y"].tolist()); days.extend(d["days"].tolist())
        for name in BASE_MODELS:
            probs[name].append(d["base_probabilities"][name])
        with threadpool_limits(limits=1):
            cand_p.append(fitted[fold].predict_proba(np.concatenate([
                np.log(np.clip(d["base_probabilities"][name], cfg["probabilities"]["clip_min"], cfg["probabilities"]["clip_max"]))
                for name in BASE_MODELS], axis=1)))
    y = np.asarray(labels, dtype=np.int64)
    days_arr = np.asarray(days, dtype=np.float64)
    fold_arr = np.asarray(folds, dtype=np.int64)
    base_all = {name: np.concatenate(parts, axis=0) for name, parts in probs.items()}
    mean_all = np.mean(np.stack([base_all[name] for name in BASE_MODELS], axis=0), axis=0)
    candidate_all = np.concatenate(cand_p, axis=0)
    for name, p in {**base_all, "Fixed_mean_3model": mean_all, "Stacker_Logistic_C1": candidate_all}.items():
        assert_probability(p, len(y), 1e-5, f"combined {name}")
    prediction = {name: p.argmax(axis=1) for name, p in {
        **base_all, "Fixed_mean_3model": mean_all, "Stacker_Logistic_C1": candidate_all}.items()}
    full = {name: score_metrics(y, pred) for name, pred in prediction.items()}
    days_report = {}
    masks = day_masks(days_arr)
    for scope, mask in masks.items():
        if np.any(mask):
            days_report[scope] = {name: score_metrics(y[mask], prediction[name][mask]) for name in METHODS}
    fold_report = {}
    for fold in FOLDS:
        mask = fold_arr == fold
        fold_report[str(fold)] = {"n": int(mask.sum()), "methods": {name: score_metrics(y[mask], prediction[name][mask]) for name in METHODS},
            "paired": {name: paired_correctness(y[mask], prediction["LightGBM_sqrt_macro"][mask], prediction[name][mask])
                       for name in ("CatBoost", "TabICL_A_raw", "Fixed_mean_3model", "Stacker_Logistic_C1")}}
    paired = {name: paired_correctness(y, prediction["LightGBM_sqrt_macro"], prediction[name])
              for name in ("Fixed_mean_3model", "Stacker_Logistic_C1")}
    trap_transition = np.bincount(4 * prediction["LightGBM_sqrt_macro"] + prediction["Stacker_Logistic_C1"], minlength=16).reshape(4, 4)
    gate = cfg["evaluation"]["gate"]
    class_delta = [{"label": i,
                    "recall_delta": full["Stacker_Logistic_C1"]["classes"][i]["recall"] - full["LightGBM_sqrt_macro"]["classes"][i]["recall"],
                    "f1_delta": full["Stacker_Logistic_C1"]["classes"][i]["f1"] - full["LightGBM_sqrt_macro"]["classes"][i]["f1"]}
                   for i in range(4)]
    day_delta = {scope: days_report[scope]["Stacker_Logistic_C1"]["micro_f1"] - days_report[scope]["LightGBM_sqrt_macro"]["micro_f1"]
                 for scope in ("1-7", "8-30", "31-90", "91+") if scope in days_report and days_report[scope]["LightGBM_sqrt_macro"]["n"] > 0}
    # Bootstrap is deliberately a joint row-level resample over one OUTER row per vessel.
    bootstrap = bootstrap_paired(y, prediction["LightGBM_sqrt_macro"], prediction["Stacker_Logistic_C1"],
                                 prediction["Fixed_mean_3model"], cfg["evaluation"]["bootstrap"]["repetitions"],
                                 cfg["evaluation"]["bootstrap"]["seed"])
    ci_low = bootstrap["Stacker_Logistic_C1_vs_LightGBM_sqrt_macro"]["ci95_percentile"][0]
    baseline_expected = cfg["evaluation"]["baseline_expected"]
    if (full["LightGBM_sqrt_macro"]["correct"] != baseline_expected["correct"]
            or abs(full["LightGBM_sqrt_macro"]["micro_f1"] - baseline_expected["micro_f1"]) > 1e-12
            or abs(full["LightGBM_sqrt_macro"]["macro_f1"] - baseline_expected["macro_f1"]) > 1e-12):
        raise ValueError("Recomputed baseline does not match frozen round002 development OUTER baseline")
    checks = {
        "candidate_micro_delta_ge_0_005": paired["Stacker_Logistic_C1"]["micro_delta"] >= gate["candidate_micro_delta_min"],
        "candidate_paired_ci_lower_gt_0": ci_low > gate["paired_ci_lower_gt"],
        "candidate_macro_drop_le_0_03": full["Stacker_Logistic_C1"]["macro_f1"] - full["LightGBM_sqrt_macro"]["macro_f1"] >= gate["macro_f1_delta_min"],
        "every_class_recall_drop_le_0_03": all(x["recall_delta"] >= gate["each_class_recall_delta_min"] for x in class_delta),
        "every_class_f1_drop_le_0_03": all(x["f1_delta"] >= gate["each_class_f1_delta_min"] for x in class_delta),
        "each_observed_days_micro_drop_le_0_03": all(v >= gate["each_observed_days_micro_delta_min"] for v in day_delta.values()) and len(day_delta) == 4,
        "provenance_and_reload_pass": True,
    }
    progress_gate_pass = all(checks.values())
    result = {
        "round": "round_020", "status": "completed_development_outer_comparison",
        "scope": "Repeated development OUTER only; no holdout/2025Test/raw F-drive values read.",
        "cohort_year": cfg["dataset"]["cohort_year"], "cohort_year_source": cfg["dataset"]["cohort_year_source"],
        "year_is_rowwise_measured": False,
        "class_order": cfg["dataset"]["class_order"], "rows": len(y),
        "methods": full, "observed_days": days_report, "folds": fold_report,
        "paired_vs_baseline": paired, "paired_bootstrap95": bootstrap,
        "trap_prediction_transition_matrix_baseline_rows_candidate_columns": trap_transition.tolist(),
        "trap_prediction_count_change": int(np.count_nonzero(prediction["Stacker_Logistic_C1"] == 2) - np.count_nonzero(prediction["LightGBM_sqrt_macro"] == 2)),
        "class_recall_f1_deltas_candidate_minus_baseline": class_delta,
        "observed_days_micro_deltas_candidate_minus_baseline": day_delta,
        "progress_gate": {"checks": checks, "pass": progress_gate_pass, "candidate_micro_delta_min": gate["candidate_micro_delta_min"]},
        "development_goal": {"threshold_micro_f1": cfg["evaluation"]["development_goal_micro_f1"],
                              "candidate_reached": full["Stacker_Logistic_C1"]["micro_f1"] >= cfg["evaluation"]["development_goal_micro_f1"]},
        "independent_verified_performance": None, "official_score": None,
        "probability_row_sum_errors": {str(f): outer[f]["max_probability_row_sum_errors"] for f in FOLDS},
        "limitation": "A development OUTER result and paired bootstrap do not establish independent or official performance.",
    }
    rows = []
    all_probs = {**base_all, "Fixed_mean_3model": mean_all, "Stacker_Logistic_C1": candidate_all}
    fold_positions = np.concatenate([np.full(len(outer[f]["ids"]), f, dtype=np.int64) for f in FOLDS])
    for i, vessel in enumerate(ids):
        for method in METHODS:
            p = all_probs[method][i]
            rows.append({"id": vessel, "year": int(years[i]), "fold": int(fold_positions[i]), "role": "OUTER",
                         "model": method, "p0": float(p[0]), "p1": float(p[1]), "p2": float(p[2]), "p3": float(p[3]),
                         "y_true": int(y[i]), "observed_days": float(days_arr[i]) if math.isfinite(float(days_arr[i])) else None})
    return result, rows


def write_predictions_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ("id", "year", "fold", "role", "model", "p0", "p1", "p2", "p3", "y_true", "observed_days")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row[k] is None else row[k]) for k in fields})


def run(cfg: dict, config_path: Path) -> None:
    global PHASE
    start_clock = time.perf_counter()
    paths = source_paths(cfg)
    output_dir = path_from_config(cfg["paths"]["output_dir"])
    PHASE = "verify_prepared_manifest"
    prepared_path = output_dir / "input_manifest.json"
    if not prepared_path.is_file():
        raise FileNotFoundError("Run requires a reviewed --prepare input_manifest.json")
    prepared = read_json(prepared_path)
    current = build_input_manifest(cfg, config_path)
    if current["fingerprint_sha256"] != prepared.get("fingerprint_sha256"):
        raise ValueError("Prepared input manifest no longer matches source/config/code hashes")
    approval = load_approval(cfg, current, config_path)
    PHASE = "load_select_only"
    source_meta = validate_round002_sources(cfg, paths)
    state, prep_audit = prepare_select_state(cfg, paths, source_meta)
    ensure_select_only_probabilities_ready(state)
    prep_audit["select_diagnostics"] = select_diagnostics(cfg, state["select"])
    PHASE = "fit_and_reload_meta_models"
    with threadpool_limits(limits=1):
        fitted, fit_records = fit_and_reload(cfg, state, output_dir, start_clock)
    if len(fit_records) != 3 or not all(x["reload_check_pass"] for x in fit_records):
        raise AssertionError("Exactly three meta models must be saved and reloaded before OUTER access")
    PHASE = "revalidate_approval_before_outer"
    after_fit_manifest = build_input_manifest(cfg, config_path)
    if after_fit_manifest["fingerprint_sha256"] != current["fingerprint_sha256"]:
        raise ValueError("Source/config/code changed between approved fit and OUTER scoring")
    approval = load_approval(cfg, after_fit_manifest, config_path)
    PHASE = "outer_probability_load_after_meta_reload"
    outer = load_outer_after_reload(cfg, paths, state)
    result, rows = evaluate(cfg, outer, fitted)
    result.update({
        "runner_sha256": current["runner_sha256"], "config_sha256": current["config_sha256"],
        "input_manifest_fingerprint_sha256": current["fingerprint_sha256"],
        "input_hashes": {row["path"]: row["sha256"] for row in current["files"]},
        "manager_approval": approval,
        "fit_accounting": {"base_fits": 0, "meta_fits": len(fit_records), "grid_searches": 0,
                           "blend_grid_searches": 0, "retries": 0, "fits_sequential": True,
                           "records": fit_records},
        "source_alignment": {"fit_es_select_outer_roles_verified": True,
                             "all_source_labels_aligned": True, "probability_class_columns_aligned": True,
                             "tabicl_inner_source": "same-fold inner_predictions.csv only",
                             "tabicl_global_oof_used_for_inner": False,
                             "tabicl_global_oof_used_for_outer_only": True,
                             "year_is_cohort_provenance_not_rowwise_measured": True},
        "preflight_scope": prep_audit,
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
                        "scikit_learn": sklearn.__version__, "pid": os.getpid()},
        "elapsed_seconds": time.perf_counter() - start_clock,
    })
    PHASE = "write_outputs"
    write_json(output_dir / "result.json", result)
    write_predictions_csv(output_dir / "outer_predictions_long.csv", rows)
    write_json(output_dir / "select_audit.json", {"round": "round_020", "status": "SELECT_ONLY_PREPARED_AND_RUN",
                "input_manifest_fingerprint_sha256": current["fingerprint_sha256"], "folds": prep_audit["folds"],
                "select_diagnostics": prep_audit["select_diagnostics"], "outer_probability_values_loaded_after_reload": True})
    print(json.dumps({"status": result["status"], "candidate_micro_f1": result["methods"]["Stacker_Logistic_C1"]["micro_f1"],
                      "candidate_correct": result["methods"]["Stacker_Logistic_C1"]["correct"],
                      "progress_gate_pass": result["progress_gate"]["pass"],
                      "development_goal_reached": result["development_goal"]["candidate_reached"],
                      "result": str(output_dir / "result.json"),
                      "predictions": str(output_dir / "outer_predictions_long.csv")}, ensure_ascii=False))


def write_select_raw_probabilities(cfg: dict, state: dict, output_dir: Path) -> None:
    rows = []
    for fold in FOLDS:
        d = state["select"][fold]
        for i, vessel in enumerate(d["ids"]):
            for model_name, p in d["base_probabilities"].items():
                rows.append({"id": vessel, "year": int(cfg["dataset"]["cohort_year"]), "fold": fold,
                             "role": "INNER_SELECT", "model": model_name,
                             "p0": float(p[i, 0]), "p1": float(p[i, 1]),
                             "p2": float(p[i, 2]), "p3": float(p[i, 3]),
                             "y_true": int(d["y"][i]),
                             "observed_days": float(d["days"][i]) if math.isfinite(float(d["days"][i])) else None})
    write_predictions_csv(output_dir / "select_raw_probabilities.csv", rows)


def fit_baseline_only(cfg: dict, config_path: Path) -> None:
    """Fit/reload only the frozen 12-feature baseline; no spatial or OUTER access."""
    global PHASE
    start_clock = time.perf_counter()
    output_dir = path_from_config(cfg["paths"]["output_dir"])
    prepared_path = output_dir / "input_manifest.json"
    if not prepared_path.is_file():
        raise FileNotFoundError("Baseline fit requires a reviewed/prepared input_manifest.json")
    current = build_input_manifest(cfg, config_path)
    prepared = read_json(prepared_path)
    if current["fingerprint_sha256"] != prepared.get("fingerprint_sha256"):
        raise ValueError("Prepared source/config/runner manifest no longer matches current baseline stage")
    approval = load_approval(cfg, current, config_path)
    PHASE = "baseline_select_only_alignment"
    paths = source_paths(cfg)
    source_meta = validate_round002_sources(cfg, paths)
    state, audit = prepare_select_state(cfg, paths, source_meta)
    ensure_select_only_probabilities_ready(state)
    write_select_raw_probabilities(cfg, state, output_dir)
    PHASE = "baseline_fit_save_reload"
    fitted, fit_records = fit_and_reload(cfg, state, output_dir, start_clock)
    if len(fit_records) != 3 or not all(r["reload_check_pass"] for r in fit_records):
        raise AssertionError("Baseline requires exactly three saved/reloaded fold models")
    result = {"round": "round_021", "status": "baseline_12_fit_reloaded_select_only",
              "fits": {"base_fits": 0, "meta_fits": 3, "candidate_fits": 0,
                       "grid_searches": 0, "retries": 0},
              "scope": "INNER_SELECT only; spatial extraction and all OUTER probability values excluded",
              "input_manifest_fingerprint_sha256": current["fingerprint_sha256"],
              "runner_sha256": current["runner_sha256"], "config_sha256": current["config_sha256"],
              "approval": approval, "fit_records": fit_records,
              "select_rows": sum(len(state["select"][f]["ids"]) for f in FOLDS),
              "select_raw_probability_csv": str(output_dir / "select_raw_probabilities.csv"),
              "select_audit": audit["folds"], "elapsed_seconds": time.perf_counter() - start_clock,
              "outer_probability_values_loaded": False, "historical_rows_loaded": False}
    write_json(output_dir / "baseline_fit.json", result)
    print(json.dumps({"status": result["status"], "meta_fits": 3,
                      "all_reload_checks_pass": True, "outer_probability_values_loaded": False,
                      "result": str(output_dir / "baseline_fit.json")}, ensure_ascii=False))


def main() -> int:
    global PHASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="metadata and INNER_SELECT only; zero fits and no OUTER probability load")
    mode.add_argument("--fit-baseline", action="store_true", help="requires reviewed manager approval; three 12-feature SELECT-only fits/reloads")
    mode.add_argument("--run", action="store_true", help="legacy path temporarily disabled until all six Round021 models are frozen")
    args = parser.parse_args()
    config_path = args.config.resolve()
    try:
        cfg = read_json(config_path)
        if cfg.get("experiment") != "round_021_seed42_stacker12_vs_spatial20":
            raise ValueError("Unexpected Round021 config identity")
        if args.prepare:
            prepare(cfg, config_path)
        elif args.fit_baseline:
            fit_baseline_only(cfg, config_path)
        else:
            raise RuntimeError("--run is disabled: Round021 requires staged baseline, spatial candidate, then one OUTER evaluation")
        return 0
    except Exception as exc:
        out = path_from_config(read_json(config_path)["paths"]["output_dir"])
        write_json(out / "run_failure.json", {"round": "round_021", "status": "failed", "phase": PHASE,
                    "time_utc": utc_now(), "pid": os.getpid(), "error_type": type(exc).__name__,
                    "error": str(exc), "traceback": traceback.format_exc(),
                    "retry_count": 0, "fits_started_by_exception_handler": 0})
        print(json.dumps({"status": "failed", "phase": PHASE, "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
