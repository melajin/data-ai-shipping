"""Bounded, label-blind extraction of selected hourly geometry rows.

The production CLI requires explicit canonical, cache, raw, registry and fresh
output paths.  This module intentionally contains no accident-label logic.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

ROUND_DIR = Path(__file__).resolve().parent
EXPECTED_MONTH_ROWS = (497942, 479290, 657292, 717294, 761846, 773405)
EXPECTED_RAW_SHA256 = {
    1: "800afffb3f107d02ee132645c76f7efe902d3189aab83d60b031d4dc195f1176",
    5: "b4eafc1494e8dc4aa4f72c6bf6d40efa63f29b2599ceafb2ca2eeb14ad960709",
    6: "4976ed8540aa0a57c7b01a97369a36a9122923fa11e0e1654e5866502a7b3a0a",
}
R7_RUN_ROUND7_SHA256 = "19ad0ff9d630bccdf3195971a4919817284da331e24ad41c67c485613a2f6282"
UPSTREAM_PARSER_SHA256 = "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c"
CANONICAL_COLUMNS = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
CACHE_COLUMNS = ["row_index", "part_dt", "rfid_time", "n_coords", "len_m", "bbox_m", "cen_lon", "cen_lat"]
RAW_HEADER_PREFIX = ["part_dt", "rfid_id", "rfid_time", "geom", "fishing_code"]
EARTH_R = 6_371_000.0
EXTRA_MIB = 768
RESERVE_MIB = 640


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Round7 copied helper (R7 run_round7.py; source hash in notes)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def parse_multilinestring(wkt: str) -> list[list[tuple[float, float]]]:
    """Round7's parser copied verbatim in behavior; source hash is documented."""
    s = wkt.strip()
    prefix = "MULTILINESTRING ("
    if not (s.startswith(prefix) and s.endswith(")")):
        raise ValueError("wrapper")
    inner = s[len(prefix):-1]
    if not inner:
        raise ValueError("empty")
    raw_parts = inner.split("), (")
    raw_parts[0] = raw_parts[0].lstrip("(")
    raw_parts[-1] = raw_parts[-1].rstrip(")")
    parts: list[list[tuple[float, float]]] = []
    for chunk in raw_parts:
        chunk = chunk.strip()
        if not chunk:
            continue
        pts = []
        for token in chunk.split(", "):
            lon_s, lat_s = token.split(" ")
            pts.append((float(lon_s), float(lat_s)))
        if pts:
            parts.append(pts)
    if not parts:
        raise ValueError("no_parts")
    return parts


def source_clock_hour(part_dt: str, rfid_time: int) -> int:
    """Reproduce upstream _ts_hours: naive YYYYMMDD hour index; timezone unknown."""
    if not isinstance(part_dt, str) or len(part_dt) != 8 or not part_dt.isdigit():
        raise ValueError("part_dt must be exactly 8 digits YYYYMMDD")
    if isinstance(rfid_time, bool) or not isinstance(rfid_time, int) or not 0 <= rfid_time <= 23:
        raise ValueError("rfid_time must be an integer in [0, 23]")
    d = dt.datetime.strptime(part_dt, "%Y%m%d")
    return int((d - dt.datetime(1970, 1, 1)).total_seconds() // 3600) + rfid_time


def ordinal_month_index(source_ordinal: int, offsets: list[int]) -> tuple[int, int]:
    """Return 1-based month and 0-based post-header CSV row index."""
    for i, offset in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else None
        if source_ordinal >= offset and (end is None or source_ordinal < end):
            return i + 1, source_ordinal - offset
    raise ValueError(f"source_ordinal outside all monthly ranges: {source_ordinal}")


def part_features(points: list[tuple[float, float]], part_index: int) -> dict[str, Any]:
    n = len(points)
    finite = all(math.isfinite(lon) and math.isfinite(lat) for lon, lat in points)
    unique = len(set(points)) if finite else len({(lon, lat) for lon, lat in points if math.isfinite(lon) and math.isfinite(lat)})
    if not finite:
        return {"part_index": part_index, "n_points": n, "n_unique_coords": unique,
                "path_length_m": None, "endpoint_distance_m": None, "shape_dl": None,
                "finite_coordinates": False, "eligible": False, "reason": "non_finite_coordinate"}
    path = sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))
    endpoint = haversine_m(points[0][0], points[0][1], points[-1][0], points[-1][1]) if n else 0.0
    ratio = endpoint / path if path > 0 else None
    if n < 2:
        reason = "fewer_than_two_points"
    elif unique < 3:
        reason = "fewer_than_three_unique_coordinates"
    elif path <= 0:
        reason = "non_positive_path_length"
    elif ratio is None or not math.isfinite(ratio):
        reason = "non_finite_shape_dl"
    elif ratio < -1e-9 or ratio > 1.0 + 1e-9:
        reason = "shape_dl_out_of_range"
    else:
        reason = "eligible"
    eligible = reason == "eligible"
    if eligible:
        ratio = min(1.0, max(0.0, ratio))
    return {"part_index": part_index, "n_points": n, "n_unique_coords": unique,
            "path_length_m": path, "endpoint_distance_m": endpoint, "shape_dl": ratio,
            "finite_coordinates": True, "eligible": eligible, "reason": reason}


