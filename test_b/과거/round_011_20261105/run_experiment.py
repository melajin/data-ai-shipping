"""Fixed Round011 experiment; no legacy imports, fitting, or external collection.

Run: python -B testB/round_011_20261105/run_experiment.py
Only observed epoch-hour endpoints are candidates. Output is valid only when
execution.json has status=complete. A memory refusal exits 75 and preserves a
timestamped execution/memory receipt; partial CSV files are never final results.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import ctypes
from datetime import datetime, timedelta, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
INPUT_DIR = HERE.parent / "round_008_linkage_audit_20261105"
COLS = ("rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat")
ROW_DTYPE = np.dtype([(name, "<i8" if i < 2 else "<f8") for i, name in enumerate(COLS)])
CONTEXTS = ("T", "L", "TL")
RULES = tuple(f"{c}_{metric}" for c in CONTEXTS for metric in ("lin", "activity", "joint")) + ("raw_lin",)
BOOTSTRAP_B = 4000
BOOTSTRAP_SEED = 11052026
MIN_AVAILABLE_BYTES = 768 * 2**20
ESTIMATED_PEAK_BYTES = 512 * 2**20
EARTH_RADIUS_M = 6371008.8
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
SCORE_FIELDS = [
    "rfid_id", "ts", "ts_utc", "year_month", "stored_hour", "n_rows",
    "n_valid_rows", "n_lin_valid", "n_pairs", "lin_raw", "A", "M",
    "end_lon", "end_lat", "end_center_valid", "quality_valid", "quality_reason",
    "common_candidate", "score_raw_lin",
]
for _context in CONTEXTS:
    SCORE_FIELDS.extend(f"{_context}_{suffix}" for suffix in (
        "eligible_endpoints", "eligible_days", "ref_count", "ref_ts_json",
        "reference_max_ts", "unknown_reason", "score_lin", "score_activity", "score_joint"))
EVENT_FIELDS = [
    "acc_id", "rfid_id", "tier", "acc_ts", "acc_ts_utc", "year_month", "stored_hour",
    "rule", "evaluable", "unknown_reason", "candidate_count", "candidate_min_ts", "candidate_max_ts",
    "observed_near_count", "quality_near_count", "common_near_count", "near_coverage_13h",
    "chance", "top1_expected", "top10_probability", "conservative_top1_expected",
    "conservative_top10_probability", "max_score", "top1_tie_count", "top1_tie_hits",
    "top10_k", "top10_cutoff", "top10_above_count", "top10_boundary_count",
    "top10_boundary_hits", "top10_boundary_draws", "top10_above_hits",
]


def now_iso():
    return datetime.now().astimezone().isoformat()


def json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                                    default=json_default) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def epoch_fields(ts):
    dt = EPOCH + timedelta(hours=int(ts))
    return dt.isoformat().replace("+00:00", "Z"), dt.strftime("%Y-%m"), int(ts) % 24


class MemoryDeferred(RuntimeError):
    pass


def memory_state():
    """OS available physical memory, using only stdlib (no monitoring loop)."""
    if os.name == "nt":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in (
                    "total_phys", "avail_phys", "total_page", "avail_page",
                    "total_virtual", "avail_virtual", "avail_extended")]
        status = Status()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed; memory availability is unknown")
        return int(status.avail_phys), int(status.total_phys)
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, value = line.split(":", 1)
        info[name] = int(value.split()[0]) * 1024
    return info["MemAvailable"], info["MemTotal"]


def process_snapshot():
    """Top working sets, names/PIDs only; never query command lines or kill."""
    if os.name == "nt":
        command = ("Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 12 "
                   "Id,ProcessName,WorkingSet64 | ConvertTo-Json -Compress")
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    capture_output=True, text=True, timeout=20,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
            data = json.loads(result.stdout)
            data = [data] if isinstance(data, dict) else data
            return [{"pid": p["Id"], "name": p["ProcessName"], "rss_bytes": p["WorkingSet64"]}
                    for p in data]
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return [{"snapshot_error": str(exc)}]
    processes = []
    for status_path in Path("/proc").glob("[0-9]*/status"):
        try:
            values = dict(line.split(":", 1) for line in status_path.read_text().splitlines() if ":" in line)
            processes.append({"pid": int(status_path.parent.name), "name": values["Name"].strip(),
                              "rss_bytes": int(values.get("VmRSS", "0 kB").split()[0]) * 1024})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(processes, key=lambda p: p["rss_bytes"], reverse=True)[:12]


class MemoryGuard:
    def __init__(self, output):
        self.path = Path(output) / "memory.json"
        self.records = []

    def check(self, stage):
        # Obtain the process inventory first, then the freshest available-RAM value.
        processes = process_snapshot()
        available, total = memory_state()
        record = {"stage": stage, "checked_at": now_iso(), "available_bytes": available,
                  "total_bytes": total, "estimated_peak_bytes": ESTIMATED_PEAK_BYTES,
                  "minimum_available_bytes": MIN_AVAILABLE_BYTES,
                  "estimate_basis": "8192-row Arrow batches; six selected columns; target rows x48B "
                  "compact storage plus ingestion copy; one vessel at a time; <=720h reference pool; "
                  "streamed CSV; 4000x4 bootstrap outputs; Python/Arrow/numpy overhead within 512MiB",
                  "other_processes": [p for p in processes if p.get("pid") != os.getpid()],
                  "current_process": next((p for p in processes if p.get("pid") == os.getpid()), None),
                  "simultaneous_dataset_jobs_authorized": False,
                  "allowed": available >= MIN_AVAILABLE_BYTES}
        self.records.append(record)
        write_json(self.path, self.records)
        print(json.dumps({"stage": stage, "available_mib": round(available / 2**20, 2),
                          "allowed": record["allowed"]}), flush=True)
        if not record["allowed"]:
            raise MemoryDeferred(f"{stage}: available {available / 2**20:.2f}MiB <768MiB")
        return record


def load_events(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"acc_id", "rfid_id", "tier", "acc_ts"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"Missing event columns: {required - set(reader.fieldnames or ())}")
        events = [{key: int(row[key]) for key in required} for row in reader]
    if len({e["acc_id"] for e in events}) != len(events):
        raise ValueError("Duplicate acc_id in fixed event input")
    return events


def load_target_rows(path, target_ids):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    if not set(COLS).issubset(parquet.schema_arrow.names):
        raise ValueError("Parquet is missing required columns")
    target_values = pa.array(sorted(target_ids), type=parquet.schema_arrow.field(COLS[0]).type)
    pieces, scanned = [], 0
    for batch in parquet.iter_batches(batch_size=8192, columns=list(COLS), use_threads=False):
        scanned += batch.num_rows
        keep = pc.fill_null(pc.is_in(batch.column(0), value_set=target_values), False)
        filtered = batch.filter(keep)
        if not filtered.num_rows:
            continue
        compact = np.empty(filtered.num_rows, dtype=ROW_DTYPE)
        for index, name in enumerate(COLS):
            column = filtered.column(index)
            if index < 2 and column.null_count:
                raise ValueError(f"Null {name} in target input")
            if index >= 2:
                column = pc.fill_null(column, float("nan"))
            compact[name] = column.to_numpy(zero_copy_only=False)
        pieces.append(compact)
    rows = np.concatenate(pieces) if pieces else np.empty(0, dtype=ROW_DTYPE)
    del pieces
    # In-place structured sort avoids a second complete sorted table.
    rows.sort(order=[COLS[0], "ts"])
    if len(rows) > 1:
        duplicate = ((rows[COLS[0]][1:] == rows[COLS[0]][:-1]) &
                     (rows["ts"][1:] == rows["ts"][:-1]))
        if duplicate.any():
            raise ValueError("Duplicate vessel/epoch-hour rows; no implicit deduplication permitted")
    return rows, {"parquet_rows": parquet.metadata.num_rows, "scanned_rows": scanned,
                  "retained_rows": len(rows), "compact_bytes": rows.nbytes,
                  "batch_size": 8192, "use_threads": False, "selected_columns": list(COLS)}


def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = [np.deg2rad(v) for v in (lon1, lat1, lon2, lat2)]
    a = np.sin((lat2 - lat1) / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2)**2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def valid_centers(lon, lat):
    return np.isfinite(lon) & np.isfinite(lat) & (np.abs(lon) <= 180) & (np.abs(lat) <= 90)


def build_windows(rows):
    """Current/past identical trailing [t-6,t] windows at observed endpoints."""
    ts, length, bbox, lon, lat = [rows[name] for name in COLS[1:]]
    if len(ts) > 1 and np.any(np.diff(ts) <= 0):
        raise ValueError("Vessel timestamps must be unique and increasing")
    count = len(rows)
    length_valid = np.isfinite(length) & (length >= 0)
    geometry_valid = length_valid & np.isfinite(bbox) & (bbox >= 0)
    lin_valid = geometry_valid & (length >= 1)
    centers = valid_centers(lon, lat)
    lin = np.full(count, np.nan)
    activity = np.full(count, np.nan)
    movement = np.full(count, np.nan)
    n_rows, n_valid, n_lin, n_pairs = [np.zeros(count, dtype=np.int16) for _ in range(4)]
    # Each pair is attached to its right endpoint; gaps/invalid centers stay invalid.
    pair_valid = np.zeros(count, dtype=bool)
    pair_dist = np.full(count, np.nan)
    if count > 1:
        pair_valid[1:] = (np.diff(ts) == 1) & centers[:-1] & centers[1:]
        indices = np.flatnonzero(pair_valid)
        pair_dist[indices] = haversine(lon[indices-1], lat[indices-1], lon[indices], lat[indices])
    for i, t in enumerate(ts):
        left = int(np.searchsorted(ts, t - 6, side="left"))
        section = slice(left, i + 1)
        n_rows[i] = i + 1 - left
        n_valid[i] = np.count_nonzero(geometry_valid[section])
        mask = lin_valid[section]
        n_lin[i] = np.count_nonzero(mask)
        if n_lin[i]:
            lin[i] = np.mean(bbox[section][mask] / length[section][mask])
        mask = length_valid[section]
        if mask.any():
            activity[i] = np.mean(np.log1p(length[section][mask]))
        pairs = pair_valid[left + 1:i + 1]
        n_pairs[i] = np.count_nonzero(pairs)
        if n_pairs[i]:
            movement[i] = np.mean(pair_dist[left + 1:i + 1][pairs])
    quality = ((n_valid >= 4) & (n_lin >= 3) & (n_pairs >= 2) &
               np.isfinite(lin) & np.isfinite(activity) & np.isfinite(movement))
    return {"ts": ts, "n_rows": n_rows, "n_valid_rows": n_valid, "n_lin_valid": n_lin,
            "n_pairs": n_pairs, "lin_raw": lin, "A": activity, "M": movement,
            "end_lon": lon, "end_lat": lat, "end_center_valid": centers, "quality_valid": quality}


def quality_reason(windows, i):
    reasons = []
    for field, minimum, reason in (("n_valid_rows", 4, "valid_geometry_rows_lt4"),
                                   ("n_lin_valid", 3, "lin_valid_rows_lt3"),
                                   ("n_pairs", 2, "exact_1h_center_pairs_lt2")):
        if windows[field][i] < minimum:
            reasons.append(reason)
    if not all(np.isfinite(windows[key][i]) for key in ("lin_raw", "A", "M")):
        reasons.append("nonfinite_window_feature")
    return "|".join(reasons)


def select_references(windows, i, context):
    if context not in CONTEXTS:
        raise ValueError(context)
    empty = {"indices": np.empty(0, dtype=np.int64), "eligible_endpoints": 0, "eligible_days": 0,
             "unknown_reason": ""}
    if not windows["quality_valid"][i]:
        return {**empty, "unknown_reason": "current_quality:" + quality_reason(windows, i)}
    spatial = context in ("L", "TL")
    if spatial and not windows["end_center_valid"][i]:
        return {**empty, "unknown_reason": "current_end_center_invalid"}
    ts = windows["ts"]
    t = int(ts[i])
    lo, hi = np.searchsorted(ts, [t - 720, t - 24], side="left")
    hi = int(np.searchsorted(ts, t - 24, side="right"))
    candidates = np.arange(int(lo), hi)
    coverage_gap = np.abs(windows["n_rows"][candidates] - windows["n_rows"][i])
    good = windows["quality_valid"][candidates] & (coverage_gap <= 1)
    hod = np.abs(ts[candidates] % 24 - t % 24)
    hod = np.minimum(hod, 24 - hod)
    if context in ("T", "TL"):
        good &= hod <= 1
    distances = np.full(len(candidates), np.inf)
    if spatial:
        valid = windows["end_center_valid"][candidates]
        distances[valid] = haversine(windows["end_lon"][i], windows["end_lat"][i],
                                    windows["end_lon"][candidates[valid]], windows["end_lat"][candidates[valid]])
        good &= valid & (distances <= 10000)
    positions = np.flatnonzero(good)
    days = np.unique(ts[candidates[positions]] // 24)[::-1]
    selected = []
    for day in days[:10]:
        p = positions[ts[candidates[positions]] // 24 == day]
        # np.lexsort's final key is primary; ts breaks ties toward the earlier hour.
        if context == "T":
            order = np.lexsort((ts[candidates[p]], coverage_gap[p], hod[p]))
        elif context == "L":
            order = np.lexsort((ts[candidates[p]], coverage_gap[p], distances[p]))
        else:
            order = np.lexsort((ts[candidates[p]], coverage_gap[p], distances[p], hod[p]))
        selected.append(int(candidates[p[order[0]]]))
    indices = np.asarray(selected, dtype=np.int64)
    if len(indices):
        assert np.all((ts[indices] >= t - 720) & (ts[indices] <= t - 24))
        assert len(np.unique(ts[indices] // 24)) == len(indices)
    return {"indices": indices, "eligible_endpoints": len(positions), "eligible_days": len(days),
            "unknown_reason": "" if len(days) >= 10 else "reference_days_lt10"}


def mid_percentile(value, reference):
    reference = np.asarray(reference)
    if not len(reference) or not np.isfinite(value) or not np.isfinite(reference).all():
        raise ValueError("Percentile requires finite value and finite references")
    return float((np.count_nonzero(reference < value) + 0.5 * np.count_nonzero(reference == value)) / len(reference))


def csv_value(value):
    if isinstance(value, (float, np.floating)) and not math.isfinite(value):
        return ""
    if isinstance(value, (np.bool_, bool)):
        return int(value)
    return value.item() if isinstance(value, np.generic) else value


def score_vessel(rows, writer=None):
    windows = build_windows(rows)
    n = len(rows)
    scores = np.full((n, len(RULES)), np.nan)
    unknown_counts = {context: Counter() for context in CONTEXTS}
    quality_counts = Counter()
    for i, ts in enumerate(windows["ts"]):
        reason = quality_reason(windows, i)
        if reason:
            quality_counts[reason] += 1
        iso, month, hod = epoch_fields(ts)
        row = {"rfid_id": int(rows[COLS[0]][i]), "ts": int(ts), "ts_utc": iso,
               "year_month": month, "stored_hour": hod, "quality_reason": reason}
        for field in ("n_rows", "n_valid_rows", "n_lin_valid", "n_pairs", "lin_raw", "A", "M",
                      "end_lon", "end_lat", "end_center_valid", "quality_valid"):
            row[field] = windows[field][i]
        if windows["quality_valid"][i]:
            scores[i, -1] = -windows["lin_raw"][i]
        row["score_raw_lin"] = scores[i, -1]
        for ci, context in enumerate(CONTEXTS):
            reference = select_references(windows, i, context)
            indices = reference["indices"]
            selected_ts = windows["ts"][indices]
            row.update({f"{context}_eligible_endpoints": reference["eligible_endpoints"],
                        f"{context}_eligible_days": reference["eligible_days"],
                        f"{context}_ref_count": len(indices),
                        f"{context}_ref_ts_json": json.dumps(selected_ts.tolist(), separators=(",", ":")),
                        f"{context}_reference_max_ts": int(selected_ts.max()) if len(indices) else "",
                        f"{context}_unknown_reason": reference["unknown_reason"]})
            if reference["unknown_reason"]:
                unknown_counts[context][reference["unknown_reason"]] += 1
            else:
                lin_p, a_p, m_p = [mid_percentile(windows[key][i], windows[key][indices])
                                      for key in ("lin_raw", "A", "M")]
                scores[i, ci * 3:ci * 3 + 3] = (1 - lin_p, 1 - a_p, (1 - a_p) * m_p)
            for offset, metric in enumerate(("lin", "activity", "joint")):
                row[f"{context}_score_{metric}"] = scores[i, ci * 3 + offset]
        row["common_candidate"] = bool(np.isfinite(scores[i]).all())
        if writer is not None:
            writer.writerow({key: csv_value(value) for key, value in row.items()})
    return {"windows": windows, "scores": scores, "common": np.isfinite(scores).all(axis=1),
            "quality_unknown_counts": dict(quality_counts),
            "context_unknown_counts": {c: dict(counts) for c, counts in unknown_counts.items()}}


def ranking_metrics(scores, near, k=10):
    """Uniform maximum tie and exact boundary sampling without replacement."""
    scores = np.asarray(scores)
    near = np.asarray(near, dtype=bool)
    if scores.ndim != 1 or len(scores) != len(near) or not len(scores) or not np.isfinite(scores).all():
        raise ValueError("Ranking requires nonempty equal finite score/near arrays")
    if k < 1:
        raise ValueError("k must be positive")
    maximum = np.max(scores)
    maximum_mask = scores == maximum
    top_ties, top_hits = int(maximum_mask.sum()), int(np.count_nonzero(maximum_mask & near))
    take = min(k, len(scores))
    cutoff = np.partition(scores, len(scores) - take)[len(scores) - take]
    above, boundary = scores > cutoff, scores == cutoff
    above_count, boundary_count = int(above.sum()), int(boundary.sum())
    above_hits = int(np.count_nonzero(above & near))
    boundary_hits = int(np.count_nonzero(boundary & near))
    draws = take - above_count
    if above_hits:
        top_probability = 1.0
    elif boundary_count - boundary_hits < draws:
        top_probability = 1.0
    else:
        # C(b-h,d)/C(b,d), evaluated as <=10 factors to avoid huge combinations.
        miss = math.prod((boundary_count - boundary_hits - j) / (boundary_count - j) for j in range(draws))
        top_probability = 1.0 - miss
    return {"chance": float(np.mean(near)), "top1_expected": top_hits / top_ties,
            "top10_probability": top_probability, "max_score": float(maximum),
            "top1_tie_count": top_ties, "top1_tie_hits": top_hits, "top10_k": take,
            "top10_cutoff": float(cutoff), "top10_above_count": above_count,
            "top10_boundary_count": boundary_count, "top10_boundary_hits": boundary_hits,
            "top10_boundary_draws": draws, "top10_above_hits": above_hits}


def evaluate_vessel(events, result):
    w, scores, common = result["windows"], result["scores"], result["common"]
    candidate_ts = w["ts"][common]
    evaluable = len(candidate_ts) >= 100
    output = []
    for event in events:
        near_all = np.abs(w["ts"] - event["acc_ts"]) <= 6
        near = np.abs(candidate_ts - event["acc_ts"]) <= 6
        iso, month, hod = epoch_fields(event["acc_ts"])
        base = {**event, "acc_ts_utc": iso, "year_month": month, "stored_hour": hod,
                "evaluable": int(evaluable), "unknown_reason": "" if evaluable else "common_candidates_lt100",
                "candidate_count": len(candidate_ts),
                "candidate_min_ts": int(candidate_ts.min()) if len(candidate_ts) else "",
                "candidate_max_ts": int(candidate_ts.max()) if len(candidate_ts) else "",
                "observed_near_count": int(near_all.sum()),
                "quality_near_count": int(np.count_nonzero(near_all & w["quality_valid"])),
                "common_near_count": int(near.sum()), "near_coverage_13h": float(near.sum() / 13)}
        for ri, rule in enumerate(RULES):
            row = {**base, "rule": rule}
            if evaluable:
                row.update(ranking_metrics(scores[common, ri], near))
                row["conservative_top1_expected"] = row["top1_expected"]
                row["conservative_top10_probability"] = row["top10_probability"]
            else:
                row.update({"conservative_top1_expected": 0.0, "conservative_top10_probability": 0.0})
            output.append(row)
    return output


def cluster_bootstrap(vessel_ids, differences, b=BOOTSTRAP_B, seed=BOOTSTRAP_SEED):
    """Resample vessels; every sampled vessel contributes all its events."""
    differences = np.asarray(differences, dtype=float)
    if differences.ndim == 1:
        differences = differences[:, None]
    if len(vessel_ids) != len(differences) or not np.isfinite(differences).all():
        raise ValueError("Bad cluster bootstrap inputs")
    if not len(vessel_ids):
        return {"mean": [None] * differences.shape[1], "ci_low": [None] * differences.shape[1],
                "ci_high": [None] * differences.shape[1], "n_clusters": 0, "n_events": 0,
                "b": b, "seed": seed, "confidence": 0.9875, "quantile_method": "linear",
                "resampling_unit": "vessel_all_events"}
    unique, inverse = np.unique(vessel_ids, return_inverse=True)
    sums = np.zeros((len(unique), differences.shape[1]))
    counts = np.bincount(inverse)
    np.add.at(sums, inverse, differences)
    rng = np.random.default_rng(seed)
    samples = np.empty((b, differences.shape[1]))
    for iteration in range(b):
        draw = rng.integers(0, len(unique), size=len(unique))
        samples[iteration] = sums[draw].sum(axis=0) / counts[draw].sum()
    low, high = np.quantile(samples, [0.00625, 0.99375], axis=0, method="linear")
    return {"mean": differences.mean(axis=0).tolist(), "ci_low": low.tolist(), "ci_high": high.tolist(),
            "n_clusters": len(unique), "n_events": len(vessel_ids), "b": b, "seed": seed,
            "confidence": 0.9875, "quantile_method": "linear", "resampling_unit": "vessel_all_events"}


def summarize(events, metrics, vessel_coverage):
    profiles = {}
    for name, choose in (("tier01", lambda e: e["tier"] <= 1), ("all100", lambda e: True)):
        selected_ids = {e["acc_id"] for e in events if choose(e)}
        selected = [row for row in metrics if row["acc_id"] in selected_ids]
        rules = {}
        for rule in RULES:
            rows = [row for row in selected if row["rule"] == rule]
            valid = [row for row in rows if row["evaluable"]]
            total = len(rows)
            rules[rule] = {"n_total": total, "n_evaluable": len(valid), "n_unknown": total - len(valid),
                           "n_evaluable_vessels": len({r["rfid_id"] for r in valid}),
                           "top1_expected_sum": sum(r.get("top1_expected", 0) for r in rows),
                           "top1_conditional": float(np.mean([r["top1_expected"] for r in valid])) if valid else None,
                           "top10_conditional": float(np.mean([r["top10_probability"] for r in valid])) if valid else None,
                           "chance_conditional": float(np.mean([r["chance"] for r in valid])) if valid else None,
                           "top1_unconditional": sum(r["conservative_top1_expected"] for r in rows) / total if total else None,
                           "top10_unconditional": sum(r["conservative_top10_probability"] for r in rows) / total if total else None,
                           "n_evaluable_without_near_candidates": sum(r["common_near_count"] == 0 for r in valid)}
        profiles[name] = {"n_total": len(selected_ids), "rules": rules}
    lookup = {(r["acc_id"], r["rule"]): r for r in metrics}
    primary_events = [e for e in events if e["tier"] <= 1 and lookup[e["acc_id"], "TL_lin"]["evaluable"]]
    specs = (("H1_TL_minus_T", "TL_lin", "T_lin"), ("H1_TL_minus_L", "TL_lin", "L_lin"),
             ("H2_TL_minus_T", "TL_joint", "T_joint"), ("H2_TL_minus_L", "TL_joint", "L_joint"))
    differences = np.asarray([[lookup[e["acc_id"], a]["top1_expected"] - lookup[e["acc_id"], b]["top1_expected"]
                               for _, a, b in specs] for e in primary_events], dtype=float).reshape(-1, 4)
    boot = cluster_bootstrap([e["rfid_id"] for e in primary_events], differences)
    contrasts = []
    for index, (name, a, b) in enumerate(specs):
        support = len(primary_events) >= 30 and boot["ci_low"][index] is not None and boot["ci_low"][index] > 0
        contrasts.append({"contrast": name, "rule_a": a, "rule_b": b, "profile": "tier01",
                          "n_events": len(primary_events), "n_clusters": boot["n_clusters"],
                          "mean_difference": boot["mean"][index], "ci_low": boot["ci_low"][index],
                          "ci_high": boot["ci_high"][index], "exploratory_improvement_supported": support,
                          "decision": "supported" if support else ("insufficient_common_evaluable_events" if len(primary_events) < 30 else "not_supported")})
    return {"profiles": profiles, "primary_contrasts": contrasts, "bootstrap": {k: v for k, v in boot.items()
            if k not in ("mean", "ci_low", "ci_high")}, "vessel_coverage": vessel_coverage}


def run_experiment(input_parquet, input_events, output, protocol, expected_counts=(100, 82, 60)):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    execution_path = output / "execution.json"
    lock = output / "experiment.lock"
    lock_fd = None
    execution = {"status": "starting", "started_at": now_iso(), "pid": os.getpid(),
                 "command": sys.argv, "python": sys.version, "platform": platform.platform(),
                 "numpy_version": np.__version__, "protocol": str(Path(protocol).resolve()),
                 "inputs": {"parquet": str(Path(input_parquet).resolve()), "events": str(Path(input_events).resolve())},
                 "estimated_peak_bytes": ESTIMATED_PEAK_BYTES, "minimum_available_bytes": MIN_AVAILABLE_BYTES}
    start = time.perf_counter()
    guard = MemoryGuard(output)
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, f"pid={os.getpid()} started={execution['started_at']}\n".encode())
        write_json(execution_path, execution)
        guard.check("before_input_metadata_and_hashing")
        execution["protocol_sha256"] = sha256(protocol)
        execution["code_sha256"] = {"run_experiment.py": sha256(__file__)}
        test_path = HERE / "test_experiment.py"
        if test_path.exists():
            execution["code_sha256"][test_path.name] = sha256(test_path)
        execution["input_sha256"] = {"parquet": sha256(input_parquet), "events": sha256(input_events)}
        events = load_events(input_events)
        counts = (len(events), len({e["rfid_id"] for e in events}), sum(e["tier"] <= 1 for e in events))
        if expected_counts is not None and counts != expected_counts:
            raise ValueError(f"Fixed input counts changed: {counts} != {expected_counts}")
        execution["input_counts"] = dict(zip(("events", "vessels", "tier01_events"), counts))
        write_json(execution_path, execution)
        guard.check("before_streaming_parquet")
        rows, input_profile = load_target_rows(input_parquet, {e["rfid_id"] for e in events})
        import pyarrow
        execution["pyarrow_version"] = pyarrow.__version__
        execution["input_profile"] = input_profile
        gc.collect()
        metrics, coverage = [], []
        score_path, event_path = output / "timestamp_scores.csv", output / "event_metrics.csv"
        guard.check("before_sequential_vessel_scoring")
        with score_path.open("w", encoding="utf-8", newline="") as score_file, event_path.open("w", encoding="utf-8", newline="") as event_file:
            score_writer = csv.DictWriter(score_file, fieldnames=SCORE_FIELDS)
            event_writer = csv.DictWriter(event_file, fieldnames=EVENT_FIELDS)
            score_writer.writeheader()
            event_writer.writeheader()
            ids = rows[COLS[0]]
            for vessel_id in sorted({e["rfid_id"] for e in events}):
                # A vessel is a resource-stage boundary; no concurrent data jobs.
                guard.check(f"before_vessel_{vessel_id}")
                lo, hi = np.searchsorted(ids, [vessel_id, vessel_id + 1])
                vessel_rows = rows[int(lo):int(hi)]
                result = score_vessel(vessel_rows, score_writer)
                vessel_events = [e for e in events if e["rfid_id"] == vessel_id]
                if not len(vessel_rows):
                    # Preserve all events, including vessels with no observed rows.
                    result = {"windows": build_windows(vessel_rows), "scores": np.empty((0, 10)),
                              "common": np.empty(0, dtype=bool), "quality_unknown_counts": {}, "context_unknown_counts": {c: {} for c in CONTEXTS}}
                vessel_metrics = evaluate_vessel(vessel_events, result)
                metrics.extend(vessel_metrics)
                event_writer.writerows(vessel_metrics)
                common_ts = result["windows"]["ts"][result["common"]]
                coverage.append({"rfid_id": vessel_id, "n_events": len(vessel_events),
                                 "observed_endpoints": len(vessel_rows),
                                 "quality_endpoints": int(result["windows"]["quality_valid"].sum()),
                                 "common_candidates": len(common_ts), "evaluable": len(common_ts) >= 100,
                                 "observed_min_ts": int(vessel_rows["ts"][0]) if len(vessel_rows) else None,
                                 "observed_max_ts": int(vessel_rows["ts"][-1]) if len(vessel_rows) else None,
                                 "common_min_ts": int(common_ts.min()) if len(common_ts) else None,
                                 "common_max_ts": int(common_ts.max()) if len(common_ts) else None,
                                 "quality_unknown_counts": result["quality_unknown_counts"],
                                 "context_unknown_counts": result["context_unknown_counts"]})
                score_file.flush()
                event_file.flush()
                del result, vessel_metrics, vessel_rows
        del rows
        gc.collect()
        guard.check("before_cluster_bootstrap_and_summary")
        summary = summarize(events, metrics, coverage)
        if sha256(protocol) != execution["protocol_sha256"]:
            raise RuntimeError("Protocol changed during execution")
        summary.update({"status": "complete", "created_at": now_iso(), "input_counts": execution["input_counts"],
                        "input_profile": input_profile, "protocol_sha256": execution["protocol_sha256"],
                        "input_sha256": execution["input_sha256"], "code_sha256": execution["code_sha256"],
                        "candidate_definition": "observed endpoints only, all 10 rules finite, >=100 per vessel",
                        "row_quality_definition": "n_rows=observed; >=4 finite nonnegative len+bbox; >=3 of those len>=1; >=2 exact1h valid-center pairs; A independent valid len",
                        "time_interpretation": "stored epoch-hour, UTC rendering for inspection only; actual local timezone unverified",
                        "percentile_ties": "(< +0.5*==)/10, original float exact equality",
                        "top1_ties": "uniform random choice among exact maximum ties: hit_count/tie_count",
                        "top10_ties": "all above cutoff plus uniform boundary sample without replacement; 1-C(b-h,d)/C(b,d)",
                        "unknown_policy": "conditional metrics missing; unconditional zero with fixed 60/100 denominators",
                        "memory_records": "memory.json", "timestamp_score_rows": input_profile["retained_rows"],
                        "event_metric_rows": len(metrics), "rules": RULES,
                        "limits": ["Repeated dev use: exploratory, not confirmatory", "Accident-related behavior candidate, not physical drift truth",
                                   "Overlapping candidate windows are not independent alerts", "No hardware experiment or new model fitting"]})
        write_json(output / "summary.json", summary)
        execution["outputs"] = {name: {"sha256": sha256(output / name), "bytes": (output / name).stat().st_size}
                                for name in ("timestamp_scores.csv", "event_metrics.csv", "summary.json")}
        execution["status"] = "complete"
        return 0
    except MemoryDeferred as exc:
        execution.update(status="memory_deferred", error=str(exc), exit_code=75)
        return 75
    except Exception as exc:
        execution.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(), exit_code=1)
        return 1
    finally:
        # A competing invocation must not overwrite the active runner's receipts.
        if lock_fd is not None:
            execution["finished_at"] = now_iso()
            execution["elapsed_seconds"] = time.perf_counter() - start
            execution.setdefault("exit_code", 0 if execution["status"] == "complete" else 1)
            execution["partial_outputs_are_results"] = False
            write_json(execution_path, execution)
            os.close(lock_fd)
            lock.unlink(missing_ok=True)
            print(json.dumps({"status": execution["status"], "exit_code": execution["exit_code"],
                              "elapsed_seconds": round(execution["elapsed_seconds"], 3)}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-parquet", type=Path, default=INPUT_DIR / "dev_hourly_scores.parquet")
    parser.add_argument("--input-events", type=Path, default=INPUT_DIR / "devset_positives.csv")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--protocol", type=Path, default=HERE / "PROTOCOL.md")
    args = parser.parse_args(argv)
    return run_experiment(args.input_parquet, args.input_events, args.output_dir, args.protocol)


if __name__ == "__main__":
    sys.exit(main())
