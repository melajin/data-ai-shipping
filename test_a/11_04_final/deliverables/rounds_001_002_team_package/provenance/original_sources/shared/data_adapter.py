"""Read-only source adapter and fixed-fold feature cache builder for exp01.

This module imports no original project modules. It reads existing CSV caches and
writes only the caller-selected experiment artifact directory.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from eval_contract import (
    CLASS_NAMES, CLASS_TO_INDEX, FEATURE_COMPONENTS, FOLDS, N_FEATURES,
    validate_class_order,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ORIGINAL_RESULTS_ROOT = Path(
    r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과"
)
RAW_DATA_ROOT = Path(r"F:\문제 데이터_수정_1027")
DEFAULT_TEAM_ROOT = ORIGINAL_RESULTS_ROOT.parent / "31일" / "팀원자료" / "TabICLv2_F156_공유자료"
DEFAULT_WORK_ROOT = REPOSITORY_ROOT / "11월 4일" / "work"
DEFAULT_T5_ROOT = ORIGINAL_RESULTS_ROOT / "outputs" / "f156_merge" / "for_teammate"
DEFAULT_ARTIFACTS = REPOSITORY_ROOT / "coach" / "gpt" / "rank1_experiments_20261104" / "artifacts" / "exp01"
DEFAULT_REPORTS = REPOSITORY_ROOT / "coach" / "gpt" / "rank1_experiments_20261104" / "reports" / "exp01"


@dataclass(frozen=True)
class PreparedFold:
    fold: int
    rfid_ids: np.ndarray
    y: np.ndarray
    roles: np.ndarray
    X: np.ndarray
    feature_names: tuple[str, ...]
    obs_days: np.ndarray


def validate_feature_join(target_ids, feature_blocks):
    """Align feature blocks to one fixed vessel order and reject unsafe joins.

    Each block is `(name, block_ids, values, feature_names)`. Extra rows in a
    source block are allowed, but every target vessel must exist exactly once.
    NaNs are preserved for LightGBM; infinities and duplicate columns are rejected.
    Returns `(X, ordered_feature_names, per_block_validation_summary)`.
    """
    target = [str(r) for r in target_ids]
    if not target or len(target) != len(set(target)):
        raise ValueError("target vessel IDs must be nonempty and unique")
    matrices = []
    all_names = []
    summaries = {}
    for block_name, block_ids_raw, values, columns_raw in feature_blocks:
        block_ids = [str(r) for r in block_ids_raw]
        columns = [str(c) for c in columns_raw]
        array = np.asarray(values, dtype=np.float64)
        if array.ndim != 2 or array.shape != (len(block_ids), len(columns)):
            raise ValueError(f"{block_name}: IDs/feature names do not match matrix shape {array.shape}")
        if len(block_ids) != len(set(block_ids)):
            raise ValueError(f"{block_name}: duplicate source vessel IDs")
        if len(columns) != len(set(columns)):
            raise ValueError(f"{block_name}: duplicate feature names")
        missing = set(target) - set(block_ids)
        if missing:
            raise ValueError(f"{block_name}: {len(missing)} target vessels missing, e.g. {sorted(missing)[:3]}")
        positions = {rid: i for i, rid in enumerate(block_ids)}
        aligned = array[np.fromiter((positions[rid] for rid in target), dtype=np.int64, count=len(target))]
        if np.isinf(aligned).any():
            raise ValueError(f"{block_name}: aligned features contain infinite values")
        overlap = set(all_names) & set(columns)
        if overlap:
            raise ValueError(f"{block_name}: feature names collide: {sorted(overlap)[:5]}")
        matrices.append(aligned)
        all_names.extend(columns)
        summaries[str(block_name)] = {
            "target_rows": len(target), "source_rows": len(block_ids),
            "extra_source_rows": len(set(block_ids) - set(target)),
            "missing_target_rows": 0, "columns": len(columns),
            "aligned_nan_values": int(np.isnan(aligned).sum()),
        }
    if not matrices:
        raise ValueError("at least one feature block is required")
    return np.concatenate(matrices, axis=1), tuple(all_names), summaries


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_indexed(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype={"rfid_id": str})
    if "rfid_id" not in frame.columns:
        raise ValueError(f"missing rfid_id column: {path}")
    frame["rfid_id"] = frame["rfid_id"].astype(str)
    if frame["rfid_id"].duplicated().any():
        duplicates = frame.loc[frame["rfid_id"].duplicated(), "rfid_id"].head(3).tolist()
        raise ValueError(f"duplicate rfid_id in {path}: {duplicates}")
    return frame.set_index("rfid_id", drop=True)


def expected_t5_columns() -> list[str]:
    return ([f"t5_main_{name}" for name in CLASS_NAMES]
            + [f"t5_month_{name}" for name in CLASS_NAMES]
            + ["t5_fine_grid_ok_ratio", "t5_log1p_fishing_rows"])


def validate_role_table(roles: pd.DataFrame, labels: dict[str, str],
                        holdout_ids: set[str]) -> dict[str, Any]:
    required = {"rfid_id", "outer_fold", "role"}
    if not required.issubset(roles.columns):
        raise ValueError(f"role table missing columns: {sorted(required - set(roles.columns))}")
    table = roles.copy()
    table["rfid_id"] = table["rfid_id"].astype(str)
    table["outer_fold"] = pd.to_numeric(table["outer_fold"], errors="raise").astype(int)
    table["role"] = table["role"].astype(str).str.upper()
    if not set(table["outer_fold"].unique()).issubset(FOLDS):
        raise ValueError(f"unexpected folds: {sorted(table['outer_fold'].unique().tolist())}")
    if not set(table["role"].unique()).issubset({"FIT", "INNER", "OUTER"}):
        raise ValueError(f"unexpected role labels: {sorted(table['role'].unique().tolist())}")
    if table.duplicated(["outer_fold", "rfid_id"]).any():
        raise ValueError("a vessel has more than one role within a fold")
    missing_label = sorted(set(table["rfid_id"]) - set(labels))
    if missing_label:
        raise ValueError(f"role table contains unlabeled vessels, examples={missing_label[:3]}")
    overlap = sorted(set(table["rfid_id"]) & holdout_ids)
    if overlap:
        raise ValueError(f"frozen holdout overlaps development roles, examples={overlap[:3]}")
    if set(table["outer_fold"].unique()) != set(FOLDS):
        raise ValueError("role table does not contain all frozen folds 0, 1, 2")

    counts: dict[str, Any] = {}
    for fold in FOLDS:
        part = table[table["outer_fold"] == fold]
        fold_summary: dict[str, Any] = {}
        for role in ("FIT", "INNER", "OUTER"):
            role_rows = part[part["role"] == role]
            role_labels = [labels[r] for r in role_rows["rfid_id"]]
            class_counts = {name: int(sum(v == name for v in role_labels)) for name in CLASS_NAMES}
            if len(role_rows) == 0 or any(class_counts[name] == 0 for name in CLASS_NAMES):
                raise ValueError(f"empty role or missing class: fold={fold}, role={role}, counts={class_counts}")
            ordered_ids = role_rows["rfid_id"].tolist()
            id_payload = "\n".join(ordered_ids).encode("utf-8")
            fold_summary[role] = {
                "n": len(ordered_ids), "class_counts": class_counts,
                "ordered_rfid_id_sha256": hashlib.sha256(id_payload).hexdigest(),
            }
        counts[str(fold)] = fold_summary

    outer_counts = table[table["role"] == "OUTER"].groupby("rfid_id")["outer_fold"].nunique()
    if (outer_counts != 1).any():
        raise ValueError("each development vessel must be OUTER in exactly one fold")
    all_dev_ids = set(table["rfid_id"])
    for fold in FOLDS:
        fold_ids = set(table.loc[table["outer_fold"] == fold, "rfid_id"])
        if fold_ids != all_dev_ids:
            raise ValueError(f"fold {fold} roster differs from the fixed development roster")
    outer_ids = set(table.loc[table["role"] == "OUTER", "rfid_id"])
    if all_dev_ids != outer_ids:
        raise ValueError("OUTER folds do not partition the development roster")
    return {
        "n_role_rows": int(len(table)),
        "n_development_vessels": len(all_dev_ids),
        "n_outer_vessels": len(outer_ids),
        "folds": counts,
        "outer_partition_sha256": hashlib.sha256(
            "\n".join(sorted(outer_ids)).encode("utf-8")).hexdigest(),
    }


class DataAdapter:
    def __init__(self, repository_root: Path = REPOSITORY_ROOT,
                 original_results_root: Path = ORIGINAL_RESULTS_ROOT,
                 team_root: Path | None = None, work_root: Path | None = None,
                 t5_root: Path | None = None):
        self.repository_root = Path(repository_root)
        self.original_results_root = Path(original_results_root)
        self.team_root = Path(team_root) if team_root else self.original_results_root.parent / "31일" / "팀원자료" / "TabICLv2_F156_공유자료"
        self.work_root = Path(work_root) if work_root else self.repository_root / "11월 4일" / "work"
        self.t5_root = Path(t5_root) if t5_root else self.original_results_root / "outputs" / "f156_merge" / "for_teammate"
        self.labels_path = self.team_root / "data" / "train_labels.csv"
        self.roles_path = self.team_root / "splits" / "development_roles_long.csv"
        self.holdout_path = self.team_root / "splits" / "holdout_ids.csv"
        self.classes_path = self.team_root / "metadata" / "classes.json"
        self.roles = pd.read_csv(self.roles_path, dtype={"rfid_id": str})
        self.labels_frame = pd.read_csv(self.labels_path, dtype={"rfid_id": str})
        self.labels_frame["rfid_id"] = self.labels_frame["rfid_id"].astype(str)
        self.labels_frame["fishing_code"] = self.labels_frame["fishing_code"].astype(str)
        if self.labels_frame["rfid_id"].duplicated().any():
            raise ValueError("duplicate vessel labels")
        self.labels = dict(zip(self.labels_frame["rfid_id"], self.labels_frame["fishing_code"]))
        unknown_labels = set(self.labels.values()) - set(CLASS_NAMES)
        if unknown_labels:
            raise ValueError(f"unexpected label classes: {sorted(unknown_labels)}")
        class_payload = json.loads(self.classes_path.read_text(encoding="utf-8"))
        self.join_validation: dict[str, Any] = {}
        validate_class_order(class_payload)
        self.holdout_ids = set(pd.read_csv(self.holdout_path, dtype={"rfid_id": str})["rfid_id"].astype(str))
        self.split_summary = validate_role_table(self.roles, self.labels, self.holdout_ids)
        self.behavior = _read_indexed(self.work_root / "behavior_B50_train2026.csv")
        self.local_rel = _read_indexed(self.work_root / "local_rel_train2026.csv")
        self.input_hashes = self._hash_inputs()

    def _hash_inputs(self) -> dict[str, dict[str, Any]]:
        paths = [self.labels_path, self.roles_path, self.holdout_path, self.classes_path,
                 self.work_root / "behavior_B50_train2026.csv",
                 self.work_root / "local_rel_train2026.csv",
                 self.original_results_root / "tools" / "run_005_main_20261101.py",
                 self.original_results_root / "tools" / "run_005_F156_merge_20261101.py",
                 self.original_results_root / "tools" / "run_cycle4_3_featAC_20261101.py",
                 self.original_results_root / "tools" / "run_remeasure_20261031.py",
                 self.original_results_root / "outputs" / "f156_merge" / "export_run.log",
                 self.repository_root / "11월 4일" / "code" / "01_build_behavior_features_20261104.py",
                 self.repository_root / "11월 4일" / "code" / "07_local_relative_20261104.py",
                 self.repository_root / "11월 4일" / "results" / "01_build_report.json",
                 self.repository_root / "11월 4일" / "results" / "07_local_relative.json",
                 self.repository_root / "coach" / "gpt" / "rank1_experiments_20261104" / "artifacts" / "exp06" / "input_audit.json",
                 self.repository_root / "coach" / "gpt" / "rank1_experiments_20261104" / "reports" / "exp06" / "input_audit.md",
                 self.original_results_root.parents[1] / "26_11_2" / "work" / "\uC7AC\uC2DD\uBCC4_\uD22C\uD2B8\uB799_001r1" / "s3_hourly.parquet"]
        # T5's cached fishing mask uses Train activity geometry and shared harbors
        # computed from Train + unlabeled 2025 Test geometry, all in existing parquet caches.
        parquet_cache = self.original_results_root / "outputs" / "remeasure_20261031"
        for dataset in ("train", "test"):
            for month in range(1, 7):
                paths.append(parquet_cache / f"rows_{dataset}_{month}.parquet")
        for fold in FOLDS:
            paths.extend([
                self.team_root / "data" / "cv" / f"fold_{fold}" / "F156_train.csv",
                self.t5_root / f"fold_{fold}_t5.csv",
            ])
        out: dict[str, dict[str, Any]] = {}
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(path)
            out[str(path)] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        return out

    def load_fold(self, fold: int) -> PreparedFold:
        if fold not in FOLDS:
            raise ValueError(f"fold must be one of {FOLDS}")
        roles = self.roles.copy()
        roles["rfid_id"] = roles["rfid_id"].astype(str)
        roles["outer_fold"] = pd.to_numeric(roles["outer_fold"], errors="raise").astype(int)
        roles["role"] = roles["role"].astype(str).str.upper()
        role_rows = roles[roles["outer_fold"] == fold].reset_index(drop=True)
        rids = role_rows["rfid_id"].tolist()

        f156 = _read_indexed(self.team_root / "data" / "cv" / f"fold_{fold}" / "F156_train.csv")
        t5 = _read_indexed(self.t5_root / f"fold_{fold}_t5.csv")
        fcols = [c for c in f156.columns]
        tcols = [c for c in t5.columns]
        bcols = [c for c in self.behavior.columns if c != "obs_days"]
        lcols = [c for c in self.local_rel.columns]
        if len(fcols) != FEATURE_COMPONENTS[0][1]:
            raise ValueError(f"fold {fold}: expected 156 F156 columns, found {len(fcols)}")
        if tcols != expected_t5_columns():
            raise ValueError(f"fold {fold}: T5 feature order differs from expected generator schema")
        if len(bcols) != FEATURE_COMPONENTS[2][1]:
            raise ValueError(f"expected 68 behavior columns excluding obs_days, found {len(bcols)}")
        if len(lcols) != FEATURE_COMPONENTS[3][1]:
            raise ValueError(f"expected 70 local_rel columns, found {len(lcols)}")
        if len(tcols) != FEATURE_COMPONENTS[1][1]:
            raise ValueError(f"expected 10 T5 columns, found {len(tcols)}")
        feature_names = tuple(fcols + tcols + bcols + lcols)
        if len(feature_names) != N_FEATURES or len(set(feature_names)) != N_FEATURES:
            raise ValueError(f"feature schema must contain 304 unique ordered names, got {len(feature_names)}")
        for rid in rids:
            if rid not in self.labels or rid not in f156.index or rid not in t5.index or rid not in self.behavior.index or rid not in self.local_rel.index:
                raise ValueError(f"fold {fold}: missing source row for vessel {rid}")
        if set(rids) != set(t5.index):
            raise ValueError(f"fold {fold}: T5 cached roster differs from frozen role roster")
        if t5.index.tolist() != rids:
            raise ValueError(f"fold {fold}: T5 cached row order differs from frozen role table")

        feature_blocks = [
            ("F156", f156.index.tolist(), f156[fcols].to_numpy(dtype=np.float64), fcols),
            ("T5", t5.index.tolist(), t5[tcols].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=np.float64), tcols),
            ("behavior", self.behavior.index.tolist(), self.behavior[bcols].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=np.float64), bcols),
            ("local_rel", self.local_rel.index.tolist(), self.local_rel[lcols].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=np.float64), lcols),
        ]
        X, joined_names, join_summary = validate_feature_join(rids, feature_blocks)
        self.join_validation[str(fold)] = join_summary
        feature_names = tuple(joined_names)
        if X.shape != (len(rids), N_FEATURES):
            raise ValueError(f"fold {fold}: unexpected model matrix shape {X.shape}")
        if np.isinf(X).any():
            raise ValueError(f"fold {fold}: model matrix contains infinite values")
        y = np.asarray([CLASS_TO_INDEX[self.labels[r]] for r in rids], dtype=np.int64)
        role_values = role_rows["role"].to_numpy(dtype=str)
        obs_days = pd.to_numeric(self.behavior.loc[rids, "obs_days"], errors="coerce").to_numpy(dtype=np.float64)
        return PreparedFold(fold, np.asarray(rids, dtype=str), y, role_values, X,
                            feature_names, obs_days)


def save_prepared_fold(data: PreparedFold, output_dir: Path = DEFAULT_ARTIFACTS) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"fold_{data.fold}_features.npz"
    np.savez_compressed(target, fold=np.int64(data.fold), rfid_ids=data.rfid_ids,
                        y=data.y, roles=data.roles, X=data.X,
                        feature_names=np.asarray(data.feature_names, dtype=str),
                        obs_days=data.obs_days)
    return target


def load_fold(fold: int, artifacts_dir: Path = DEFAULT_ARTIFACTS) -> PreparedFold:
    """Load one immutable prepared fold artifact; does no source import or write."""
    if fold not in FOLDS:
        raise ValueError(f"fold must be one of {FOLDS}")
    path = Path(artifacts_dir) / f"fold_{fold}_features.npz"
    if not path.is_file():
        raise FileNotFoundError(f"prepared fold cache missing: {path}; run prepare_fold_cache.py first")
    with np.load(path, allow_pickle=False) as z:
        stored_fold = int(z["fold"])
        if stored_fold != fold:
            raise ValueError(f"artifact fold mismatch: requested {fold}, got {stored_fold}")
        out = PreparedFold(stored_fold, z["rfid_ids"].astype(str), z["y"].astype(np.int64),
                           z["roles"].astype(str), z["X"].astype(np.float64),
                           tuple(z["feature_names"].astype(str).tolist()),
                           z["obs_days"].astype(np.float64))
    if out.X.shape != (len(out.rfid_ids), N_FEATURES) or len(out.feature_names) != N_FEATURES:
        raise ValueError("prepared fold artifact violates 304-column contract")
    if len(set(out.rfid_ids.tolist())) != len(out.rfid_ids):
        raise ValueError("prepared fold artifact contains duplicate vessel IDs")
    return out


def prepare_all_folds(artifact_dir: Path = DEFAULT_ARTIFACTS,
                      report_dir: Path = DEFAULT_REPORTS,
                      repository_root: Path = REPOSITORY_ROOT,
                      original_results_root: Path = ORIGINAL_RESULTS_ROOT) -> dict[str, Any]:
    adapter = DataAdapter(repository_root=repository_root,
                          original_results_root=original_results_root)
    feature_names: tuple[str, ...] | None = None
    folds: dict[str, Any] = {}
    roster_rows: list[dict[str, Any]] = []
    for fold in FOLDS:
        data = adapter.load_fold(fold)
        if feature_names is None:
            feature_names = data.feature_names
        elif feature_names != data.feature_names:
            raise ValueError("feature names/order differ between folds")
        path = save_prepared_fold(data, artifact_dir)
        folds[str(fold)] = {
            "artifact": str(path), "artifact_bytes": path.stat().st_size,
            "artifact_sha256": sha256_file(path), "n_rows": len(data.rfid_ids),
            "role_counts": {r: int((data.roles == r).sum()) for r in ("FIT", "INNER", "OUTER")},
            "class_counts": {name: int(np.sum(data.y == i)) for i, name in enumerate(CLASS_NAMES)},
            "matrix_bytes_uncompressed": int(data.X.nbytes),
            "feature_join_validation": adapter.join_validation[str(fold)],
        }
        roster_rows.extend({"rfid_id": rid, "fold": fold, "role": role, "y_true": int(y)}
                           for rid, role, y in zip(data.rfid_ids, data.roles, data.y))
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    roster = pd.DataFrame(roster_rows)
    roster_path = Path(artifact_dir) / "fixed_split_roster.csv"
    roster.to_csv(roster_path, index=False, encoding="utf-8")
    report = {
        "contract_version": "manager_execution_record_v1",
        "repository_root": str(repository_root),
        "original_results_root": str(original_results_root),
        "raw_data_root_checked_only": str(RAW_DATA_ROOT),
        "raw_data_root_exists": RAW_DATA_ROOT.is_dir(),
        "raw_source_files_read": False,
        "raw_csv_metadata_only": ([{"path": str(path), "bytes": path.stat().st_size}
                                    for path in sorted(RAW_DATA_ROOT.rglob("*.csv"))]
                                   if RAW_DATA_ROOT.is_dir() else []),
        "team_root": str(adapter.team_root), "t5_cache_root": str(adapter.t5_root),
        "behavior_cache": str(adapter.work_root / "behavior_B50_train2026.csv"),
        "local_rel_cache": str(adapter.work_root / "local_rel_train2026.csv"),
        "class_order": list(CLASS_NAMES), "feature_components": list(FEATURE_COMPONENTS),
        "feature_count": N_FEATURES, "feature_names": list(feature_names or ()),
        "input_hashes": adapter.input_hashes,
        "split_validation": adapter.split_summary,
        "feature_population_provenance": {
            "behavior_B68": {
                "generator": "11월 4일/code/01_build_behavior_features_20261104.py",
                "source": "26_11_2/work/hourly S3 parquet (hashed source path in input_hashes)",
                "population": "each vessel's own full Jan-Jun 2026 Train hourly rows",
                "aggregation": "deterministic per-vessel summaries; no cross-vessel statistic and no labels",
                "coordinates": "three null-centroid rows excluded before coordinate-grid calculations; raw WKT/line stitching not used",
                "model_columns": 68,
                "obs_days": "included in source cache but excluded from X304; retained for diagnostics and exp05 candidate input",
                "fit_only": False,
                "transductive_across_vessels": False,
            },
            "local_rel70": {
                "generator": "11월 4일/code/07_local_relative_20261104.py",
                "source": "behavior_B50 table plus same S3 hourly cache",
                "population": "all 2026 Train cohort for regional medians/MAD; year-specific, unlabeled, self included",
                "region_key": "dominant 0.1-degree cell per vessel; exact ties first-seen",
                "fallback": "regions with fewer than 20 vessels use whole-cohort median/MAD; zero MAD fallback; z clipped to [-10,10]",
                "model_columns": 70,
                "fit_only": False,
                "transductive_across_vessels": True,
            },
            "independent_value_and_missing_mask_check": {
                "source": "exp06 input audit",
                "scope": "all 3 folds; X304 blocks compared with NaN masks",
                "reported_max_finite_difference": 0,
                "source_block_values_match": True,
            },
        },
        "folds": folds,
        "fixed_split_roster": {"path": str(roster_path), "rows": len(roster),
                                "sha256": sha256_file(roster_path)},
        "t5_cache_provenance": {
            "generator": "run_005_main_20261101.py::stage_export",
            "generator_sha256": sha256_file(adapter.original_results_root / "tools" / "run_005_main_20261101.py"),
            "execution_receipt": str(adapter.original_results_root / "outputs" / "f156_merge" / "export_run.log"),
            "execution_receipt_sha256": adapter.input_hashes[str(adapter.original_results_root / "outputs" / "f156_merge" / "export_run.log")]["sha256"],
            "execution_receipt_found": True,
            "execution_receipt_logged_fold_rows": {"0": 5897, "1": 5897, "2": 5897},
            "fold_specific_fit_labels_only": True,
            "leave_self_out_for_fit_vessels": True,
            "global_harbor_reference": "stop-location geometry from Jan-Jun 2026 Train plus Jan-Jun 2025 Test; labels are not used",
            "transductive_geometry_use": "unlabeled 2025 Test coordinates contribute to shared harbor candidates used by the Train fishing mask",
            "fishing_mask_population": "active Jan-Jun 2026 Train rows, filtered by distance to the Train+Test shared harbors and Train-only own moorings",
            "fit_label_reference": "fold-specific FIT vessel labels only; leave-self-out for FIT query vessels",
            "query_period": "each development vessel's full Jan-Jun 2026 train-track geometry",
            "cached_file_ids_and_t5_schema_verified": True,
            "dynamic_vs_csv_numeric_delta_measured": False,
            "note": "T5 class counts use only fold FIT labels; held-out labels are not used. The shared harbor reference includes unlabeled 2025 Test geometry (transductive). The export receipt proves creation of the three fold CSV outputs and row counts; dynamic S6 T5 arrays were not directly compared numerically with the serialized fold CSV. All four conditions use the exact same hashed cached 304-column matrix.",
        },
    }
    out_path = report_dir / "data_validation.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