def summarize_parts(parts: list[list[tuple[float, float]]]) -> dict[str, Any]:
    features = [part_features(p, i) for i, p in enumerate(parts)]
    eligible = [f for f in features if f["eligible"]]
    chosen = min(eligible, key=lambda f: (-f["path_length_m"], f["part_index"])) if eligible else None
    if not parts:
        status, reason = "missing_geometry", "no_parts"
    elif chosen is not None:
        status, reason = "informative", "longest_eligible_part"
    else:
        status = "uninformative"
        reason = ";".join(sorted({f["reason"] for f in features}))
    return {"n_parts": len(parts), "n_informative_parts": len(eligible), "chosen": chosen,
            "geometry_status": status, "geometry_reason": reason, "part_features": features}


def check_key(raw_rfid: str, part_dt: str, rfid_time: int, canonical: dict[str, Any]) -> None:
    """Raise on any target raw-to-canonical key discrepancy."""
    if str(raw_rfid) != str(canonical["rfid_id"]):
        raise ValueError(f"rfid mismatch: raw={raw_rfid!r} canonical={canonical['rfid_id']!r}")
    if source_clock_hour(part_dt, rfid_time) != int(canonical["ts"]):
        raise ValueError(f"source-clock ts mismatch: raw={part_dt}/{rfid_time} canonical={canonical['ts']}")


def _jsonable(v: Any) -> Any:
    if hasattr(v, "item"):
        return v.item()
    if isinstance(v, Path):
        return str(v)
    raise TypeError(type(v).__name__)


def _hash_file(path: Path, chunk_size: int = 1 << 20) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size


def _ram_preflight() -> dict[str, Any]:
    # Keep heavy parquet/dataframe imports after this check.
    try:
        import psutil  # lightweight resource probe
        vm = psutil.virtual_memory()
        avail = vm.available / (1024 * 1024)
        current_pid = os.getpid()
        jobs = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if p.info["pid"] != current_pid and "python" in (p.info["name"] or "").lower():
                    jobs.append({"pid": p.info["pid"], "name": p.info["name"],
                                 "cmdline": " ".join(p.info["cmdline"] or [])[:300]})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {"checked_at": dt.datetime.now().astimezone().isoformat(),
                "available_mib": round(avail, 2), "expected_extra_mib": EXTRA_MIB,
                "reserve_mib": RESERVE_MIB, "active_python_jobs": jobs,
                "concurrent_job_reserve_mib": EXTRA_MIB * len(jobs),
                "required_available_mib": EXTRA_MIB + RESERVE_MIB + EXTRA_MIB * len(jobs),
                "allowed": avail >= EXTRA_MIB + RESERVE_MIB + EXTRA_MIB * len(jobs),
                "estimate_basis": "bounded projected parquet batches, <=99,677 scalar target keys, one month of parsed records, and bounded parquet output batches; R7 observed process peak 334MiB; conservatively reserve 768MiB per active external Python job"}
    except ImportError:
        raise RuntimeError("psutil is required for mandatory RAM preflight")


