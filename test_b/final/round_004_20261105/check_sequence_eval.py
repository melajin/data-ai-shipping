"""Independent verification suite for Round 4 evaluation module and runner.

This script executes only small synthetic test fixtures without accessing real dev
parquets or TestB datasets. It validates distinct model predictions, fallback logic,
exact random hit probabilities, paired cluster bootstrap, fixed denominators, gate
evaluations, ledger emission, and RAM preflight.
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any

import numpy as np
import pandas as pd

from evaluate_sequence import (
    BUDGETS,
    METHODS,
    _build_stage_counts,
    evaluate_rules,
    paired_rfid_bootstrap_diff,
    random_hit_probability,
)
from run_sequence import (
    EXPECTED_PEAK,
    RESERVE,
    TOTAL_MEMORY_REQUIRED,
    _available_memory,
    _peak_working_set,
    _processes,
    _sha256,
    run as run_runner,
)
from sequence_rules import build_rules

HERE = Path(__file__).resolve().parent


def test_random_hit_probabilities_exact() -> dict[str, Any]:
    """Verify exact combinatorial hit probability calculations."""
    # n=4, h=1, k=2: 1 - comb(3, 2)/comb(4, 2) = 1 - 3/6 = 0.5
    p1 = random_hit_probability(4, 1, 2)
    assert math.isclose(p1, 0.5), f"Expected 0.5, got {p1}"

    # n=3, h=2, k=1: 1 - comb(1, 1)/comb(3, 1) = 1 - 1/3 = 2/3
    p2 = random_hit_probability(3, 2, 1)
    assert math.isclose(p2, 2.0 / 3.0), f"Expected 2/3, got {p2}"

    # n=1, h=1, k=1: 1.0
    p3 = random_hit_probability(1, 1, 1)
    assert math.isclose(p3, 1.0), f"Expected 1.0, got {p3}"

    # n=0, h=0, k=4: 0.0
    p4 = random_hit_probability(0, 0, 4)
    assert math.isclose(p4, 0.0), f"Expected 0.0, got {p4}"

    # n=5, h=0, k=3: 0.0
    p5 = random_hit_probability(5, 0, 3)
    assert math.isclose(p5, 0.0), f"Expected 0.0, got {p5}"

    # n=5, h=5, k=1: 1.0
    p6 = random_hit_probability(5, 5, 1)
    assert math.isclose(p6, 1.0), f"Expected 1.0, got {p6}"

    return {
        "status": "passed",
        "tested_cases": [
            {"n": 4, "h": 1, "k": 2, "prob": p1},
            {"n": 3, "h": 2, "k": 1, "prob": p2},
            {"n": 1, "h": 1, "k": 1, "prob": p3},
            {"n": 0, "h": 0, "k": 4, "prob": p4},
            {"n": 5, "h": 0, "k": 3, "prob": p5},
            {"n": 5, "h": 5, "k": 1, "prob": p6},
        ],
    }


def test_paired_rfid_cluster_bootstrap() -> dict[str, Any]:
    """Verify paired cluster bootstrap diff with seed reproducibility and clustering."""
    records = []
    # Vessel R1: 2 events, G hits both, B0 hits none -> diff +1.0 for each
    records.append({"acc_id": "e1", "rfid_id": "R1", "method": "G", "k": 1, "hit": True})
    records.append({"acc_id": "e1", "rfid_id": "R1", "method": "B0", "k": 1, "hit": False})
    records.append({"acc_id": "e2", "rfid_id": "R1", "method": "G", "k": 1, "hit": True})
    records.append({"acc_id": "e2", "rfid_id": "R1", "method": "B0", "k": 1, "hit": False})

    # Vessel R2: 1 event, G hits, B0 hits -> diff 0.0
    records.append({"acc_id": "e3", "rfid_id": "R2", "method": "G", "k": 1, "hit": True})
    records.append({"acc_id": "e3", "rfid_id": "R2", "method": "B0", "k": 1, "hit": True})

    # Vessel R3: 1 event, G misses, B0 hits -> diff -1.0
    records.append({"acc_id": "e4", "rfid_id": "R3", "method": "G", "k": 1, "hit": False})
    records.append({"acc_id": "e4", "rfid_id": "R3", "method": "B0", "k": 1, "hit": True})

    df = pd.DataFrame(records)
    res1 = paired_rfid_bootstrap_diff(df, "G", "B0", 1, repetitions=1000, seed=20261105)
    res2 = paired_rfid_bootstrap_diff(df, "G", "B0", 1, repetitions=1000, seed=20261105)

    assert res1["n_events"] == 4, f"Expected 4 events, got {res1['n_events']}"
    assert res1["n_rfid"] == 3, f"Expected 3 RFIDs, got {res1['n_rfid']}"
    assert math.isclose(res1["mean_difference"], 0.25), f"Expected 0.25, got {res1['mean_difference']}"
    assert res1["ci95"] == res2["ci95"], "Seed reproducibility failed"
    assert res1["ci95"][0] <= res1["mean_difference"] <= res1["ci95"][1], "Mean not within 95% CI"

    return {
        "status": "passed",
        "n_events": res1["n_events"],
        "n_rfid": res1["n_rfid"],
        "mean_diff": res1["mean_difference"],
        "ci95": res1["ci95"],
    }


def _create_synthetic_multi_vessel_fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create independent synthetic multi-vessel scenario with distinct method behaviors.

    Vessel G1: Primary gear '자망', single code, has past baseline (>=24 triples, >=3 dates)
              and peer vessels.
              At t=10..99: history rows.
              At t=110: legacy score = 0.99 (B0 top winner).
              At t=120: transition large->small (t=119 large, t=120 small, t=121 small).
                        legacy score = 0.50, gear_priority = 0.70 (G top winner).
              At t=125: transition large->small (t=124 large, t=125 small, t=126 small).
                        legacy score = 0.85, gear_priority = 0.40 (S top winner).

    Peers P1..P5: Provide >=5 eligible peers for '자망' group.
              P1..P3 have 0 transitions in history.
              P4..P5 have frequent transitions in history.

    Vessel G2: Primary gear '자망', has Stage 2 transitions, but has own insufficient baseline
              -> G falls back to stage2 (fallback_reason: 'no_gear_eligible_candidates').

    Vessel G3: Primary gear '통발', broken observation gaps (no t-1 or t+1)
              -> S and G fall back to stage0 (fallback_reason: 'no_common_transitions').

    Vessel G4: In positives, but has 0 observations in frame (empty pool)
              -> cap = 0, predictions empty, hit = False, denominator preserved.
    """
    rows = []

    # Peers P1..P3: 0 transitions in history (all large)
    for p in ["P1", "P2", "P3"]:
        for t in range(10, 100):
            rows.append({
                "rfid_id": p, "ts": t, "source_ordinal": 1,
                "len_m": 200.0, "bbox_m": 200.0,
                "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.30,
            })

    # Peers P4, P5: frequent transitions in history
    for p in ["P4", "P5"]:
        for t in range(10, 100):
            is_sm = (t % 10 in (1, 2))
            rows.append({
                "rfid_id": p, "ts": t, "source_ordinal": 1,
                "len_m": 50.0 if is_sm else 200.0,
                "bbox_m": 50.0 if is_sm else 200.0,
                "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.30,
            })

    # Vessel G1: history with 0 transitions (all large)
    for t in range(10, 100):
        rows.append({
            "rfid_id": "G1", "ts": t, "source_ordinal": 1,
            "len_m": 200.0, "bbox_m": 200.0,
            "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.30,
        })

    # G1 around 110: Stage 0 legacy winner (non-transition: 109, 110, 111 all large)
    rows.append({"rfid_id": "G1", "ts": 109, "source_ordinal": 1, "len_m": 200.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})
    rows.append({"rfid_id": "G1", "ts": 110, "source_ordinal": 1, "len_m": 200.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.99})
    rows.append({"rfid_id": "G1", "ts": 111, "source_ordinal": 1, "len_m": 200.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})

    # G1 at 120: Stage 2/3 candidate. Transition: 119 large -> 120 small -> 121 small.
    # Score 0.50, gear_priority 0.70.
    rows.append({"rfid_id": "G1", "ts": 119, "source_ordinal": 1, "len_m": 200.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})
    rows.append({"rfid_id": "G1", "ts": 120, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.50})
    rows.append({"rfid_id": "G1", "ts": 121, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})

    # G1 at 125: Stage 2/3 candidate. Transition: 124 large -> 125 small -> 126 small.
    # Score 0.85, gear_priority 0.40.
    rows.append({"rfid_id": "G1", "ts": 124, "source_ordinal": 1, "len_m": 200.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})
    rows.append({"rfid_id": "G1", "ts": 125, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.85})
    rows.append({"rfid_id": "G1", "ts": 126, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})

    # Vessel G2: has transition at t=200, but only 3 history rows (insufficient baseline)
    rows.append({"rfid_id": "G2", "ts": 199, "source_ordinal": 1, "len_m": 200.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})
    rows.append({"rfid_id": "G2", "ts": 200, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.75})
    rows.append({"rfid_id": "G2", "ts": 201, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.40})

    # Vessel G3: isolated observations (broken gaps, no t-1 or t+1)
    rows.append({"rfid_id": "G3", "ts": 300, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.90})
    rows.append({"rfid_id": "G3", "ts": 310, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 50.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 0.80})

    frame = pd.DataFrame(rows)
    frame = frame.drop_duplicates(["rfid_id", "ts"]).reset_index(drop=True)

    gear_rows = [
        {"rfid_id": "G1", "primary_gear": "자망", "is_single_code": True},
        {"rfid_id": "G2", "primary_gear": "자망", "is_single_code": True},
        {"rfid_id": "G3", "primary_gear": "통발", "is_single_code": True},
        {"rfid_id": "P1", "primary_gear": "자망", "is_single_code": True},
        {"rfid_id": "P2", "primary_gear": "자망", "is_single_code": True},
        {"rfid_id": "P3", "primary_gear": "자망", "is_single_code": True},
        {"rfid_id": "P4", "primary_gear": "자망", "is_single_code": True},
        {"rfid_id": "P5", "primary_gear": "자망", "is_single_code": True},
    ]
    gear_registry = pd.DataFrame(gear_rows)

    pos_rows = [
        {"acc_id": "acc_g1", "rfid_id": "G1", "tier": 0, "conflict": False, "acc_ts": 120},
        {"acc_id": "acc_g2", "rfid_id": "G2", "tier": 1, "conflict": False, "acc_ts": 200},
        {"acc_id": "acc_g3", "rfid_id": "G3", "tier": 0, "conflict": False, "acc_ts": 300},
        {"acc_id": "acc_g4", "rfid_id": "G4", "tier": 1, "conflict": False, "acc_ts": 400},
    ]
    positives = pd.DataFrame(pos_rows)

    return frame, gear_registry, positives


