"""Streaming, geometry-only features for Round 028.

The module reads only the Train CSV id and geom columns. It has no label,
prediction, holdout, Test, or model dependency. Each CSV row is handled as one
bounded WKT record; separate MultiLineString parts and separate source rows are
never connected.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Callable, Iterator, Sequence


for _thread_var in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
):
    os.environ[_thread_var] = "1"


EARTH_RADIUS_M = 6_371_008.8
MIN_TURN_RAD = math.radians(15.0)
MIN_RETURN_PATH_LAG_M = 500.0
MAX_RETURN_DISTANCE_M = 100.0
MAX_ADJACENT_SEGMENT_M = 10_000.0
MAX_WKT_CHARS = 16 * 1024 * 1024
MAX_POINTS_PER_ROW = 100_000
MAX_RETURN_DISTANCE_CHECKS_PER_ROW = 1_000_000
_BUCKET_M = MAX_RETURN_DISTANCE_M
_BUCKET_NEIGHBORS = (-2, -1, 0, 1, 2)

FEATURE_NAMES = (
    "turn_sign_reversal_fraction",
    "nonlocal_return_vertex_fraction",
)

TRAIN_MONTH_FILES = tuple(f"vpass_{month}월 데이터.csv" for month in range(1, 7))
DEFAULT_TRAIN_DIR = Path(
    r"F:\문제 데이터_수정_1027\vpass_26년(1월_6월) 데이터\vpass_1월_6월 데이터"
)
DEFAULT_ROSTER_NPZ = Path(
    r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104"
    r"\artifacts\exp01\fold_0_features.npz"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_TOKEN_RE = re.compile(rf"\s*([(),]|{_NUMBER})")
_HEADER_RE = re.compile(r"^\s*MULTILINESTRING\b", re.IGNORECASE)


class GeometryError(ValueError):
    """A WKT row cannot safely contribute geometry features."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RowFeatures:
    valid: bool
    reason: str | None
    turn_numerator: int = 0
    turn_denominator: int = 0
    return_numerator: int = 0
    return_denominator: int = 0
    part_count: int = 0
    point_count: int = 0


class _Scanner:
    def __init__(self, text: str, start: int):
        self.text = text
        self.pos = start

    def next(self) -> str | None:
        if self.pos >= len(self.text):
            return None
        match = _TOKEN_RE.match(self.text, self.pos)
        if match is None:
            if self.text[self.pos:].strip() == "":
                self.pos = len(self.text)
                return None
            raise GeometryError("malformed_wkt")
        self.pos = match.end()
        return match.group(1)

    def number(self) -> float:
        token = self.next()
        if token is None or token in ("(", ")", ","):
            raise GeometryError("malformed_wkt")
        try:
            value = float(token)
        except (TypeError, ValueError, OverflowError) as exc:
            raise GeometryError("malformed_wkt") from exc
        if not math.isfinite(value):
            raise GeometryError("nonfinite_coordinate")
        return value


