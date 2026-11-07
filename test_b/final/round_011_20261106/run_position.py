"""Root integration: frozen centroid-distance CDF rules and fixed numerical evaluation."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R8 = HERE.parent / "round_008_20261106"
FROZEN_R10 = "c3943c953143a4f71335bfa8cceadac6c96b30287f40a935e41b375a429b63b8"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(output_dir):
    out = Path(output_dir).resolve()
    if HERE not in out.parents or out.exists():
        raise ValueError("A NEW output directory inside this round is required")
    out.mkdir(parents=True)
    common = load("r11_root_common", HERE.parent / "round_009_20261106" / "run_transition.py")
    sha, write_json = common.sha, common.write_json
    started = time.perf_counter()
    receipt = {"status": "starting", "experiment": "R11 one-tail self/peer distance CDF", "command": sys.argv,
               "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "stages": {}}
    try:
        available = common.available_bytes()
        receipt["ram_preflight"] = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "available_mib": available/1048576, "expected_extra_mib": 1280, "reserve_mib": 640,
            "basis": "One sequential99k canonical/position/derived frames and bounded distance CDF histories; prior R8 peak425MiB", "allowed": available >= 1920*1048576}
        write_json(out / "EXECUTION.json", receipt)
        if not receipt["ram_preflight"]["allowed"]:
            receipt.update(status="memory_deferred", exit_code=75)
            return 75
        helpers = load("r11_verified_key_merge_helpers", R8 / "run_shape.py")
        receipt["other_processes"] = helpers._processes()
        import numpy as np
        import pandas as pd
        import pyarrow.parquet as pq
        rules_path = HERE / "position_rules.py"
        inventory_dir = HERE / "inventory_outputs" / "actual_001"
        inventory_path = inventory_dir / "per_vessel.csv"
        cases_path = inventory_dir / "independent_cdf_cases.csv"
        inventory_receipt = json.loads((inventory_dir / "EXECUTION.json").read_text(encoding="utf-8-sig"))
        if inventory_receipt.get("status") != "complete":
            raise ValueError("Independent inventory not complete")
        position_path = HERE.parent / "round_010_20261106" / "probe_outputs" / "actual_001" / "position_ledger.parquet"
        if sha(position_path) != FROZEN_R10:
            raise ValueError("R10 frozen position ledger changed")
        canonical_path = HERE.parent / "round_004_20261105" / "execution_001" / "candidate_ledger.parquet"
        registry_path = HERE.parent / "round_003_20261105" / "gear_registry.csv"
        positive_paths = sorted((ROOT / "testB").glob("*/round_008_linkage_audit_20261105/devset_positives.csv"))
        if len(positive_paths) != 1:
            raise ValueError("Event source must be unique")
        positives_path = positive_paths[0]
        sources = [Path(__file__), rules_path, HERE / "independent_distance_history.py", HERE / "PROTOCOL.md", HERE / "CONTRACT.md",
                   R8 / "evaluate_shape.py", R8 / "run_shape.py", R8 / "shape_rules.py",
                   HERE.parent / "round_009_20261106" / "run_transition.py", HERE.parent / "round_002_20261105" / "data_eval.py"]
        source_hashes = {str(p): sha(p) for p in sources}
        receipt["sources_sha256"] = source_hashes
        inputs = [position_path, canonical_path, registry_path, inventory_path, cases_path,
                  inventory_dir / "summary.json", inventory_dir / "EXECUTION.json", positives_path]
        input_hashes = {str(p): sha(p) for p in inputs}
        receipt["inputs_sha256"] = input_hashes
        stage_start = time.perf_counter()
        canonical_cols = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
        canonical = pq.read_table(canonical_path, columns=canonical_cols).to_pandas()
        position = pq.read_table(position_path).to_pandas()
        frame = helpers.validate_and_merge_geometry(canonical, position)
        if len(frame) != 99677 or frame.rfid_id.nunique() != 82:
            raise ValueError("Merged input roster mismatch")
        registry = pd.read_csv(registry_path, usecols=["rfid_id", "primary_gear", "is_single_code"], dtype={"rfid_id": str})
        rules = load("r11_frozen_position_rules", rules_path)
        artifacts = rules.build_position_rules(frame, registry)
        artifacts["gear_registry"] = registry
        ledger = artifacts["ledger"]
        if len(ledger) != 99677:
            raise ValueError("Rule ledger row count changed")
        for field in ["rfid_id", "ts", "source_ordinal", "own_ref_n", "own_ref_dates", "peer_eligible_n", "nearest_distance_m"]:
            if not ledger[field].equals(frame[field]):
                raise ValueError(f"Immutable R10 input changed: {field}")
        for i in range(1, 5):
            if (ledger[f"s{i}_ok"] & ~ledger[f"s{i-1}_ok"]).any():
                raise ValueError("Stage hierarchy violation")
        counts = ledger.groupby("rfid_id", sort=True).agg(observed_n=("ts", "size"),
            raw_distance_available_n=("raw_distance_available", "sum"),
            self_distribution_eligible_n=("self_distance_history_eligible", "sum"),
            peer_distribution_eligible_n=("peer_distance_history_eligible", "sum")).astype("int64")
        independent = pd.read_csv(inventory_path, dtype={"rfid_id": str})
        if len(independent) != 82 or independent.rfid_id.duplicated().any():
            raise ValueError("Independent inventory roster mismatch")
        independent = independent.set_index("rfid_id")[list(counts.columns)].sort_index().astype("int64")
        if not counts.equals(independent):
            pd.concat({"rules": counts, "independent": independent}, axis=1).to_csv(out / "INVENTORY_MISMATCH.csv")
            raise ValueError("Distance-distribution counts disagree")
        cases = pd.read_csv(cases_path, dtype={"rfid_id": str})
        if len(cases) != 12 or cases.source_ordinal.duplicated().any():
            raise ValueError("Twelve predetermined CDF queries required")
        by_ord = ledger.set_index("source_ordinal", verify_integrity=True)
        sample_records = []
        for case in cases.itertuples(index=False):
            row = by_ord.loc[int(case.source_ordinal)]
            if row.rfid_id != case.rfid_id or int(row.ts) != int(case.ts) or not row.self_distance_history_eligible:
                raise ValueError("CDF query key or eligibility mismatch")
            for field in ["self_distance_ref_n", "self_distance_ref_dates", "peer_distance_eligible_n"]:
                if int(row[field]) != int(getattr(case, field)):
                    raise ValueError(f"CDF query reference count mismatch: {field}")
            errors = {}
            for field in ["self_distance_cdf", "peer_distance_cdf_mean"]:
                actual, expected = row[field], getattr(case, field)
                if pd.isna(actual) and pd.isna(expected):
                    errors[field] = None
                elif pd.isna(actual) or pd.isna(expected) or not np.isfinite(float(actual)) or abs(float(actual)-float(expected)) > 1e-12:
                    raise ValueError(f"CDF query discrepancy: {field}")
                else:
                    errors[field] = abs(float(actual)-float(expected))
            sample_records.append({"source_ordinal": int(case.source_ordinal), **errors})
        pd.DataFrame(sample_records).to_csv(out / "cdf_concordance.csv", index=False)
        concordance = {"all_82_counts_match": True, "scalar_cdf_queries_match": 12,
            "counts": {f: int(counts[f].sum()) for f in counts}, "verified_before_event_parse": True}
        write_json(out / "PRELABEL_CONCORDANCE.json", concordance)
        receipt["independent_concordance"] = concordance
        receipt["stages"]["read_build_validate"] = {"seconds": time.perf_counter()-stage_start,
            "rows": len(ledger), "prediction_rows": len(artifacts["predictions"])}
        artifacts["predictions"].to_csv(out / "predictions.csv", index=False)
        artifacts["pool_manifest"].to_csv(out / "pool_manifest.csv", index=False)
        ledger.to_parquet(out / "candidate_ledger.parquet", index=False)
        frozen = {name: sha(out/name) for name in ["predictions.csv", "pool_manifest.csv"]}
        receipt["frozen_before_event_parse"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "hashes": frozen}
        write_json(out / "EXECUTION.json", receipt)
        positives = pd.read_csv(positives_path, usecols=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"], dtype={"rfid_id": str})
        tier01 = positives[positives.tier <= 1]
        if (len(positives), positives.rfid_id.nunique(), len(tier01), tier01.rfid_id.nunique()) != (100, 82, 60, 55):
            raise ValueError("Evaluation cohorts changed")
        evaluator = load("r11_reused_generic_evaluation", R8 / "evaluate_shape.py")
        result = evaluator.evaluate_shape(artifacts, positives, out)
        if any(sha(out/name) != digest for name, digest in frozen.items()):
            raise ValueError("Pre-label frozen predictions/pool changed")
        receipt["frozen_post_eval_unchanged"] = True
        result["metrics"]["description"] = "R11 one-tail centroid-distance CDF, generic R8 numerical evaluator reused"
        evaluator._write_json(out / "metrics.json", result["metrics"])
        if any(sha(Path(p)) != h for p, h in source_hashes.items()) or any(sha(Path(p)) != h for p, h in input_hashes.items()):
            raise ValueError("Source/input changed during actual execution")
        receipt.update(status="complete", exit_code=0, source_and_input_hashes_unchanged=True,
            peak_working_set_bytes=helpers._peak_working_set(), operational_gate_passed=result["metrics"]["operational_gate"]["overall_passed"])
        receipt["outputs"] = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in out.iterdir() if p.is_file() and p.name != "EXECUTION.json"}
        print(json.dumps({"status": "complete", "gate": result["metrics"]["operational_gate"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        receipt.update(status="failed", exit_code=1, error=str(exc), traceback=traceback.format_exc())
        print(traceback.format_exc(), file=sys.stderr)
        return 1
    finally:
        receipt.update(elapsed_seconds=time.perf_counter()-started, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        write_json(out / "EXECUTION.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(HERE / "execution_001"))
    args = parser.parse_args()
    sys.exit(run(args.output_dir))