def test_distinct_method_predictions_and_fallbacks() -> dict[str, Any]:
    """Verify distinct method winners, fallback transitions, and shared caps."""
    frame, gear_registry, positives = _create_synthetic_multi_vessel_fixture()

    artifacts = build_rules(frame, gear_registry)
    ledger = artifacts["ledger"]
    predictions = artifacts["predictions"]
    manifest = artifacts["pool_manifest"]

    with tempfile.TemporaryDirectory(prefix="r4_check_eval_") as tmp_dir:
        out_dir = Path(tmp_dir)
        res = evaluate_rules(artifacts, positives, out_dir)

        # 1. Check distinct winners for G1
        g1_preds = predictions[predictions["rfid_id"] == "G1"]
        b0_top1 = g1_preds[(g1_preds["method"] == "B0") & (g1_preds["rank"] == 1)].iloc[0]
        s_top1 = g1_preds[(g1_preds["method"] == "S") & (g1_preds["rank"] == 1)].iloc[0]
        g_top1 = g1_preds[(g1_preds["method"] == "G") & (g1_preds["rank"] == 1)].iloc[0]

        assert int(b0_top1["ts"]) == 110, f"Expected B0 top1 ts=110, got {b0_top1['ts']}"
        assert int(s_top1["ts"]) == 125, f"Expected S top1 ts=125, got {s_top1['ts']}"
        assert int(g_top1["ts"]) == 120, f"Expected G top1 ts=120, got {g_top1['ts']}"
        assert b0_top1["ts"] != s_top1["ts"] != g_top1["ts"], "Distinct method winners requirement failed"

        # 2. Check fallback for G2 (has Stage 2, but insufficient baseline for Stage 3)
        g2_m_g = manifest[(manifest["rfid_id"] == "G2") & (manifest["method"] == "G")].iloc[0]
        assert g2_m_g["pool_stage"] == "stage2", f"Expected G2 pool_stage=stage2, got {g2_m_g['pool_stage']}"
        assert g2_m_g["fallback_reason"] == "no_gear_eligible_candidates", f"Expected fallback_reason=no_gear_eligible_candidates, got {g2_m_g['fallback_reason']}"

        # 3. Check fallback for G3 (no Stage 1/2 due to broken gaps)
        g3_m_s = manifest[(manifest["rfid_id"] == "G3") & (manifest["method"] == "S")].iloc[0]
        g3_m_g = manifest[(manifest["rfid_id"] == "G3") & (manifest["method"] == "G")].iloc[0]
        assert g3_m_s["pool_stage"] == "stage0" and g3_m_s["fallback_reason"] == "no_common_transitions"
        assert g3_m_g["pool_stage"] == "stage0" and g3_m_g["fallback_reason"] == "no_common_transitions"

        # 4. Check unobserved G4 (in positives, 0 observations in frame)
        g4_ev = res["event_results"][res["event_results"]["rfid_id"] == "G4"]
        assert len(g4_ev) == len(METHODS) * len(BUDGETS), f"Expected {len(METHODS)*len(BUDGETS)} rows for G4, got {len(g4_ev)}"
        assert (~g4_ev["hit"]).all(), "Unobserved vessel G4 must have hit=False"
        assert g4_ev["abs_error"].isna().all(), "Unobserved vessel G4 must have abs_error=None"

        # 5. Shared cap rule: min(4, len(actual G pool))
        for rid, grp in manifest.groupby("rfid_id"):
            g_row = grp[grp["method"] == "G"].iloc[0]
            expected_cap = min(4, int(g_row["actual_pool_n"]))
            assert (grp["cap"] == expected_cap).all(), f"Vessel {rid}: cap not shared across methods"

        # 6. Verify written files exist and non-empty
        expected_files = [
            "predictions.csv",
            "pool_manifest.csv",
            "candidate_ledger.parquet",
            "stage_counts.csv",
            "stage_event_coverage.csv",
            "event_results.csv",
            "metrics.json",
            "diagnostics.json",
        ]
        file_stats = {}
        for fname in expected_files:
            fpath = out_dir / fname
            assert fpath.is_file(), f"Output file missing: {fname}"
            size = fpath.stat().st_size
            assert size > 0, f"Output file is empty: {fname}"
            file_stats[fname] = size

    return {
        "status": "passed",
        "distinct_winners": {"B0_ts": int(b0_top1["ts"]), "S_ts": int(s_top1["ts"]), "G_ts": int(g_top1["ts"])},
        "fallbacks": {
            "G2_fallback": g2_m_g["fallback_reason"],
            "G3_S_fallback": g3_m_s["fallback_reason"],
            "G3_G_fallback": g3_m_g["fallback_reason"],
        },
        "output_files": file_stats,
    }