def parse_multilinestring(
    wkt: str,
    *,
    max_wkt_chars: int = MAX_WKT_CHARS,
    max_points: int = MAX_POINTS_PER_ROW,
) -> list[list[tuple[float, float]]]:
    """Parse a strict 2D MULTILINESTRING, retaining every part boundary.

    A source row is rejected in full if it exceeds either cap. No prefix of a
    truncated row is returned as though it were complete.
    """
    if not isinstance(wkt, str) or not wkt.strip():
        raise GeometryError("missing_wkt")
    if len(wkt) > max_wkt_chars:
        raise GeometryError("wkt_char_limit_exceeded")
    header = _HEADER_RE.match(wkt)
    if header is None:
        raise GeometryError("malformed_wkt")

    remainder = wkt[header.end():]
    if re.fullmatch(r"\s*EMPTY\s*", remainder, flags=re.IGNORECASE):
        return []

    scanner = _Scanner(wkt, header.end())
    parts: list[list[tuple[float, float]]] = []
    total_points = 0

    def expect(expected: str) -> None:
        if scanner.next() != expected:
            raise GeometryError("malformed_wkt")

    def coordinate() -> tuple[float, float]:
        nonlocal total_points
        lon = scanner.number()
        lat = scanner.number()
        if lon < -180.0 or lon > 180.0 or lat < -90.0 or lat > 90.0:
            raise GeometryError("coordinate_out_of_lonlat_range")
        total_points += 1
        if total_points > max_points:
            raise GeometryError("point_limit_exceeded")
        return lon, lat

    expect("(")
    while True:
        expect("(")
        first = scanner.next()
        if first is None or first in ("(", ")", ","):
            raise GeometryError("malformed_wkt")
        try:
            lon = float(first)
        except (TypeError, ValueError, OverflowError) as exc:
            raise GeometryError("malformed_wkt") from exc
        if not math.isfinite(lon):
            raise GeometryError("nonfinite_coordinate")
        lat = scanner.number()
        if lon < -180.0 or lon > 180.0 or lat < -90.0 or lat > 90.0:
            raise GeometryError("coordinate_out_of_lonlat_range")
        total_points += 1
        if total_points > max_points:
            raise GeometryError("point_limit_exceeded")
        part = [(lon, lat)]
        while True:
            token = scanner.next()
            if token == ",":
                part.append(coordinate())
                continue
            if token == ")":
                break
            raise GeometryError("malformed_wkt")
        if len(part) < 2:
            raise GeometryError("part_too_short")
        parts.append(part)

        token = scanner.next()
        if token == ",":
            continue
        if token == ")":
            break
        raise GeometryError("malformed_wkt")

    if scanner.next() is not None:
        raise GeometryError("malformed_wkt")
    return parts


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    sin_lat = math.sin(dlat / 2.0)
    sin_lon = math.sin(dlon / 2.0)
    hav = sin_lat * sin_lat + math.cos(lat1) * math.cos(lat2) * sin_lon * sin_lon
    hav = min(1.0, max(0.0, hav))
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(hav))


def _project_local(
    point: tuple[float, float], lon0: float, lat0: float
) -> tuple[float, float]:
    """Local equirectangular coordinates in metres for neighborhood lookup."""
    x = EARTH_RADIUS_M * math.radians(point[0] - lon0) * math.cos(math.radians(lat0))
    y = EARTH_RADIUS_M * math.radians(point[1] - lat0)
    return x, y


def _part_turn_counts(part: Sequence[tuple[float, float]]) -> tuple[int, int]:
    # Collapse only exactly repeated adjacent coordinates; no distance-based
    # simplification or data-tuned epsilon is applied.
    points = [part[0]]
    for point in part[1:]:
        if point != points[-1]:
            points.append(point)
    if len(points) < 3:
        return 0, 0

    lon0 = sum(point[0] for point in points) / len(points)
    lat0 = sum(point[1] for point in points) / len(points)
    if abs(lat0) > 85.0:
        raise GeometryError("mean_latitude_exceeds_85_degrees")
    if max(p[0] for p in points) - min(p[0] for p in points) > 20.0:
        raise GeometryError("part_longitude_span_exceeds_20_degrees")
    if max(p[1] for p in points) - min(p[1] for p in points) > 20.0:
        raise GeometryError("part_latitude_span_exceeds_20_degrees")

    xy = [_project_local(point, lon0, lat0) for point in points]
    vectors = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(xy, xy[1:])]
    turns: list[int] = []
    for before, after in zip(vectors, vectors[1:]):
        before_norm = math.hypot(*before)
        after_norm = math.hypot(*after)
        if before_norm == 0.0 or after_norm == 0.0:
            continue
        cross = before[0] * after[1] - before[1] * after[0]
        dot = before[0] * after[0] + before[1] * after[1]
        angle = math.atan2(cross, dot)
        if angle <= -math.pi:
            angle = math.pi
        if abs(angle) >= MIN_TURN_RAD:
            turns.append(1 if angle > 0.0 else -1)
    denominator = max(0, len(turns) - 1)
    numerator = sum(left != right for left, right in zip(turns, turns[1:]))
    return numerator, denominator


