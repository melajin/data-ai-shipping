"""Root integration and event-window availability, not event prediction."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(probe_dir, independent_dir, output_dir):
    probe_dir, independent_dir, out = [Path(x).resolve() for x in (probe_dir, independent_dir, output_dir)]
    if any(HERE not in p.parents for p in (probe_dir, independent_dir, out)) or out.exists():
        raise ValueError("Use round-local inputs and a NEW root validation output directory")
    out.mkdir(parents=True)
    start = time.perf_counter()
    receipt = {"status": "starting", "experiment": "R10 centroid proxy feasibility ONLY", "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        r9 = load("r10_root_memory", HERE.parent / "round_009_20261106" / "run_transition.py")
        available = r9.available_bytes()
        receipt["ram_preflight"] = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "available_mib": available / 1048576, "expected_extra_mib": 1280, "reserve_mib": 640,
            "basis": "One99k ledger+canonical projection/count tables; no new full histories; prior actual R9 peak356MiB", "allowed": available >= 1920 * 1048576}
        write_json(out / "EXECUTION.json", receipt)
        if not receipt["ram_preflight"]["allowed"]:
            receipt.update(status="memory_deferred", exit_code=75)
            return 75
        r8 = load("r10_verified_key_helpers", HERE.parent / "round_008_20261106" / "run_shape.py")
        receipt["other_processes"] = r8._processes()
        import numpy as np
        import pandas as pd
        import pyarrow.parquet as pq
        worker_receipts = {}
        for name, folder in [("probe", probe_dir), ("independent", independent_dir)]:
            data = json.loads((folder / "EXECUTION.json").read_text(encoding="utf-8-sig"))
            if data.get("status") != "complete":
                raise ValueError(f"{name} worker did not complete")
            worker_receipts[name] = data
        ledger_path = probe_dir / "position_ledger.parquet"
        canonical_path = HERE.parent / "round_004_20261105" / "execution_001" / "candidate_ledger.parquet"
        input_paths = [ledger_path, canonical_path, probe_dir / "per_vessel.csv", independent_dir / "per_vessel.csv",
                       independent_dir / "independent_distance_cases.csv", probe_dir / "EXECUTION.json", independent_dir / "EXECUTION.json"]
        hashes = {str(p): sha(p) for p in input_paths}
        receipt["inputs_sha256"] = hashes
        receipt["sources_sha256"] = {str(p): sha(p) for p in [Path(__file__), HERE / "position_probe.py", HERE / "independent_availability.py", HERE / "CONTRACT.md"]}
        ledger = r8.validate_raw_keys(pq.read_table(ledger_path).to_pandas(), "position ledger")
        canonical = r8.validate_raw_keys(pq.read_table(canonical_path, columns=["rfid_id", "ts", "source_ordinal", "cen_lon", "cen_lat"]).to_pandas(), "canonical")
        if len(ledger) != 99677 or ledger.rfid_id.nunique() != 82:
            raise ValueError("Position ledger roster mismatch")
        for col in ["rfid_id", "ts", "source_ordinal"]:
            if not ledger[col].equals(canonical[col]):
                raise ValueError(f"Canonical keys/order changed: {col}")
        for col in ["cen_lon", "cen_lat"]:
            if not np.array_equal(ledger[col].to_numpy(dtype=float), canonical[col].to_numpy(dtype=float), equal_nan=True):
                raise ValueError(f"Canonical coordinate copy changed: {col}")
        if (ledger.own_distance_eligible & ~ledger.coordinate_valid).any() or (ledger.peer_eligible & ~ledger.own_distance_eligible).any():
            raise ValueError("Availability hierarchy violation")
        eligible_distances = ledger.loc[ledger.own_distance_eligible, "nearest_distance_m"].to_numpy(dtype=float)
        if not np.all(np.isfinite(eligible_distances)) or (eligible_distances < 0).any():
            raise ValueError("Eligible distance is invalid")
        actual_counts = ledger.groupby("rfid_id", sort=True).agg(observed_n=("ts", "size"), valid_position_n=("coordinate_valid", "sum"),
            own_eligible_n=("own_distance_eligible", "sum"), peer_eligible_n=("peer_eligible", "sum")).astype("int64")
        fields = list(actual_counts.columns)
        for name, folder in [("probe", probe_dir), ("independent", independent_dir)]:
            counts = pd.read_csv(folder / "per_vessel.csv", dtype={"rfid_id": str})
            if len(counts) != 82 or counts.rfid_id.duplicated().any():
                raise ValueError(f"{name} count roster mismatch")
            counts = counts.set_index("rfid_id")[fields].sort_index().astype("int64")
            if not actual_counts.equals(counts):
                pd.concat({"ledger": actual_counts, name: counts}, axis=1).to_csv(out / "COUNT_MISMATCH.csv")
                raise ValueError(f"{name} per-vessel count mismatch")
        cases = pd.read_csv(independent_dir / "independent_distance_cases.csv", dtype={"rfid_id": str})
        if len(cases) != 12 or cases.source_ordinal.duplicated().any():
            raise ValueError("Expected12 distinct predetermined queries")
        by_ord = ledger.set_index("source_ordinal", verify_integrity=True)
        comparisons = []
        for case in cases.itertuples(index=False):
            row = by_ord.loc[int(case.source_ordinal)]
            if row.rfid_id != case.rfid_id or int(row.ts) != int(case.ts) or not row.own_distance_eligible:
                raise ValueError("Scalar query key/eligibility mismatch")
            error = abs(float(row.nearest_distance_m) - float(case.nearest_distance_m))
            if error > 1e-4:
                raise ValueError(f"Scalar distance discrepancy: {error}")
            for field in ["nearest_source_ordinal", "nearest_ts", "own_ref_n", "own_ref_dates"]:
                if int(row[field]) != int(getattr(case, field)):
                    raise ValueError(f"Scalar neighbor/history mismatch: {field}")
            neighbor = by_ord.loc[int(row.nearest_source_ordinal)]
            if neighbor.rfid_id != row.rfid_id or not int(row.ts)-720 <= int(neighbor.ts) < int(row.ts):
                raise ValueError("Nearest neighbor violates strict own history")
            comparisons.append({"source_ordinal": int(case.source_ordinal), "distance_error_m": error,
                                "nearest_source_ordinal": int(row.nearest_source_ordinal)})
        pd.DataFrame(comparisons).to_csv(out / "distance_concordance.csv", index=False)
        validation = {"all_82_count_rows_match": True, "scalar_queries_match": 12,
            "max_distance_error_m": max(x["distance_error_m"] for x in comparisons),
            "totals": {f: int(actual_counts[f].sum()) for f in fields}, "frozen_position_ledger_sha256": hashes[str(ledger_path)],
            "validated_before_event_labels": True, "performance_claim": False}
        write_json(out / "ROOT_VALIDATION.json", validation)
        # Only now parse event labels; this remains availability, not hit scoring.
        event_paths = sorted((ROOT / "testB").glob("*/round_008_linkage_audit_20261105/devset_positives.csv"))
        if len(event_paths) != 1:
            raise ValueError("Event source must be unique")
        positives = pd.read_csv(event_paths[0], usecols=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"], dtype={"rfid_id": str})
        t01 = positives[positives.tier <= 1]
        if (len(positives), positives.rfid_id.nunique(), len(t01), t01.rfid_id.nunique()) != (100, 82, 60, 55):
            raise ValueError("Event cohorts changed")
        groups = {rid: g for rid, g in ledger.groupby("rfid_id", sort=False)}
        records = []
        for event in positives.itertuples(index=False):
            group = groups[event.rfid_id]
            window = group[(group.ts - int(event.acc_ts)).abs() <= 6]
            records.append({"acc_id": int(event.acc_id), "rfid_id": event.rfid_id, "tier": int(event.tier),
                "acc_ts": int(event.acc_ts), "observed_window_n": len(window),
                "valid_coordinate_in_window": bool(window.coordinate_valid.any()),
                "own_eligible_in_window": bool(window.own_distance_eligible.any()),
                "peer_eligible_in_window": bool(window.peer_eligible.any()),
                "whole_vessel_own_eligible": bool(group.own_distance_eligible.any()),
                "whole_vessel_peer_eligible": bool(group.peer_eligible.any())})
        availability = pd.DataFrame(records)
        availability.to_csv(out / "event_availability.csv", index=False)
        tier01 = availability[availability.tier <= 1]
        own_event_n = int(tier01.own_eligible_in_window.sum())
        peer_vessel_n = int((actual_counts.peer_eligible_n > 0).sum())
        gate = {"kind": "FEASIBILITY ONLY, not accident performance", "tier01_own_eligible_events": own_event_n,
            "tier01_denominator": 60, "required_tier01_own_events": 50,
            "rfids_with_any_peer_eligible": peer_vessel_n, "required_peer_rfids": 6,
            "passed": bool(own_event_n >= 50 and peer_vessel_n >= 6),
            "all_own_eligible_events": int(availability.own_eligible_in_window.sum()),
            "all_peer_eligible_events": int(availability.peer_eligible_in_window.sum()),
            "tier01_peer_eligible_events": int(tier01.peer_eligible_in_window.sum()),
            "does_not_establish_hit_improvement": True}
        write_json(out / "availability_gate.json", gate)
        if any(sha(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("Probe input changed during validation")
        receipt.update(status="complete", exit_code=0, validation=validation, availability_gate=gate,
            peak_working_set_bytes=r8._peak_working_set(), no_predictions_generated=True)
        receipt["outputs"] = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in out.iterdir() if p.is_file() and p.name != "EXECUTION.json"}
        print(json.dumps(gate, ensure_ascii=False))
        return 0
    except Exception as exc:
        receipt.update(status="failed", exit_code=1, error=str(exc), traceback=traceback.format_exc())
        print(traceback.format_exc(), file=sys.stderr)
        return 1
    finally:
        receipt.update(elapsed_seconds=time.perf_counter()-start, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        write_json(out / "EXECUTION.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-dir", default=str(HERE / "probe_outputs" / "actual_001"))
    parser.add_argument("--independent-dir", default=str(HERE / "independent_outputs" / "actual_001"))
    parser.add_argument("--output-dir", default=str(HERE / "root_validation_001"))
    args = parser.parse_args()
    sys.exit(run(args.probe_dir, args.independent_dir, args.output_dir))