def _sha256_self() -> str:
    return _hash_file(Path(__file__))[0]


def _geometry_schema(pa: Any) -> Any:
    """Stable nullable output schema, independent of first-row nullability."""
    return pa.schema([
        pa.field("rfid_id", pa.string()), pa.field("ts", pa.int64()), pa.field("source_ordinal", pa.int64()),
        pa.field("len_m", pa.float64()), pa.field("bbox_m", pa.float64()), pa.field("cen_lon", pa.float64()),
        pa.field("cen_lat", pa.float64()), pa.field("score", pa.float64()), pa.field("canonical_order", pa.int64()),
        pa.field("source_month", pa.int32()), pa.field("row_index", pa.int64()), pa.field("primary_gear", pa.string()),
        pa.field("n_parts", pa.int64()), pa.field("n_informative_parts", pa.int64()),
        pa.field("chosen_part_index", pa.int64()), pa.field("chosen_n_points", pa.int64()),
        pa.field("chosen_n_unique", pa.int64()), pa.field("chosen_path_m", pa.float64()),
        pa.field("chosen_endpoint_m", pa.float64()), pa.field("shape_dl", pa.float64()),
        pa.field("geometry_status", pa.string()), pa.field("geometry_reason", pa.string()),
        pa.field("raw_record_sha256", pa.string()), pa.field("cache_n_coords", pa.int64()),
        pa.field("cache_len_m", pa.float64()), pa.field("cache_bbox_m", pa.float64()),
        pa.field("cache_cen_lon", pa.float64()), pa.field("cache_cen_lat", pa.float64()),
    ])


def write_geometry_rows(rows: Iterable[dict[str, Any]], path: Path, pa: Any, pq: Any, batch_size: int = 4096) -> int:
    """Write each row exactly once in bounded batches with stable nullable types."""
    schema = _geometry_schema(pa)
    writer = pq.ParquetWriter(path, schema, compression="zstd")
    batch: list[dict[str, Any]] = []
    count = 0
    try:
        for row in rows:
            batch.append(row)
            if len(batch) >= batch_size:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                count += len(batch)
                batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            count += len(batch)
    finally:
        writer.close()
    return count


def _validate_output_new(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"--output-dir must be new: {path}")