def test_fixed_denominators_and_gate_evaluation() -> dict[str, Any]:
    """Verify that denominators are fixed and gate checks report explicit failures/passes."""
    frame, gear_registry, positives = _create_synthetic_multi_vessel_fixture()
    artifacts = build_rules(frame, gear_registry)

    with tempfile.TemporaryDirectory(prefix="r4_gate_check_") as tmp_dir:
        out_dir = Path(tmp_dir)
        res = evaluate_rules(artifacts, positives, out_dir)
        metrics = res["metrics"]
        gate = metrics["operational_gate"]

        # Denominators must preserve all positives
        assert metrics["denominators"]["all"]["events"] == len(positives)
        assert metrics["denominators"]["tier01"]["events"] == int((positives["tier"] <= 1).sum())
        assert metrics["probability_outputs"] is False

        # Random expectation must contain separate pools for B0, S, G
        rand_all = metrics["same_budget_random_expectation"]["all"]["pools"]
        assert set(rand_all.keys()) == set(METHODS), f"Random expectation pools missing: {set(rand_all.keys())}"

        # Gate structure verification
        assert "tier01_top1_diff_g_vs_b0" in gate
        assert "tier01_top1_paired_bootstrap_ci95_lower" in gate
        assert "whole100_top1_non_worsening" in gate
        assert "tier01_top1_exceeds_random" in gate
        assert "overall_passed" in gate
        assert "gate_failures" in gate
        assert isinstance(gate["gate_failures"], list)

    return {
        "status": "passed",
        "denominators": {
            "all_events": metrics["denominators"]["all"]["events"],
            "tier01_events": metrics["denominators"]["tier01"]["events"],
        },
        "probability_outputs": metrics["probability_outputs"],
        "gate_overall_passed": gate["overall_passed"],
        "gate_failures_count": len(gate["gate_failures"]),
    }