def _part_return_counts(
    part: Sequence[tuple[float, float]],
    *,
    remaining_comparison_budget: int,
) -> tuple[int, int, int]:
    # Remove exact consecutive duplicates so repeated stationary samples cannot
    # inflate the vertex denominator. Part boundaries are never crossed.
    points = [part[0]]
    for point in part[1:]:
        if point != points[-1]:
            points.append(point)
    if len(points) < 2:
        return 0, 0, 0

    lon0 = sum(point[0] for point in points) / len(points)
    lat0 = sum(point[1] for point in points) / len(points)
    if abs(lat0) > 85.0:
        raise GeometryError("mean_latitude_exceeds_85_degrees")
    if max(p[0] for p in points) - min(p[0] for p in points) > 20.0:
        raise GeometryError("part_longitude_span_exceeds_20_degrees")
    if max(p[1] for p in points) - min(p[1] for p in points) > 20.0:
        raise GeometryError("part_latitude_span_exceeds_20_degrees")

    positions: list[tuple[float, float, float]] = []
    cumulative = 0.0
    positions.append((0.0, *_project_local(points[0], lon0, lat0)))
    for previous, current in zip(points, points[1:]):
        segment = _haversine_m(previous, current)
        if segment > MAX_ADJACENT_SEGMENT_M:
            raise GeometryError("adjacent_segment_over_10km")
        cumulative += segment
        xy = _project_local(current, lon0, lat0)
        positions.append((cumulative, xy[0], xy[1]))

    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    activate = 0
    numerator = 0
    denominator = 0
    comparisons = 0
    for current_index, (path_m, x, y) in enumerate(positions):
        while (
            activate < current_index
            and path_m - positions[activate][0] >= MIN_RETURN_PATH_LAG_M
        ):
            old_path, old_x, old_y = positions[activate]
            cell = (math.floor(old_x / _BUCKET_M), math.floor(old_y / _BUCKET_M))
            grid[cell].append(activate)
            activate += 1

        if path_m < MIN_RETURN_PATH_LAG_M:
            continue
        denominator += 1
        cell_x, cell_y = math.floor(x / _BUCKET_M), math.floor(y / _BUCKET_M)
        found = False
        for dx in _BUCKET_NEIGHBORS:
            if found:
                break
            for dy in _BUCKET_NEIGHBORS:
                for prior_index in grid.get((cell_x + dx, cell_y + dy), ()):
                    comparisons += 1
                    if comparisons > remaining_comparison_budget:
                        raise GeometryError("return_comparison_budget_exceeded")
                    if _haversine_m(points[current_index], points[prior_index]) <= MAX_RETURN_DISTANCE_M:
                        found = True
                        break
                if found:
                    break
        if found:
            numerator += 1
    return numerator, denominator, comparisons


def extract_row_features(
    wkt: str | None,
    *,
    coordinate_order_confirmed: bool = False,
    max_wkt_chars: int = MAX_WKT_CHARS,
    max_points: int = MAX_POINTS_PER_ROW,
) -> RowFeatures:
    """Compute one row's two feature count pairs or fail closed with a reason.

    The caller must explicitly confirm the documented X=longitude, Y=latitude
    contract. EPSG/datum remain unconfirmed; return distance uses a spherical
    haversine approximation, and turn signs use a local tangent approximation.
    """
    if wkt is None or (isinstance(wkt, str) and not wkt.strip()):
        return RowFeatures(False, "missing_wkt")
    if not coordinate_order_confirmed:
        return RowFeatures(False, "coordinate_order_unconfirmed")
    try:
        parts = parse_multilinestring(
            wkt, max_wkt_chars=max_wkt_chars, max_points=max_points
        )
        if not parts:
            return RowFeatures(False, "empty_geometry")
        turn_num = turn_den = return_num = return_den = 0
        return_comparisons = 0
        points_seen = 0
        for part in parts:
            points_seen += len(part)
            part_turn_num, part_turn_den = _part_turn_counts(part)
            part_return_num, part_return_den, part_comparisons = _part_return_counts(
                part,
                remaining_comparison_budget=(
                    MAX_RETURN_DISTANCE_CHECKS_PER_ROW - return_comparisons
                ),
            )
            turn_num += part_turn_num
            turn_den += part_turn_den
            return_num += part_return_num
            return_den += part_return_den
            return_comparisons += part_comparisons
        return RowFeatures(
            True, None, turn_num, turn_den, return_num, return_den,
            part_count=len(parts), point_count=points_seen,
        )
    except GeometryError as exc:
        return RowFeatures(False, exc.reason)
    except (ValueError, OverflowError, ZeroDivisionError):
        return RowFeatures(False, "geometry_calculation_error")


