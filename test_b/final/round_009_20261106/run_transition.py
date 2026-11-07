"""Root integration: label-blind observed-transition rules and reused fixed evaluator."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R8 = HERE.parent / "round_008_20261106"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def available_bytes():
    if os.name == "nt":
        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (n, ctypes.c_ulonglong) for n in ("total", "available", "totalpage", "availablepage", "totalvirtual", "availablevirtual", "extended")]
        mem = Memory()
        mem.length = ctypes.sizeof(mem)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            raise OSError("RAM query failed")
        return int(mem.available)
    values = {line.split(":")[0]: int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()}
    return values["MemAvailable"]


def run(output_dir):
    out = Path(output_dir).resolve()
    if HERE not in out.parents or out.exists():
        raise ValueError("Output must be a NEW directory within this round")
    out.mkdir(parents=True)
    started = time.perf_counter()
    receipt = {"status": "starting", "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "command": sys.argv, "experiment": "R9 observed small-small-non-small transition", "stages": {}}
    try:
        avail = available_bytes()
        receipt["ram_preflight"] = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "available_mib": avail / 1048576, "expected_extra_mib": 1280, "reserve_mib": 640,
            "basis": "Sequential99k numeric/derived frames, bounded triplet history; R8 actual424.60MiB peak, conservative1280MiB plus640reserve", "allowed": avail >= 1920 * 1048576}
        write_json(out / "EXECUTION.json", receipt)
        if not receipt["ram_preflight"]["allowed"]:
            receipt.update(status="memory_deferred", exit_code=75)
            return 75
        helpers = load_module("r9_verified_r8_runner_helpers", R8 / "run_shape.py")
        receipt["other_processes"] = helpers._processes()
        import pandas as pd
        import pyarrow.parquet as pq
        rules_path = HERE / "transition_rules.py"
        inventory = HERE / "inventory_outputs" / "per_vessel.csv"
        inv_summary = HERE / "inventory_outputs" / "summary.json"
        canonical = HERE.parent / "round_004_20261105" / "execution_001" / "candidate_ledger.parquet"
        registry_path = HERE.parent / "round_003_20261105" / "gear_registry.csv"
        positives_paths = sorted((ROOT / "testB").glob("*/round_008_linkage_audit_20261105/devset_positives.csv"))
        if len(positives_paths) != 1:
            raise ValueError("Positive source must be unique")
        positives_path = positives_paths[0]
        sources = [Path(__file__), rules_path, HERE / "independent_inventory.py", HERE / "CONTRACT.md",
                   HERE / "PROTOCOL.md", R8 / "run_shape.py", R8 / "evaluate_shape.py",
                   HERE.parent / "round_002_20261105" / "data_eval.py"]
        source_hashes = {str(p): sha(p) for p in sources}
        receipt["sources"] = source_hashes
        receipt["inputs"] = {str(p): {"sha256": sha(p), "bytes": p.stat().st_size}
                             for p in [canonical, registry_path, inventory, inv_summary, positives_path]}
        stage_start = time.perf_counter()
        cols = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
        frame = helpers.validate_raw_keys(pq.read_table(canonical, columns=cols).to_pandas(), "canonical")
        if len(frame) != 99677 or frame.rfid_id.nunique() != 82:
            raise ValueError("Canonical roster mismatch")
        registry = pd.read_csv(registry_path, usecols=["rfid_id", "primary_gear", "is_single_code"], dtype={"rfid_id": str})
        rules = load_module("r9_frozen_transition_rules", rules_path)
        artifacts = rules.build_transition_rules(frame, registry)
        artifacts["gear_registry"] = registry
        ledger = artifacts["ledger"]
        if len(ledger) != 99677 or not ledger.source_ordinal.equals(frame.source_ordinal):
            raise ValueError("Rule ledger changed canonical rows/order")
        for i in range(1, 5):
            if (ledger[f"s{i}_ok"] & ~ledger[f"s{i-1}_ok"]).any():
                raise ValueError(f"Stage inclusion violation at s{i}")
        # Independent lower-worker count check BEFORE any event labels parsed.
        own_counts = ledger.groupby("rfid_id", sort=True).agg(valid_triple_n=("triplet_valid", "sum"), pattern_n=("pattern", "sum")).astype("int64")
        inv = pd.read_csv(inventory, dtype={"rfid_id": str})
        if inv.rfid_id.duplicated().any() or len(inv) != 82:
            raise ValueError("Independent inventory roster mismatch")
        inv = inv.set_index("rfid_id")[["valid_triple_n", "pattern_n"]].sort_index().astype("int64")
        if not own_counts.equals(inv):
            pd.concat({"rules": own_counts, "inventory": inv}, axis=1).to_csv(out / "INVENTORY_MISMATCH.csv")
            raise ValueError("Independent pattern counts disagree")
        summary = json.loads(inv_summary.read_text(encoding="utf-8-sig"))
        for field in ["valid_triple_n", "pattern_n"]:
            if int(summary[field]) != int(own_counts[field].sum()):
                raise ValueError(f"Independent summary mismatch: {field}")
        receipt["inventory_concordance"] = {"all_82_rfids_match": True,
            "valid_triple_n": int(own_counts.valid_triple_n.sum()), "pattern_n": int(own_counts.pattern_n.sum())}
        receipt["stages"]["read_build_validate"] = {"seconds": time.perf_counter()-stage_start,
            "ledger_rows": len(ledger), "prediction_rows": len(artifacts["predictions"])}
        artifacts["predictions"].to_csv(out / "predictions.csv", index=False)
        artifacts["pool_manifest"].to_csv(out / "pool_manifest.csv", index=False)
        ledger.to_parquet(out / "candidate_ledger.parquet", index=False)
        frozen = {name: sha(out / name) for name in ["predictions.csv", "pool_manifest.csv"]}
        receipt["frozen_pre_label"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "hashes": frozen}
        write_json(out / "EXECUTION.json", receipt)
        # Labels only now enter the pipeline. No new model or source extraction.
        positives = pd.read_csv(positives_path, usecols=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"], dtype={"rfid_id": str})
        tier01 = positives[positives.tier <= 1]
        if (len(positives), positives.rfid_id.nunique(), len(tier01), tier01.rfid_id.nunique()) != (100, 82, 60, 55):
            raise ValueError("Evaluation cohorts changed")
        evaluator = load_module("r9_reused_generic_r8_evaluation", R8 / "evaluate_shape.py")
        result = evaluator.evaluate_shape(artifacts, positives, out)
        for name, digest in frozen.items():
            if sha(out / name) != digest:
                raise ValueError(f"Frozen pre-label file changed: {name}")
        receipt["frozen_post_eval_unchanged"] = True
        result["metrics"]["description"] = "R9 observed transition; fixed generic R8 numerical evaluator reused without shape features"
        evaluator._write_json(out / "metrics.json", result["metrics"])
        if any(sha(Path(p)) != h for p, h in source_hashes.items()):
            raise ValueError("Source revision changed during actual execution")
        receipt["source_hashes_unchanged"] = True
        receipt["peak_working_set_bytes"] = helpers._peak_working_set()
        receipt["outputs"] = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
                              for p in out.iterdir() if p.is_file() and p.name != "EXECUTION.json"}
        receipt.update(status="complete", exit_code=0, operational_gate_passed=result["metrics"]["operational_gate"]["overall_passed"])
        print(json.dumps({"status": "complete", "gate": result["metrics"]["operational_gate"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        receipt.update(status="failed", exit_code=1, error=str(exc), traceback=traceback.format_exc())
        print(traceback.format_exc(), file=sys.stderr)
        return 1
    finally:
        receipt["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        receipt["elapsed_seconds"] = time.perf_counter()-started
        write_json(out / "EXECUTION.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(HERE / "execution_001"))
    args = parser.parse_args()
    sys.exit(run(args.output_dir))