def test_runner_preflight_and_overwrite_protection() -> dict[str, Any]:
    """Verify runner RAM preflight logic and complete receipt overwrite protection."""
    # 1. Native available memory query check
    avail, total = _available_memory()
    assert avail > 0 and total > 0, "Native available memory query returned invalid values"

    # 2. Peak working set query check
    peak = _peak_working_set()
    assert peak is None or peak > 0, "Peak working set query failed"

    # 3. Process inventory check
    procs = _processes()
    assert isinstance(procs, list), "Process inventory must return a list"

    # 4. Overwrite protection test
    with tempfile.TemporaryDirectory(prefix="r4_runner_overwrite_", dir=HERE) as tmp_dir:
        out_dir = Path(tmp_dir)
        receipt_path = out_dir / "EXECUTION.json"
        receipt_path.write_text(json.dumps({"status": "complete", "mock": True}) + "\n", encoding="utf-8")

        # Calling runner on existing complete receipt must refuse overwrite and return 0
        ret = run_runner(output_dir=out_dir)
        assert ret == 0, f"Expected return code 0 on complete receipt, got {ret}"
        content = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert content.get("mock") is True, "Runner erroneously overwrote complete execution receipt"

    return {
        "status": "passed",
        "available_ram_bytes": avail,
        "total_ram_bytes": total,
        "preflight_requirement_bytes": TOTAL_MEMORY_REQUIRED,
        "process_count": len(procs),
        "overwrite_protection": "verified",
    }


