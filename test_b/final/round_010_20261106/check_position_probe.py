"""Synthetic checks and the single authorized Round10 numeric probe runner."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ACTUAL_DIR = HERE / "probe_outputs" / "actual_001"
CANONICAL = HERE.parent / "round_004_20261105" / "execution_001" / "candidate_ledger.parquet"
REGISTRY = HERE.parent / "round_003_20261105" / "gear_registry.csv"
PROBE = HERE / "position_probe.py"
CHECKER = Path(__file__).resolve()


def ram_preflight() -> dict:
    current_pid = os.getpid()
    jobs = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] != current_pid and "python" in (proc.info["name"] or "").lower():
                jobs.append({"pid": proc.info["pid"], "name": proc.info["name"],
                             "cmdline": " ".join(proc.info["cmdline"] or [])[:220]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    available_mib = psutil.virtual_memory().available / 1048576
    # Fixed Gemini overlap reserve plus all other locally visible Python jobs.
    fixed_gemini = 512
    other_jobs = 512 * len(jobs)
    required = 768 + fixed_gemini + other_jobs + 640
    receipt = {
        "checked_at": dt.datetime.now().astimezone().isoformat(),
        "available_mib": round(available_mib, 2),
        "luna_probe_extra_mib": 768,
        "gemini_synthetic_reserve_mib": fixed_gemini,
        "additional_visible_python_jobs": jobs,
        "additional_job_reserve_mib": other_jobs,
        "reserve_mib": 640,
        "required_available_mib": required,
        "allowed": available_mib >= required,
        "basis": "bounded 720-hour histories and per-row distance vector; fixed Luna 768 + Gemini 512 + 640 reserve, plus 512 per other visible Python job",
    }
    if not receipt["allowed"]:
        raise MemoryError(f"RAM preflight failed; defer without source read: {receipt}")
    return receipt


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def make_fixture(pd):
    rows = []
    next_ordinal = 0

    def add(rid, t, lon, lat, ordinal=None):
        nonlocal next_ordinal
        if ordinal is None:
            ordinal = next_ordinal
        next_ordinal = max(next_ordinal + 1, int(ordinal) + 1)
        rows.append({"rfid_id": rid, "ts": int(t), "source_ordinal": int(ordinal),
                     "cen_lon": lon, "cen_lat": lat})

    def history(rid, current_t=720, n=24, gear=None, single=False):
        assert n in (23, 24)
        counts = [n // 3 + int(i < n % 3) for i in range(3)]
        for base, count in zip((0, 240, 480), counts):
            for j in range(count):
                add(rid, base + j, 10.0 + (j % 2), 20.0, None)
        add(rid, current_t, 11.0, 20.0, None)

    # Main known-gear vessel has 25 past rows, three past dates and two
    # same-hour rows so ordinal can resolve exact distance ties.
    add("A", 0, 0.0, 0.0)
    for t in range(1, 8):
        add("A", t, 20.0, 20.0)
    add("A", 240, 5.0, 5.0, ordinal=900)
    add("A", 240, 5.0, 5.0, ordinal=100)
    for t in range(241, 248):
        add("A", t, 20.0, 20.0)
    add("A", 480, 5.0, 5.0)
    for t in range(481, 488):
        add("A", t, 20.0, 20.0)
    a_known = len(rows); add("A", 720, 1.0, 0.0, ordinal=200)
    a_tie = len(rows); add("A", 720, 5.0, 5.0, ordinal=201)
    a_repeat = len(rows); add("A", 721, 1.0, 0.0, ordinal=202)
    a_nan = len(rows); add("A", 722, float("nan"), 0.0, ordinal=203)
    # The following t=721 row is future relative to both t=720 queries.

    # 23 rows in [0,720), with the t-720 row at -1 included for t=719 but
    # excluded from t=720 as its t-721 row.
    add("BOUND", -1, -5.0, 0.0)
    add("BOUND", 0, -4.0, 0.0)
    for t in range(240, 251):
        add("BOUND", t, -3.0, 0.0)
    for t in range(480, 491):
        add("BOUND", t, -2.0, 0.0)
    bound719 = len(rows); add("BOUND", 719, float("nan"), 0.0)
    bound720 = len(rows); add("BOUND", 720, -1.0, 0.0)

    # 24 positions on only two source-clock dates must remain ineligible.
    for t in range(12):
        add("TWODATE", t, 30.0, 0.0)
    for t in range(24, 36):
        add("TWODATE", t, 31.0, 0.0)
    two_date_current = len(rows); add("TWODATE", 720, 32.0, 0.0)

    # Five same-single-gear peers qualify from history only, with no t=720 row.
    peer_ids = [f"P{i}" for i in range(1, 6)]
    for rid in peer_ids:
        for base in (0, 240, 480):
            for j in range(8):
                add(rid, base + j, 40.0 + j, 10.0)

    # Singleton and unknown-gear rows have own history but no peer gate.
    for rid in ("SINGLE", "UNKNOWN"):
        for base in (0, 240, 480):
            for j in range(8):
                add(rid, base + j, 60.0 + j, 10.0)
    solo_current = len(rows); add("SINGLE", 720, 61.0, 10.0)
    unknown_current = len(rows); add("UNKNOWN", 720, 61.0, 10.0)

    out_history = []
    for base in (0, 240, 480):
        for j in range(8):
            add("OUT", base + j, 70.0 + j, 5.0)
    out_current = len(rows); add("OUT", 720, 181.0, 0.0)
    future_row = {"rfid_id": "A", "ts": 2000, "source_ordinal": 204,
                  "cen_lon": -150.0, "cen_lat": 70.0}

    frame = pd.DataFrame(rows)
    registry_rows = [{"rfid_id": "A", "primary_gear": "G", "is_single_code": True}]
    registry_rows.extend({"rfid_id": rid, "primary_gear": "G", "is_single_code": True} for rid in peer_ids)
    registry_rows.extend([
        {"rfid_id": "BOUND", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "TWODATE", "primary_gear": "2D", "is_single_code": True},
        {"rfid_id": "SINGLE", "primary_gear": "Solo", "is_single_code": True},
        {"rfid_id": "UNKNOWN", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "OUT", "primary_gear": None, "is_single_code": False},
        {"rfid_id": "REGZERO", "primary_gear": "Unused", "is_single_code": True},
    ])
    registry = pd.DataFrame(registry_rows)
    indices = {"a_known": a_known, "a_tie": a_tie, "a_repeat": a_repeat, "a_nan": a_nan,
               "bound719": bound719, "bound720": bound720, "two_date": two_date_current,
               "solo": solo_current, "unknown": unknown_current, "out": out_current,
               "future_row": future_row, "peer_ids": peer_ids}
    return frame, registry, indices


def run_synthetic() -> dict:
    ram = ram_preflight()
    pd = importlib.import_module("pandas")
    np = importlib.import_module("numpy")
    module = importlib.import_module("position_probe")
    paths = {"position_probe.py": PROBE, "check_position_probe.py": CHECKER}
    hashes_before = {k: sha256(v) for k, v in paths.items()}
    frame, registry, ix = make_fixture(pd)
    result = module.build_position_probe(frame, registry)
    ledger, per_vessel, summary = result["ledger"], result["per_vessel"], result["summary"]
    checks = []

    assert len(ledger) == len(frame) and ledger["source_ordinal"].tolist() == frame["source_ordinal"].tolist()
    assert len(per_vessel) == len(registry) and "REGZERO" in set(per_vessel.rfid_id)
    checks.append("all input rows and ordinals are preserved, including registry-only zero-count vessels")

    a_known = ledger.iloc[ix["a_known"]]
    expected_deg = 111_194.92664455874
    assert bool(a_known.coordinate_valid) and int(a_known.own_ref_n) == 25 and int(a_known.own_ref_dates) == 3
    assert bool(a_known.own_distance_eligible) and abs(float(a_known.nearest_distance_m) - expected_deg) < 1e-6
    assert int(a_known.nearest_ts) == 0 and int(a_known.nearest_source_ordinal) == int(ledger.iloc[0].source_ordinal)
    checks.append("valid coordinate, 25-position/3-date history, and known one-degree haversine distance pass")

    tie = ledger.iloc[ix["a_tie"]]
    assert float(tie.nearest_distance_m) == 0.0 and int(tie.nearest_ts) == 240
    assert int(tie.nearest_source_ordinal) == 100
    checks.append("exact nearest-distance ties choose earliest timestamp, then lowest ordinal at that timestamp")

    repeated = ledger.iloc[ix["a_repeat"]]
    assert float(repeated.nearest_distance_m) == 0.0 and int(repeated.nearest_ts) == 720
    checks.append("a repeated past centroid yields zero distance; same-time/current and future rows are excluded")

    b719, b720 = ledger.iloc[ix["bound719"]], ledger.iloc[ix["bound720"]]
    assert int(b719.own_ref_n) == 24 and not bool(b719.coordinate_valid)
    assert int(b720.own_ref_n) == 23 and not bool(b720.own_distance_eligible)
    checks.append("t-720 is included while t-721 is excluded; resulting 24/23 position gate is exact")

    two_date = ledger.iloc[ix["two_date"]]
    assert int(two_date.own_ref_n) == 24 and int(two_date.own_ref_dates) == 2
    assert not bool(two_date.own_distance_eligible)
    checks.append("24 past positions on only two distinct source-clock dates defer")

    for ix_name in ("a_nan", "out"):
        bad = ledger.iloc[ix[ix_name]]
        assert not bool(bad.coordinate_valid) and not bool(bad.own_distance_eligible)
        assert bad.own_status == "defer" and pd.isna(bad.nearest_distance_m)
    checks.append("NaN and out-of-range current coordinates are retained and explicitly deferred")

    target_rows = ledger[(ledger.rfid_id == "A") & (ledger.ts == 720)]
    assert target_rows.peer_eligible_n.tolist() == [5, 5]
    assert target_rows.peer_eligible.all()
    assert not ((ledger.rfid_id.isin(ix["peer_ids"])) & ledger.ts.eq(720)).any()
    checks.append("peer count excludes own vessel and accepts five history-qualified peers without current observations")

    solo, unknown = ledger.iloc[ix["solo"]], ledger.iloc[ix["unknown"]]
    assert bool(solo.own_distance_eligible) and int(solo.peer_eligible_n) == 0 and not bool(solo.peer_eligible)
    assert bool(unknown.own_distance_eligible) and int(unknown.peer_eligible_n) == 0 and not bool(unknown.peer_eligible)
    checks.append("known singleton and unknown gear keep own distance eligibility but defer at the peer stage")

    assert (ledger.own_distance_eligible <= ledger.coordinate_valid).all()
    assert (ledger.peer_eligible <= ledger.own_distance_eligible).all()
    checks.append("availability stages are monotone: valid current coordinate, own history, then peer history")

    base = ledger.copy()
    future_frame = pd.concat([frame, pd.DataFrame([ix["future_row"]])], ignore_index=True)
    extended = module.build_position_probe(future_frame, registry)["ledger"].iloc[:len(frame)]
    compare_cols = ["own_ref_n", "own_ref_dates", "own_distance_eligible", "nearest_distance_m",
                    "nearest_source_ordinal", "nearest_ts", "peer_eligible_n", "peer_eligible"]
    pd.testing.assert_frame_equal(base[compare_cols], extended[compare_cols], check_dtype=False)
    checks.append("appending a future row leaves existing reference counts, distances, peers, and eligibility unchanged")

    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    try:
        module.build_position_probe(duplicate, registry)
        raise AssertionError("duplicate full raw key accepted")
    except ValueError:
        pass
    fractional = frame.copy()
    fractional["ts"] = fractional["ts"].astype(np.float64) + 0.5
    try:
        module.build_position_probe(fractional, registry)
        raise AssertionError("fractional source hour accepted")
    except ValueError:
        pass
    checks.append("duplicate RFID/hour/ordinal and fractional source-clock keys are rejected")

    hashes_after = {k: sha256(v) for k, v in paths.items()}
    assert hashes_before == hashes_after
    code_hashes_before = {k: hashes_before[k] for k in ("position_probe.py", "check_position_probe.py")}
    code_hashes_after = {k: hashes_after[k] for k in ("position_probe.py", "check_position_probe.py")}
    payload = {
        "status": "passed", "requested_model": "GPT-6 Luna", "requested_effort": "xhigh",
        "check_count": len(checks), "checks": checks, "synthetic_rows": int(len(frame)),
        "synthetic_rfid_n": int(frame.rfid_id.nunique()), "summary": summary,
        "known_haversine_distance_m": expected_deg,
        "source_hashes_before": hashes_before, "source_hashes_after": hashes_after,
        "code_hashes_before": code_hashes_before, "code_hashes_after": code_hashes_after,
        "ram_preflight": ram,
        "scope": "synthetic in-memory coordinates only; no actual source, labels, events, scoring, or training accessed",
    }
    write_json(HERE / "probe_checks.json", payload)
    return payload


def _peak_working_set_mib() -> float | None:
    try:
        info = psutil.Process().memory_info()
        peak = getattr(info, "peak_wset", None)
        if peak is None:
            peak = info.rss
        return round(float(peak) / 1048576, 2)
    except (psutil.Error, OSError):
        return None


def run_actual_once() -> int:
    if ACTUAL_DIR.exists():
        raise FileExistsError(f"refusing to overwrite existing actual output folder: {ACTUAL_DIR}")
    ram = ram_preflight()  # before pandas/numpy/pyarrow imports or source reads
    ACTUAL_DIR.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    receipt = {
        "status": "running", "experiment": "R10 past-centroid nearest-distance and peer-history availability",
        "started_at": dt.datetime.now().astimezone().isoformat(), "command": sys.argv,
        "requested_model": "GPT-6 Luna", "requested_effort": "xhigh",
        "ram_preflight": ram, "inputs": {}, "source_hashes_before": {},
        "source_hashes_after": {}, "code_hashes_before": {}, "code_hashes_after": {}, "outputs": {},
        "scope": "numeric centroid availability only; no event/accident/label access or predictions",
    }
    write_json(ACTUAL_DIR / "EXECUTION.json", receipt)
    source_paths = {
        "position_probe.py": PROBE, "check_position_probe.py": CHECKER,
        "TASK_LUNA.md": HERE / "TASK_LUNA.md", "PROTOCOL.md": HERE / "PROTOCOL.md",
        "CONTRACT.md": HERE / "CONTRACT.md",
    }
    input_paths = {"canonical_numeric_ledger": CANONICAL, "gear_registry": REGISTRY}
    exit_code = 1
    error = None
    try:
        missing = [str(p) for p in list(source_paths.values()) + list(input_paths.values()) if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"required source/input files missing: {missing}")
        receipt["source_hashes_before"] = {name: sha256(path) for name, path in source_paths.items()}
        receipt["code_hashes_before"] = {
            k: receipt["source_hashes_before"][k] for k in ("position_probe.py", "check_position_probe.py")
        }
        receipt["inputs"] = {name: {"path": str(path), "bytes": path.stat().st_size,
                                    "sha256_before": sha256(path)} for name, path in input_paths.items()}
        receipt["source_metadata"] = {"canonical_rows_expected": 99677, "canonical_rfids_expected": 82,
                                      "projection": ["rfid_id", "ts", "source_ordinal", "cen_lon", "cen_lat"],
                                      "registry_projection": ["rfid_id", "primary_gear", "is_single_code"]}

        pd = importlib.import_module("pandas")
        np = importlib.import_module("numpy")
        pq = importlib.import_module("pyarrow.parquet")
        probe = importlib.import_module("position_probe")
        frame = pq.read_table(CANONICAL, columns=probe.INPUT_COLUMNS).to_pandas()
        registry = pd.read_csv(REGISTRY, usecols=probe.REGISTRY_COLUMNS, dtype={"rfid_id": str})
        receipt["input_rows_read"] = int(len(frame))
        receipt["input_rfid_n_read"] = int(frame.rfid_id.nunique())
        if len(frame) != 99677 or frame.rfid_id.nunique() != 82:
            raise ValueError("canonical numeric ledger must contain exactly 99,677 rows and 82 RFIDs")

        artifacts = probe.build_position_probe(frame, registry)
        ledger = artifacts["ledger"]
        per_vessel = artifacts["per_vessel"]
        summary = artifacts["summary"]
        if len(ledger) != len(frame) or not np.array_equal(
            ledger["source_ordinal"].to_numpy(dtype="int64"),
            frame["source_ordinal"].reset_index(drop=True).to_numpy(dtype="int64"),
        ):
            raise ValueError("position ledger did not preserve every canonical row and ordinal order")
        if len(per_vessel) != 82 or per_vessel.rfid_id.duplicated().any():
            raise ValueError("per-vessel export must contain exactly one row for all 82 RFIDs")
        if summary["rfid_n"] != 82 or summary["row_n"] != 99677:
            raise ValueError("summary roster/row counts mismatch")

        ledger.to_parquet(ACTUAL_DIR / "position_ledger.parquet", index=False)
        per_vessel.to_csv(ACTUAL_DIR / "per_vessel.csv", index=False)
        write_json(ACTUAL_DIR / "summary.json", summary)
        receipt["summary"] = summary
        receipt["input_rows_preserved"] = True
        receipt["per_vessel_rows"] = int(len(per_vessel))
        exit_code = 0
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        exit_code = 1
    finally:
        receipt["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        receipt["finished_at"] = dt.datetime.now().astimezone().isoformat()
        receipt["peak_working_set_mib"] = _peak_working_set_mib()
        try:
            receipt["available_ram_after_mib"] = round(psutil.virtual_memory().available / 1048576, 2)
        except psutil.Error:
            receipt["available_ram_after_mib"] = None
        try:
            if receipt["source_hashes_before"]:
                after = {name: sha256(path) for name, path in source_paths.items()}
                receipt["source_hashes_after"] = after
                receipt["source_hashes_unchanged"] = (after == receipt["source_hashes_before"])
                receipt["code_hashes_after"] = {
                    k: after[k] for k in ("position_probe.py", "check_position_probe.py")
                }
                receipt["code_hashes_unchanged"] = (
                    receipt["code_hashes_after"] == receipt["code_hashes_before"]
                )
                if not receipt["source_hashes_unchanged"]:
                    error = error or {"type": "SourceHashChanged", "message": "code/document hash changed during actual probe"}
                    exit_code = 1
            for name, item in receipt["inputs"].items():
                path = input_paths[name]
                item["sha256_after"] = sha256(path)
                item["unchanged"] = item["sha256_after"] == item.get("sha256_before")
                if not item["unchanged"]:
                    error = error or {"type": "InputHashChanged", "message": f"input changed during run: {name}"}
                    exit_code = 1
        except Exception as exc:
            error = error or {"type": type(exc).__name__, "message": f"final hash check failed: {exc}"}
            exit_code = 1

        outputs = {}
        for name in ("position_ledger.parquet", "per_vessel.csv", "summary.json"):
            path = ACTUAL_DIR / name
            if path.is_file():
                outputs[name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
        write_json(ACTUAL_DIR / "OUTPUT_HASHES.json", {"files": outputs,
                    "note": "EXECUTION.json and OUTPUT_HASHES.json are excluded from this file's own file list"})
        outputs["OUTPUT_HASHES.json"] = {"bytes": (ACTUAL_DIR / "OUTPUT_HASHES.json").stat().st_size,
                                         "sha256": sha256(ACTUAL_DIR / "OUTPUT_HASHES.json")}
        receipt["outputs"] = outputs
        receipt["error"] = error
        receipt["exit_code"] = exit_code
        receipt["status"] = "complete" if exit_code == 0 and error is None else "failed"
        write_json(ACTUAL_DIR / "EXECUTION.json", receipt)
    print(json.dumps({"status": receipt["status"], "output_dir": str(ACTUAL_DIR),
                      "rows": receipt.get("input_rows_read"), "elapsed_seconds": receipt["elapsed_seconds"],
                      "error": error}, ensure_ascii=False, default=str))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", action="store_true", help="run the single authorized actual numeric probe")
    args = parser.parse_args()
    if args.actual:
        return run_actual_once()
    result = run_synthetic()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
