#!/usr/bin/env python3
"""Read-only structural inspection for CSV datasets (Python 3.10+)."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import datetime as dt
import json
import math
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

VERSION = "1.1"
REQUIRED = ("part_dt", "rfid_id", "rfid_time", "geom")
KNOWN = (*REQUIRED, "fishing_code")
KEY_COLUMNS = ("part_dt", "rfid_id", "rfid_time")
GEOMETRY_NOTE = "limited_wkt_2d_multilinestring_structure"
GEOMETRY_SUBSET = (
    "2D MULTILINESTRING with finite XY pairs and at least two points per part; "
    "whole-geometry EMPTY is recognized but is not analyzable; "
    "Z, M, ZM, and EWKT are unsupported; this is not a full OGC WKT validator"
)
_WKT_NUMBER = re.compile(
    r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|inf(?:inity)?|nan)",
    re.IGNORECASE,
)


class _InspectionError(ValueError):
    """An error carrying only a fixed, safe report code."""


class _GeometryError(ValueError):
    """An error carrying only a fixed, safe geometry code."""


@dataclass(frozen=True)
class _GeometryValidation:
    state: str
    issue_code: str | None = None
    part_point_counts: tuple[int, ...] = ()


class _GeometryParser:
    """Parse a limited XY subset without joining parts or retaining coordinates."""

    def __init__(self, value: str, coordinate_assumption: str):
        self.value = value
        self.position = 0
        self.coordinate_assumption = coordinate_assumption
        self.out_of_range = False

    def _space(self) -> bool:
        start = self.position
        while self.position < len(self.value) and self.value[self.position].isspace():
            self.position += 1
        return self.position != start

    def _expect(self, token: str) -> None:
        self._space()
        if self.position >= len(self.value) or self.value[self.position] != token:
            raise _GeometryError("geom_malformed_structure")
        self.position += 1

    def _number(self) -> float:
        self._space()
        match = _WKT_NUMBER.match(self.value, self.position)
        if match is None:
            raise _GeometryError("geom_malformed_structure")
        self.position = match.end()
        number = float(match.group())
        if not math.isfinite(number):
            raise _GeometryError("geom_non_finite_coordinate")
        return number

    def parse(self) -> _GeometryValidation:
        self._expect("(")
        part_point_counts = []
        while True:
            self._expect("(")
            points = 0
            while True:
                x = self._number()
                if not self._space():
                    raise _GeometryError("geom_malformed_structure")
                y = self._number()
                if self.coordinate_assumption == "lonlat" and not (-180 <= x <= 180 and -90 <= y <= 90):
                    self.out_of_range = True
                points += 1
                self._space()
                if self.position >= len(self.value):
                    raise _GeometryError("geom_malformed_structure")
                token = self.value[self.position]
                self.position += 1
                if token == ")":
                    break
                if token != ",":
                    raise _GeometryError("geom_malformed_structure")
            if points < 2:
                raise _GeometryError("geom_part_too_short")
            part_point_counts.append(points)
            self._space()
            if self.position >= len(self.value):
                raise _GeometryError("geom_malformed_structure")
            token = self.value[self.position]
            self.position += 1
            if token == ")":
                break
            if token != ",":
                raise _GeometryError("geom_malformed_structure")
        self._space()
        if self.position != len(self.value):
            raise _GeometryError("geom_malformed_structure")
        return _GeometryValidation(
            "structured_nonempty",
            "geom_lonlat_out_of_range" if self.out_of_range else None,
            tuple(part_point_counts),
        )


def _validate_geometry(value: str, coordinate_assumption: str = "unconfirmed") -> _GeometryValidation:
    """Return only safe codes and part sizes, never raw coordinates."""
    text = value.strip()
    if re.match(r"SRID\s*=", text, re.IGNORECASE):
        return _GeometryValidation("unsupported", "geom_unsupported_representation")
    keyword = re.match(r"[A-Za-z]+", text)
    if keyword is None or keyword.group().upper() != "MULTILINESTRING":
        return _GeometryValidation("invalid", "geom_prefix_mismatch")
    body = text[keyword.end():].lstrip()
    if re.match(r"(?:ZM|Z|M)(?=\s|\(|$)", body, re.IGNORECASE):
        return _GeometryValidation("unsupported", "geom_unsupported_representation")
    if body.upper() == "EMPTY":
        return _GeometryValidation("empty", "geom_empty")
    try:
        return _GeometryParser(body, coordinate_assumption).parse()
    except _GeometryError as exc:
        return _GeometryValidation("invalid", str(exc))


def _is_reparse(st: os.stat_result) -> bool:
    # Windows junctions and symlinks carry FILE_ATTRIBUTE_REPARSE_POINT.
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _safe_file(path: Path) -> bool:
    try:
        st = path.lstat()
    except OSError:
        return False
    return not (stat.S_ISLNK(st.st_mode) or _is_reparse(st)) and stat.S_ISREG(st.st_mode)


def _walk(root: Path, recursive: bool, limit: int) -> tuple[list[Path], bool, int, int, int]:
    """Collect no more than limit+1 regular, non-link files; return truncation."""
    found: list[Path] = []
    excluded_links = 0
    traversal_errors = 0
    placeholders = 0

    def visit(folder: Path) -> Iterator[Path]:
        nonlocal excluded_links, traversal_errors, placeholders
        try:
            entries = os.scandir(folder)
        except OSError:
            traversal_errors += 1
            return
        with entries:
            for entry in entries:
                if entry.name == ".gitkeep":
                    placeholders += 1
                    continue
                path = Path(entry.path)
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    traversal_errors += 1
                    continue
                if stat.S_ISLNK(st.st_mode) or _is_reparse(st):
                    excluded_links += 1
                    continue
                if stat.S_ISREG(st.st_mode):
                    yield path
                elif recursive and stat.S_ISDIR(st.st_mode):
                    yield from visit(path)

    for path in visit(root):
        found.append(path)
        if len(found) > limit:
            return found[:limit], True, excluded_links, traversal_errors, placeholders
    return found, False, excluded_links, traversal_errors, placeholders


def _csv_report(path: Path, rel: str, size: int, args: argparse.Namespace) -> dict[str, Any]:
    before = path.stat()
    coordinate_assumption = args.coordinate_assumption
    geometry_counts = {
        "checked_values": 0,
        "structured_nonempty": 0,
        "empty": 0,
        "unsupported": 0,
        "invalid": 0,
        "parts": 0,
        "points": 0,
        "coordinate_out_of_range": 0,
    }
    geometry_issue_rows: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "source": path.name,
        "relative_path": rel,
        "status": "ok",
        "size_bytes": size,
        "header": [],
        "sample_rows": 0,
        "sample_limit_rows": args.sample_rows,
        "total_rows": None,
        "sample_truncated": False,
        "field_empty_counts": {},
        "issue_counts": {},
        "geometry_validation": GEOMETRY_NOTE,
        "geometry_supported_subset": GEOMETRY_SUBSET,
        "geometry_part_handling": "parsed_separately_without_cross_part_segments",
        "geometry_counts": geometry_counts,
        "geometry_issue_rows": geometry_issue_rows,
        "geometry_issue_row_numbering": "one_based_data_records_excluding_header",
        "coordinate_assumption": coordinate_assumption,
        "coordinate_validation": (
            "bounds_checked_under_explicit_lonlat_assumption"
            if coordinate_assumption == "lonlat" else "not_checked_crs_unconfirmed"
        ),
        "crs_verified": False,
        "distance_calculation_performed": False,
        "source_change_detection": "size_mtime_checked",
    }
    # A large configured ceiling must not request that much memory for a tiny
    # file. One extra byte detects growth beyond the inspected size snapshot.
    read_limit = min(size, args.max_bytes)
    if read_limit >= sys.maxsize:
        raise _InspectionError("read_size_exceeds_supported_integer_range")
    try:
        csv.field_size_limit(read_limit)
    except OverflowError:
        raise _InspectionError("csv_field_size_limit_unsupported") from None
    with path.open("rb") as stream:
        data = stream.read(read_limit + 1)
    if len(data) > args.max_bytes:
        raise _InspectionError("source_changed_during_read")
    try:
        decoded = data.decode(args.encoding, errors="strict")
    except (UnicodeDecodeError, LookupError) as exc:
        raise _InspectionError(f"encoding_error:{type(exc).__name__}") from None
    reader = csv.reader(decoded.splitlines(keepends=True), delimiter=args.delimiter, strict=True)
    try:
        header = next(reader)
    except StopIteration:
        header = []
    except csv.Error:
        raise _InspectionError("csv_parse_error_in_header") from None
    recognized_header = bool(set(header) & set(KNOWN))
    # The first record may be data containing one accidental known field name.
    # Unknown header strings must never become output values or dictionary keys.
    result["header"] = [name for name in header if name in KNOWN]
    result["header_recognized"] = recognized_header
    result["header_column_count"] = len(header)
    result["unknown_header_column_count"] = sum(name not in KNOWN for name in header)
    issues: dict[str, int] = {}
    dupes = len(header) - len(set(header))
    if dupes:
        issues["duplicate_header_names"] = dupes
    blanks = sum(1 for h in header if not h.strip())
    if blanks:
        issues["blank_header_names"] = blanks
    missing = [name for name in REQUIRED if name not in header]
    if args.expect == "train" and "fishing_code" not in header:
        missing.append("fishing_code")
    if missing:
        issues["missing_required_columns"] = len(set(missing))
        result["missing_columns"] = sorted(set(missing))
    invalid_header = bool(dupes or blanks or not recognized_header)
    empty_counts = {} if invalid_header else {name: 0 for name in header if name in KNOWN}
    result["semantic_validation"] = "skipped_invalid_header" if invalid_header else "checked_sample"
    key_available = not invalid_header and all(name in header for name in KEY_COLUMNS)
    key_counts: dict[tuple[str, ...], int] = {}
    key_skipped_rows = 0
    sampled = 0
    more = False
    parse_error_stage = None
    try:
        for row in reader:
            if sampled >= args.sample_rows:
                more = True
                break
            sampled += 1
            if len(row) != len(header):
                issues["sample_column_count_mismatch"] = issues.get("sample_column_count_mismatch", 0) + 1
            if not invalid_header:
                for idx, name in enumerate(header):
                    if name in KNOWN and (idx >= len(row) or row[idx] == ""):
                        empty_counts[name] += 1
            if invalid_header:
                key_skipped_rows += 1
                continue
            values = {name: row[idx] for idx, name in enumerate(header) if name in KNOWN and idx < len(row)}
            if key_available and all(values.get(name) for name in KEY_COLUMNS):
                key = tuple(values[name] for name in KEY_COLUMNS)
                key_counts[key] = key_counts.get(key, 0) + 1
            else:
                key_skipped_rows += 1
            if "part_dt" in values and values["part_dt"]:
                value = values["part_dt"]
                try:
                    if len(value) != 8 or not value.isascii() or not value.isdigit():
                        raise ValueError
                    dt.datetime.strptime(value, "%Y%m%d")
                except ValueError:
                    issues["invalid_part_dt"] = issues.get("invalid_part_dt", 0) + 1
            if "rfid_time" in values and values["rfid_time"]:
                value = values["rfid_time"]
                normalized_hour = value.lstrip("0") or "0"
                if (not value.isascii() or not value.isdigit() or len(normalized_hour) > 2
                        or int(normalized_hour) > 23):
                    issues["invalid_rfid_time"] = issues.get("invalid_rfid_time", 0) + 1
            if "geom" in values and values["geom"]:
                validation = _validate_geometry(values["geom"], coordinate_assumption)
                geometry_counts["checked_values"] += 1
                geometry_counts[validation.state] += 1
                geometry_counts["parts"] += len(validation.part_point_counts)
                geometry_counts["points"] += sum(validation.part_point_counts)
                if validation.issue_code == "geom_lonlat_out_of_range":
                    geometry_counts["coordinate_out_of_range"] += 1
                if validation.issue_code:
                    code = validation.issue_code
                    issues[code] = issues.get(code, 0) + 1
                    geometry_issue_rows.append({"data_row": sampled, "code": code})
    except csv.Error:
        # csv.reader parses one lookahead record to decide whether the sample
        # was truncated. Keep the already inspected rows if that parse fails.
        parse_error_stage = "after_sample" if sampled >= args.sample_rows else "in_sample"
        issues[f"csv_parse_error_{parse_error_stage}"] = 1
        result["csv_parse_error"] = {
            "code": "csv_parse_error",
            "stage": parse_error_stage,
            "next_data_row": sampled + 1,
        }
        more = True
    result["sample_rows"] = sampled
    result["sample_truncated"] = more
    result["sampling_stop_reason"] = (
        f"csv_parse_error_{parse_error_stage}" if parse_error_stage
        else "sample_limit" if more else "end_of_file"
    )
    if not more and recognized_header:
        result["total_rows"] = sampled
    eligible_rows = sum(key_counts.values())
    result["candidate_key_check"] = {
        "columns": list(KEY_COLUMNS),
        "scope": "inspected_sample_only",
        "available": key_available,
        "eligible_rows": eligible_rows,
        "skipped_rows": key_skipped_rows,
        "distinct_keys": len(key_counts),
        "collision_rows": eligible_rows - len(key_counts),
        "collision_groups": sum(count > 1 for count in key_counts.values()),
        "uniqueness_requirement_verified": False,
        "deduplication_performed": False,
    }
    result["field_empty_counts"] = empty_counts
    required_values = (*REQUIRED, "fishing_code") if args.expect == "train" else REQUIRED
    blank_required = sum(empty_counts.get(name, 0) for name in required_values)
    if blank_required:
        issues["empty_required_values"] = blank_required
    result["issue_counts"] = issues
    if issues:
        result["status"] = "sample_issues_detected"
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(data) != size:
        raise _InspectionError("source_changed_during_read")
    return result


def _inspect(path: Path, rel: str, args: argparse.Namespace) -> dict[str, Any]:
    try:
        if not _safe_file(path):
            return {"source": path.name, "relative_path": rel, "status": "skipped_symlink_or_nonfile"}
        before = path.stat()
        size = before.st_size
        if size > args.max_bytes:
            return {"source": path.name, "relative_path": rel, "status": "metadata_only_size_limit", "size_bytes": size,
                    "total_rows": None, "source_change_detection": "metadata_snapshot_only"}
        if path.suffix.lower() != ".csv":
            return {"source": path.name, "relative_path": rel, "status": "metadata_only", "size_bytes": size,
                    "format": "zip" if path.suffix.lower() == ".zip" else "unsupported", "total_rows": None,
                    "source_change_detection": "metadata_snapshot_only"}
        return _csv_report(path, rel, size, args)
    except (OSError, ValueError, csv.Error) as exc:
        if isinstance(exc, _InspectionError):
            reason = str(exc)
        elif isinstance(exc, OSError):
            reason = "file_io_error"
        elif isinstance(exc, csv.Error):
            reason = "csv_parse_error"
        else:
            reason = "inspection_value_error"
        status = "error"
        return {"source": path.name, "relative_path": rel, "status": status,
                "error": reason, "issue_counts": {"file_inspection_error": 1},
                "source_change_detection": "size_mtime_checked"}


def _within(candidate: Path, directory: Path) -> bool:
    try:
        candidate.relative_to(directory)
        return True
    except ValueError:
        return False


def _has_reparse_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            st = current.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode) or _is_reparse(st):
            return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only CSV structure inspection")
    parser.add_argument("path", help="Input file or directory")
    parser.add_argument("--output", help="Write JSON report to a path (default: stdout)")
    parser.add_argument("--recursive", action="store_true", help="Recurse through input directories")
    parser.add_argument("--sample-rows", type=int, default=100)
    parser.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-files", type=int, default=100)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--expect", choices=("unknown", "train", "test"), default="unknown")
    parser.add_argument(
        "--coordinate-assumption", choices=("unconfirmed", "lonlat"), default="unconfirmed",
        help="Check longitude/latitude bounds only under an explicit lonlat assumption; this does not verify CRS",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.sample_rows < 1 or args.max_bytes < 1 or args.max_files < 1:
        parser.error("sample-rows, max-bytes, and max-files must be positive integers")
    if len(args.delimiter) != 1 or args.delimiter in "\r\n\"":
        parser.error("delimiter must be one non-newline, non-quote character")
    try:
        "".encode(args.encoding)
    except LookupError:
        parser.error(f"unknown encoding: {args.encoding}")
    source_candidate = Path(args.path).expanduser().absolute()
    if _has_reparse_component(source_candidate):
        parser.error("input source symlinks and reparse points are excluded")
    source = source_candidate.resolve()
    if not source.exists():
        parser.error("input path does not exist")
    if not source.is_file() and not source.is_dir():
        parser.error("input path must be a file or directory")
    output = Path(args.output).expanduser().resolve() if args.output else None
    if output is not None:
        if source.is_file() and output == source:
            parser.error("output must not be the input file")
        if source.is_dir() and _within(output, source):
            parser.error("output must be outside the input directory")

    truncated = False
    excluded_links = 0
    traversal_errors = 0
    placeholders = 0
    if source.is_file():
        files = [source]
        root = source.parent
    else:
        root = source
        files, truncated, excluded_links, traversal_errors, placeholders = _walk(
            source, args.recursive, args.max_files
        )
    if output is not None and output.exists():
        try:
            if any(output.samefile(path) for path in files):
                parser.error("output must not be the same file as an input file")
        except OSError:
            pass
    entries = []
    errors = 0
    csv_files = 0
    metadata_files = 0
    for path in files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        report = _inspect(path, rel, args)
        entries.append(report)
        errors += report.get("status") == "error"
        csv_files += report.get("status") in ("ok", "sample_issues_detected")
        metadata_files += report.get("status", "").startswith("metadata_only")
    result = {
        "version": VERSION,
        "evidence": "local_structure_inspection",
        "real_data_evaluation_performed": False,
        "expect": args.expect,
        "coordinate_assumption": args.coordinate_assumption,
        "crs_verified": False,
        "distance_calculation_performed": False,
        "scanned_files": entries,
        "csv_files_inspected": csv_files,
        "metadata_only_files": metadata_files,
        "no_supported_data_found": csv_files == 0,
        "truncated": truncated,
        "excluded_symlink_or_reparse_entries": excluded_links,
        "traversal_errors": traversal_errors,
        "placeholder_files_excluded": placeholders,
        "sampling_limits": {"sample_rows": args.sample_rows, "max_bytes": args.max_bytes,
                            "max_files": args.max_files, "recursive": args.recursive,
                            "encoding": args.encoding, "delimiter": args.delimiter},
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        temporary_name = None
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                             dir=output.parent, prefix=".inspect_data-",
                                             suffix=".tmp", delete=False) as stream:
                temporary_name = stream.name
                stream.write(rendered)
            os.replace(temporary_name, output)
        except OSError as exc:
            if temporary_name:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    pass
            print(f"cannot write output report: {exc}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(rendered)
    sampled_issues = any(bool(item.get("issue_counts")) for item in entries)
    return 1 if errors or traversal_errors or sampled_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
