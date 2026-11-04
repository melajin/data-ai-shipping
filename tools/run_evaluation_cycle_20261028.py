#!/usr/bin/env python3
"""Privacy-preserving streaming inventory for the 2026-10-28 source review.

This tool records only aggregate CSV/WKT diagnostics and salted identifiers in
SQLite. It does not train, infer, or copy source rows/geometries.
"""
from __future__ import annotations

import argparse
import codecs
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import stat
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_OUT = ROOT / "outputs" / "evaluation_cycle_20261028"
SALT = b"fishing-evaluation-cycle-20261028-id-index-v1"
VERSION = "evaluation_cycle_inventory_v2"
KNOWN = {"part_dt", "rfid_id", "rfid_time", "geom", "fishing_code"}
CLASS_LABELS = {"연안복합", "자망", "채낚기연승낚시", "통발"}
NUM = re.compile(r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|inf(?:inity)?|nan)", re.I)


class DigestRaw(io.RawIOBase):
    """Read-through wrapper that hashes exact source bytes during CSV decoding."""
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes_hashed = 0
        self.eof_reached = False

    def readable(self):
        return True

    def readinto(self, buffer):
        chunk = self.stream.read(len(buffer))
        if not chunk:
            self.eof_reached = True
            return 0
        self.digest.update(chunk)
        self.bytes_hashed += len(chunk)
        buffer[:len(chunk)] = chunk
        return len(chunk)

    def close(self):
        if not self.closed:
            self.stream.close()
        super().close()


def salted_hash(value: str) -> str:
    return hashlib.sha256(SALT + value.encode("utf-8", errors="surrogatepass")).hexdigest()


def geometry_summary(value: str, include_parts: bool = False) -> dict:
    """Parse a restricted 2D MULTILINESTRING, retaining counts and global bounds only."""
    text = value.strip()
    if re.match(r"SRID\s*=", text, re.I):
        return {"state": "unsupported", "issue": "geom_unsupported_representation"}
    kw = re.match(r"[A-Za-z]+", text)
    if not kw or kw.group().upper() != "MULTILINESTRING":
        return {"state": "invalid", "issue": "geom_prefix_mismatch"}
    body = text[kw.end():].lstrip()
    if re.match(r"(?:ZM|Z|M)(?=\s|\(|$)", body, re.I):
        return {"state": "unsupported", "issue": "geom_unsupported_representation"}
    if body.upper() == "EMPTY":
        return {"state": "empty", "issue": "geom_empty", "parts": 0, "points": 0}
    pos = 0
    count_parts = count_points = 0
    xmin = ymin = math.inf
    xmax = ymax = -math.inf
    out_of_range = False
    parsed_parts = []

    def ws():
        nonlocal pos
        start = pos
        while pos < len(body) and body[pos].isspace():
            pos += 1
        return pos != start

    def expect(ch):
        nonlocal pos
        ws()
        if pos >= len(body) or body[pos] != ch:
            raise ValueError
        pos += 1

    def number():
        nonlocal pos
        ws()
        m = NUM.match(body, pos)
        if not m:
            raise ValueError
        pos = m.end()
        n = float(m.group())
        if not math.isfinite(n):
            raise OverflowError
        return n

    try:
        expect("(")
        while True:
            expect("(")
            part_points = 0
            coordinates = []
            while True:
                x = number()
                if not ws():
                    raise ValueError
                y = number()
                xmin, xmax = min(xmin, x), max(xmax, x)
                ymin, ymax = min(ymin, y), max(ymax, y)
                out_of_range |= not (-180 <= x <= 180 and -90 <= y <= 90)
                coordinates.append([x, y])
                part_points += 1
                ws()
                if pos >= len(body):
                    raise ValueError
                token = body[pos]
                pos += 1
                if token == ")":
                    break
                if token != ",":
                    raise ValueError
            if part_points < 2:
                return {"state": "invalid", "issue": "geom_part_too_short"}
            count_parts += 1
            count_points += part_points
            if include_parts:
                parsed_parts.append(coordinates)
            ws()
            if pos >= len(body):
                raise ValueError
            token = body[pos]
            pos += 1
            if token == ")":
                break
            if token != ",":
                raise ValueError
        ws()
        if pos != len(body):
            raise ValueError
    except OverflowError:
        return {"state": "invalid", "issue": "geom_non_finite_coordinate"}
    except ValueError:
        return {"state": "invalid", "issue": "geom_malformed_structure"}
    result = {"state": "structured_nonempty", "issue": None, "parts": count_parts,
              "points": count_points, "bounds": (xmin, ymin, xmax, ymax),
              "lonlat_out_of_range": out_of_range}
    if include_parts:
        result["parsed_parts"] = parsed_parts
    return result


