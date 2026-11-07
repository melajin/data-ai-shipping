from __future__ import annotations

"""S1 spatial posterior features for the Round022 FIT-only gate.

The profile cache contains only row indices, month, grid cell, and record counts.
Each source row is an observed-record/time-bin proxy; it is not dwell time.
"""

import gc
import hashlib
import json
import math
import sqlite3
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RESOLUTIONS = (0.01, 0.05, 0.10)
ALPHA = 5.0
N_CLASSES = 4
FEATURE_NAMES = tuple(
    name
    for res in RESOLUTIONS
    for name in (
        *(f"s1_full_r{int(round(res * 100)):03d}_c{c}" for c in range(N_CLASSES)),
        *(f"s1_month_range_r{int(round(res * 100)):03d}_c{c}" for c in range(N_CLASSES)),
    )
)
REQUIRED_SOURCE_COLUMNS = ("id", "year", "date", "cen_lon", "cen_lat")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_ordered_ids(ids: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for value in ids:
        digest.update(str(value).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _workspace_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Round022 output must stay inside workspace: {resolved}") from exc
    return resolved


def _as_month(value: object) -> int:
    if isinstance(value, (datetime, date)):
        return int(value.month)
    # Arrow date/timestamp values are normally datetime/date. Handle ISO strings
    # as a defensive schema variation without accepting ambiguous formats.
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return int(parsed.month)
    raise ValueError(f"Unsupported date value type in filtered source: {type(value).__name__}")


def build_profile_cache(
    parquet_path: Path,
    ordered_ids: Sequence[str],
    sqlite_path: Path,
    *,
    expected_source_sha256: str | None = None,
    batch_size: int = 65_536,
) -> dict:
    """Build the 2026 FIT-only monthly/full record-count profiles.

    Predicate and column projection are attached to the Arrow scanner before
    any batches are materialized. The mixed-year parquet may be physically
    scanned at row-group granularity; only rows returned by `year == 2026` and
    the exact FIT ID predicate are converted to Python records.
    """
    source = Path(parquet_path).expanduser().resolve()
    output = _workspace_path(Path(sqlite_path))
    if not source.is_file():
        raise FileNotFoundError(source)
    ids = [str(value) for value in ordered_ids]
    if len(ids) == 0 or len(set(ids)) != len(ids):
        raise ValueError("FIT roster must be nonempty and unique")
    try:
        integer_ids = [int(value) for value in ids]
    except ValueError as exc:
        raise ValueError("Source parquet id:int64 cannot be joined safely to FIT IDs") from exc
    if len(set(integer_ids)) != len(ids):
        raise ValueError("FIT IDs collapse after integer conversion")
    row_index = {value: i for i, value in enumerate(integer_ids)}

    started = time.perf_counter()
    source_sha_before = sha256_file(source)
    if expected_source_sha256 and source_sha_before.lower() != expected_source_sha256.lower():
        raise ValueError("Source parquet hash differs from the approved input hash")

    try:
        import pyarrow.dataset as ds
    except ImportError as exc:
        raise RuntimeError("The approved Arrow environment with pyarrow is required") from exc

    dataset = ds.dataset(str(source), format="parquet")
    if not set(REQUIRED_SOURCE_COLUMNS).issubset(set(dataset.schema.names)):
        raise ValueError(f"Source parquet lacks required projected columns: {REQUIRED_SOURCE_COLUMNS}")
    predicate = (ds.field("year") == 2026) & ds.field("id").isin(integer_ids)
    scanner = dataset.scanner(
        columns=list(REQUIRED_SOURCE_COLUMNS),
        filter=predicate,
        batch_size=batch_size,
        use_threads=False,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an existing profile cache: {output}")
    connection = sqlite3.connect(str(output))
    returned_rows = valid_coordinate_rows = invalid_coordinate_rows = 0
    missing_coordinate_rows = 0
    returned_year_mismatches = returned_id_mismatches = 0
    profile_rows = 0
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            "CREATE TABLE profile_count ("
            "vessel_idx INTEGER NOT NULL, month INTEGER NOT NULL, res_idx INTEGER NOT NULL, "
            "cell_x INTEGER NOT NULL, cell_y INTEGER NOT NULL, observations INTEGER NOT NULL, "
            "PRIMARY KEY(vessel_idx, month, res_idx, cell_x, cell_y))"
        )
        connection.execute("CREATE INDEX profile_count_lookup ON profile_count(vessel_idx, month, res_idx)")
        connection.execute("BEGIN")
        upsert = (
            "INSERT INTO profile_count(vessel_idx,month,res_idx,cell_x,cell_y,observations) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(vessel_idx,month,res_idx,cell_x,cell_y) "
            "DO UPDATE SET observations=observations+excluded.observations"
        )
        for batch in scanner.to_batches():
            ids_col = batch.column(batch.schema.get_field_index("id")).to_pylist()
            year_col = batch.column(batch.schema.get_field_index("year")).to_pylist()
            date_col = batch.column(batch.schema.get_field_index("date")).to_pylist()
            lon_col = batch.column(batch.schema.get_field_index("cen_lon")).to_pylist()
            lat_col = batch.column(batch.schema.get_field_index("cen_lat")).to_pylist()
            batch_counts: dict[tuple[int, int, int, int, int], int] = defaultdict(int)
            for vessel_id, year, observed_at, lon, lat in zip(ids_col, year_col, date_col, lon_col, lat_col):
                returned_rows += 1
                if year != 2026:
                    returned_year_mismatches += 1
                    continue
                idx = row_index.get(int(vessel_id))
                if idx is None:
                    returned_id_mismatches += 1
                    continue
                if observed_at is None:
                    missing_coordinate_rows += 1
                    continue
                if lon is None or lat is None:
                    missing_coordinate_rows += 1
                    continue
                lon_f, lat_f = float(lon), float(lat)
                if (not math.isfinite(lon_f) or not math.isfinite(lat_f)
                        or not (-180.0 <= lon_f <= 180.0 and -90.0 <= lat_f <= 90.0)):
                    invalid_coordinate_rows += 1
                    continue
                month = _as_month(observed_at)
                if month < 1 or month > 6:
                    raise ValueError("Filtered source falls outside the frozen Jan-Jun 2026 period")
                for res_idx, res in enumerate(RESOLUTIONS):
                    cell_x = math.floor(lon_f / res)
                    cell_y = math.floor(lat_f / res)
                    batch_counts[(idx, month, res_idx, cell_x, cell_y)] += 1
                    # Month zero is the all-month (Jan-Jun as filtered) profile.
                    batch_counts[(idx, 0, res_idx, cell_x, cell_y)] += 1
                valid_coordinate_rows += 1
            if batch_counts:
                connection.executemany(upsert, ((*key, value) for key, value in batch_counts.items()))
                connection.commit()
                connection.execute("BEGIN")
        connection.commit()
        connection.execute("ANALYZE")
        connection.commit()
        profile_rows = int(connection.execute("SELECT COUNT(*) FROM profile_count").fetchone()[0])
    except Exception:
        connection.rollback()
        connection.close()
        output.unlink(missing_ok=True)
        raise
    finally:
        try:
            connection.close()
        except Exception:
            pass

    source_sha_after = sha256_file(source)
    if source_sha_before != source_sha_after:
        output.unlink(missing_ok=True)
        raise ValueError("Source parquet changed while filtered profiles were built")
    if returned_rows == 0 or valid_coordinate_rows == 0:
        output.unlink(missing_ok=True)
        raise ValueError("Filtered 2026 FIT profile input is empty")
    if returned_year_mismatches or returned_id_mismatches:
        output.unlink(missing_ok=True)
        raise ValueError("Scanner returned rows outside the frozen year/ID predicate")

    manifest = {
        "status": "round022_s1_profiles_written",
        "source_path": str(source),
        "source_sha256": source_sha_before,
        "source_bytes": source.stat().st_size,
        "source_schema": str(dataset.schema),
        "predicate": "year == 2026 AND id IN exact fold0 FIT roster",
        "projected_columns": list(REQUIRED_SOURCE_COLUMNS),
        "materialized_rows_returned_by_scanner": returned_rows,
        "returned_year_mismatches": returned_year_mismatches,
        "returned_id_mismatches": returned_id_mismatches,
        "valid_coordinate_timebin_rows": valid_coordinate_rows,
        "missing_coordinate_or_date_rows": missing_coordinate_rows,
        "invalid_coordinate_rows": invalid_coordinate_rows,
        "profile_rows": profile_rows,
        "ordered_fit_roster_sha256": hash_ordered_ids(ids),
        "fit_roster_size": len(ids),
        "resolutions_deg": list(RESOLUTIONS),
        "profile_weight_semantics": "observed 2026 record/time-bin counts normalized per vessel-period; proxy only, not dwell time",
        "cell_definition": "floor(longitude/resolution_deg), floor(latitude/resolution_deg)",
        "stored_identity": "row index only; raw vessel IDs are not written to the profile cache",
        "physical_rowgroup_decode_of_unmatched_rows": "not measured; scanner predicate is applied before batch materialization",
        "sqlite_bytes": output.stat().st_size,
        "sqlite_sha256": sha256_file(output),
        "elapsed_seconds": time.perf_counter() - started,
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


class S1ProfileStore:
    """Small FIT roster profile view backed by the row-index-only SQLite cache."""

    def __init__(self, sqlite_path: Path, expected_source_sha256: str | None = None):
        self.path = Path(sqlite_path).resolve()
        manifest_path = self.path.with_suffix(self.path.suffix + ".manifest.json")
        if not self.path.is_file() or not manifest_path.is_file():
            raise FileNotFoundError("S1 profile cache and manifest are both required")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if self.manifest.get("status") != "round022_s1_profiles_written":
            raise ValueError("Unexpected S1 profile cache manifest status")
        if sha256_file(self.path) != self.manifest.get("sqlite_sha256"):
            raise ValueError("S1 profile SQLite cache differs from its manifest hash")
        if expected_source_sha256 and self.manifest.get("source_sha256", "").lower() != expected_source_sha256.lower():
            raise ValueError("S1 profile cache is bound to a different spatial source")
        if self.manifest.get("resolutions_deg") != list(RESOLUTIONS):
            raise ValueError("S1 cache resolution order differs from the frozen S1 schema")
        self.n_rows = int(self.manifest["fit_roster_size"])
        with sqlite3.connect(str(self.path)) as connection:
            self.profile_count_rows = int(connection.execute("SELECT COUNT(*) FROM profile_count").fetchone()[0])

    def period_profiles(self, month: int) -> list[list[dict[tuple[int, int], float]]]:
        """Load one full/month period, then release it before the next period."""
        if month not in (0, 1, 2, 3, 4, 5, 6):
            raise ValueError("Period must be full(0) or Jan-Jun(1..6)")
        profiles = [[{} for _ in range(self.n_rows)] for _ in RESOLUTIONS]
        totals = [np.zeros(self.n_rows, dtype=np.float64) for _ in RESOLUTIONS]
        with sqlite3.connect(str(self.path)) as connection:
            cursor = connection.execute(
                "SELECT vessel_idx,res_idx,cell_x,cell_y,observations FROM profile_count "
                "WHERE month=? ORDER BY res_idx,vessel_idx,cell_x,cell_y", (month,)
            )
            for vessel_idx, res_idx, cell_x, cell_y, observations in cursor:
                idx, resolution = int(vessel_idx), int(res_idx)
                if not (0 <= idx < self.n_rows and 0 <= resolution < len(RESOLUTIONS)):
                    raise ValueError("Profile cache has an index outside the frozen S1 schema")
                cell = (int(cell_x), int(cell_y))
                count = float(observations)
                profiles[resolution][idx][cell] = count
                totals[resolution][idx] += count
        for res_idx in range(len(RESOLUTIONS)):
            for vessel_idx, cells in enumerate(profiles[res_idx]):
                total = totals[res_idx][vessel_idx]
                if total > 0:
                    for cell in list(cells):
                        cells[cell] /= total
        return profiles


def _build_counts(
    period_profiles: list[list[dict[tuple[int, int], float]]],
    train_indices: np.ndarray,
    train_labels: np.ndarray,
    res_idx: int,
) -> dict[tuple[int, int], list[float]]:
    counts: dict[tuple[int, int], list[float]] = {}
    for vessel_idx, cls in zip(train_indices.tolist(), train_labels.tolist()):
        profile = period_profiles[res_idx][int(vessel_idx)]
        for cell in profile:
            entry = counts.get(cell)
            if entry is None:
                entry = [0.0, 0.0, 0.0, 0.0]
                counts[cell] = entry
            entry[int(cls)] += 1.0
    return counts


def _cell_posterior(
    store: S1ProfileStore,
    period_profiles: list[list[dict[tuple[int, int], float]]],
    counts_by_res: Sequence[dict[tuple[int, int], list[float]]],
    train_label_by_index: dict[int, int],
    global_counts: np.ndarray,
    query_idx: int,
    month: int,
    requested_res_idx: int,
    requested_cell: tuple[int, int],
) -> np.ndarray:
    return _posterior_for_cell(
        store, period_profiles, counts_by_res, train_label_by_index, global_counts,
        query_idx, month, requested_res_idx, requested_cell,
    )


def build_features(
    store: S1ProfileStore,
    query_indices: Sequence[int],
    train_indices: Sequence[int],
    train_labels: Sequence[int],
) -> np.ndarray:
    """Return 24 columns; validation labels are not accepted by this function.

    FIT queries use leave-one-vessel-out contributions in cell counts and global
    prior. Non-FIT validation queries use only the supplied CV-train population.
    Each resolution falls back to its coarser cell, then the train-only global
    prior. The monthly range is max-minus-min across observed query months.
    """
    query_indices = np.asarray(query_indices, dtype=np.int64)
    train_indices = np.asarray(train_indices, dtype=np.int64)
    train_labels = np.asarray(train_labels, dtype=np.int64)
    if len(train_indices) != len(train_labels) or len(train_indices) == 0:
        raise ValueError("CV training indices and labels must be nonempty and aligned")
    if np.any(train_labels < 0) or np.any(train_labels >= N_CLASSES):
        raise ValueError("CV training labels fall outside the frozen four-class order")
    if len(np.unique(train_indices)) != len(train_indices):
        raise ValueError("CV training indices are not unique")
    if np.any(query_indices < 0) or np.any(query_indices >= store.n_rows):
        raise ValueError("Query index is outside the cached FIT roster")
    if np.any(train_indices < 0) or np.any(train_indices >= store.n_rows):
        raise ValueError("Training index is outside the cached FIT roster")
    train_label_by_index = {int(i): int(y) for i, y in zip(train_indices.tolist(), train_labels.tolist())}
    global_counts = np.bincount(train_labels, minlength=N_CLASSES).astype(np.float64)
    output = np.full((len(query_indices), len(FEATURE_NAMES)), np.nan, dtype=np.float32)
    query_position = {int(v): pos for pos, v in enumerate(query_indices.tolist())}

    # Construct one period at a time to keep sparse counts bounded in memory.
    periods: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    month_min: dict[tuple[int, int], np.ndarray] = {}
    month_max: dict[tuple[int, int], np.ndarray] = {}
    for month in periods:
        period_profiles = store.period_profiles(month)
        counts_by_res = [_build_counts(period_profiles, train_indices, train_labels, r) for r in range(len(RESOLUTIONS))]
        for res_idx in range(len(RESOLUTIONS)):
            full_feature_start = res_idx * 8
            if month == 0:
                for query_idx in query_indices.tolist():
                    profile = period_profiles[res_idx][int(query_idx)]
                    if not profile:
                        continue
                    value = np.zeros(N_CLASSES, dtype=np.float64)
                    for cell, weight in profile.items():
                        posterior = _cell_posterior(
                            store, period_profiles, counts_by_res, train_label_by_index, global_counts,
                            int(query_idx), 0, res_idx, cell,
                        )
                        value += weight * posterior
                    output[query_position[int(query_idx)], full_feature_start:full_feature_start + 4] = value.astype(np.float32)
            else:
                month_values: dict[int, np.ndarray] = {}
                for query_idx in query_indices.tolist():
                    profile = period_profiles[res_idx][int(query_idx)]
                    if not profile:
                        continue
                    value = np.zeros(N_CLASSES, dtype=np.float64)
                    for cell, weight in profile.items():
                        value += weight * _cell_posterior(
                            store, period_profiles, counts_by_res, train_label_by_index, global_counts,
                            int(query_idx), month, res_idx, cell,
                        )
                    month_values[int(query_idx)] = value
                for query_idx, value in month_values.items():
                    old_min = month_min.setdefault((res_idx, query_idx), value.copy())
                    old_max = month_max.setdefault((res_idx, query_idx), value.copy())
                    np.minimum(old_min, value, out=old_min)
                    np.maximum(old_max, value, out=old_max)
        # Per-query month values are already copied into month_min/month_max.
        # Release the last resolution's temporary dict before loading the next
        # month's sparse profiles and counts.
        if month > 0:
            del month_values
        # Counts are released before the next month is built.
        del period_profiles, counts_by_res
        gc.collect()

    for res_idx in range(len(RESOLUTIONS)):
        start = res_idx * 8 + 4
        for query_idx in query_indices.tolist():
            low = month_min.get((res_idx, int(query_idx)))
            high = month_max.get((res_idx, int(query_idx)))
            if low is not None and high is not None:
                output[query_position[int(query_idx)], start:start + 4] = (high - low).astype(np.float32)
    if np.isinf(output).any():
        raise ValueError("S1 feature matrix contains infinite values")
    return output


def _posterior_for_cell(
    store: S1ProfileStore,
    period_profiles: list[list[dict[tuple[int, int], float]]],
    counts_by_res: Sequence[dict[tuple[int, int], list[float]]],
    train_label_by_index: dict[int, int],
    global_counts: np.ndarray,
    query_idx: int,
    month: int,
    requested_res_idx: int,
    requested_cell: tuple[int, int],
) -> np.ndarray:
    prior_counts = global_counts.copy()
    query_is_fit = query_idx in train_label_by_index
    if query_is_fit:
        prior_counts[train_label_by_index[query_idx]] -= 1.0
    prior_total = float(prior_counts.sum())
    prior = prior_counts / prior_total if prior_total > 0 else np.full(N_CLASSES, 1.0 / N_CLASSES)
    cell_x, cell_y = requested_cell
    res_idx = requested_res_idx
    while True:
        counts = counts_by_res[res_idx].get((cell_x, cell_y))
        adjusted = np.asarray(counts if counts is not None else [0.0] * N_CLASSES, dtype=np.float64)
        if query_is_fit:
            if period_profiles[res_idx][query_idx].get((cell_x, cell_y), 0.0) > 0:
                adjusted[train_label_by_index[query_idx]] -= 1.0
        adjusted = np.maximum(adjusted, 0.0)
        total = float(adjusted.sum())
        if total > 1e-15:
            return (adjusted + ALPHA) / (total + ALPHA * N_CLASSES)
        if res_idx >= len(RESOLUTIONS) - 1:
            return prior
        factor = int(round(RESOLUTIONS[res_idx + 1] / RESOLUTIONS[res_idx]))
        cell_x = math.floor(cell_x / factor)
        cell_y = math.floor(cell_y / factor)
        res_idx += 1