@dataclass
class VesselAccumulator:
    rows_seen: int = 0
    geometry_valid_rows: int = 0
    geometry_missing_rows: int = 0
    geometry_empty_rows: int = 0
    geometry_invalid_rows: int = 0
    geometry_truncated_rows: int = 0
    turn_numerator: int = 0
    turn_denominator: int = 0
    return_numerator: int = 0
    return_denominator: int = 0
    error_reasons: Counter[str] | None = None

    def add(self, result: RowFeatures) -> None:
        self.rows_seen += 1
        if result.valid:
            self.geometry_valid_rows += 1
            self.turn_numerator += result.turn_numerator
            self.turn_denominator += result.turn_denominator
            self.return_numerator += result.return_numerator
            self.return_denominator += result.return_denominator
            return
        if result.reason == "missing_wkt":
            self.geometry_missing_rows += 1
        elif result.reason == "empty_geometry":
            self.geometry_empty_rows += 1
        else:
            self.geometry_invalid_rows += 1
        if result.reason and (
            "limit_exceeded" in result.reason or result.reason == "point_limit_exceeded"
        ):
            self.geometry_truncated_rows += 1
        if self.error_reasons is None:
            self.error_reasons = Counter()
        self.error_reasons[result.reason or "unknown"] += 1

    def output_row(self, vessel_id: str) -> dict[str, str | int]:
        turn_fraction = (
            self.turn_numerator / self.turn_denominator
            if self.turn_denominator > 0 else ""
        )
        return_fraction = (
            self.return_numerator / self.return_denominator
            if self.return_denominator > 0 else ""
        )
        reason_counts = json.dumps(
            dict(sorted((self.error_reasons or {}).items())),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return {
            "rfid_id": vessel_id,
            "turn_sign_reversal_fraction": turn_fraction,
            "nonlocal_return_vertex_fraction": return_fraction,
            "turn_sign_reversal_numerator": self.turn_numerator,
            "turn_sign_reversal_denominator": self.turn_denominator,
            "nonlocal_return_vertex_numerator": self.return_numerator,
            "nonlocal_return_vertex_denominator": self.return_denominator,
            "rows_seen": self.rows_seen,
            "geometry_valid_rows": self.geometry_valid_rows,
            "geometry_missing_rows": self.geometry_missing_rows,
            "geometry_empty_rows": self.geometry_empty_rows,
            "geometry_invalid_rows": self.geometry_invalid_rows,
            "geometry_truncated_rows": self.geometry_truncated_rows,
            "geometry_error_reasons_json": reason_counts,
        }


OUTPUT_COLUMNS = (
    "rfid_id",
    *FEATURE_NAMES,
    "turn_sign_reversal_numerator",
    "turn_sign_reversal_denominator",
    "nonlocal_return_vertex_numerator",
    "nonlocal_return_vertex_denominator",
    "rows_seen",
    "geometry_valid_rows",
    "geometry_missing_rows",
    "geometry_empty_rows",
    "geometry_invalid_rows",
    "geometry_truncated_rows",
    "geometry_error_reasons_json",
)


class ExtractionError(RuntimeError):
    pass


class _LimitedPhysicalLines:
    """Yield at most N physical data lines to csv.reader for pilot mode."""
    def __init__(self, stream, limit: int):
        self.stream = stream
        self.limit = limit
        self.yielded = 0

    def __iter__(self) -> "_LimitedPhysicalLines":
        return self

    def __next__(self) -> str:
        if self.yielded >= self.limit:
            raise StopIteration
        line = self.stream.readline()
        if line == "":
            raise StopIteration
        self.yielded += 1
        return line


def expected_train_paths(train_dir: Path = DEFAULT_TRAIN_DIR) -> list[Path]:
    """Resolve the six approved Train2026 month files and no other CSVs."""
    train_dir = Path(train_dir)
    if train_dir.name != "vpass_1월_6월 데이터" or train_dir.parent.name != "vpass_26년(1월_6월) 데이터":
        raise ExtractionError("train_dir must be the recorded Train2026 monthly directory")
    paths = [train_dir / name for name in TRAIN_MONTH_FILES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise ExtractionError(f"required Train2026 month files are missing: {missing}")
    return paths


def load_roster_npz(path: Path, key: str = "rfid_ids") -> set[str]:
    """Read only FIT IDs and roles from the fold archive; no labels/features."""
    try:
        import numpy as np
    except ImportError as exc:
        raise ExtractionError("numpy is required only to read the fold roster IDs") from exc
    try:
        with np.load(path, allow_pickle=False) as archive:
            if key not in archive.files or "roles" not in archive.files:
                raise ExtractionError(f"roster archive must contain {key!r} and 'roles'")
            values = archive[key]
            roles = archive["roles"]
            if values.ndim != 1 or roles.ndim != 1 or len(values) != len(roles):
                raise ExtractionError("roster IDs and roles must be aligned vectors")
            def as_text(value) -> str:
                if isinstance(value, (bytes, np.bytes_)):
                    return value.decode("utf-8").strip()
                return str(value).strip()
            fit_ids = [
                as_text(vessel_id)
                for vessel_id, role in zip(values.tolist(), roles.tolist())
                if as_text(role).upper() == "FIT"
            ]
            ids = set(fit_ids)
            if len(fit_ids) != len(ids):
                raise ExtractionError("fold FIT roster contains duplicate vessel IDs")
    except (OSError, ValueError, KeyError) as exc:
        raise ExtractionError(f"could not read roster IDs from {path}") from exc
    ids.discard("")
    if len(ids) != 3144:
        raise ExtractionError(f"fold0 FIT roster must contain 3144 unique IDs; found {len(ids)}")
    return ids


def _input_metadata(paths: Sequence[Path]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in paths:
        try:
            info = path.stat()
        except OSError as exc:
            raise ExtractionError(f"could not stat input file {path}") from exc
        result.append({
            "path": str(path),
            "size_bytes": int(info.st_size),
            "mtime_ns": int(info.st_mtime_ns),
        })
    return result


def _headers_and_indices(line: str, path: Path) -> tuple[list[str], int, int]:
    try:
        headers = next(csv.reader([line], strict=True))
    except (csv.Error, StopIteration) as exc:
        raise ExtractionError(f"invalid CSV header in {path}") from exc
    # April and June source files contain unnamed, trailing CSV padding columns.
    # Named columns must still be unique and padding may not interrupt them.
    named_headers = [name for name in headers if name]
    if len(named_headers) != len(set(named_headers)):
        raise ExtractionError(f"duplicate named CSV header in {path}")
    if "" in headers and any(headers[headers.index("") :]):
        raise ExtractionError(f"unnamed CSV header before named columns in {path}")
    for name in ("rfid_id", "geom"):
        if name not in headers:
            raise ExtractionError(f"required column {name!r} missing in {path}")
    return headers, headers.index("rfid_id"), headers.index("geom")


def _iter_source_rows(
    path: Path,
    *,
    physical_line_limit: int | None = None,
) -> tuple[Iterator[tuple[int, list[str]]], dict[str, object], int, int]:
    """Open one CSV and expose logical rows with only metadata on errors.

    The generator owns its file handle. In pilot mode, the header counts as one
    physical line and at most physical_line_limit-1 later lines are exposed.
    """
    if physical_line_limit is not None and physical_line_limit < 1:
        raise ExtractionError("physical_line_limit must be >= 1")
    stream = open(path, "r", encoding="utf-8-sig", newline="")
    header_line = stream.readline()
    if not header_line:
        stream.close()
        raise ExtractionError(f"empty CSV file: {path}")
    _, id_index, geom_index = _headers_and_indices(header_line, path)
    stats: dict[str, object] = {
        "path": str(path),
        "data_rows_read": 0,
        "physical_lines_read": 1,
        "pilot_physical_line_limit": physical_line_limit,
        "pilot_source_complete": physical_line_limit is None,
        "pilot_incomplete_record": False,
    }

    def generate() -> Iterator[tuple[int, list[str]]]:
        nonlocal stream
        try:
            if physical_line_limit is None:
                reader = csv.reader(stream, strict=True)
            else:
                reader = csv.reader(
                    _LimitedPhysicalLines(stream, physical_line_limit - 1),
                    strict=True,
                )
            ordinal = 0
            while True:
                try:
                    row = next(reader)
                except StopIteration:
                    if physical_line_limit is not None:
                        stats["physical_lines_read"] = min(
                            physical_line_limit, 1 + getattr(reader, "line_num", 0)
                        )
                    break
                except csv.Error:
                    if physical_line_limit is None:
                        raise ExtractionError(
                            f"CSV parse error in {path} after data row {ordinal}"
                        )
                    stats["pilot_incomplete_record"] = True
                    stats["physical_lines_read"] = physical_line_limit
                    break
                ordinal += 1
                stats["data_rows_read"] = ordinal
                if physical_line_limit is None:
                    stats["physical_lines_read"] = 1 + getattr(reader, "line_num", 0)
                yield ordinal, row
        finally:
            stream.close()

    return generate(), stats, id_index, geom_index


def extract_csv_files(
    input_paths: Sequence[Path],
    *,
    roster_ids: set[str] | None,
    coordinate_order_confirmed: bool,
    physical_line_limit: int | None = None,
    resource_check: Callable[[str, float], None] | None = None,
) -> tuple[dict[str, VesselAccumulator], dict[str, object]]:
    if not coordinate_order_confirmed:
        raise ExtractionError("explicit coordinate-order confirmation is required")
    if not input_paths:
        raise ExtractionError("at least one Train CSV is required")
    if physical_line_limit is not None and len(input_paths) != 1:
        raise ExtractionError("pilot mode accepts exactly one Train CSV")
    csv.field_size_limit(MAX_WKT_CHARS)
    accumulators: dict[str, VesselAccumulator] = (
        {vessel_id: VesselAccumulator() for vessel_id in roster_ids}
        if roster_ids is not None else {}
    )
    file_stats: list[dict[str, object]] = []
    total = Counter()

    for file_index, path in enumerate(input_paths):
        if resource_check is not None:
            resource_check(f"before_month_{file_index + 1}", 1.0)
        row_iterator, stats, id_index, geom_index = _iter_source_rows(
            Path(path),
            physical_line_limit=physical_line_limit if file_index == 0 else None,
        )
        try:
            for ordinal, row in row_iterator:
                total["logical_data_rows"] += 1
                if len(row) <= id_index or not row[id_index].strip():
                    total["missing_id_rows"] += 1
                    continue
                vessel_id = row[id_index].strip()
                if roster_ids is not None and vessel_id not in roster_ids:
                    total["non_roster_rows_skipped"] += 1
                    continue
                total["roster_matched_rows"] += 1
                accumulator = accumulators.setdefault(vessel_id, VesselAccumulator())
                wkt = row[geom_index] if len(row) > geom_index else None
                accumulator.add(extract_row_features(
                    wkt, coordinate_order_confirmed=True
                ))
        except ExtractionError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ExtractionError(f"CSV read failure in {path} after row {stats['data_rows_read']}") from exc
        file_stats.append(stats)
        total["files_read"] += 1
        if resource_check is not None:
            resource_check(f"after_month_{file_index + 1}", 1.0)

    manifest = {
        "input_mode": "Train2026_geom_only",
        "feature_names": list(FEATURE_NAMES),
        "coordinate_order_confirmed_by_caller": bool(coordinate_order_confirmed),
        "crs_epsg_datum": "unconfirmed; distances use declared spherical/local approximations",
        "csv_columns_used": ["rfid_id", "geom"],
        "label_values_read": False,
        "predictions_read": False,
        "test_or_holdout_read": False,
        "part_boundaries_preserved": True,
        "cross_row_or_cross_part_pairs": False,
        "physical_line_pilot": physical_line_limit is not None,
        "physical_line_limit": physical_line_limit,
        "feature_parameters": {
            "turn_sign_reversal": {
                "minimum_absolute_turn_degrees_inclusive": 15.0,
                "exact_adjacent_duplicate_coordinates_collapsed": True,
                "other_distance_simplification": False,
            },
            "nonlocal_return": {
                "minimum_prior_along_part_path_lag_m": 500.0,
                "maximum_haversine_distance_m_inclusive": 100.0,
                "maximum_adjacent_segment_m": MAX_ADJACENT_SEGMENT_M,
            },
            "limits": {
                "max_wkt_characters_per_row": MAX_WKT_CHARS,
                "max_points_per_row": MAX_POINTS_PER_ROW,
                "max_candidate_haversine_checks_per_row": MAX_RETURN_DISTANCE_CHECKS_PER_ROW,
                "limit_behavior": "reject entire row and count reason; never use a prefix",
            },
            "aggregation": "sum row/part numerators and denominators per vessel, then divide",
            "zero_denominator": "blank value with denominator 0; never impute zero",
        },
        "files": file_stats,
        "file_metadata": _input_metadata(input_paths),
        "totals": dict(total),
        "roster_count": len(roster_ids) if roster_ids is not None else None,
        "output_vessel_count": len(accumulators),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    return accumulators, manifest


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temp_name = stream.name
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def _memory_snapshot() -> tuple[int | None, int | None, list[dict[str, object]] | None]:
    """Return system-available bytes, current RSS bytes, and other Python jobs."""
    try:
        import psutil
        available = int(psutil.virtual_memory().available)
        current_pid = os.getpid()
        rss = int(psutil.Process(current_pid).memory_info().rss)
        others: list[dict[str, object]] = []
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                if int(proc.info["pid"]) == current_pid:
                    continue
                name = str(proc.info.get("name") or "")
                if "python" not in name.casefold():
                    continue
                info = proc.info.get("memory_info")
                others.append({
                    "pid": int(proc.info["pid"]),
                    "name": name,
                    "rss_bytes": int(info.rss) if info else None,
                })
            except (psutil.Error, OSError, TypeError, ValueError):
                pass
        return available, rss, others
    except ImportError:
        if os.name != "nt":
            return None, None, None

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        class _ProcessCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MemoryStatus)]
        kernel32.GlobalMemoryStatusEx.restype = ctypes.c_int
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None, None
        counters = _ProcessCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        process = kernel32.GetCurrentProcess()
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_ProcessCounters), ctypes.c_ulong
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return int(status.ullAvailPhys), None, None
        return int(status.ullAvailPhys), int(counters.WorkingSetSize), None


def _set_low_priority_and_single_thread() -> dict[str, object]:
    thread_vars = (
        "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
    )
    for variable in thread_vars:
        os.environ[variable] = "1"
    priority = "unsupported_platform"
    if os.name == "nt":
        below_normal = 0x00004000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel32.SetPriorityClass.restype = ctypes.c_int
        kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        kernel32.GetPriorityClass.restype = ctypes.c_ulong
        handle = kernel32.GetCurrentProcess()
        set_ok = bool(kernel32.SetPriorityClass(handle, below_normal))
        observed = int(kernel32.GetPriorityClass(handle)) if set_ok else None
        priority = "BELOW_NORMAL_PRIORITY_CLASS" if observed == below_normal else "set_failed"
    return {"thread_environment": {name: os.environ[name] for name in thread_vars},
            "windows_priority": priority}


def _resource_recorder(
    path: Path,
    *,
    expected_peak_gib: float = 0.50,
    rss_limit_gib: float = 0.75,
    execution_controls: dict[str, object] | None = None,
) -> Callable[[str, float], None]:
    def check(stage: str, minimum_available_gib: float) -> None:
        available, rss, other_python = _memory_snapshot()
        record = {
            "stage": stage,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "timestamp_local": datetime.now().astimezone().isoformat(),
            "available_bytes": available,
            "available_gib": available / (1024 ** 3) if available is not None else None,
            "process_rss_bytes": rss,
            "process_rss_gib": rss / (1024 ** 3) if rss is not None else None,
            "minimum_available_gib": minimum_available_gib,
            "expected_peak_gib": expected_peak_gib,
            "rss_limit_gib": rss_limit_gib,
            "other_python_processes": other_python,
            "execution_controls": execution_controls,
            "estimate_basis": (
                "single CSV row capped at 16 MiB WKT/100,000 points; only 3,144 FIT accumulators; "
                "streaming rows, no DataFrame/model arrays. 0.50 GiB is a planning estimate, not measured."
            ),
        }
        records: list[dict[str, object]] = []
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and isinstance(existing.get("checks"), list):
                    records = existing["checks"]
            except (OSError, json.JSONDecodeError):
                records = []
        available_ok = available is not None and available >= minimum_available_gib * (1024 ** 3)
        rss_ok = rss is not None and rss <= rss_limit_gib * (1024 ** 3)
        priority_ok = not execution_controls or execution_controls.get("windows_priority") != "set_failed"
        record["priority_ok"] = bool(priority_ok)
        record["passed"] = bool(available_ok and rss_ok and priority_ok)
        records.append(record)
        _atomic_write_json(path, {"checks": records})
        if not available_ok or not rss_ok or not priority_ok:
            raise ExtractionError(
                f"RAM gate failed at {stage}; see {path} (no polling or automatic retry)"
            )
    return check


def write_feature_outputs(
    accumulators: dict[str, VesselAccumulator],
    output_csv: Path,
    manifest: dict[str, object],
    manifest_path: Path,
    *,
    overwrite: bool = False,
) -> None:
    output_csv = Path(output_csv)
    manifest_path = Path(manifest_path)
    if not overwrite and (output_csv.exists() or manifest_path.exists()):
        raise ExtractionError("output exists; pass --overwrite only after reviewing it")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8-sig", newline="", dir=output_csv.parent,
            prefix=output_csv.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temp_name = stream.name
            writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for vessel_id in sorted(accumulators):
                writer.writerow(accumulators[vessel_id].output_row(vessel_id))
        os.replace(temp_name, output_csv)
        temp_name = None
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    manifest["output_csv"] = str(output_csv)
    manifest["output_rows"] = len(accumulators)
    manifest["output_columns"] = list(OUTPUT_COLUMNS)
    _atomic_write_json(manifest_path, manifest)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("pilot", "extract"):
        sub = subparsers.add_parser(mode)
        sub.add_argument("--train-dir", type=Path, default=DEFAULT_TRAIN_DIR)
        sub.add_argument("--roster-npz", type=Path, default=DEFAULT_ROSTER_NPZ)
        sub.add_argument("--roster-key", default="rfid_ids")
        sub.add_argument("--overwrite", action="store_true")
        sub.add_argument(
            "--coordinate-order-confirmed", action="store_true", required=True,
            help="caller confirms official X=longitude, Y=latitude input contract",
        )
        if mode == "pilot":
            sub.add_argument("--physical-line-limit", type=int, default=100)
            sub.add_argument(
                "--output", type=Path,
                default=DEFAULT_OUTPUT_DIR / "pilot_100_features.csv",
            )
            sub.add_argument(
                "--manifest", type=Path,
                default=DEFAULT_OUTPUT_DIR / "pilot_100_manifest.json",
            )
        else:
            sub.add_argument(
                "--output", type=Path,
                default=DEFAULT_OUTPUT_DIR / "derived_features.csv",
            )
            sub.add_argument(
                "--manifest", type=Path,
                default=DEFAULT_OUTPUT_DIR / "derived_features.manifest.json",
            )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        paths = expected_train_paths(args.train_dir)
        if not args.overwrite and (args.output.exists() or args.manifest.exists()):
            raise ExtractionError("output exists; pass --overwrite only after reviewing it")
        controls = _set_low_priority_and_single_thread()
        resource_file = DEFAULT_OUTPUT_DIR / "resource_checks.json"
        resource_check = _resource_recorder(
            resource_file, expected_peak_gib=0.50, rss_limit_gib=0.75,
            execution_controls=controls,
        )
        resource_check("entry_preflight_before_roster_or_scan", 1.5)
        if args.mode == "pilot":
            if not 1 <= args.physical_line_limit <= 100:
                raise ExtractionError("pilot physical-line limit must be between 1 and 100")
            inputs = paths[:1]
            roster = load_roster_npz(args.roster_npz, args.roster_key) if args.roster_npz else None
            limit = args.physical_line_limit
        else:
            inputs = paths
            if not args.roster_npz:
                raise ExtractionError("full extraction requires a FIT roster NPZ")
            roster = load_roster_npz(args.roster_npz, args.roster_key)
            limit = None
        accumulators, manifest = extract_csv_files(
            inputs,
            roster_ids=roster,
            coordinate_order_confirmed=args.coordinate_order_confirmed,
            physical_line_limit=limit,
            resource_check=resource_check,
        )
        manifest["mode"] = args.mode
        manifest["roster_source"] = str(args.roster_npz) if args.roster_npz else None
        manifest["roster_key_read"] = args.roster_key if args.roster_npz else None
        write_feature_outputs(
            accumulators, args.output, manifest, args.manifest,
            overwrite=args.overwrite,
        )
        print(json.dumps({
            "status": "pilot_written" if args.mode == "pilot" else "features_written",
            "mode": args.mode,
            "output_csv": str(args.output),
            "manifest": str(args.manifest),
            "output_rows": len(accumulators),
            "logical_data_rows": manifest["totals"].get("logical_data_rows", 0),
            "roster_matched_rows": manifest["totals"].get("roster_matched_rows", 0),
        }, ensure_ascii=False))
        return 0
    except ExtractionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