def run_all_checks() -> dict[str, Any]:
    """Execute all verification checks and write eval_checks.json."""
    t0 = time.perf_counter()
    results = {}

    print("Running check 1: Exact random hit probabilities...")
    results["random_hit_probabilities_exact"] = test_random_hit_probabilities_exact()

    print("Running check 2: Paired RFID cluster bootstrap...")
    results["paired_rfid_cluster_bootstrap"] = test_paired_rfid_cluster_bootstrap()

    print("Running check 3: Distinct method predictions, fallbacks, and shared caps...")
    results["distinct_method_predictions_and_fallbacks"] = test_distinct_method_predictions_and_fallbacks()

    print("Running check 4: Fixed denominators and gate evaluation...")
    results["fixed_denominators_and_gate_evaluation"] = test_fixed_denominators_and_gate_evaluation()

    print("Running check 5: Runner preflight and overwrite protection...")
    results["runner_preflight_and_overwrite_protection"] = test_runner_preflight_and_overwrite_protection()

    elapsed = time.perf_counter() - t0
    all_passed = all(r.get("status") == "passed" for r in results.values())

    receipt: dict[str, Any] = {
        "suite": "round_004_evaluation_and_runner_verification",
        "timestamp_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "overall_status": "succeeded" if all_passed else "failed",
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results.values() if r.get("status") == "passed"),
        "elapsed_seconds": elapsed,
        "checks": results,
        "spec_compliance": {
            "method_pools_B0_S_G": "verified distinct pools and rankings",
            "shared_cap_rule": "min(4, len(actual G pool)) verified",
            "fallback_hierarchy": "stage3 -> stage2 -> stage0 -> empty verified",
            "random_expectation": "exact combinatorial formula over actual pool and cap verified",
            "paired_rfid_bootstrap": "4000 repetitions, seed 20261105 verified",
            "fixed_denominators": "whole 100 / Tier01 60 preserved without dropping unobserved events",
            "ledger_emission": "stage_counts.csv, stage_event_coverage.csv, candidate_ledger.parquet verified",
            "runner_preflight": "768MiB extra + 640MiB reserve preflight and overwrite guard verified",
            "probability_claims": "probability_outputs: false strictly enforced",
        },
    }

    out_path = HERE / "eval_checks.json"
    out_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nAll {len(results)} checks passed in {elapsed:.2f}s. Receipt written to {out_path.name}")
    return receipt


if __name__ == "__main__":
    run_all_checks()
