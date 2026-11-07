from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np


ROOT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final")
P = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
EXP = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
ROUND = ROOT / "rounds" / "round_005"
FOLD = 0
SEED = 42
EXPECTED_CLASSES = ["연안복합", "자망", "통발", "채낚기연승낚시"]
EXPECTED_NPZ_SHA256 = "858688c0bd690eb82612a1d940b6cc002a31ee33d3acb2c322f176e28152de95"
EXPECTED_HASHES = {
    "split_manifest": "b99a81c7573acbc65ab4b8780790dfc2377252893a0947ac760eedc510dae686",
    "decision_rule": "ce491771be71327d6ba18388e55828c6f153a374bd4c8fb6b91b0cf6f019557f",
    "parent_fingerprint": "64b992fb807b4ada967d641279c625e5640865997234d38c003f179cb9b25475",
    "fold0_vocabulary_state": "402f44fd2fe8bfef82709452b5678a17cea40d302d1eac61731f96a61665397d",
    "seed42_fold0_preprocessor": "eea7d15bd4f0610450600502fcfb36d584a6f5324f26b6b325c3014d10065740",
    "P_development_roles": "4c27dc2d3591c864cc9db8cf1defdc38540e68cd404fbbfe118be73f01efef00",
    "exp01_development_roster": "9639abbeccf5335e8baa8f0c8c165c319da453615e410674d28e4410e355e29f",
    "exp01_fold0_npz": EXPECTED_NPZ_SHA256,
    "P_run_settings": "e951067a229cf41056bd1d5d73bc46fa688430b84bae255ed79950e3ea6cb85f",
    "P_comparison_models_source": "f818c0f2c3bb79cd80781a4df22c3d6cca425528fc3e3df4a08e55324d914251",
    "P_split_generator_source": "fa2297714250f39492abde98f762e5859e64f18766d9bde68f8df2360bd67262",
    "P_BASE_digest_json_source": "d9054e929ad67ea11d32b8c4dab59ee63b2896320efdcb65557d888a46a6c381",
}
CONFIG = {
    "fold": FOLD,
    "seed": SEED,
    "allowed_source_root": str(P),
    "development_npz_sha256": EXPECTED_NPZ_SHA256,
    "fit_rows": 3144,
    "inner_rows": 787,
    "outer_rows": 1966,
    "features_raw": 156,
    "features_exported": 312,
    "classes": EXPECTED_CLASSES,
    "query_policy": "first two row IDs in ordered fold0 inner_ids; frozen before probability access",
    "transform": "FIT saved medians; raw-column missing flags; C-order float32",
}
SOURCE_AT_LAUNCH_SHA256 = None
SOURCE_AT_LAUNCH_UTC = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_json(value) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def numeric_sorted_newline_digest(ids) -> str:
    """Frozen membership convention: numeric sort, normalized integer text, no trailing newline."""
    return sha_bytes("\n".join(str(int(value)) for value in sorted(ids, key=int)).encode("utf-8"))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def atomic_npz(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def build(output_dir: Path) -> dict:
    source_path = Path(__file__).resolve()
    source_at_start_sha256 = SOURCE_AT_LAUNCH_SHA256 or sha_file(source_path)
    source_at_start_utc = SOURCE_AT_LAUNCH_UTC or utc_now()
    output_dir = output_dir.resolve()
    if not output_dir.is_relative_to(ROUND.resolve()):
        raise ValueError("export output must remain under rounds/round_005")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [output_dir / "fold0_seed42_context.npz", output_dir / "query_freeze.json",
               output_dir / "export_result.json"]
    if any(path.exists() for path in outputs):
        raise FileExistsError("immutable export attempt already has an output; choose a new attempt directory")

    paths = {
        "split_manifest": P / "splits" / "splits_original.json",
        "decision_rule": P / "evaluation" / "final_fixed_decision_rule.json",
        "parent_fingerprint": P / "evaluation" / "seed_42" / "parent_fingerprint.json",
        "fold0_vocabulary_state": P / "metadata" / "fold_0" / "vocabulary_state.json",
        "seed42_fold0_preprocessor": P / "evaluation" / "seed_42" / "fold_0" / "preprocessor.json",
        "P_development_roles": P / "splits" / "development_roles_long.csv",
        "exp01_development_roster": EXP / "fixed_split_roster.csv",
        "exp01_fold0_npz": EXP / "fold_0_features.npz",
        "P_feature_columns": P / "metadata" / "feature_columns.json",
        "P_classes": P / "metadata" / "classes.json",
        "P_run_settings": P / "metadata" / "run_settings.json",
        "P_comparison_models_source": next((P / "code" / "historical" / "TabM").glob("*/comparison_models.py")),
        "P_split_generator_source": next((P / "code" / "historical" / "TabM").glob("*/run_experiments.py")),
        "P_BASE_digest_json_source": next((P / "code" / "historical" / "TinyTabM").glob("*/fishing_tiny_tabm.py")),
        "round003_v4_idhash_result": ROOT / "rounds" / "round_003" / "verification_20261105" / "v4_idhash.json",
        "round004_replay_contract": ROOT / "rounds" / "round_004" / "runtime_author" / "replay_contract.json",
    }
    p_names = {"split_manifest", "decision_rule", "parent_fingerprint", "fold0_vocabulary_state",
               "seed42_fold0_preprocessor", "P_development_roles", "P_feature_columns", "P_classes",
               "P_run_settings", "P_comparison_models_source", "P_split_generator_source",
               "P_BASE_digest_json_source"}
    exp_names = {"exp01_development_roster", "exp01_fold0_npz"}
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"required source missing: {name}")
        resolved = path.resolve()
        if name in p_names and not resolved.is_relative_to(P.resolve()):
            raise ValueError(f"unexpected P input location for {name}")
        if name in exp_names and not resolved.is_relative_to(EXP.resolve()):
            raise ValueError(f"unexpected exp01 input location for {name}")
        if name == "round003_v4_idhash_result" and not resolved.is_relative_to((ROOT / "rounds" / "round_003").resolve()):
            raise ValueError("v4 idhash record must remain inside the project root")
        if name == "round004_replay_contract" and not resolved.is_relative_to((ROOT / "rounds" / "round_004").resolve()):
            raise ValueError("replay contract must remain inside the project root")
    inputs = {name: {"path": str(path), "sha256": sha_file(path), "bytes": path.stat().st_size}
              for name, path in paths.items()}
    for name, expected in EXPECTED_HASHES.items():
        if name in {"P_feature_columns", "P_classes"}:
            continue
        if inputs[name]["sha256"] != expected:
            raise ValueError(f"pinned input SHA256 mismatch: {name}")

    split = read_json(paths["split_manifest"])
    if not isinstance(split, dict) or not isinstance(split.get("folds"), list):
        raise ValueError("split manifest schema mismatch")
    if not isinstance(split.get("development_ids"), list) or not isinstance(split.get("holdout_ids"), list):
        raise ValueError("split manifest development/holdout ID schema mismatch")
    dev_ids = split["development_ids"]
    holdout_ids = split["holdout_ids"]
    if (len(dev_ids) != 5897 or not all(isinstance(x, str) for x in dev_ids)
            or len(set(dev_ids)) != len(dev_ids)):
        raise ValueError("development ID count/type/uniqueness check failed")
    if (len(holdout_ids) != 1475 or not all(isinstance(x, str) for x in holdout_ids)
            or len(set(holdout_ids)) != len(holdout_ids)):
        raise ValueError("holdout ID metadata count/type/uniqueness check failed")
    if set(dev_ids) & set(holdout_ids):
        raise ValueError("development/holdout manifest ID sets overlap")
    folds = [entry for entry in split["folds"] if isinstance(entry, dict) and entry.get("fold") == FOLD]
    if len(folds) != 1:
        raise ValueError("fold0 entry missing or duplicated")
    fold = folds[0]
    expected_counts = {"fit_ids": 3144, "inner_ids": 787, "outer_ids": 1966}
    fold_ids = {}
    for key, count in expected_counts.items():
        ids = fold.get(key)
        if not isinstance(ids, list) or len(ids) != count or not all(isinstance(x, str) for x in ids) \
                or len(set(ids)) != count:
            raise ValueError(f"fold0 {key} count/type/uniqueness check failed")
        fold_ids[key] = list(ids)
    role_sets = [set(fold_ids[key]) for key in expected_counts]
    if role_sets[0] & role_sets[1] or role_sets[0] & role_sets[2] or role_sets[1] & role_sets[2]:
        raise ValueError("fold0 FIT/INNER/OUTER IDs are not pairwise disjoint")
    if set.union(*role_sets) != set(dev_ids):
        raise ValueError("fold0 FIT/INNER/OUTER union is not exactly the development ID set")
    fit_ids = fold_ids["fit_ids"]
    inner_ids = fold_ids["inner_ids"]

    rule = read_json(paths["decision_rule"])
    rule_entries = [row for row in rule.get("inner_choices", [])
                    if row.get("seed") == SEED and row.get("fold") == FOLD]
    if len(rule_entries) != 1:
        raise ValueError("frozen rule has no unique seed42/fold0 INNER digest")
    frozen_fit_membership = rule_entries[0].get("fit_ids_sha256")
    frozen_inner_membership = rule_entries[0].get("inner_ids_sha256")
    actual_fit_membership = numeric_sorted_newline_digest(fit_ids)
    actual_inner_membership = numeric_sorted_newline_digest(inner_ids)
    ordered_fit_base_digest = digest_json(fit_ids)
    ordered_inner_base_digest = digest_json(inner_ids)
    # Perform exactly one direct ordered digest comparison to diagnose the old contract ambiguity.
    # Membership is checked separately using the serialization recovered in v4_idhash.json.
    ordered_inner_matches_frozen = ordered_inner_base_digest == frozen_inner_membership
    if ordered_inner_matches_frozen:
        raise ValueError("ordered BASE JSON digest unexpectedly equals frozen numeric-membership digest")
    recovered = read_json(paths["round003_v4_idhash_result"]).get("recovered", {})
    recovered_fit = recovered.get("fit/fold0", {})
    recovered_inner = recovered.get("inner/fold0", {})
    expected_serialization = "sorted_int_as_int|newline"
    if (recovered_fit.get("serialization") != expected_serialization
            or recovered_fit.get("source") != "splits_original.json folds[0][fit_ids]"
            or recovered_fit.get("n") != len(fit_ids)
            or recovered_inner.get("serialization") != expected_serialization
            or recovered_inner.get("source") != "splits_original.json folds[0][inner_ids]"
            or recovered_inner.get("n") != len(inner_ids)):
        raise ValueError("ID-only v4 digest record does not show the expected fold0 membership serialization")
    if (actual_fit_membership != recovered_fit.get("sha256")
            or actual_inner_membership != recovered_inner.get("sha256")
            or actual_fit_membership != frozen_fit_membership
            or actual_inner_membership != frozen_inner_membership):
        raise ValueError("fold0 FIT/INNER numeric-sorted newline membership digest mismatch")
    if rule.get("split_manifest_sha256") != inputs["split_manifest"]["sha256"]:
        raise ValueError("split manifest SHA does not match frozen rule")
    parent = read_json(paths["parent_fingerprint"])
    parent_hashes = [v for k, v in parent.get("input_lineage", {}).get("files", {}).items()
                     if k.lower().endswith("work\\splits.json")]
    if len(parent_hashes) != 1 or parent_hashes[0] != inputs["split_manifest"]["sha256"]:
        raise ValueError("parent fingerprint does not bind the exact split manifest SHA")

    vocab = read_json(paths["fold0_vocabulary_state"]).get("provenance", {})
    # The vocabulary source computes BASE.digest_json(sorted(set(map(str, fit_ids))));
    # validate that separate membership contract rather than reuse the frozen-rule serialization.
    vocabulary_fit_digest = digest_json(sorted(set(map(str, fit_ids))))
    if vocab.get("fit_id_count") != len(fit_ids) or vocab.get("fit_ids_sha256") != vocabulary_fit_digest:
        raise ValueError("fold0 FIT membership differs from frozen vocabulary fingerprint")
    p_roles = [row for row in read_csv(paths["P_development_roles"]) if int(row["outer_fold"]) == FOLD]
    roster = [row for row in read_csv(paths["exp01_development_roster"]) if int(row["fold"]) == FOLD]
    role_map = {row["rfid_id"]: row["role"].upper() for row in p_roles}
    roster_map = {row["rfid_id"]: (row["role"].upper(), int(row["y_true"])) for row in roster}
    if len(role_map) != len(p_roles) or len(roster_map) != len(roster):
        raise ValueError("fold0 role/roster IDs are duplicated")
    if set(role_map) != set(dev_ids) or set(roster_map) != set(dev_ids):
        raise ValueError("fold0 filtered role/roster IDs do not equal development IDs")

    classes_raw = read_json(paths["P_classes"])
    class_names = [classes_raw[str(index)] for index in range(4)]
    if class_names != EXPECTED_CLASSES:
        raise ValueError("canonical class order differs from the frozen four-class order")
    feature_columns = [str(value) for value in read_json(paths["P_feature_columns"])]
    prep = read_json(paths["seed42_fold0_preprocessor"])
    medians = np.asarray(prep["median"], dtype=np.float64)
    if len(feature_columns) != 156 or len(medians) != 156 or prep.get("kind") != "fit_median_and_raw_missing_flags":
        raise ValueError("F156 saved median/missing-flag contract mismatch")
    median_sha256 = sha_bytes(np.ascontiguousarray(medians, dtype=np.float64).tobytes())

    with np.load(paths["exp01_fold0_npz"], allow_pickle=False) as data:
        npz_ids = data["rfid_ids"].astype(str)
        labels = data["y"].astype(np.int64)
        roles = data["roles"].astype(str)
        source_x = data["X"]
        names = data["feature_names"].astype(str).tolist()
        if source_x.shape != (5897, 304) or names[:156] != feature_columns:
            raise ValueError("development NPZ shape or first-156 feature-name contract mismatch")
        if len(npz_ids) != 5897 or len(set(npz_ids.tolist())) != 5897 or set(npz_ids.tolist()) != set(dev_ids):
            raise ValueError("development NPZ ID set is not exactly the manifest development set")
        if np.any(labels < 0) or np.any(labels > 3):
            raise ValueError("development NPZ contains a label outside frozen classes [0..3]")
        if len(roles) != len(npz_ids):
            raise ValueError("development NPZ role vector shape mismatch")
        index = {rid: i for i, rid in enumerate(npz_ids.tolist())}
        fit_idx = np.asarray([index[rid] for rid in fit_ids], dtype=np.int64)
        inner_idx = np.asarray([index[rid] for rid in inner_ids], dtype=np.int64)
        for key, expected_role in (("fit_ids", "FIT"), ("inner_ids", "INNER"), ("outer_ids", "OUTER")):
            if any(role_map[rid] != expected_role or roster_map[rid][0] != expected_role
                   for rid in fold_ids[key]):
                raise ValueError(f"P/exp01 fold0 {expected_role} role disagreement")
        if any(roles[index[rid]] != role_map[rid] for rid in dev_ids):
            raise ValueError("development NPZ role vector differs from P role mapping")
        y_fit = labels[fit_idx].copy()
        y_inner = labels[inner_idx].copy()
        if any(roster_map[rid][1] != int(label) for rid, label in zip(fit_ids, y_fit)) \
                or any(roster_map[rid][1] != int(label) for rid, label in zip(inner_ids, y_inner)):
            raise ValueError("NPZ FIT/INNER labels disagree with development roster")

        def transform(row_indices):
            raw = np.asarray(source_x[row_indices, :156], dtype=np.float64).copy()
            raw[~np.isfinite(raw)] = np.nan
            missing = ~np.isfinite(raw)
            imputed = np.where(missing, medians, raw)
            return np.ascontiguousarray(np.c_[imputed, missing.astype(np.float32)], dtype=np.float32), raw, missing

        X_fit, raw_fit, missing_fit = transform(fit_idx)
        X_inner, raw_inner, missing_inner = transform(inner_idx)
    if X_fit.shape != (3144, 312) or X_inner.shape != (787, 312):
        raise ValueError("transformed tensor dimensions mismatch")
    if not np.isfinite(X_fit).all() or not np.isfinite(X_inner).all():
        raise ValueError("transformed tensors contain non-finite values")
    feature_names = feature_columns + [f"{name}__missing_flag" for name in feature_columns]

    context_path = output_dir / "fold0_seed42_context.npz"
    atomic_npz(context_path, fold=np.int64(FOLD), seed=np.int64(SEED),
               ids_fit=np.asarray(fit_ids, dtype=str), ids_inner=np.asarray(inner_ids, dtype=str),
               X_fit=X_fit, X_inner=X_inner, y_fit=y_fit, y_inner=y_inner,
               feature_names=np.asarray(feature_names, dtype=str), class_names=np.asarray(class_names, dtype=str))
    context_sha = sha_file(context_path)
    query_ids = inner_ids[:2]
    freeze = {
        "schema": "round005_frozen_inner_queries.v1",
        "fold": FOLD,
        "seed": SEED,
        "selection": "first two IDs in the original ordered fold0 inner_ids list; selected before any reference-probability access",
        "query_ids": query_ids,
        "query_ids_digest_json_sha256": digest_json(query_ids),
        "full_inner_ids_digest_json_sha256": ordered_inner_base_digest,
        "context_npz_sha256": context_sha,
        "reference_probability_rows_read": 0,
        "source_manifest_sha256": inputs["split_manifest"]["sha256"],
        "created_utc": utc_now(),
    }
    atomic_json(output_dir / "query_freeze.json", freeze)

    sample_cells = []
    for row_index in (0, 1):
        for feature_index in (0, 78, 155):
            sample_cells.append({
                "fit_row_position": row_index,
                "feature_index": feature_index,
                "feature_name": feature_columns[feature_index],
                "source_is_missing": bool(missing_fit[row_index, feature_index]),
                "source_value_finite": bool(np.isfinite(raw_fit[row_index, feature_index])),
                "saved_fit_median": float(medians[feature_index]),
                "exported_imputed_value": float(X_fit[row_index, feature_index]),
                "exported_missing_flag": float(X_fit[row_index, 156 + feature_index]),
            })
    settings_hash = sha_bytes(json.dumps(CONFIG, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    result = {
        "schema": "round005_context_export_result.v1",
        "status": "CONTEXT_READY",
        "scope": {"fold": FOLD, "seed": SEED, "development_only": True,
                  "fit_rows": len(fit_ids), "inner_rows": len(inner_ids), "outer_ids_used_for_partition_checks_only": 1966,
                  "holdout_feature_label_probability_rows_loaded": 0,
                  "holdout_id_metadata_seen_for_disjointness_only": True,
                  "model_or_checkpoint_loaded": False, "training": False, "inference": False,
                  "F1_computed": False},
        "source": {"path": str(source_path), "source_at_launch_sha256": source_at_start_sha256,
                   "source_hash_captured_at_process_start": True,
                   "source_hash_captured_utc": source_at_start_utc,
                   "settings_sha256": settings_hash, "configuration": CONFIG},
        "inputs": inputs,
        "lineage": {"source_split_manifest_sha256": inputs["split_manifest"]["sha256"],
                    "frozen_rule_manifest_sha256_match": True,
                    "seed42_parent_manifest_sha256_match": True,
                    "fit_membership_vocab_hash_match": True,
                    "fold_roles_pairwise_disjoint": True,
                    "fold_role_union_equals_development_ids": True,
                    "development_npz_ids_exactly_match_manifest": True,
                    "filtered_role_and_roster_ids_unique_and_complete": True,
                    "fit_order_source": "split manifest fit_ids order used by source .loc[fold['fit_ids']]",
                    "frozen_membership_serializer": "numeric-sorted normalized integer IDs joined by LF; no trailing LF",
                    "frozen_fit_membership_expected": frozen_fit_membership,
                    "frozen_fit_membership_actual": actual_fit_membership,
                    "frozen_inner_membership_expected": frozen_inner_membership,
                    "frozen_inner_membership_actual": actual_inner_membership,
                    "v4_fit_membership_record": recovered_fit,
                    "v4_inner_membership_record": recovered_inner,
                    "vocabulary_membership_serializer": "BASE.digest_json(sorted(set(map(str, fit_ids)))) per vocabulary_features.py",
                    "vocabulary_fit_membership_expected": vocab.get("fit_ids_sha256"),
                    "vocabulary_fit_membership_actual": vocabulary_fit_digest,
                    "ordered_ids_serializer": "BASE.digest_json: json.dumps(value, sort_keys=True, ensure_ascii=False), UTF-8 SHA256",
                    "ordered_fit_ids_digest": ordered_fit_base_digest,
                    "ordered_inner_ids_digest": ordered_inner_base_digest,
                    "direct_ordered_inner_vs_frozen_membership_match": ordered_inner_matches_frozen,
                    "direct_ordered_vs_membership_mismatch_expected": not ordered_inner_matches_frozen,
                    "feature_contract": "156 raw columns + 156 FIT-median imputations' raw missing flags",
                    "saved_median_float64_sha256": median_sha256,
                    "transform_samples": sample_cells},
        "split_sequence": {
            "fit_membership_digest_expected": frozen_fit_membership,
            "fit_membership_digest_actual": actual_fit_membership,
            "fit_membership_digest_match": actual_fit_membership == frozen_fit_membership,
            "inner_membership_digest_expected": frozen_inner_membership,
            "inner_membership_digest_actual": actual_inner_membership,
            "inner_membership_digest_match": actual_inner_membership == frozen_inner_membership,
            "fit_ordered_json_digest": ordered_fit_base_digest,
            "inner_ordered_json_digest": ordered_inner_base_digest,
            "inner_ordered_base_digest_vs_frozen_match": ordered_inner_matches_frozen,
            "fit_membership_vocab_hash_match": vocab.get("fit_ids_sha256") == vocabulary_fit_digest,
            "future_query_ids_first2": query_ids,
            "fit_ids_sha256": digest_json(fit_ids),
            "inner_ids_sha256": digest_json(inner_ids),
        },
        "arrays": {"X_fit": {"shape": list(X_fit.shape), "dtype": str(X_fit.dtype),
                               "sha256_C_order": sha_bytes(X_fit.tobytes(order="C"))},
                   "X_inner": {"shape": list(X_inner.shape), "dtype": str(X_inner.dtype),
                                 "sha256_C_order": sha_bytes(X_inner.tobytes(order="C"))},
                   "y_fit": {"shape": list(y_fit.shape), "dtype": str(y_fit.dtype),
                             "values_range": [int(y_fit.min()), int(y_fit.max())]},
                   "y_inner": {"shape": list(y_inner.shape), "dtype": str(y_inner.dtype),
                               "values_range": [int(y_inner.min()), int(y_inner.max())]},
                   "ids_fit_digest_json_sha256": digest_json(fit_ids),
                   "ids_inner_digest_json_sha256": digest_json(inner_ids),
                   "ids_fit_sha256": digest_json(fit_ids),
                   "ids_inner_sha256": digest_json(inner_ids),
                   "feature_names_sha256": digest_json(feature_names),
                   "class_names": class_names},
        "frozen_queries": freeze,
        "outputs": {"context_npz": {"path": str(context_path), "bytes": context_path.stat().st_size,
                                     "sha256": context_sha},
                    "query_freeze": {"path": str(output_dir / "query_freeze.json"),
                                     "sha256": sha_file(output_dir / "query_freeze.json")}},
        "command": [sys.executable, "-B", str(Path(__file__).resolve()), "--output-dir", str(output_dir)],
        "pid": os.getpid(),
    }
    atomic_json(output_dir / "export_result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path,
                        default=ROUND / "artifacts" / "context_export_attempt_001")
    args = parser.parse_args()
    start = time.perf_counter()
    receipt_path = args.output_dir.resolve() / "export_result.json"
    try:
        result = build(args.output_dir)
        result["elapsed_seconds"] = time.perf_counter() - start
        result["finished_utc"] = utc_now()
        atomic_json(receipt_path, result)
        print(json.dumps({"status": result["status"], "fit_rows": 3144, "inner_rows": 787,
                          "ordered_inner_ids_preserved": True,
                          "frozen_inner_membership_match": result["split_sequence"]["inner_membership_digest_match"],
                          "frozen_query_digest": result["frozen_queries"]["query_ids_digest_json_sha256"]},
                         ensure_ascii=False), flush=True)
    except Exception as exc:
        if args.output_dir.resolve().is_relative_to(ROUND.resolve()) and not receipt_path.exists():
            atomic_json(receipt_path, {"schema": "round005_context_export_result.v1", "status": "FAILED",
                                       "pid": os.getpid(), "source_at_launch_sha256": sha_file(Path(__file__).resolve()),
                                       "error_type": type(exc).__name__, "error": str(exc),
                                       "traceback": traceback.format_exc(), "elapsed_seconds": time.perf_counter() - start,
                                       "finished_utc": utc_now()})
        raise


if __name__ == "__main__":
    SOURCE_AT_LAUNCH_SHA256 = sha_file(Path(__file__).resolve())
    SOURCE_AT_LAUNCH_UTC = utc_now()
    main()
