from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final")
REPO = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104")
EXP01 = REPO / "artifacts" / "exp01"
P = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료")
OUT = ROOT / "rounds" / "round_004" / "lineage"
SEEDS = (42, 2026)
FOLDS = (0, 1, 2)
CLASSES = ("연안복합", "자망", "통발", "채낚기연승")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def finite_median(x: np.ndarray) -> np.ndarray:
    # Match NumPy nanmedian semantics: omit NaNs; all-NaN columns -> NaN.
    with np.errstate(all="ignore"):
        return np.nanmedian(x.astype(np.float64, copy=False), axis=0)


def main() -> None:
    checks: dict[str, Any] = {}
    mismatches: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    paths: dict[str, Path] = {}

    def add_source(label: str, path: Path) -> None:
        paths[label] = path
        hashes[label] = sha256(path)

    # Contract and source metadata only. No source CSV rows or protected files are loaded.
    round2_config_path = ROOT / "rounds" / "round_002" / "configs" / "experiment.json"
    round2_config = read_json(round2_config_path)
    add_source("round_002_config", round2_config_path)
    p_columns_path = P / "metadata" / "feature_columns.json"
    p_columns = read_json(p_columns_path)
    add_source("P_feature_columns", p_columns_path)
    p_dictionary_path = P / "metadata" / "F156_feature_dictionary.csv"
    p_dictionary_rows = read_csv(p_dictionary_path)
    add_source("P_F156_feature_dictionary", p_dictionary_path)
    p_classes_path = P / "metadata" / "classes.json"
    p_classes = read_json(p_classes_path)
    add_source("P_classes", p_classes_path)
    p_run_settings_path = P / "metadata" / "run_settings.json"
    p_run_settings = read_json(p_run_settings_path)
    add_source("P_run_settings", p_run_settings_path)
    p_rebuild_path = P / "code" / "rebuild_features.py"
    p_rebuild_code = p_rebuild_path.read_text(encoding="utf-8-sig")
    add_source("P_feature_rebuild_code", p_rebuild_path)

    exp_source_paths = {
        "exp01_data_adapter": REPO / "shared" / "data_adapter.py",
        "exp01_eval_contract": REPO / "shared" / "eval_contract.py",
        "exp01_experiment": REPO / "configs" / "exp01" / "experiment.json",
    }
    exp_source_text = {k: p.read_text(encoding="utf-8-sig") for k, p in exp_source_paths.items()}
    for label, path in exp_source_paths.items():
        add_source(label, path)

    expected_npz_hashes = round2_config["input"]["fold_sha256"]
    npz_observations: dict[str, Any] = {}
    roster_rows = read_csv(EXP01 / "fixed_split_roster.csv")
    roster_path = EXP01 / "fixed_split_roster.csv"
    add_source("exp01_development_roster", roster_path)
    p_roles_path = P / "splits" / "development_roles_long.csv"
    p_role_rows = read_csv(p_roles_path)
    add_source("P_development_roles_long", p_roles_path)

    # Validate roster uniqueness and the role table against the NPZ row order.
    roster_by_fold: dict[int, list[dict[str, str]]] = {}
    for row in roster_rows:
        fold = int(row["fold"])
        roster_by_fold.setdefault(fold, []).append(row)
    p_role_by_fold: dict[int, list[dict[str, str]]] = {}
    for row in p_role_rows:
        fold = int(row["outer_fold"])
        p_role_by_fold.setdefault(fold, []).append(row)

    role_order_checks: dict[str, Any] = {}
    label_checks: dict[str, Any] = {}
    feature_order_checks: dict[str, Any] = {}
    median_checks: dict[str, Any] = {}
    vocabulary_checks: dict[str, Any] = {}
    all_first156_exact = True
    all_roles_labels_order_exact = True

    p_col_list = [str(c) for c in p_columns]
    dict_col_list = [row["feature"] for row in p_dictionary_rows]
    dict_positions = [int(row["position_0based"]) for row in p_dictionary_rows]
    metadata_definition_order_exact = (
        len(p_col_list) == 156
        and len(dict_col_list) == 156
        and dict_positions == list(range(156))
        and p_col_list == dict_col_list
    )
    if not metadata_definition_order_exact:
        mismatches.append({"type": "P_metadata_feature_order", "detail": "feature_columns.json and dictionary order differ or are not 156"})

    expected_feature_count = int(round2_config["input"]["feature_count"])
    expected_components = round2_config["input"]["features_in_order"]
    class_order_config = round2_config["input"]["class_order"]
    p_class_order = [p_classes[str(i)] for i in range(4)]
    p_declares_no_missing_flags = "no missing flags" in p_run_settings.get("fit_preprocess", "").lower()

    for fold in FOLDS:
        npz_path = EXP01 / f"fold_{fold}_features.npz"
        label = f"exp01_fold_{fold}_features_npz"
        add_source(label, npz_path)
        actual_hash = hashes[label]
        expected_hash = expected_npz_hashes[str(fold)]
        if actual_hash != expected_hash:
            mismatches.append({"type": "round002_NPZ_hash", "fold": fold, "expected": expected_hash, "actual": actual_hash})
        with np.load(npz_path, allow_pickle=False) as z:
            keys = sorted(z.files)
            expected_keys = sorted(["fold", "rfid_ids", "y", "roles", "X", "feature_names", "obs_days"])
            stored_fold = int(z["fold"])
            ids = z["rfid_ids"].astype(str)
            y = z["y"].astype(np.int64)
            roles = z["roles"].astype(str)
            x = z["X"].astype(np.float64, copy=False)
            names = z["feature_names"].astype(str).tolist()
            obs_days = z["obs_days"].astype(np.float64)

        fold_roster = roster_by_fold.get(fold, [])
        fold_roles = p_role_by_fold.get(fold, [])
        roster_ids = [r["rfid_id"] for r in fold_roster]
        p_ids = [r["rfid_id"] for r in fold_roles]
        p_roles = [r["role"].upper() for r in fold_roles]
        p_folds = [int(r["outer_fold"]) for r in fold_roles]
        row_order_equal = ids.tolist() == roster_ids == p_ids
        roles_equal = roles.tolist() == [r["role"].upper() for r in fold_roster] == p_roles
        label_equal = y.tolist() == [int(r["y_true"]) for r in fold_roster]
        shapes_ok = (stored_fold == fold and len(ids) == 5897 and x.shape == (5897, 304)
                     and len(names) == 304 and len(y) == len(roles) == len(obs_days) == len(ids))
        key_set_ok = keys == expected_keys
        if not key_set_ok:
            mismatches.append({"type": "NPZ_key_set", "fold": fold, "expected": expected_keys, "actual": keys})
        if not shapes_ok:
            mismatches.append({"type": "NPZ_shapes_or_fold", "fold": fold, "shape": list(x.shape), "rows": len(ids), "stored_fold": stored_fold})
        if not row_order_equal:
            mismatches.append({"type": "development_row_order", "fold": fold, "npz_rows": len(ids), "exp_roster_rows": len(roster_ids), "P_role_rows": len(p_ids), "first_divergence": next((i for i, pair in enumerate(zip(ids.tolist(), roster_ids, p_ids)) if len(set(pair)) != 1), None)})
        if not roles_equal:
            mismatches.append({"type": "development_role_order", "fold": fold})
        if not label_equal:
            mismatches.append({"type": "NPZ_label_roster_mapping", "fold": fold})
        all_roles_labels_order_exact &= row_order_equal and roles_equal and label_equal

        first156_equal = names[:156] == p_col_list
        if not first156_equal:
            first_divergence = next((i for i, pair in enumerate(zip(names[:156], p_col_list)) if pair[0] != pair[1]), None)
            mismatches.append({"type": "first156_names_order", "fold": fold, "first_divergence": first_divergence,
                               "exp01_name": names[first_divergence] if first_divergence is not None else None,
                               "P_name": p_col_list[first_divergence] if first_divergence is not None else None})
        all_first156_exact &= first156_equal

        expected_extra_counts = [156, 10, 68, 70]
        extra_names = names[156:]
        feature_order_checks[str(fold)] = {
            "npz_key_set_exact": key_set_ok,
            "matrix_shape": list(x.shape),
            "total_ordered_feature_names": len(names),
            "P_F156_name_order_exact_first156": first156_equal,
            "extra_148_names_by_exp01_contract": {"T5": 10, "behavior_without_obs_days": 68, "local_rel": 70},
            "extra_columns_not_part_of_P_F156": len(extra_names) == 148,
            "all_names_unique": len(names) == len(set(names)),
            "all_finite_or_nan_no_inf": bool(not np.isinf(x).any()),
            "component_contract_from_round002": expected_components,
        }

        roster_n = len(fold_roster)
        fit_mask = roles == "FIT"
        fit_count = int(fit_mask.sum())
        if fit_count != 3144 and fold != 2 or fit_count != 3145 and fold == 2:
            mismatches.append({"type": "FIT_row_count", "fold": fold, "actual": fit_count})
        actual_counts = {name: int(np.sum(y == i)) for i, name in enumerate(CLASSES)}
        vocabulary_path = P / "metadata" / f"fold_{fold}" / "vocabulary_state.json"
        vocabulary = read_json(vocabulary_path)
        add_source(f"P_fold_{fold}_vocabulary_state", vocabulary_path)
        vocab_mode_names = [f"vocabulary_mode{i}__day_fraction" for i in range(16)]
        vocab_mode_names += [f"vocabulary_mode{i}__stay_probability" for i in range(16)]
        expected_vocab_positions = [p_col_list.index(n) for n in vocab_mode_names if n in p_col_list]
        vocab_meta = vocabulary.get("provenance", {})
        vocab_fit_count = int(vocab_meta.get("fit_id_count", -1))
        vocabulary_checks[str(fold)] = {
            "P_vocab_metadata_present": True,
            "fit_id_count_metadata": vocab_fit_count,
            "fit_id_sha256_metadata_present": bool(vocab_meta.get("fit_ids_sha256")),
            "mode_feature_names_present_in_P_F156": len(expected_vocab_positions) == 32,
            "mode_feature_indices": expected_vocab_positions,
            "NPZ_uses_same_feature_names_and_fold_specific_schema": first156_equal,
            "semantic_equal_of_vocabulary_values_independently_replayed": False,
        }

        npz_observations[str(fold)] = {
            "sha256": actual_hash,
            "expected_round002_sha256": expected_hash,
            "hash_matches_round002": actual_hash == expected_hash,
            "keys": keys,
            "shapes": {"rfid_ids": list(ids.shape), "y": list(y.shape), "roles": list(roles.shape),
                       "X": list(x.shape), "feature_names": [len(names)], "obs_days": list(obs_days.shape)},
            "dtypes": {"rfid_ids": str(ids.dtype), "y": str(y.dtype), "roles": str(roles.dtype),
                       "X": str(x.dtype), "feature_names": "str", "obs_days": str(obs_days.dtype)},
            "development_roster_rows": roster_n,
            "P_development_role_rows": len(fold_roles),
            "row_order_exact_NPZ_vs_exp01_vs_P_roles": row_order_equal,
            "roles_exact": roles_equal,
            "label_mapping_exact_to_exp01_development_roster": label_equal,
            "label_counts_by_config_class_order": actual_counts,
            "role_counts": {r: int(np.sum(roles == r)) for r in ["FIT", "INNER", "OUTER"]},
            "FIT_count": fit_count,
            "obs_days_nonfinite_count": int((~np.isfinite(obs_days)).sum()),
        }

        if metadata_definition_order_exact and first156_equal and row_order_equal and roles_equal and label_equal:
            for seed in SEEDS:
                prep_path = P / "evaluation" / f"seed_{seed}" / f"fold_{fold}" / "preprocessor.json"
                prep = read_json(prep_path)
                add_source(f"P_seed_{seed}_fold_{fold}_preprocessor", prep_path)
                saved_medians = np.asarray(prep["median"], dtype=np.float64)
                if len(saved_medians) != 156:
                    mismatches.append({"type": "preprocessor_median_count", "seed": seed, "fold": fold, "actual": int(len(saved_medians))})
                    continue
                npz_medians = finite_median(x[fit_mask, :156])
                delta = npz_medians - saved_medians
                abs_delta = np.abs(delta)
                finite = np.isfinite(abs_delta)
                mismatch_idx = np.flatnonzero(~finite | (abs_delta > 1e-10))
                median_checks[f"seed_{seed}_fold_{fold}"] = {
                    "preprocessor_kind": prep.get("kind"),
                    "saved_median_count": int(len(saved_medians)),
                    "npz_FIT_rows": fit_count,
                    "numpy_nanmedian_from_NPZ_FIT_vs_saved_abs_tol_1e-10": len(mismatch_idx) == 0,
                    "max_abs_delta": float(np.nanmax(abs_delta)) if finite.any() else None,
                    "mismatch_count": int(len(mismatch_idx)),
                    "first_mismatches": [
                        {"index": int(i), "feature": names[i], "npz_fit_nanmedian": float(npz_medians[i]),
                         "saved_preprocessor_median": float(saved_medians[i]), "abs_delta": float(abs_delta[i])}
                        for i in mismatch_idx[:10]
                    ],
                }
                if len(mismatch_idx):
                    mismatches.append({"type": "FIT_median_mismatch", "seed": seed, "fold": fold,
                                       "count": int(len(mismatch_idx)), "max_abs_delta": float(np.nanmax(abs_delta))})
        else:
            median_checks[f"fold_{fold}"] = {"status": "not_run", "reason": "exact feature definition/order/role/label mapping gate not satisfied"}

    # Metadata source definition/order, class order and pipeline shape.
    exp_schema = read_json(exp_source_paths["exp01_experiment"])
    p_class_mapping_equal = p_class_order == list(exp_schema["model"]["class_order"])
    if not p_class_mapping_equal:
        mismatches.append({"type": "class_order", "P": p_class_order, "exp01": exp_schema["model"]["class_order"]})
    # DFs are represented in source adapter code by direct first-block loading from F156_train.csv.
    adapter = exp_source_text["exp01_data_adapter"]
    exp_source_f156_direct = (
        '("F156", f156.index.tolist(), f156[fcols].to_numpy(dtype=np.float64), fcols)' in adapter
        and 'feature_names = tuple(fcols + tcols + bcols + lcols)' in adapter
        and "expected 156 F156 columns" in adapter
    )
    p_rebuild_contract = (
        "metadata/feature_columns.json" in p_rebuild_code
        and "scope = 'production' if a.fold is None else f'fold{a.fold}'" in p_rebuild_code
        and "t[cols].sort_index()" in p_rebuild_code
    )
    if not exp_source_f156_direct:
        mismatches.append({"type": "exp01_F156_source_contract", "detail": "source no longer expresses direct F156 block in first columns"})
    if not p_rebuild_contract:
        mismatches.append({"type": "P_rebuild_source_contract", "detail": "expected metadata-driven ordered output/fold vocabulary scope not found"})

    round2_feature_count = int(round2_config["input"]["feature_count"])
    result = {
        "task": "Round 004 development-only input lineage audit",
        "status": "PASS_WITH_LIMITATIONS" if not mismatches else "MISMATCHES_FOUND",
        "scope": {
            "authorized_reads": ["P code/metadata", "P seed_42/seed_2026 per-fold preprocessor/training/parent_fingerprint metadata", "exp01 fold NPZs", "exp01 development roster", "P development roles roster", "round_002 frozen config"],
            "prohibited_reads_performed": {"full7372_F156_rows": 0, "train_labels_rows": 0, "components_train_rows": 0, "holdout_ids_or_rows": 0, "Test2025_rows": 0, "raw_rows": 0},
            "model_loads": 0,
            "training_calls": 0,
            "inference_calls": 0,
            "F1_or_performance_computations": 0,
        },
        "contracts": {
            "round002_config_sha256": hashes["round_002_config"],
            "round002_feature_count": round2_feature_count,
            "round002_components": expected_components,
            "exp01_source_direct_F156_first_block": exp_source_f156_direct,
            "P_metadata_feature_definitions_and_order_exact": metadata_definition_order_exact,
            "P_F156_count": len(p_col_list),
            "P_F156_dictionary_row_count": len(p_dictionary_rows),
            "P_class_order_matches_exp01": p_class_mapping_equal,
            "P_run_settings_says_no_missing_flags": p_declares_no_missing_flags,
            "P_preprocessor_is_156_medians": all(v.get("preprocessor_kind") == "fit_median_and_raw_missing_flags" and v.get("saved_median_count") == 156 for v in median_checks.values()) if median_checks else None,
            "expected_TabICL_width_from_saved_contract": 312 if p_declares_no_missing_flags is False else "contradictory: settings says no flags, saved preprocessors/code append flags",
        },
        "npz_folds": npz_observations,
        "feature_order_checks": feature_order_checks,
        "role_row_order_and_labels_exact_all_folds": all_roles_labels_order_exact,
        "all_first156_feature_names_exact": all_first156_exact and metadata_definition_order_exact,
        "vocabulary_checks": vocabulary_checks,
        "fit_median_comparisons": median_checks,
        "mismatches": mismatches,
        "source_input_sha256": hashes,
        "commands": [
            "python rounds/round_004/lineage/audit_input_lineage.py",
            "Only the script itself, result.json, and LINEAGE_REPORT.md are written under rounds/round_004/lineage.",
        ],
        "check_counts": {
            "folds": len(FOLDS),
            "seed_fold_preprocessor_comparisons": len(median_checks),
            "protected_row_sources_read": 0,
            "npz_hashes_verified": sum(bool(v["hash_matches_round002"]) for v in npz_observations.values()),
            "first156_name_orders_verified": sum(bool(v["P_F156_name_order_exact_first156"]) for v in feature_order_checks.values()),
            "FIT_median_mismatches": sum(v.get("mismatch_count", 0) for v in median_checks.values()),
        },
    }
    (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["check_counts"], "mismatches": mismatches}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