def run_extract(args: argparse.Namespace) -> int:
    started = time.time()
    output_dir = Path(args.output_dir).resolve()
    _validate_output_new(output_dir)
    preflight = _ram_preflight()
    if not preflight["allowed"]:
        raise MemoryError(f"memory_deferred: available {preflight['available_mib']} MiB < {EXTRA_MIB + RESERVE_MIB} MiB")
    # Heavy modules are intentionally imported only after the current RAM gate.
    import pyarrow as pa
    import pyarrow.parquet as pq
    import psutil

    canonical_path = Path(args.canonical).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    raw_dir = Path(args.raw_dir).resolve()
    registry_path = Path(args.registry).resolve()
    output_dir.mkdir(parents=True)
    errors: list[dict[str, Any]] = []  # bounded receipt samples; full row diagnostics stream to JSONL.
    error_count = 0
    mismatch_count = 0
    mismatch_path = output_dir / "mismatch_registry.jsonl"
    mismatch_file = mismatch_path.open("w", encoding="utf-8", newline="\n")

    def add_error(item: dict[str, Any]) -> None:
        nonlocal error_count
        error_count += 1
        if len(errors) < 100:
            errors.append(item)

    def add_mismatch(item: dict[str, Any]) -> None:
        nonlocal mismatch_count
        mismatch_count += 1
        mismatch_file.write(json.dumps(item, ensure_ascii=False, default=_jsonable) + "\n")
    input_hashes = {str(p): _hash_file(p) for p in (canonical_path, registry_path)}

    # R4 canonical numeric input: retain only scalar columns, preserving row order.
    target_by_ordinal: dict[int, dict[str, Any]] = {}
    by_month: dict[int, dict[int, dict[str, Any]]] = {m: {} for m in range(1, 7)}
    canonical_pf = pq.ParquetFile(canonical_path)
    canonical_count = 0
    seen_keys: set[tuple[str, int]] = set()
    offsets: list[int] = []
    acc = 0
    cache_counts = {}
    cache_files = {}
    for month in range(1, 7):
        cp = cache_dir / f"rows_train_{month}.parquet"
        cmeta = pq.read_metadata(cp)
        cache_counts[month] = cmeta.num_rows
        cache_files[month] = cp
        offsets.append(acc)
        acc += cmeta.num_rows
    if tuple(cache_counts[m] for m in range(1, 7)) != EXPECTED_MONTH_ROWS:
        raise ValueError(f"cache month row counts differ from contract: {cache_counts}")

    for batch in canonical_pf.iter_batches(columns=CANONICAL_COLUMNS, batch_size=8192):
        for row in batch.to_pylist():
            canonical_count += 1
            rid = str(row["rfid_id"])
            ts = row["ts"]
            if ts is None or isinstance(ts, bool) or int(ts) != ts:
                raise ValueError(f"non-integer source-clock hour at canonical row {canonical_count-1}")
            key = (rid, int(ts))
            if key in seen_keys:
                raise ValueError(f"duplicate canonical rfid_id/ts key: {key}")
            seen_keys.add(key)
            ordinal = int(row["source_ordinal"])
            month, row_index = ordinal_month_index(ordinal, offsets)
            row.update({"rfid_id": rid, "ts": int(ts), "source_ordinal": ordinal,
                        "canonical_order": canonical_count - 1, "source_month": month,
                        "row_index": row_index})
            target_by_ordinal[ordinal] = row
            by_month[month][row_index] = row
    if canonical_count != 99677 or len(seen_keys) != 99677 or len({x[0] for x in seen_keys}) != 82:
        raise ValueError(f"canonical roster contract mismatch: rows={canonical_count}, rfids={len({x[0] for x in seen_keys})}")
    if len(target_by_ordinal) != canonical_count:
        raise ValueError("canonical source_ordinal is not unique")

    # Gear registry is small and read using stdlib CSV; no label or event file is opened.
    gear_by_rfid: dict[str, str] = {}
    with registry_path.open("r", encoding="utf-8-sig", newline="") as f:
        rr = csv.DictReader(f)
        if not {"rfid_id", "primary_gear"}.issubset(rr.fieldnames or []):
            raise ValueError("gear registry must contain rfid_id,primary_gear")
        for row in rr:
            rid = str(row["rfid_id"])
            if rid in gear_by_rfid:
                raise ValueError(f"duplicate gear registry RFID: {rid}")
            gear_by_rfid[rid] = row["primary_gear"]

    spool_path = output_dir / ".geometry_spool.sqlite"
    db = sqlite3.connect(spool_path)
    db.execute("CREATE TABLE rows (ord INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
    try:
        for month in range(1, 7):
            cp = cache_files[month]
            targets = by_month[month]
            cache_targets: dict[int, dict[str, Any]] = {}
            c_pf = pq.ParquetFile(cp)
            for batch in c_pf.iter_batches(columns=CACHE_COLUMNS, batch_size=8192):
                for cr in batch.to_pylist():
                    idx = int(cr["row_index"])
                    if idx in targets:
                        if idx in cache_targets:
                            add_error({"month": month, "row_index": idx, "error": "duplicate_cache_row_index"})
                        cache_targets[idx] = cr
            missing_cache = set(targets) - set(cache_targets)
            for idx in sorted(missing_cache):
                add_error({"month": month, "row_index": idx, "source_ordinal": targets[idx]["source_ordinal"], "error": "missing_cache_row"})

            raw_path = raw_dir / f"vpass_{month}월 데이터.csv"
            raw_hash, raw_bytes = None, None
            found: set[int] = set()
            row_count = 0
            try:
                before = raw_path.stat()
                raw_hash, raw_bytes = _hash_file(raw_path)
                expected_hash = EXPECTED_RAW_SHA256.get(month)
                if expected_hash is not None and raw_hash != expected_hash:
                    add_error({"month": month, "error": "expected_raw_hash_mismatch", "expected": expected_hash, "observed": raw_hash})
                csv.field_size_limit(10 * 1024 * 1024)
                with raw_path.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if not header or header[:5] != RAW_HEADER_PREFIX:
                        add_error({"month": month, "error": "raw_header_mismatch", "observed_first5": header[:5] if header else None})
                    for idx, record in enumerate(reader):
                        row_count = idx + 1
                        if idx not in targets:
                            continue
                        rec_errors: list[dict[str, Any]] = []
                        ordinal = int(targets[idx]["source_ordinal"])
                        try:
                            if len(record) < 5:
                                raise ValueError(f"target CSV row has {len(record)} fields; expected >=5")
                            part_dt = record[0]
                            rid = record[1]
                            if not record[2].isdigit():
                                raise ValueError("rfid_time is not an integer token")
                            hour = int(record[2])
                            check_key(rid, part_dt, hour, targets[idx])
                            cache_row = cache_targets.get(idx)
                            if cache_row is None:
                                raise ValueError("missing cache row")
                            if str(cache_row["part_dt"]) != part_dt or int(cache_row["rfid_time"]) != hour:
                                rec_errors.append({"field": "cache_raw_key", "raw": [part_dt, hour], "cache": [str(cache_row["part_dt"]), cache_row["rfid_time"]]})
                            try:
                                parts = parse_multilinestring(record[3])  # Only raw geometry field row[3], as upstream.
                                geom = summarize_parts(parts)
                            except Exception as ex:
                                parts, geom = [], {"n_parts": 0, "n_informative_parts": 0, "chosen": None,
                                    "geometry_status": "parse_error", "geometry_reason": f"{type(ex).__name__}:{ex}", "part_features": []}
                                rec_errors.append({"field": "geometry_parse", "error": str(ex)})
                            cache_values = {"n_coords": int(cache_row["n_coords"]), "len_m": float(cache_row["len_m"]),
                                            "bbox_m": float(cache_row["bbox_m"]), "cen_lon": float(cache_row["cen_lon"]),
                                            "cen_lat": float(cache_row["cen_lat"])}
                            if len(parts) and sum(len(p) for p in parts) != cache_values["n_coords"]:
                                rec_errors.append({"field": "n_coords", "cache": cache_values["n_coords"], "raw": sum(map(len, parts))})
                            # Cache values must independently agree with the canonical ledger.
                            tol = {"len_m": 1e-4, "bbox_m": 1e-4, "cen_lon": 1e-7, "cen_lat": 1e-7}
                            reconstructed = None
                            if parts:
                                coords = [pt for part in parts for pt in part]
                                if all(math.isfinite(x) and math.isfinite(y) for x, y in coords):
                                    length = sum(haversine_m(a[0], a[1], b[0], b[1]) for part in parts for a, b in zip(part, part[1:]))
                                    b_m = haversine_m(min(x for x, _ in coords), min(y for _, y in coords), max(x for x, _ in coords), max(y for _, y in coords))
                                    reconstructed = {"n_coords": len(coords), "len_m": length, "bbox_m": b_m,
                                                     "cen_lon": sum(x for x, _ in coords)/len(coords), "cen_lat": sum(y for _, y in coords)/len(coords)}
                            for field, tolerance in tol.items():
                                if abs(cache_values[field] - float(targets[idx][field])) > tolerance:
                                    rec_errors.append({"field": f"canonical_cache_{field}", "canonical": float(targets[idx][field]), "cache": cache_values[field]})
                                if reconstructed is not None and abs(cache_values[field] - reconstructed[field]) > tolerance:
                                    rec_errors.append({"field": f"raw_cache_{field}", "cache": cache_values[field], "raw": reconstructed[field]})
                            if reconstructed is not None and reconstructed["n_coords"] != cache_values["n_coords"]:
                                rec_errors.append({"field": "raw_cache_n_coords", "cache": cache_values["n_coords"], "raw": reconstructed["n_coords"]})
                            row_out = {k: targets[idx][k] for k in CANONICAL_COLUMNS}
                            chosen = geom["chosen"]
                            row_out.update({"canonical_order": targets[idx]["canonical_order"], "source_month": month, "row_index": idx,
                                "primary_gear": gear_by_rfid.get(rid), "n_parts": geom["n_parts"],
                                "n_informative_parts": geom["n_informative_parts"],
                                "chosen_part_index": chosen["part_index"] if chosen else None,
                                "chosen_n_points": chosen["n_points"] if chosen else None,
                                "chosen_n_unique": chosen["n_unique_coords"] if chosen else None,
                                "chosen_path_m": chosen["path_length_m"] if chosen else None,
                                "chosen_endpoint_m": chosen["endpoint_distance_m"] if chosen else None,
                                "shape_dl": chosen["shape_dl"] if chosen else None,
                                "geometry_status": geom["geometry_status"], "geometry_reason": geom["geometry_reason"],
                                "raw_record_sha256": hashlib.sha256("\x1f".join(record).encode("utf-8")).hexdigest(),
                                "cache_n_coords": cache_values["n_coords"], "cache_len_m": cache_values["len_m"],
                                "cache_bbox_m": cache_values["bbox_m"], "cache_cen_lon": cache_values["cen_lon"], "cache_cen_lat": cache_values["cen_lat"]})
                            if rec_errors:
                                row_out["geometry_status"] = "validation_failed" if geom["geometry_status"] != "parse_error" else "parse_error"
                                row_out["geometry_reason"] = ";".join(e.get("field", e.get("error", "mismatch")) for e in rec_errors)
                                add_mismatch({"month": month, "row_index": idx, "source_ordinal": ordinal, "rfid_id": rid,
                                              "ts": int(targets[idx]["ts"]), "mismatches": rec_errors})
                                for item in rec_errors:
                                    add_error({"month": month, "row_index": idx, "source_ordinal": ordinal, **item})
                            db.execute("INSERT INTO rows VALUES (?, ?)", (int(row_out["canonical_order"]), json.dumps(row_out, default=_jsonable, allow_nan=True)))
                            found.add(idx)
                        except Exception as ex:
                            add_error({"month": month, "row_index": idx, "source_ordinal": ordinal, "error": f"{type(ex).__name__}:{ex}"})
                            add_mismatch({"month": month, "row_index": idx, "source_ordinal": ordinal, "mismatches": [{"error": str(ex)}]})
                            # Preserve one row per canonical key even when raw/key validation fails.
                            row_out = {k: targets[idx][k] for k in CANONICAL_COLUMNS}
                            row_out.update({"canonical_order": targets[idx]["canonical_order"], "source_month": month, "row_index": idx,
                                "primary_gear": gear_by_rfid.get(str(targets[idx]["rfid_id"])), "n_parts": None,
                                "n_informative_parts": 0, "chosen_part_index": None, "chosen_n_points": None,
                                "chosen_n_unique": None, "chosen_path_m": None, "chosen_endpoint_m": None, "shape_dl": None,
                                "geometry_status": "validation_failed", "geometry_reason": str(ex), "raw_record_sha256": None,
                                "cache_n_coords": None, "cache_len_m": None, "cache_bbox_m": None, "cache_cen_lon": None, "cache_cen_lat": None})
                            db.execute("INSERT OR REPLACE INTO rows VALUES (?, ?)", (int(row_out["canonical_order"]), json.dumps(row_out, default=_jsonable, allow_nan=True)))
                            found.add(idx)
                if row_count != cache_counts[month]:
                    add_error({"month": month, "error": "raw_record_count_mismatch", "raw": row_count, "cache": cache_counts[month]})
                after = raw_path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    add_error({"month": month, "error": "raw_file_changed_during_read"})
            except Exception as ex:
                add_error({"month": month, "error": f"raw_stream_failure:{type(ex).__name__}:{ex}"})
            # Every canonical row survives missing raw/cache input as an explicit failure row.
            for idx in sorted(set(targets) - found):
                ordinal = int(targets[idx]["source_ordinal"])
                add_error({"month": month, "row_index": idx, "source_ordinal": ordinal, "error": "missing_target_raw_record"})
                add_mismatch({"month": month, "row_index": idx, "source_ordinal": ordinal,
                              "mismatches": [{"error": "missing_target_raw_record"}]})
                row_out = {k: targets[idx][k] for k in CANONICAL_COLUMNS}
                row_out.update({"canonical_order": targets[idx]["canonical_order"], "source_month": month, "row_index": idx,
                    "primary_gear": gear_by_rfid.get(str(targets[idx]["rfid_id"])), "n_parts": None,
                    "n_informative_parts": 0, "chosen_part_index": None, "chosen_n_points": None,
                    "chosen_n_unique": None, "chosen_path_m": None, "chosen_endpoint_m": None, "shape_dl": None,
                    "geometry_status": "missing_raw_record", "geometry_reason": "missing_target_raw_record", "raw_record_sha256": None,
                    "cache_n_coords": None, "cache_len_m": None, "cache_bbox_m": None, "cache_cen_lon": None, "cache_cen_lat": None})
                db.execute("INSERT OR REPLACE INTO rows VALUES (?, ?)", (int(row_out["canonical_order"]), json.dumps(row_out, default=_jsonable, allow_nan=True)))
            db.commit()
            if raw_hash is not None and raw_bytes is not None:
                input_hashes[str(raw_path)] = (raw_hash, raw_bytes)
    finally:
        db.commit()

    # Ordered incremental parquet emission from disk spool; no 99k-row Python output list.
    records = db.execute("SELECT payload FROM rows ORDER BY ord")
    count_out = write_geometry_rows((json.loads(payload) for (payload,) in records), output_dir / "geometry_ledger.parquet", pa, pq)
    db.close()
    spool_path.unlink()

    mismatch_file.flush()
    mismatch_file.close()
    # Concise per-gear descriptives from emitted parquet projection, still batch bounded.
    gear_stats: dict[str, dict[str, Any]] = {}
    for b in pq.ParquetFile(output_dir / "geometry_ledger.parquet").iter_batches(columns=["primary_gear", "geometry_status", "shape_dl", "chosen_path_m"], batch_size=8192):
        for row in b.to_pylist():
            gear = row["primary_gear"] or "unknown"
            st = gear_stats.setdefault(gear, {"n_rows": 0, "n_informative": 0, "shape_dl_min": None, "shape_dl_max": None,
                "shape_dl_sum": 0.0, "path_m_min": None, "path_m_max": None, "path_m_sum": 0.0,
                "shape_dl_decile_counts": [0] * 10})
            st["n_rows"] += 1
            if row["shape_dl"] is not None and math.isfinite(row["shape_dl"]):
                st["n_informative"] += 1
                st["shape_dl_sum"] += row["shape_dl"]
                bin_i = min(9, int(row["shape_dl"] * 10))
                st["shape_dl_decile_counts"][bin_i] += 1
                st["path_m_sum"] += row["chosen_path_m"]
                for key, v in (("shape_dl", row["shape_dl"]), ("path_m", row["chosen_path_m"])):
                    lo, hi = f"{key}_min", f"{key}_max"
                    st[lo] = v if st[lo] is None else min(st[lo], v)
                    st[hi] = v if st[hi] is None else max(st[hi], v)
    for st in gear_stats.values():
        n_info = st["n_informative"]
        st["shape_dl_mean"] = st["shape_dl_sum"] / n_info if n_info else None
        st["chosen_path_m_mean"] = st["path_m_sum"] / n_info if n_info else None
        del st["shape_dl_sum"]
        del st["path_m_sum"]
    (output_dir / "gear_distributions.json").write_text(json.dumps(gear_stats, indent=2), encoding="utf-8")
    proc = psutil.Process()
    peak_rss = proc.memory_info().rss / (1024 * 1024)
    peak_wset = getattr(proc.memory_info(), "peak_wset", None)
    status = "complete" if error_count == 0 and count_out == 99677 else "failed_validation"
    receipt = {"status": status, "rows_written": count_out, "canonical_rows_expected": canonical_count,
        "mismatch_count": mismatch_count, "error_count": error_count, "error_samples_first_100": errors,
        "ram_preflight": preflight, "process_rss_mib_at_end": round(peak_rss, 2),
        "process_peak_working_set_mib": round(peak_wset/(1024*1024), 2) if peak_wset else None,
        "elapsed_sec": round(time.time()-started, 3), "timezone": "unknown; source-clock integer hours only; no localization",
        "cache_month_rows": cache_counts, "monthly_offsets": {m: offsets[m-1] for m in range(1, 7)},
        "input_sha256_bytes": {k: {"sha256": v[0], "bytes": v[1]} for k, v in input_hashes.items()},
        "extractor_sha256": _sha256_self(), "haversine_radius_m": EARTH_R,
        "tolerances": {"len_m": 1e-4, "bbox_m": 1e-4, "cen_lon": 1e-7, "cen_lat": 1e-7},
        "release_ready_for_scoring": status == "complete"}
    (output_dir / "runtime_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    output_hashes = {}
    for path in output_dir.iterdir():
        if path.is_file() and path.name != "output_manifest.json":
            h, n = _hash_file(path)
            output_hashes[path.name] = {"sha256": h, "bytes": n}
    raw_file_manifest = {}
    for m in range(1, 7):
        raw_name = str(raw_dir / f"vpass_{m}월 데이터.csv")
        observed = receipt["input_sha256_bytes"].get(raw_name)
        raw_file_manifest[str(m)] = {"sha256": observed["sha256"] if observed else None,
            "bytes": observed["bytes"] if observed else None,
            "expected_r7_sha256": EXPECTED_RAW_SHA256.get(m),
            "observed": observed is not None}
    manifest = {"code": {"extract_geometry.py": receipt["extractor_sha256"]},
                "references": {"testB/final/round_007_20261106/run_round7.py": R7_RUN_ROUND7_SHA256,
                               "upstream_run_remeasure_20261031.py": UPSTREAM_PARSER_SHA256},
                "inputs": receipt["input_sha256_bytes"], "outputs": output_hashes,
                "raw_hash_check_scope": "full bounded-byte SHA-256; months 1/5/6 compared to R7 expected values; months 2/3/4 are newly observed",
                "raw_files": raw_file_manifest}
    (output_dir / "output_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if status == "complete" else 2


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--canonical", required=True, help="R4 candidate_ledger.parquet")
    p.add_argument("--registry", required=True, help="R3 gear_registry.csv")
    p.add_argument("--cache-dir", required=True, help="directory containing rows_train_1..6.parquet")
    p.add_argument("--raw-dir", required=True, help="directory containing vpass_{month}월 데이터.csv")
    p.add_argument("--output-dir", required=True, help="new output directory; existing directories are refused")
    return p


if __name__ == "__main__":
    try:
        sys.exit(run_extract(make_parser().parse_args()))
    except MemoryError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(75)
    except Exception as exc:
        print(f"extract_geometry failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