def _connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    has_meta = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='scan_meta'").fetchone()
    old_schema = con.execute("SELECT value FROM scan_meta WHERE key='schema'").fetchone() if has_meta else None
    if old_schema and old_schema[0] != VERSION:
        existing = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("files", "records", "vessel_label_pairs", "vessel_summary", "key_seen", "feature_samples", "quarantine_rows", "label_index"):
            if table in existing:
                con.execute(f"DELETE FROM {table}")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS scan_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS files(
        file_ordinal INTEGER PRIMARY KEY, relative_path TEXT, size_bytes INTEGER,
        mtime_ns INTEGER, sha256 TEXT, status TEXT, rows_scanned INTEGER,
        partial INTEGER, elapsed_seconds REAL, aggregate_json TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS records(
        file_ordinal INTEGER NOT NULL, record_ordinal INTEGER NOT NULL,
        vessel_hash TEXT, key_hash TEXT, date_text TEXT, time_text TEXT,
        label_index INTEGER, label_sha256 TEXT, geom_state TEXT,
        geom_parts INTEGER, geom_points INTEGER,
        PRIMARY KEY(file_ordinal, record_ordinal));
      CREATE TABLE IF NOT EXISTS vessel_label_pairs(
        vessel_hash TEXT NOT NULL, label_sha256 TEXT NOT NULL,
        PRIMARY KEY(vessel_hash,label_sha256));
      CREATE TABLE IF NOT EXISTS vessel_summary(
        file_ordinal INTEGER NOT NULL, vessel_hash TEXT NOT NULL, label_sha256 TEXT,
        label_code TEXT, record_count INTEGER NOT NULL, min_date TEXT, max_date TEXT,
        PRIMARY KEY(file_ordinal,vessel_hash,label_sha256));
      CREATE TABLE IF NOT EXISTS key_seen(key_hash TEXT PRIMARY KEY, occurrences INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS quarantine_rows(
        file_ordinal INTEGER NOT NULL, record_ordinal INTEGER NOT NULL, vessel_hash TEXT,
        label_sha256 TEXT, reason_codes_json TEXT NOT NULL,
        PRIMARY KEY(file_ordinal,record_ordinal));
      CREATE TABLE IF NOT EXISTS feature_samples(
        file_ordinal INTEGER NOT NULL, record_ordinal INTEGER NOT NULL, vessel_hash TEXT NOT NULL,
        sample_sha256 TEXT NOT NULL, label_sha256 TEXT NOT NULL, label_code TEXT NOT NULL,
        part_dt TEXT, month INTEGER, time_band INTEGER, geometry_state TEXT NOT NULL, feature_valid INTEGER NOT NULL,
        feature_reason TEXT, feature_values_json TEXT, degree_control_values_json TEXT,
        PRIMARY KEY(file_ordinal,record_ordinal));
      CREATE TABLE IF NOT EXISTS label_index(
        label_index INTEGER PRIMARY KEY, label_sha256 TEXT UNIQUE NOT NULL, label_code TEXT);
    """)
    columns = {row[1] for row in con.execute("PRAGMA table_info(label_index)")}
    if "label_code" not in columns:
        con.execute("ALTER TABLE label_index ADD COLUMN label_code TEXT")
    sample_columns = {row[1] for row in con.execute("PRAGMA table_info(feature_samples)")}
    if "month" not in sample_columns:
        con.execute("ALTER TABLE feature_samples ADD COLUMN month INTEGER")
    if "degree_control_values_json" not in sample_columns:
        con.execute("ALTER TABLE feature_samples ADD COLUMN degree_control_values_json TEXT")
    con.execute("INSERT OR REPLACE INTO scan_meta VALUES (?,?)", ("schema", VERSION))
    con.execute("INSERT OR REPLACE INTO scan_meta VALUES (?,?)", ("id_hash", "sha256(fixed_salt || UTF-8 value); salt identifier=20261028_v1"))
    return con


def _safe_csv_files(root: Path) -> list[Path]:
    found = []
    for folder, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(folder)
        safe_dirs = []
        for name in dirnames:
            candidate = base / name
            try:
                st = candidate.lstat()
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and not (getattr(st, "st_file_attributes", 0) & 0x400):
                safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in filenames:
            candidate = base / name
            if candidate.suffix.lower() != ".csv":
                continue
            try:
                st = candidate.lstat()
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode) and not (getattr(st, "st_file_attributes", 0) & 0x400):
                found.append(candidate)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix().casefold())


def _month_from_path(path: Path) -> int | None:
    match = re.search(r"(?:^|[^0-9])([1-9]|1[0-2])월", path.name)
    return int(match.group(1)) if match else None


def _write_vessel_features(con: sqlite3.Connection, out: Path) -> dict:
    label_rows = {}
    for vessel_hash, label_hash, label_code, row_count in con.execute(
            "SELECT vessel_hash,label_sha256,label_code,SUM(record_count) FROM vessel_summary "
            "WHERE label_sha256 IS NOT NULL GROUP BY vessel_hash,label_sha256,label_code"):
        label_rows.setdefault(vessel_hash, []).append((label_hash, label_code, row_count))
    conflicts = {v: rows for v, rows in label_rows.items() if len(rows) != 1}
    vessels = []
    feature_row_count = 0
    for vessel_hash, labels in label_rows.items():
        if vessel_hash in conflicts:
            continue
        label_hash, label_code, total_rows = labels[0]
        rows = []
        for file_ordinal, record_ordinal, month, valid, reason, values, degree in con.execute(
                "SELECT file_ordinal,record_ordinal,month,feature_valid,feature_reason,feature_values_json,degree_control_values_json "
                "FROM feature_samples WHERE vessel_hash=? AND label_sha256=? ORDER BY file_ordinal,record_ordinal",
                (vessel_hash, label_hash)):
            rows.append({"file_ordinal": file_ordinal, "record_ordinal": record_ordinal, "month": month,
                         "valid": bool(valid), "reason": reason, "values": json.loads(values),
                         "degree_control_values": json.loads(degree)})
        feature_row_count += len(rows)
        vessels.append({"vessel_hash": vessel_hash, "label": label_code, "rows": rows})
    payload = {"schema_version": "fishing_real_vessel_features_v1", "source_type": "real_csv_deterministic_sample",
               "selection": {"rule": "lowest SHA256(salted_vessel_hash || file_ordinal || record_ordinal)",
                             "per_labeled_train_file_per_vessel": 4,
                             "max_rows_per_vessel_if_six_months": 24,
                             "selected_by_label_or_geometry": False},
               "feature_names": ["mean_part_straightness", "mean_abs_turn_rad", "turn_direction_concentration",
                                 "std_turn_rad", "max_abs_turn_rad", "mean_part_spread_ratio",
                                 "mean_part_chord_deviation_ratio", "cloud_spread_ratio",
                                 "cloud_radial_fourth_moment_ratio"],
               "coordinate_assumptions": {"order": "X=longitude,Y=latitude",
                                           "local_tangent": "x=(lon-lon0)*pi/180*cos(lat0*pi/180); y=(lat-lat0)*pi/180; Earth radius omitted",
                                           "degree_control": "x=lon-lon0; y=lat-lat0",
                                           "exact_datum_epsg": "unconfirmed", "metric_distance_or_speed": False},
               "one_label_vessels": len(vessels), "conflicting_label_vessels_excluded": len(conflicts),
               "conflicting_label_rows_excluded": sum(sum(row[2] for row in rows) for rows in conflicts.values()),
               "feature_rows_including_invalid": feature_row_count,
               "limitations": ["Each row is a deterministic bounded geometry sample, not a full-vessel time series.",
                               "Invalid selected rows remain in the row denominator with valid=false.",
                               "local_tangent features omit Earth radius and do not represent metres or speed.",
                               "The exact datum/EPSG remains unconfirmed."],
               "vessels": vessels}
    target = out / "vessel_features.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return {"path": str(target), "vessel_count": len(vessels), "conflicting_label_vessels_excluded": len(conflicts),
            "conflicting_label_rows_excluded": payload["conflicting_label_rows_excluded"],
            "feature_rows_including_invalid": feature_row_count}


def repair_cached_outputs(out: Path) -> dict:
    """Create a safe corrected view from the completed v1 cache without rereading CSVs."""
    out = out.resolve()
    report_path = out / "full_scan.json"
    feature_path = out / "vessel_features.json"
    db_path = out / "inspection_cache.sqlite3"
    existing_v2 = out / "vessel_features_v2.json"
    existing_audit = out / "cache_repair_audit.json"
    if report_path.is_file() and existing_v2.is_file() and existing_audit.is_file():
        try:
            current = json.loads(report_path.read_text(encoding="utf-8"))
            if current.get("schema_version") == "evaluation_cycle_inventory_v2_repaired":
                return {"already_repaired": True, "train_gate": current.get("evaluation_gates", {}).get("train_six_month_full_hash_and_clean_eof"),
                        "test_gate": current.get("evaluation_gates", {}).get("test_six_month_full_parse"),
                        "feature_cache": current.get("feature_cache"),
                        "vessel_features_v2_sha256": hashlib.sha256(existing_v2.read_bytes()).hexdigest(),
                        "repair_audit": str(existing_audit)}
        except (OSError, json.JSONDecodeError):
            pass
    if not report_path.is_file() or not feature_path.is_file() or not db_path.is_file():
        raise ValueError("completed v1 scan artifacts are required")
    report_bytes = report_path.read_bytes()
    feature_bytes = feature_path.read_bytes()
    original_report_sha = hashlib.sha256(report_bytes).hexdigest()
    original_feature_sha = hashlib.sha256(feature_bytes).hexdigest()
    report = json.loads(report_bytes.decode("utf-8"))
    features = json.loads(feature_bytes.decode("utf-8"))
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    files = {row["file_ordinal"]: dict(row) for row in conn.execute("SELECT file_ordinal,relative_path,size_bytes,mtime_ns,sha256,status,rows_scanned,partial,elapsed_seconds,aggregate_json FROM files")}
    month_by_file = {i: _month_from_path(Path(row["relative_path"])) for i, row in files.items()}
    if any(month_by_file.get(i) != i + 1 for i in range(6)):
        conn.close()
        raise ValueError("train CSV basenames do not map cleanly to months 1-6")
    quarantine = conn.execute("SELECT file_ordinal,record_ordinal,vessel_hash,label_sha256,label_code,part_dt,time_band,geometry_state,feature_valid FROM feature_samples WHERE file_ordinal=5 AND record_ordinal=127862").fetchone()
    if (quarantine is None or quarantine["part_dt"] is not None or quarantine["time_band"] is not None
            or quarantine["geometry_state"] != "invalid" or quarantine["feature_valid"] != 0
            or quarantine["label_code"] in CLASS_LABELS):
        conn.close()
        raise ValueError("the identified structural-invalid row did not match cached evidence")

    # Verify every selected source date agrees with the month encoded in its CSV basename.
    date_mismatches = 0
    selected_rows = 0
    for row in conn.execute("SELECT file_ordinal,record_ordinal,part_dt FROM feature_samples"):
        selected_rows += 1
        expected_month = month_by_file.get(row["file_ordinal"])
        actual_month = int(row["part_dt"][5:7]) if row["part_dt"] else None
        if (row["file_ordinal"], row["record_ordinal"]) == (5, 127862):
            continue
        date_mismatches += int(actual_month is None or actual_month != expected_month)
    if date_mismatches:
        conn.close()
        raise ValueError("selected-row date/month alignment failed")

    unknown_entries = [entry for entry in report.get("label_distribution", [])
                       if entry.get("label_code") not in CLASS_LABELS]
    unknown_counts = {}
    unknown_codes = set()
    for entry in unknown_entries:
        digest = entry.get("label_sha256") or salted_hash(entry.get("label_code", ""))
        unknown_counts[digest] = unknown_counts.get(digest, 0) + int(entry.get("rows", 0))
        unknown_codes.add(entry.get("label_code", ""))
    if sum(unknown_counts.values()) != 1:
        conn.close()
        raise ValueError("expected exactly one unknown label row in source report")

    # Rebuild the feature payload by quarantining only the diagnosed row, never its vessel wholesale.
    class_vessels = []
    skipped_rows = 0
    for vessel in features.get("vessels", []):
        code = vessel.get("label")
        kept_rows = []
        for row in vessel.get("rows", []):
            location = (row.get("file_ordinal"), row.get("record_ordinal"))
            if location == (5, 127862):
                skipped_rows += 1
                continue
            row["month"] = month_by_file.get(row.get("file_ordinal"))
            if code not in CLASS_LABELS:
                # This can only represent the structurally invalid label bucket here.
                skipped_rows += 1
                continue
            kept_rows.append(row)
        if code in CLASS_LABELS and kept_rows:
            class_vessels.append({"vessel_hash": vessel["vessel_hash"], "label": code, "rows": kept_rows})
        elif code not in CLASS_LABELS:
            skipped_rows += max(0, len(vessel.get("rows", [])) - skipped_rows)
    conn.close()
    if skipped_rows != 1:
        raise ValueError("exactly one selected row must be quarantined")

    support = {}
    for code in CLASS_LABELS:
        rows = [row for vessel in class_vessels if vessel["label"] == code for row in vessel["rows"]]
        support[code] = {"vessels": sum(v["label"] == code for v in class_vessels),
                         "selected_rows": len(rows),
                         "valid_rows": sum(bool(row["valid"]) for row in rows),
                         "invalid_rows": sum(not bool(row["valid"]) for row in rows)}

    safe_report = report
    safe_report["schema_version"] = "evaluation_cycle_inventory_v2_repaired"
    safe_report["label_vocabulary"] = {"official_class_count": 4, "unknown_label_text_suppressed": True,
                                       "unknown_buckets": [{"label_sha256": h, "rows": n} for h, n in sorted(unknown_counts.items())]}
    safe_report["label_distribution"] = [entry for entry in report.get("label_distribution", [])
                                           if entry.get("label_code") in CLASS_LABELS]
    safe_report["label_distribution"] = sorted(safe_report["label_distribution"], key=lambda e: e["label_sha256"])
    for index, entry in enumerate(safe_report["label_distribution"]):
        entry["label_index"] = index
    for file_row in safe_report.get("files", []):
        agg = file_row.get("aggregate", {})
        raw_counts = agg.get("label_counts", {})
        safe_counts = {code: count for code, count in raw_counts.items() if code in CLASS_LABELS}
        hashes = agg.get("label_hashes", {})
        safe_hashes = {digest: code for digest, code in hashes.items() if code in CLASS_LABELS}
        unknown = {salted_hash(code): count for code, count in raw_counts.items() if code not in CLASS_LABELS}
        agg["label_counts"] = safe_counts
        agg["label_hashes"] = safe_hashes
        agg["unknown_label_counts"] = unknown
        if file_row.get("file_ordinal") == 5:
            agg["quarantined_rows"] = 1
            agg["quarantine_reason_counts"] = {"invalid_or_missing_part_dt": 1,
                                                "invalid_or_missing_rfid_time": 1,
                                                "nonclass_label_hash_only": 1}
        # Explicitly distinguish first-pass temporary parses from final retained K rows.
        agg["temporary_reservoir_candidate_parses"] = agg.pop("geometry_sampled_values", 0)
        agg["retained_feature_rows"] = sum(1 for v in class_vessels for r in v["rows"] if r["file_ordinal"] == file_row.get("file_ordinal"))
    safe_report["feature_cache"] = {"path": str(out / "vessel_features_v2.json"),
                                    "vessel_count": len(class_vessels),
                                    "conflicting_label_vessels_excluded": 0,
                                    "quarantined_rows": 1,
                                    "feature_rows_including_invalid": sum(x["selected_rows"] for x in support.values()),
                                    "class_support": support,
                                    "ready_for_model_input": True}
    train_files = [safe_report["files"][i] for i in range(6)]
    train_gate = all(row.get("status") == "scan_completed" and len(row.get("sha256", "")) == 64
                     and row.get("source_changed_during_scan") is False for row in train_files)
    test_files = safe_report["files"][6:12]
    safe_report["evaluation_gates"] = {"train_six_month_full_hash_and_clean_eof": train_gate,
                                      "test_six_month_full_parse": all(row.get("status") == "scan_completed" for row in test_files),
                                      "test_limitations": "file ordinal 11 has a CSV parse error; only 61,586 rows reached the parser",
                                      "model_training_or_evaluation_performed": False}
    safe_report["quarantine"] = [{"file_ordinal": 5, "record_ordinal": 127862,
                                  "label_sha256": quarantine["label_sha256"],
                                  "vessel_hash": quarantine["vessel_hash"],
                                  "reason_codes": ["invalid_or_missing_part_dt", "invalid_or_missing_rfid_time",
                                                   "nonclass_label_hash_only", "geom_prefix_mismatch"],
                                  "action": "exclude this row from label/vessel/model aggregates; source CSV unchanged"}]
    safe_report["month_mapping"] = {str(i): month_by_file[i] for i in range(6)}
    safe_report["month_mapping_check"] = {"selected_source_dates_checked": selected_rows - 1,
                                           "mismatches": date_mismatches,
                                           "source": "CSV basename, cross-checked against selected part_dt month"}
    safe_report["repair_audit_path"] = str(out / "cache_repair_audit.json")

    v2 = dict(features)
    v2["schema_version"] = "fishing_real_vessel_features_v2"
    v2["vessels"] = class_vessels
    v2["one_label_vessels"] = len(class_vessels)
    v2["conflicting_label_vessels_excluded"] = 0
    v2["quarantined_rows_excluded"] = 1
    v2["class_support"] = support
    v2["month_source"] = "monthly CSV basename, validated against source part_dt month"
    v2["selection"]["quarantined_rows_excluded_after_hash_selection"] = 1
    v2_path = out / "vessel_features_v2.json"
    v2_path.write_text(json.dumps(v2, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    safe_report_bytes = (json.dumps(safe_report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    report_path.write_bytes(safe_report_bytes)
    feature_path.write_text(json.dumps({"schema_version": "superseded_vessel_features_v1",
                                        "superseded_by": "vessel_features_v2.json",
                                        "reason": "A structurally invalid row contained a nonclass label; use the repaired version."},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit = {"schema_version": "evaluation_cycle_cache_repair_audit_v1",
             "original_full_scan_sha256": original_report_sha,
             "original_vessel_features_sha256": original_feature_sha,
             "repaired_full_scan_sha256": hashlib.sha256(safe_report_bytes).hexdigest(),
             "vessel_features_v2_sha256": hashlib.sha256(v2_path.read_bytes()).hexdigest(),
             "unknown_label_buckets": [{"label_sha256": h, "rows": n} for h, n in sorted(unknown_counts.items())],
             "quarantine": safe_report["quarantine"],
             "month_mapping": safe_report["month_mapping"],
             "month_selected_date_mismatches": date_mismatches,
             "removed_feature_rows": skipped_rows,
             "source_csv_modified": False,
             "source_full_scan_repeated": False,
             "sqlite_v1_modified": False,
             "known_public_class_labels": sorted(CLASS_LABELS),
             "notes": ["Unknown raw label text is not copied into repaired reports.",
                       "Only the structurally invalid selected row is quarantined.",
                       "The v1 SQLite cache is preserved as read-only evidence."]}
    audit_path = out / "cache_repair_audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw_tokens = [x.encode("utf-8") for x in unknown_codes if x]
    if any(token in report_path.read_bytes() or token in v2_path.read_bytes() or token in audit_path.read_bytes()
           or token in feature_path.read_bytes() for token in raw_tokens):
        raise RuntimeError("unknown label text remains in repaired artifacts")
    return {"train_gate": train_gate, "test_gate": safe_report["evaluation_gates"]["test_six_month_full_parse"],
            "feature_cache": safe_report["feature_cache"], "vessel_features_v2_sha256": audit["vessel_features_v2_sha256"],
            "repair_audit": str(audit_path)}


def write_cache_quality_supplement(out: Path) -> dict:
    """Write a supplemental aggregate without changing hash-frozen v2 artifacts."""
    out = out.resolve()
    report_path, feature_path, audit_path = (out / "full_scan.json", out / "vessel_features_v2.json", out / "cache_repair_audit.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    features = json.loads(feature_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    train = report.get("files", [])[:6]
    missing_labels = sum(row.get("aggregate", {}).get("empty_known", {}).get("fishing_code", 0) for row in train)
    support = features.get("class_support", {})
    supplement = {"schema_version": "evaluation_cycle_cache_quality_supplement_v1",
                  "base_artifact_hashes": {"full_scan_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                                           "vessel_features_v2_sha256": hashlib.sha256(feature_path.read_bytes()).hexdigest(),
                                           "cache_repair_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest()},
                  "train_structural_summary": {"file_count": len(train),
                                               "row_column_mismatches": sum(row.get("aggregate", {}).get("row_column_mismatch", 0) for row in train),
                                               "invalid_dates": sum(row.get("aggregate", {}).get("invalid_dates", 0) for row in train),
                                               "invalid_time_bands": sum(row.get("aggregate", {}).get("invalid_times", 0) for row in train),
                                               "missing_label_rows": missing_labels,
                                               "missing_label_record_ordinal": None,
                                               "missing_label_feature_sample_included": False,
                                               "missing_label_model_input_included": False,
                                               "missing_label_separate_from_unknown_nonclass_row": True},
                  "unknown_nonclass_label_buckets": report.get("label_vocabulary", {}).get("unknown_buckets", []),
                  "quarantined_known_invalid_row_count": len(report.get("quarantine", [])),
                  "feature_cache_class_support": support,
                  "source_csv_modified": False, "full_source_reread": False,
                  "base_hash_frozen_artifacts_modified": False,
                  "limitations": ["The missing-label row has no cached record ordinal; its location is deliberately unassigned.",
                                  "This supplement does not add rows to the model cache or change its labels."]}
    path = out / "cache_quality_supplement.json"
    path.write_text(json.dumps(supplement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "missing_label_rows": missing_labels, "source_full_scan_repeated": False}


def _summarize_file(path: Path, file_ordinal: int, con: sqlite3.Connection,
                    sample_bytes: int | None, progress_every: int, geometry_modulus: int,
                    samples_per_vessel: int = 4, max_candidate_bytes: int = 256 * 1024 * 1024) -> dict:
    st_before = path.stat()
    started = time.perf_counter()
    partial = sample_bytes is not None
    counts = {"rows": 0, "invalid_dates": 0, "valid_dates": 0, "invalid_times": 0,
              "blank_header_columns": 0, "blank_header_nonblank_cells": 0,
              "row_column_mismatch": 0, "empty_known": {}, "label_counts": {}, "label_hashes": {},
              "unknown_label_counts": {}, "quarantine_reason_counts": {}, "quarantined_rows": 0,
              "geometry_values": 0, "geometry_sampled_values": 0,
              "reservoir_candidates_seen": 0, "retained_feature_rows": 0,
              "candidate_bytes_peak": 0,
              "expected_sample_boundary_truncation": False,
              "geometry": {k: 0 for k in ("checked", "structured_nonempty", "empty", "unsupported", "invalid", "parts", "points", "lonlat_out_of_range")},
              "coordinate_bounds_unconfirmed": None, "date_min": None, "date_max": None,
              "rows_with_label": 0, "rows_with_vessel": 0, "blank_labels": 0}
    hash_raw = None
    vessel_state = {}
    candidate_heaps = {}
    candidate_bytes = 0
    bounds = [math.inf, math.inf, -math.inf, -math.inf]
    try:
        binary = path.open("rb")
        if partial:
            data = binary.read(sample_bytes)
            binary.close()
            try:
                decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
                decoded = decoder.decode(data, final=False)
            except UnicodeDecodeError:
                return {"status": "encoding_error", "rows": 0, "partial": True,
                        "elapsed_seconds": time.perf_counter() - started, "sha256": None}
            text = io.StringIO(decoded, newline="")
        else:
            hash_raw = DigestRaw(binary)
            text = io.TextIOWrapper(io.BufferedReader(hash_raw), encoding="utf-8-sig", errors="strict", newline="")
        old_limit = csv.field_size_limit()
        csv.field_size_limit(max(old_limit, 128 * 1024 * 1024))
        reader = csv.reader(text, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            header = []
        except csv.Error:
            return {"status": "csv_header_error", "rows": 0, "partial": partial,
                    "elapsed_seconds": time.perf_counter() - started, "sha256": None}
        indices = {name: [i for i, value in enumerate(header) if value == name] for name in KNOWN}
        unique = {k: v[0] for k, v in indices.items() if len(v) == 1}
        is_labeled_train = "fishing_code" in unique
        blank_positions = [i for i, value in enumerate(header) if not value.strip()]
        counts["blank_header_columns"] = len(blank_positions)
        counts["empty_known"] = {k: 0 for k in unique}
        try:
            for ordinal, row in enumerate(reader, 1):
                counts["rows"] += 1
                row_matches_header = len(row) == len(header)
                if not row_matches_header:
                    counts["row_column_mismatch"] += 1
                for i in blank_positions:
                    if i < len(row) and row[i].strip():
                        counts["blank_header_nonblank_cells"] += 1
                vals = {name: row[idx] for name, idx in unique.items() if idx < len(row)}
                for name in counts["empty_known"]:
                    if not vals.get(name, "").strip():
                        counts["empty_known"][name] += 1
                date_value = vals.get("part_dt", "")
                normalized_date = None
                date_valid = False
                if date_value:
                    try:
                        if len(date_value) != 8 or not date_value.isascii() or not date_value.isdigit():
                            raise ValueError
                        parsed = dt.datetime.strptime(date_value, "%Y%m%d").date()
                        normalized_date = parsed.isoformat()
                        date_valid = True
                        counts["valid_dates"] += 1
                        counts["date_min"] = min(counts["date_min"], normalized_date) if counts["date_min"] else normalized_date
                        counts["date_max"] = max(counts["date_max"], normalized_date) if counts["date_max"] else normalized_date
                    except ValueError:
                        counts["invalid_dates"] += 1
                time_value = vals.get("rfid_time", "")
                time_valid = False
                if time_value and time_value.isascii() and time_value.isdigit():
                    stripped = time_value.lstrip("0") or "0"
                    if len(stripped) <= 2 and int(stripped) <= 23:
                        time_valid = True
                    else:
                        counts["invalid_times"] += 1
                else:
                    counts["invalid_times"] += 1
                vessel = vals.get("rfid_id", "")
                vessel_hash = salted_hash(vessel) if vessel else None
                if vessel_hash:
                    counts["rows_with_vessel"] += 1
                label = vals.get("fishing_code", "")
                label_hash = salted_hash(label) if label else None
                if not label_hash:
                    counts["blank_labels"] += 1
                class_label = label in CLASS_LABELS
                if label_hash and not class_label:
                    counts["unknown_label_counts"][label_hash] = counts["unknown_label_counts"].get(label_hash, 0) + 1
                reasons = []
                if not row_matches_header:
                    reasons.append("row_column_mismatch")
                if not date_valid:
                    reasons.append("invalid_or_missing_part_dt")
                if not time_valid:
                    reasons.append("invalid_or_missing_rfid_time")
                if not vessel_hash:
                    reasons.append("missing_rfid_id")
                if is_labeled_train and not label_hash:
                    reasons.append("empty_fishing_code")
                elif is_labeled_train and not class_label:
                    reasons.append("nonclass_label_hash_only")
                structurally_valid = not reasons
                if reasons:
                    counts["quarantined_rows"] += 1
                    for reason in reasons:
                        counts["quarantine_reason_counts"][reason] = counts["quarantine_reason_counts"].get(reason, 0) + 1
                    con.execute("INSERT OR REPLACE INTO quarantine_rows VALUES (?,?,?,?,?)",
                                (file_ordinal, ordinal, vessel_hash, label_hash, json.dumps(reasons, separators=(",", ":"))))
                time_band = None
                if time_value and time_value.isascii() and time_value.isdigit():
                    try:
                        candidate_hour = int(time_value)
                        if 0 <= candidate_hour <= 23:
                            time_band = candidate_hour
                    except ValueError:
                        pass
                key_hash = salted_hash((normalized_date or "") + "\0" + (vessel_hash or "") + "\0" + str(time_band)) if normalized_date and vessel_hash and time_band is not None else None
                if key_hash and row_matches_header and date_valid and time_valid:
                    con.execute("INSERT INTO key_seen(key_hash,occurrences) VALUES (?,1) ON CONFLICT(key_hash) DO UPDATE SET occurrences=occurrences+1", (key_hash,))
                if vessel_hash and row_matches_header and date_valid and time_valid and (not is_labeled_train or (label_hash and class_label)):
                    included_label_hash = label_hash if (not is_labeled_train or class_label) else None
                    included_label = label if (not is_labeled_train or class_label) else None
                    vessel_key = (vessel_hash, included_label_hash)
                    state = vessel_state.setdefault(vessel_key, {"count": 0, "min_date": None, "max_date": None, "label": included_label})
                    state["count"] += 1
                    if normalized_date:
                        state["min_date"] = min(state["min_date"], normalized_date) if state["min_date"] else normalized_date
                        state["max_date"] = max(state["max_date"], normalized_date) if state["max_date"] else normalized_date
                geom = vals.get("geom", "")
                if geom.strip():
                    counts["geometry_values"] += 1
                sample_hash = None
                candidate_score = None
                heap = None
                selected_candidate = False
                if not partial and is_labeled_train and class_label and label_hash and vessel_hash and structurally_valid and samples_per_vessel:
                    counts["reservoir_candidates_seen"] += 1
                    sample_hash = hashlib.sha256(f"{vessel_hash}\0{file_ordinal}\0{ordinal}".encode("ascii")).hexdigest()
                    candidate_score = int(sample_hash, 16)
                    heap = candidate_heaps.setdefault(vessel_hash, [])
                    selected_candidate = len(heap) < samples_per_vessel or candidate_score < -heap[0][0]
                gs = None
                geom_state = "empty" if not geom.strip() else "unparsed"
                should_parse = partial and bool(geom.strip())
                if should_parse:
                    gs = geometry_summary(geom) if geom.strip() else {"state": "empty", "issue": "geom_empty", "parts": 0, "points": 0}
                    geom_state = gs["state"]
                    counts["geometry_sampled_values"] += int(bool(geom.strip()))
                    counts["geometry"]["checked"] += int(bool(geom.strip()))
                    if geom.strip():
                        counts["geometry"][gs["state"]] += 1
                    part_count, point_count = gs.get("parts", 0), gs.get("points", 0)
                    counts["geometry"]["parts"] += part_count
                    counts["geometry"]["points"] += point_count
                    if gs.get("lonlat_out_of_range"):
                        counts["geometry"]["lonlat_out_of_range"] += 1
                    if "bounds" in gs:
                        x0, y0, x1, y1 = gs["bounds"]
                        bounds = [min(bounds[0], x0), min(bounds[1], y0), max(bounds[2], x1), max(bounds[3], y1)]
                if label_hash and vessel_hash and is_labeled_train and class_label and structurally_valid:
                    con.execute("INSERT OR IGNORE INTO vessel_label_pairs VALUES (?,?)", (vessel_hash, label_hash))
                    counts["label_counts"][label] = counts["label_counts"].get(label, 0) + 1
                    counts["label_hashes"][label_hash] = label
                    counts["rows_with_label"] += 1
                    if selected_candidate:
                        candidate = {"score": candidate_score, "sample_sha256": sample_hash,
                                     "record_ordinal": ordinal, "vessel_hash": vessel_hash,
                                     "label_sha256": label_hash, "label_code": label,
                                     "part_dt": normalized_date, "month": _month_from_path(path), "time_band": time_band,
                                     "raw_geometry": geom}
                        candidate_bytes_size = len(geom.encode("utf-8"))
                        replaced = heap[0][1] if len(heap) >= samples_per_vessel else None
                        replaced_size = len(replaced["raw_geometry"].encode("utf-8")) if replaced else 0
                        if candidate_bytes - replaced_size + candidate_bytes_size > max_candidate_bytes:
                            raise RuntimeError("bounded reservoir geometry memory budget exceeded")
                        if len(heap) < samples_per_vessel:
                            import heapq
                            heapq.heappush(heap, (-candidate["score"], candidate))
                            candidate_bytes += candidate_bytes_size
                        elif candidate["score"] < -heap[0][0]:
                            import heapq
                            heapq.heapreplace(heap, (-candidate["score"], candidate))
                            candidate_bytes += candidate_bytes_size - replaced_size
                        counts["candidate_bytes_peak"] = max(counts["candidate_bytes_peak"], candidate_bytes)
                if counts["rows"] % 10000 == 0:
                    con.commit()
                if progress_every and counts["rows"] % progress_every == 0:
                    print(json.dumps({"event": "progress", "file_ordinal": file_ordinal,
                                      "rows_scanned": counts["rows"], "source_bytes_hashed": hash_raw.bytes_hashed if hash_raw else min(sample_bytes or 0, path.stat().st_size),
                                      "elapsed_seconds": round(time.perf_counter()-started, 2)}, separators=(",", ":")), flush=True)
        except (csv.Error, UnicodeDecodeError):
            if partial:
                counts["expected_sample_boundary_truncation"] = True
            else:
                counts["row_parse_error"] = True
        finally:
            con.commit()
            csv.field_size_limit(old_limit)
        if bounds[0] != math.inf:
            counts["coordinate_bounds_unconfirmed"] = [float(f"{v:.12g}") for v in bounds]
        for (vessel_hash, label_hash), state in vessel_state.items():
            con.execute("INSERT INTO vessel_summary VALUES (?,?,?,?,?,?,?) ON CONFLICT(file_ordinal,vessel_hash,label_sha256) DO UPDATE SET record_count=record_count+excluded.record_count,min_date=MIN(min_date,excluded.min_date),max_date=MAX(max_date,excluded.max_date)",
                        (file_ordinal, vessel_hash, label_hash, state["label"], state["count"], state["min_date"], state["max_date"]))
        if not partial:
            for heap in candidate_heaps.values():
                for _, candidate in heap:
                    raw_geometry = candidate.pop("raw_geometry")
                    gs = (geometry_summary(raw_geometry, include_parts=True) if raw_geometry.strip()
                          else {"state": "empty", "issue": "geom_empty", "parts": 0, "points": 0})
                    geom_state = gs["state"]
                    counts["retained_feature_rows"] += 1
                    counts["geometry_sampled_values"] += int(bool(raw_geometry.strip()))
                    counts["geometry"]["checked"] += int(bool(raw_geometry.strip()))
                    if raw_geometry.strip():
                        counts["geometry"][geom_state] += 1
                    counts["geometry"]["parts"] += gs.get("parts", 0)
                    counts["geometry"]["points"] += gs.get("points", 0)
                    if gs.get("lonlat_out_of_range"):
                        counts["geometry"]["lonlat_out_of_range"] += 1
                    if "bounds" in gs:
                        x0, y0, x1, y1 = gs["bounds"]
                        bounds = [min(bounds[0], x0), min(bounds[1], y0), max(bounds[2], x1), max(bounds[3], y1)]
                    feature = {"valid": False, "reason": gs.get("issue", "empty"), "values": [None] * 9}
                    degree = {"valid": False, "reason": feature["reason"], "values": [None] * 9}
                    if geom_state == "structured_nonempty":
                        from fishing_demo.real_geometry_20261028 import geometry_features
                        feature = geometry_features(gs["parsed_parts"], projection="local_tangent")
                        degree = geometry_features(gs["parsed_parts"], projection="degree_control")
                    candidate["geometry_state"] = geom_state
                    candidate["feature"] = feature
                    candidate["degree_control"] = degree
                    # Drop the only retained source geometry reference immediately after extraction.
                    del raw_geometry
                    feature = candidate["feature"]
                    con.execute("""INSERT OR REPLACE INTO feature_samples
                        (file_ordinal,record_ordinal,vessel_hash,sample_sha256,label_sha256,label_code,
                         part_dt,month,time_band,geometry_state,feature_valid,feature_reason,
                         feature_values_json,degree_control_values_json)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (file_ordinal, candidate["record_ordinal"], candidate["vessel_hash"], candidate["sample_sha256"],
                                 candidate["label_sha256"], candidate["label_code"], candidate["part_dt"], candidate["month"], candidate["time_band"],
                                 candidate["geometry_state"], int(feature["valid"]), feature["reason"],
                                 json.dumps(feature["values"], separators=(",", ":")),
                                 json.dumps(candidate["degree_control"]["values"], separators=(",", ":"))))
        con.commit()
        source_eof_reached = bool(hash_raw and hash_raw.eof_reached)
        sha = hash_raw.digest.hexdigest() if source_eof_reached else None
        status = (("partial_sample_boundary_truncated" if counts.get("expected_sample_boundary_truncation") else "partial_sample")
                  if partial else ("scan_completed_with_parse_error" if counts.get("row_parse_error") else "scan_completed"))
        return {"status": status, "rows": counts["rows"], "partial": partial, "sha256": sha,
                "source_eof_reached": source_eof_reached,
                "source_bytes_hashed": hash_raw.bytes_hashed if hash_raw else min(sample_bytes or 0, st_before.st_size),
                "elapsed_seconds": time.perf_counter() - started, "aggregate": counts}
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        # Exceptions are reduced to fixed types; exception text may contain paths or field content.
        return {"status": "io_or_decode_error", "error_type": type(exc).__name__, "rows": counts["rows"],
                "partial": partial, "elapsed_seconds": time.perf_counter() - started, "sha256": None,
                "aggregate": counts}


def scan(path: Path, out: Path, sample_bytes: int | None, progress_every: int = 100000,
         geometry_sample_modulus: int | None = None, limit_files: int | None = None,
         samples_per_vessel: int = 4, max_candidate_bytes: int = 256 * 1024 * 1024) -> dict:
    path, out = path.resolve(), out.resolve()
    if not path.is_dir():
        raise ValueError("source must be a directory")
    if path == out or path in out.parents or out in path.parents:
        raise ValueError("source and output directories must be disjoint")
    out.mkdir(parents=True, exist_ok=True)
    dbpath = out / ("inspection_cache_sample.sqlite3" if sample_bytes is not None else "inspection_cache.sqlite3")
    con = _connect(dbpath)
    old_root = con.execute("SELECT value FROM scan_meta WHERE key='source_root'").fetchone()
    if old_root and old_root[0] != str(path):
        con.executescript("DELETE FROM files; DELETE FROM records; DELETE FROM vessel_label_pairs; DELETE FROM vessel_summary; DELETE FROM key_seen; DELETE FROM feature_samples; DELETE FROM label_index;")
    con.execute("INSERT OR REPLACE INTO scan_meta VALUES (?,?)", ("source_root", str(path)))
    files = _safe_csv_files(path)
    if limit_files is not None:
        files = files[:limit_files]
    geometry_modulus = geometry_sample_modulus or (1 if sample_bytes is not None else 64)
    if geometry_modulus < 1:
        raise ValueError("geometry sample modulus must be positive")
    if samples_per_vessel < 1 or max_candidate_bytes < 1:
        raise ValueError("sample count and candidate byte limit must be positive")
    invalidate = sample_bytes is not None
    if not invalidate:
        for file_ordinal, file in enumerate(files):
            st_check = file.stat()
            rel_check = file.relative_to(path).as_posix()
            cached_check = con.execute("SELECT relative_path,size_bytes,mtime_ns,sha256,status,partial FROM files WHERE file_ordinal=?", (file_ordinal,)).fetchone()
            if (not cached_check or cached_check[0] != rel_check or cached_check[1] != st_check.st_size
                    or cached_check[2] != st_check.st_mtime_ns or not cached_check[3]
                    or cached_check[4] != "scan_completed" or cached_check[5]):
                invalidate = True
                break
        if len(files) != con.execute("SELECT COUNT(*) FROM files WHERE status='scan_completed' AND partial=0").fetchone()[0]:
            invalidate = True
    if invalidate:
        con.executescript("DELETE FROM files; DELETE FROM records; DELETE FROM vessel_label_pairs; DELETE FROM vessel_summary; DELETE FROM key_seen; DELETE FROM feature_samples; DELETE FROM label_index;")
    reports = []
    full_bytes = 0
    bytes_read = 0
    available_bytes = sum(file.stat().st_size for file in files)
    for file_ordinal, file in enumerate(files):
        rel = file.relative_to(path).as_posix()
        st = file.stat()
        cached = con.execute("SELECT size_bytes,mtime_ns,sha256,status,rows_scanned,partial,elapsed_seconds,aggregate_json FROM files WHERE file_ordinal=? AND relative_path=?", (file_ordinal, rel)).fetchone()
        if sample_bytes is None and cached and cached[0] == st.st_size and cached[1] == st.st_mtime_ns and cached[5] == 0 and cached[3] == "scan_completed":
            reports.append({"file_ordinal": file_ordinal, "relative_path": rel, "size_bytes": cached[0], "mtime_ns": cached[1], "sha256": cached[2], "status": "cached", "rows": cached[4], "aggregate": json.loads(cached[7])})
            bytes_read += 0
            continue
        result = _summarize_file(file, file_ordinal, con, sample_bytes, progress_every, geometry_modulus,
                                 samples_per_vessel=samples_per_vessel, max_candidate_bytes=max_candidate_bytes)
        st_after = file.stat()
        changed = (st.st_size, st.st_mtime_ns) != (st_after.st_size, st_after.st_mtime_ns)
        if changed:
            result["status"] = "source_changed_during_scan"
        result["source_changed_during_scan"] = changed
        result["size_bytes"], result["mtime_ns"] = st.st_size, st.st_mtime_ns
        if result.get("sha256"):
            full_bytes += st.st_size
        bytes_read += st.st_size if sample_bytes is None else min(st.st_size, sample_bytes)
        reports.append({"file_ordinal": file_ordinal, "relative_path": rel, **result})
        con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (file_ordinal, rel, st.st_size, st.st_mtime_ns, result.get("sha256"), result["status"], result["rows"], int(result["partial"]), result["elapsed_seconds"], json.dumps(result.get("aggregate", {}), sort_keys=True)))
        con.commit()
    code_counts = {}
    unknown_counts = {}
    for report in reports:
        for code, count in report.get("aggregate", {}).get("label_counts", {}).items():
            code_counts[code] = code_counts.get(code, 0) + count
        for digest, count in report.get("aggregate", {}).get("unknown_label_counts", {}).items():
            unknown_counts[digest] = unknown_counts.get(digest, 0) + count
    con.execute("DELETE FROM label_index")
    for index, (code, digest) in enumerate(sorted(((code, salted_hash(code)) for code in code_counts), key=lambda item: item[1])):
        con.execute("INSERT INTO label_index(label_index,label_sha256,label_code) VALUES (?,?,?)", (index, digest, code))
    con.commit()
    distinct_vessels = con.execute("SELECT COUNT(DISTINCT vessel_hash) FROM vessel_summary").fetchone()[0]
    dup_keys = con.execute("SELECT COUNT(*) FROM key_seen WHERE occurrences>1").fetchone()[0]
    collision_rows = con.execute("SELECT COALESCE(SUM(occurrences-1),0) FROM key_seen WHERE occurrences>1").fetchone()[0]
    inconsistent_vessels = con.execute("SELECT COUNT(*) FROM (SELECT vessel_hash FROM vessel_label_pairs GROUP BY vessel_hash HAVING COUNT(DISTINCT label_sha256)>1)").fetchone()[0]
    label_distribution = [{"label_index": index, "label_code": code, "label_sha256": salted_hash(code), "rows": count}
                          for index, (code, count) in enumerate(sorted(code_counts.items(), key=lambda item: salted_hash(item[0])))]
    feature_cache = None
    complete_file_set = sample_bytes is None and limit_files is None
    if complete_file_set:
        feature_cache = _write_vessel_features(con, out)
        con.execute("DELETE FROM key_seen WHERE occurrences=1")
        con.commit()
    result = {"schema_version": VERSION, "source_type": "csv_inventory_only", "scan_mode": "sample" if sample_bytes is not None else "full",
              "source_root": str(path), "cache_path": str(dbpath), "salt_id": "20261028_v1", "file_count": len(files),
              "available_source_bytes": available_bytes, "newly_hashed_bytes": full_bytes,
              "bytes_reused_from_cache": max(0, available_bytes - full_bytes),
              "bytes_hashed_this_run": full_bytes, "partial_sample_bytes_per_file": sample_bytes,
              "bytes_read_this_run": bytes_read,
              "geometry_sampling": ({"method": "lowest SHA256(vessel_hash,file_ordinal,record_ordinal)",
                                      "per_vessel_per_labeled_monthly_train_file": samples_per_vessel,
                                      "maximum_retained_geometry_bytes": max_candidate_bytes,
                                      "scope": "selected_rows_only; raw geometry held in bounded memory until each file ends, then parsed and discarded"}
                                     if not sample_bytes else {"method": "all nonempty WKT in bounded byte prefix", "scope": "partial_prefix_only"}),
              "label_distribution": label_distribution,
              "unknown_label_buckets": [{"label_sha256": h, "rows": n} for h, n in sorted(unknown_counts.items())],
              "distinct_vessel_hashes": distinct_vessels, "candidate_duplicate_key_groups": dup_keys,
              "candidate_duplicate_key_extra_rows": collision_rows, "vessels_with_multiple_label_hashes": inconsistent_vessels,
              "feature_cache": feature_cache,
              "files": reports, "limitations": ["full-scan geometry validation/counts/bounds cover only the deterministic feature sample", "coordinate order is X=longitude,Y=latitude; exact datum/EPSG remains unconfirmed", "no model fitting or predictive evaluation performed"]}
    result_path = out / ("sample_scan.json" if sample_bytes is not None else "full_scan.json")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    con.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repair-existing-cache", action="store_true",
                        help="repair completed v1 report/features from the local cache without reading source CSVs")
    parser.add_argument("--write-quality-supplement", action="store_true",
                        help="write a separate aggregate note without changing hash-frozen scan/cache artifacts")
    parser.add_argument("--sample-bytes-per-file", type=int, default=None,
                        help="scan only a bounded prefix of each file; omit only after full-scan approval")
    parser.add_argument("--progress-every", type=int, default=100000)
    parser.add_argument("--limit-files", type=int, default=None, help="bound files for runtime calibration")
    parser.add_argument("--samples-per-vessel", type=int, default=4,
                        help="maximum hash-selected rows per vessel in each labeled monthly Train CSV")
    parser.add_argument("--max-candidate-bytes", type=int, default=256 * 1024 * 1024,
                        help="memory ceiling for bounded, temporary per-file reservoir geometry strings")
    args = parser.parse_args()
    if args.sample_bytes_per_file is not None and args.sample_bytes_per_file < 1:
        parser.error("sample-bytes-per-file must be positive")
    if args.progress_every < 0:
        parser.error("progress-every must be nonnegative")
    if args.limit_files is not None and args.limit_files < 1:
        parser.error("limit-files must be positive")
    if args.samples_per_vessel < 1 or args.max_candidate_bytes < 1:
        parser.error("samples-per-vessel and max-candidate-bytes must be positive")
    if args.repair_existing_cache:
        try:
            print(json.dumps(repair_cached_outputs(args.out), ensure_ascii=True, indent=2))
        except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
            print(json.dumps({"status": "repair_error", "error_type": type(exc).__name__}, ensure_ascii=True), file=sys.stderr)
            raise SystemExit(2)
        return
    if args.write_quality_supplement:
        try:
            print(json.dumps(write_cache_quality_supplement(args.out), ensure_ascii=True, indent=2))
        except (OSError, ValueError, sqlite3.Error) as exc:
            print(json.dumps({"status": "supplement_error", "error_type": type(exc).__name__}, ensure_ascii=True), file=sys.stderr)
            raise SystemExit(2)
        return
    if args.source is None:
        parser.error("source directory is required unless --repair-existing-cache is used")
    try:
        result = scan(args.source, args.out, args.sample_bytes_per_file, args.progress_every,
                      limit_files=args.limit_files, samples_per_vessel=args.samples_per_vessel,
                      max_candidate_bytes=args.max_candidate_bytes)
        safe = {k: v for k, v in result.items() if k != "files"}
        safe["files"] = [{k: item.get(k) for k in ("file_ordinal", "relative_path", "status", "rows", "partial", "elapsed_seconds", "size_bytes", "source_changed_during_scan")} for item in result["files"]]
        print(json.dumps(safe, ensure_ascii=True, indent=2))
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
