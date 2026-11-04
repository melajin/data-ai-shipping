"""Independent, read-only verification for the single approved round005 export.

Do not run until the manager confirms the exporter has completed. This reads only
the fold-0 development NPZ, ID-only split metadata, development role/label
metadata, frozen preprocessing metadata, and the resulting FIT/INNER context.
It does not load a model/checkpoint, train, infer, score, or access protected rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True


ROOT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final")
BASE = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING")
REPO = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104")
EXP = REPO / "artifacts" / "exp01"
P = BASE / "29-30일 모델 심층 분석" / "31일" / "팀원자료" / "TabICLv2_F156_공유자료"
PRECHECK = ROOT / "rounds" / "round_004" / "review" / "context_precheck.json"
AMENDMENT = ROOT / "rounds" / "round_005" / "PLAN_AMENDMENT_01.md"
OUT = ROOT / "rounds" / "round_005" / "review" / "independent_context_check.json"
NPZ_ANCHOR = "858688c0bd690eb82612a1d940b6cc002a31ee33d3acb2c322f176e28152de95"
EXPECTED = {"fit": 3144, "inner": 787, "development": 5897, "holdout_ids": 1475}


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def digest_json(value) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def digest_numeric_sorted_newline(values) -> str:
    """Frozen membership format: numeric sort, LF separators, no trailing LF."""
    ordered = [str(value) for value in sorted(int(v) for v in values)]
    return sha_bytes("\n".join(ordered).encode("utf-8"))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--context",
        type=Path,
        default=ROOT / "rounds" / "round_005" / "artifacts" / "context_export_attempt_001" / "fold0_seed42_context.npz",
    )
    parser.add_argument(
        "--result",
        type=Path,
        default=ROOT / "rounds" / "round_005" / "artifacts" / "context_export_attempt_001" / "export_result.json",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    context_path = args.context.resolve()
    result_path = args.result.resolve()
    out_path = args.out.resolve()
    root_resolved = ROOT.resolve()
    require(context_path.is_relative_to(root_resolved), "context input must be inside the task root")
    require(result_path.is_relative_to(root_resolved), "result input must be inside the task root")
    require(out_path.is_relative_to(root_resolved), "review output must be inside the task root")
    require(context_path.is_file(), "context NPZ not found")
    require(result_path.is_file(), "export result JSON not found")
    require(PRECHECK.is_file(), "round004 independent precheck not found")
    require(AMENDMENT.is_file(), "round005 hash-semantics amendment not found")

    result = read_json(result_path)
    require(result.get("status") in {"CONTEXT_READY", "PASS"}, "export is not marked complete")
    require(result.get("scope", {}).get("model_or_checkpoint_loaded") is False, "model/checkpoint flag is not false")
    require(result.get("scope", {}).get("training") is False, "training flag is not false")
    require(result.get("scope", {}).get("inference") is False, "inference flag is not false")
    require(result.get("scope", {}).get("F1_computed") is False, "F1 flag is not false")

    split_path = P / "splits" / "splits_original.json"
    rule_path = P / "evaluation" / "final_fixed_decision_rule.json"
    parent_path = P / "evaluation" / "seed_42" / "parent_fingerprint.json"
    vocab_path = P / "metadata" / "fold_0" / "vocabulary_state.json"
    prep_path = P / "evaluation" / "seed_42" / "fold_0" / "preprocessor.json"
    roles_path = P / "splits" / "development_roles_long.csv"
    roster_path = EXP / "fixed_split_roster.csv"
    source_npz_path = EXP / "fold_0_features.npz"
    feature_path = P / "metadata" / "feature_columns.json"
    classes_path = P / "metadata" / "classes.json"

    input_paths = {
        "split_manifest": split_path,
        "decision_rule": rule_path,
        "parent_fingerprint": parent_path,
        "fold0_vocabulary_state": vocab_path,
        "seed42_fold0_preprocessor": prep_path,
        "P_development_roles": roles_path,
        "exp01_development_roster": roster_path,
        "exp01_fold0_npz": source_npz_path,
        "P_feature_columns": feature_path,
        "P_classes": classes_path,
    }
    actual_hashes = {key: sha_file(path) for key, path in input_paths.items()}
    stored_inputs = result.get("inputs", {})
    require(actual_hashes["exp01_fold0_npz"] == NPZ_ANCHOR, "development NPZ source bytes differ from reviewed anchor")
    require(stored_inputs.get("exp01_fold0_npz", {}).get("sha256") == actual_hashes["exp01_fold0_npz"], "source NPZ bytehash differs from export record")
    for key, actual in actual_hashes.items():
        require(stored_inputs.get(key, {}).get("sha256") == actual, f"source hash differs from export record: {key}")

    # The split file contains ID metadata only. Holdout IDs are used only for a
    # disjointness check; no protected features, labels, or probabilities load.
    manifest = read_json(split_path)
    development_ids = manifest.get("development_ids")
    holdout_ids = manifest.get("holdout_ids")
    require(isinstance(development_ids, list) and len(development_ids) == EXPECTED["development"], "development ID metadata count mismatch")
    require(isinstance(holdout_ids, list) and len(holdout_ids) == EXPECTED["holdout_ids"], "holdout ID metadata count mismatch")
    dev_set, holdout_set = set(development_ids), set(holdout_ids)
    require(not (dev_set & holdout_set), "development and holdout ID metadata overlap")
    folds = [f for f in manifest.get("folds", []) if isinstance(f, dict) and f.get("fold") == 0]
    require(len(folds) == 1, "fold0 split metadata missing or duplicated")
    fold = folds[0]
    fit_ids = list(fold.get("fit_ids", []))
    inner_ids = list(fold.get("inner_ids", []))
    outer_ids = list(fold.get("outer_ids", []))
    require(len(fit_ids) == EXPECTED["fit"] and len(set(fit_ids)) == EXPECTED["fit"], "ordered FIT IDs count/uniqueness mismatch")
    require(len(inner_ids) == EXPECTED["inner"] and len(set(inner_ids)) == EXPECTED["inner"], "ordered INNER IDs count/uniqueness mismatch")
    require(len(outer_ids) == 1966 and len(set(outer_ids)) == 1966, "fold0 OUTER ID metadata count/uniqueness mismatch")
    role_sets = [set(fit_ids), set(inner_ids), set(outer_ids)]
    require(not (role_sets[0] & role_sets[1] or role_sets[0] & role_sets[2] or role_sets[1] & role_sets[2]), "fold0 FIT/INNER/OUTER ID sets overlap")
    require(set.union(*role_sets) == dev_set, "fold0 FIT/INNER/OUTER membership does not cover development IDs")

    rule = read_json(rule_path)
    rule_rows = [row for row in rule.get("inner_choices", []) if row.get("seed") == 42 and row.get("fold") == 0]
    require(len(rule_rows) == 1, "frozen rule lacks unique seed42/fold0 INNER digest")
    frozen_inner_digest = rule_rows[0].get("inner_ids_sha256")
    frozen_fit_digest = rule_rows[0].get("fit_ids_sha256")
    inner_membership_digest = digest_numeric_sorted_newline(inner_ids)
    fit_membership_digest = digest_numeric_sorted_newline(fit_ids)
    ordered_inner_json_digest = digest_json(inner_ids)
    ordered_fit_json_digest = digest_json(fit_ids)
    require(inner_membership_digest == frozen_inner_digest, "numeric-sorted newline INNER membership digest does not match frozen rule")
    require(fit_membership_digest == frozen_fit_digest, "numeric-sorted newline FIT membership digest does not match frozen rule")
    # Frozen-v4 evidence establishes that these use different semantics. Record
    # the one expected ordered-vs-membership mismatch; do not try alternatives.
    require(ordered_inner_json_digest != frozen_inner_digest, "ordered INNER JSON digest unexpectedly equals frozen membership digest")
    manifest_hash = actual_hashes["split_manifest"]
    require(rule.get("split_manifest_sha256") == manifest_hash, "manifest hash is not bound by frozen rule")
    parent = read_json(parent_path)
    split_hashes = [value for key, value in parent.get("input_lineage", {}).get("files", {}).items() if key.lower().endswith("work\\splits.json")]
    require(split_hashes == [manifest_hash], "manifest hash is not uniquely bound by parent fingerprint")

    expected_first2_digest = digest_json(inner_ids[:2])
    sequence = result.get("split_sequence", {})
    require(sequence.get("inner_membership_digest_expected") == frozen_inner_digest, "export frozen INNER membership digest differs")
    require(sequence.get("inner_membership_digest_actual") == inner_membership_digest, "export INNER membership digest differs")
    require(sequence.get("inner_membership_digest_match") is True, "export record does not attest frozen INNER membership match")
    require(sequence.get("fit_membership_digest_expected") == frozen_fit_digest, "export frozen FIT membership digest differs")
    require(sequence.get("fit_membership_digest_actual") == fit_membership_digest, "export FIT membership digest differs")
    require(sequence.get("fit_membership_digest_match") is True, "export record does not attest frozen FIT membership match")
    require(sequence.get("inner_ordered_json_digest") == ordered_inner_json_digest, "export ordered INNER JSON digest differs")
    require(sequence.get("fit_ordered_json_digest") == ordered_fit_json_digest, "export ordered FIT JSON digest differs")
    require(sequence.get("inner_ordered_base_digest_vs_frozen_match") is False, "export does not record expected ordered/frozen digest mismatch")
    require(sequence.get("fit_membership_vocab_hash_match") is True, "export FIT vocabulary check mismatch")
    require(sequence.get("future_query_ids_first2") == inner_ids[:2], "fixed query IDs are not the first two original INNER IDs")

    freeze_record = result.get("frozen_queries", {})
    require(freeze_record.get("query_ids") == inner_ids[:2], "frozen query IDs are not original INNER prefix")
    require(freeze_record.get("query_ids_digest_json_sha256") == expected_first2_digest, "frozen query ID digest mismatch")
    require(freeze_record.get("full_inner_ids_digest_json_sha256") == ordered_inner_json_digest, "frozen full INNER order digest mismatch")
    require(freeze_record.get("reference_probability_rows_read") == 0, "export read reference probabilities before query freeze")
    query_freeze_path = result_path.parent / "query_freeze.json"
    require(query_freeze_path.is_file(), "separate query freeze record is missing")
    require(read_json(query_freeze_path) == freeze_record, "query freeze file and export record differ")

    vocab = read_json(vocab_path)["provenance"]
    require(vocab.get("fit_id_count") == EXPECTED["fit"], "FIT vocabulary count mismatch")
    require(vocab.get("fit_ids_sha256") == digest_json(sorted(set(fit_ids))), "FIT vocabulary sorted-string BASE JSON fingerprint mismatch")

    p_roles = [r for r in read_csv(roles_path) if int(r["outer_fold"]) == 0]
    roster = [r for r in read_csv(roster_path) if int(r["fold"]) == 0]
    role_map = {r["rfid_id"]: r["role"].upper() for r in p_roles}
    roster_map = {r["rfid_id"]: (r["role"].upper(), int(r["y_true"])) for r in roster}
    for ids, role in ((fit_ids, "FIT"), (inner_ids, "INNER")):
        require(all(role_map.get(rid) == role for rid in ids), f"P role mapping mismatch for {role}")
        require(all(roster_map.get(rid, (None, None))[0] == role for rid in ids), f"exp01 role mapping mismatch for {role}")
    require(all(role_map.get(rid) == "OUTER" for rid in outer_ids), "P role mapping mismatch for OUTER")
    require(all(roster_map.get(rid, (None, None))[0] == "OUTER" for rid in outer_ids), "exp01 role mapping mismatch for OUTER")

    feature_names_raw = read_json(feature_path)
    feature_names_raw = [str(x) for x in feature_names_raw]
    class_map = read_json(classes_path)
    expected_classes = [str(class_map[str(i)]) for i in range(4)]
    prep = read_json(prep_path)
    medians = np.asarray(prep.get("median"), dtype=np.float64)
    require(prep.get("kind") == "fit_median_and_raw_missing_flags", "saved preprocessing kind mismatch")
    require(len(feature_names_raw) == 156 and medians.shape == (156,), "F156 feature/median length mismatch")
    expected_feature_names = feature_names_raw + [f"{name}__missing_flag" for name in feature_names_raw]

    # Independently regenerate the arrays from the pinned fold-0 development
    # NPZ and the original ordered split manifest lists.
    with np.load(source_npz_path, allow_pickle=False) as source:
        src_ids = source["rfid_ids"].astype(str)
        src_labels = source["y"].astype(np.int64)
        src_roles = source["roles"].astype(str)
        raw_x = source["X"]
        src_names = source["feature_names"].astype(str).tolist()
        require(raw_x.shape == (EXPECTED["development"], 304), "development NPZ shape mismatch")
        require(src_names[:156] == feature_names_raw, "source F156 columns do not match metadata order")
        require(len(set(src_ids.tolist())) == EXPECTED["development"], "source development IDs are duplicated")
        require(set(src_ids.tolist()) == dev_set, "source NPZ membership differs from development ID metadata")
        row_by_id = {rid: i for i, rid in enumerate(src_ids.tolist())}
        fit_idx = np.asarray([row_by_id[rid] for rid in fit_ids], dtype=np.int64)
        inner_idx = np.asarray([row_by_id[rid] for rid in inner_ids], dtype=np.int64)
        require(all(src_roles[i] == "FIT" for i in fit_idx), "source NPZ FIT role mismatch")
        require(all(src_roles[i] == "INNER" for i in inner_idx), "source NPZ INNER role mismatch")
        y_fit = src_labels[fit_idx].copy()
        y_inner = src_labels[inner_idx].copy()
        require(all(roster_map[rid][1] == int(y) for rid, y in zip(fit_ids, y_fit)), "FIT labels differ from development roster")
        require(all(roster_map[rid][1] == int(y) for rid, y in zip(inner_ids, y_inner)), "INNER labels differ from development roster")

        fit_raw = np.asarray(raw_x[fit_idx, :156], dtype=np.float64).copy()
        fit_raw[~np.isfinite(fit_raw)] = np.nan
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            independently_fit_medians = np.nanmedian(fit_raw, axis=0)
        median_delta = np.abs(independently_fit_medians - medians)
        require(np.isfinite(median_delta).all() and float(median_delta.max()) <= 1e-10, "saved medians differ from independently recomputed FIT medians")

        def transform(indices):
            raw = np.asarray(raw_x[indices, :156], dtype=np.float64).copy()
            raw[~np.isfinite(raw)] = np.nan
            missing = ~np.isfinite(raw)
            imputed = np.where(missing, medians, raw)
            return np.c_[imputed, missing.astype(float)].astype(np.float32), missing, raw

        expected_x_fit, fit_missing, fit_raw = transform(fit_idx)
        expected_x_inner, inner_missing, inner_raw = transform(inner_idx)
        require(expected_x_fit.shape == (EXPECTED["fit"], 312), "recomputed FIT shape mismatch")
        require(expected_x_inner.shape == (EXPECTED["inner"], 312), "recomputed INNER shape mismatch")
        require(np.isfinite(expected_x_fit).all() and np.isfinite(expected_x_inner).all(), "recomputed arrays contain non-finite values")

    with np.load(context_path, allow_pickle=False) as exported:
        exported_fit_ids = exported["ids_fit"].astype(str).tolist()
        exported_inner_ids = exported["ids_inner"].astype(str).tolist()
        exported_fit = exported["X_fit"]
        exported_inner = exported["X_inner"]
        exported_y_fit = exported["y_fit"].astype(np.int64)
        exported_y_inner = exported["y_inner"].astype(np.int64)
        exported_features = exported["feature_names"].astype(str).tolist()
        exported_classes = exported["class_names"].astype(str).tolist()
        require(int(exported["fold"]) == 0 and int(exported["seed"]) == 42, "context fold/seed mismatch")

    require(exported_fit_ids == fit_ids, "exported FIT ordered IDs mismatch")
    require(exported_inner_ids == inner_ids, "exported INNER ordered IDs mismatch")
    require(np.array_equal(exported_y_fit, y_fit), "exported FIT labels/order mismatch")
    require(np.array_equal(exported_y_inner, y_inner), "exported INNER labels/order mismatch")
    require(exported_features == expected_feature_names, "exported feature names/order mismatch")
    require(exported_classes == expected_classes, "exported class names/order mismatch")
    require(exported_fit.dtype == np.float32 and exported_inner.dtype == np.float32, "exported dtype is not float32")
    require(np.array_equal(exported_fit, expected_x_fit), "exported FIT transformed bytes/values differ")
    require(np.array_equal(exported_inner, expected_x_inner), "exported INNER transformed bytes/values differ")

    arrays_record = result.get("arrays", {})
    for key, values in (("X_fit", expected_x_fit), ("X_inner", expected_x_inner)):
        rec = arrays_record.get(key, {})
        expected_hash = sha_bytes(values.tobytes(order="C"))
        require(rec.get("shape") == list(values.shape), f"recorded {key} shape mismatch")
        require(rec.get("dtype") == "float32", f"recorded {key} dtype mismatch")
        require(rec.get("sha256_C_order") == expected_hash, f"recorded {key} bytehash mismatch")
    require(arrays_record.get("ids_fit_digest_json_sha256") == digest_json(fit_ids), "recorded FIT ordered ID hash mismatch")
    require(arrays_record.get("ids_inner_digest_json_sha256") == digest_json(inner_ids), "recorded INNER ordered ID hash mismatch")

    actual_context_hash = sha_file(context_path)
    output_record = result.get("outputs", {}).get("context_npz", {})
    require(output_record.get("sha256") == actual_context_hash, "context NPZ hash differs from export record")
    require(output_record.get("bytes") == context_path.stat().st_size, "context NPZ byte size differs from export record")
    require(result.get("outputs", {}).get("query_freeze", {}).get("sha256") == sha_file(query_freeze_path), "query freeze bytehash differs from export record")

    source_record = result.get("source", {})
    source_path = Path(source_record.get("path", "")).resolve()
    require(source_path.is_relative_to(root_resolved) and source_path.is_file(), "exporter source path is missing or outside task root")
    source_at_launch_hash = sha_file(source_path)
    require(source_record.get("source_at_launch_sha256") == source_at_launch_hash, "exporter source-at-launch hash differs from current code")
    require(source_record.get("source_hash_captured_at_process_start") is True, "source hash capture timing is not recorded")

    # Check several concrete cells without disclosing their values: missing raw
    # cells must become their FIT median with a 1 flag; observed cells retain
    # their source value and receive a 0 flag.
    sampled_missing = 0
    sampled_observed = 0
    for expected, raw, missing in ((expected_x_fit, fit_raw, fit_missing), (expected_x_inner, inner_raw, inner_missing)):
        miss_coords = np.argwhere(missing)[:25]
        obs_coords = np.argwhere(~missing)[:25]
        for row, col in miss_coords:
            require(expected[row, col] == np.float32(medians[col]), "sample imputation does not equal saved FIT median")
            require(expected[row, 156 + col] == np.float32(1.0), "sample missing flag is not set")
        for row, col in obs_coords:
            require(expected[row, col] == np.float32(raw[row, col]), "sample observed value changed")
            require(expected[row, 156 + col] == np.float32(0.0), "sample observed missing flag is set")
        sampled_missing += len(miss_coords)
        sampled_observed += len(obs_coords)
    require(sampled_missing > 0 and sampled_observed > 0, "sample check did not find missing and observed cells")

    # Independently cross-check every stored per-cell illustration without
    # copying its sensitive numeric values into the reviewer report.
    stored_samples = result.get("lineage", {}).get("transform_samples", [])
    require(len(stored_samples) == 6, "export has an unexpected number of imputation sample cells")
    for sample in stored_samples:
        row = int(sample["fit_row_position"])
        col = int(sample["feature_index"])
        is_missing = bool(fit_missing[row, col])
        require(bool(sample["source_is_missing"]) == is_missing, "stored sample missingness differs from source")
        require(bool(sample["source_value_finite"]) == bool(np.isfinite(fit_raw[row, col])), "stored sample finite-state differs from source")
        require(float(sample["saved_fit_median"]) == float(medians[col]), "stored sample median differs from saved FIT median")
        require(float(sample["exported_imputed_value"]) == float(expected_x_fit[row, col]), "stored sample imputation differs from recomputation")
        require(float(sample["exported_missing_flag"]) == float(expected_x_fit[row, 156 + col]), "stored sample flag differs from recomputation")

    report = {
        "schema": "round005_independent_context_check.v1",
        "status": "PASS",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_script_sha256": sha_file(Path(__file__).resolve()),
        "scope": {
            "source_rows": "fold0 development NPZ only",
            "protected_feature_label_probability_rows_read": 0,
            "holdout_id_metadata_used_only_for_disjointness": True,
            "model_or_checkpoint_loaded": False,
            "training_or_inference": False,
            "F1_or_accuracy_computed": False,
        },
        "source_sha256": actual_hashes,
        "review_basis_sha256": {
            "round004_context_precheck": sha_file(PRECHECK),
            "round005_plan_amendment": sha_file(AMENDMENT),
            "exporter_source": source_at_launch_hash,
        },
        "split_and_order": {
            "fit_count": len(fit_ids),
            "inner_count": len(inner_ids),
            "development_holdout_id_sets_disjoint": True,
            "fold0_fit_inner_outer_sets_pairwise_disjoint": True,
            "fold0_roles_cover_development_ids": True,
            "frozen_numeric_sorted_newline_fit_inner_membership_match": True,
            "ordered_fit_json_digest": ordered_fit_json_digest,
            "ordered_inner_json_digest": ordered_inner_json_digest,
            "ordered_inner_digest_vs_frozen_expected_mismatch": True,
            "fit_vocabulary_membership_match": True,
            "query_first2_digest": expected_first2_digest,
            "query_first2_are_original_inner_prefix": True,
            "ordered_ids_printed": False,
        },
        "arrays": {
            "X_fit": {"shape": list(expected_x_fit.shape), "dtype": str(expected_x_fit.dtype), "C_order_sha256": sha_bytes(expected_x_fit.tobytes(order="C")), "exact_export_match": True},
            "X_inner": {"shape": list(expected_x_inner.shape), "dtype": str(expected_x_inner.dtype), "C_order_sha256": sha_bytes(expected_x_inner.tobytes(order="C")), "exact_export_match": True},
            "labels_and_roles_order_match": True,
            "feature_name_and_class_order_match": True,
            "max_abs_saved_median_delta": float(median_delta.max()),
            "sampled_missing_cells_checked": sampled_missing,
            "sampled_observed_cells_checked": sampled_observed,
            "context_file_sha256": actual_context_hash,
            "query_freeze_sha256": sha_file(query_freeze_path),
        },
        "export_result_sha256": sha_file(result_path),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "fit": len(fit_ids), "inner": len(inner_ids), "protected_rows_read": 0, "report": str(out_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
