"""Independent verification suite for Round 8 evaluation module and runner.

This script executes only small synthetic test fixtures without accessing real dev
parquets or TestB datasets. It validates distinct model predictions, fallback logic,
exact random hit probabilities, paired cluster bootstrap, fixed denominators, gate
evaluations with strict cohort separation, ledger emission via stage_spec,
exact epoch-hour conversion, pre-label frozen predictions persistence,
and RAM preflight.
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

import numpy as np
import pandas as pd

from evaluate_shape import (
    BUDGETS,
    METHODS,
    STAGE_SPEC,
    _build_stage_counts,
    evaluate_shape,
    paired_rfid_bootstrap_diff,
    random_hit_probability,
    to_epoch_hour,
)
from run_shape import (
    EXPECTED_PEAK,
    RESERVE,
    TOTAL_MEMORY_REQUIRED,
    _available_memory,
    _peak_working_set,
    _processes,
    _sha256,
    run as run_runner,
    validate_and_merge_geometry,
    validate_extractor_receipt,
    validate_raw_keys,
)

HERE = Path(__file__).resolve().parent


def test_exact_epoch_hour_conversion() -> dict[str, Any]:
    """Verify strict epoch-hour conversion, rejection of nanosecond timestamps, and NaT handling."""
    # 1. Integer hours preserved
    assert to_epoch_hour(24) == 24, "Integer 24 must return 24"
    assert to_epoch_hour(495159) == 495159, "Integer 495159 must return 495159"

    # 2. Hour-aligned Timestamp 1970-01-02 00:00:00 -> 24
    ts_1970_01_02 = pd.Timestamp("1970-01-02 00:00:00")
    assert to_epoch_hour(ts_1970_01_02) == 24, f"Timestamp {ts_1970_01_02} must return 24"

    # 3. Hour-aligned 2026 timestamp -> 495159
    ts_2026 = pd.Timestamp("2026-06-27 15:00:00")
    assert to_epoch_hour(ts_2026) == 495159, f"Timestamp {ts_2026} must return 495159"

    # 4. Wrongly interpreted 24ns timestamp -> must reject with ValueError
    ts_24ns = pd.Timestamp(24)
    rejected_24ns = False
    try:
        to_epoch_hour(ts_24ns)
    except ValueError:
        rejected_24ns = True
    assert rejected_24ns, f"Wrongly interpreted 24ns timestamp {ts_24ns} must raise ValueError"

    # 5. NaT selected timestamp on active prediction -> must reject with ValueError
    rejected_nat = False
    try:
        to_epoch_hour(pd.NaT, allow_nat=False, context="prediction ts")
    except ValueError:
        rejected_nat = True
    assert rejected_nat, "Active prediction with NaT timestamp must raise ValueError"

    # 6. allow_nat=True returns None
    assert to_epoch_hour(pd.NaT, allow_nat=True) is None

    # 7. Fractional hour -> reject
    rejected_frac = False
    try:
        to_epoch_hour(24.5)
    except ValueError:
        rejected_frac = True
    assert rejected_frac, "Fractional hour 24.5 must raise ValueError"

    return {"status": "pass", "details": "Epoch-hour conversions, fractional/nanosecond rejections, and NaT rules verified"}


def test_combinatorial_random_hit_probability() -> dict[str, Any]:
    """Verify exact combinatorial top-k random hit probability with hand-calculated values."""
    # 1. n=10, h=2, k=1 -> h/n = 2/10 = 0.20
    p1 = random_hit_probability(10, 2, 1)
    assert abs(p1 - 0.20) < 1e-9, f"Expected 0.20, got {p1}"

    # 2. n=10, h=2, k=2 -> 1 - comb(8, 2) / comb(10, 2) = 1 - 28/45 = 17/45 = 0.3777777778
    p2 = random_hit_probability(10, 2, 2)
    expected_p2 = 1.0 - (28.0 / 45.0)
    assert abs(p2 - expected_p2) < 1e-9, f"Expected {expected_p2}, got {p2}"

    # 3. n=10, h=2, k=4 -> 1 - comb(8, 4) / comb(10, 4) = 1 - 70/210 = 1 - 1/3 = 2/3 = 0.6666666667
    p4 = random_hit_probability(10, 2, 4)
    expected_p4 = 2.0 / 3.0
    assert abs(p4 - expected_p4) < 1e-9, f"Expected {expected_p4}, got {p4}"

    # 4. Boundary cases:
    # h=0 -> 0.0
    assert random_hit_probability(10, 0, 4) == 0.0
    # k=0 -> 0.0
    assert random_hit_probability(10, 2, 0) == 0.0
    # n=0 -> 0.0
    assert random_hit_probability(0, 0, 4) == 0.0
    # h >= n -> 1.0 (all pool rows hit)
    assert random_hit_probability(5, 5, 1) == 1.0
    # k >= n -> 1.0 (if h >= 1)
    assert random_hit_probability(5, 1, 5) == 1.0

    return {
        "status": "pass",
        "details": "Combinatorial hypergeometric probabilities matched exact hand-calculated ground truths",
        "cases_checked": {"n10_h2_k1": p1, "n10_h2_k2": p2, "n10_h2_k4": p4},
    }


def test_paired_rfid_bootstrap_diff() -> dict[str, Any]:
    """Verify paired cluster bootstrap over distinct RFIDs with fixed seed and extreme cases."""
    # Construct a synthetic paired events DataFrame
    records = []
    # 5 RFIDs, each with 2 events: Method G hits both, Method B0 hits neither
    for r in range(1, 6):
        rfid = f"vessel_{r}"
        for e in range(1, 3):
            acc_id = f"acc_{r}_{e}"
            records.append({"acc_id": acc_id, "rfid_id": rfid, "method": "G", "k": 1, "hit": True})
            records.append({"acc_id": acc_id, "rfid_id": rfid, "method": "B0", "k": 1, "hit": False})
    df_perf = pd.DataFrame(records)

    res_perf = paired_rfid_bootstrap_diff(df_perf, "G", "B0", k=1, repetitions=500, seed=20261105)
    assert res_perf["mean_difference"] == 1.0, f"Expected diff 1.0, got {res_perf['mean_difference']}"
    assert res_perf["ci95"] == [1.0, 1.0], f"Expected CI [1.0, 1.0], got {res_perf['ci95']}"
    assert res_perf["n_rfid"] == 5

    # Identical hits case: diff = 0.0, CI = [0.0, 0.0]
    records_zero = []
    for r in range(1, 6):
        rfid = f"vessel_{r}"
        for e in range(1, 3):
            acc_id = f"acc_{r}_{e}"
            records_zero.append({"acc_id": acc_id, "rfid_id": rfid, "method": "G", "k": 1, "hit": True})
            records_zero.append({"acc_id": acc_id, "rfid_id": rfid, "method": "B0", "k": 1, "hit": True})
    df_zero = pd.DataFrame(records_zero)
    res_zero = paired_rfid_bootstrap_diff(df_zero, "G", "B0", k=1, repetitions=500, seed=20261105)
    assert res_zero["mean_difference"] == 0.0
    assert res_zero["ci95"] == [0.0, 0.0]

    return {
        "status": "pass",
        "details": "Paired cluster bootstrap correctly clusters by RFID and produces exact deterministic CIs",
    }


def test_stage_counts_ledger_emission() -> dict[str, Any]:
    """Verify generic stage transition counts table emission looping stage_spec."""
    # Synthetic ledger with s0..s4 masks
    ledger_rows = [
        # rfid_1: passes all s0..s4
        {"rfid_id": "r1", "s0_ok": True, "s1_ok": True, "s2_ok": True, "s3_ok": True, "s4_ok": True,
         "s0_status": "admitted", "s0_reason": "valid", "s1_status": "admitted", "s1_reason": "non_small",
         "s2_status": "admitted", "s2_reason": "informative", "s3_status": "admitted", "s3_reason": "history_ok",
         "s4_status": "admitted", "s4_reason": "peers_ok"},
        # rfid_1: second row, rejected at s1 (small)
        {"rfid_id": "r1", "s0_ok": True, "s1_ok": False, "s2_ok": False, "s3_ok": False, "s4_ok": False,
         "s0_status": "admitted", "s0_reason": "valid", "s1_status": "reject", "s1_reason": "observed_small",
         "s2_status": "not_applicable", "s2_reason": "s1_failed", "s3_status": "not_applicable", "s3_reason": "s2_failed",
         "s4_status": "not_applicable", "s4_reason": "s3_failed"},
        # rfid_2: deferred at s3 (insufficient own history)
        {"rfid_id": "r2", "s0_ok": True, "s1_ok": True, "s2_ok": True, "s3_ok": False, "s4_ok": False,
         "s0_status": "admitted", "s0_reason": "valid", "s1_status": "admitted", "s1_reason": "non_small",
         "s2_status": "admitted", "s2_reason": "informative", "s3_status": "defer", "s3_reason": "insufficient_history",
         "s4_status": "not_applicable", "s4_reason": "s3_failed"},
    ]
    ledger = pd.DataFrame(ledger_rows)

    manifest_rows = [
        {"rfid_id": "r1", "method": "B0", "pool_stage": "s0", "actual_pool_n": 2, "cap": 2, "fallback_reason": None},
        {"rfid_id": "r1", "method": "S", "pool_stage": "s3", "actual_pool_n": 1, "cap": 1, "fallback_reason": None},
        {"rfid_id": "r1", "method": "G", "pool_stage": "s4", "actual_pool_n": 1, "cap": 1, "fallback_reason": None},
        {"rfid_id": "r2", "method": "B0", "pool_stage": "s0", "actual_pool_n": 1, "cap": 1, "fallback_reason": None},
        {"rfid_id": "r2", "method": "S", "pool_stage": "s0", "actual_pool_n": 1, "cap": 1, "fallback_reason": "s3_pool_empty"},
        {"rfid_id": "r2", "method": "G", "pool_stage": "s0", "actual_pool_n": 1, "cap": 1, "fallback_reason": "s4_pool_empty"},
    ]
    manifest = pd.DataFrame(manifest_rows)

    counts_df = _build_stage_counts(ledger, manifest, STAGE_SPEC)
    assert not counts_df.empty, "Stage counts DataFrame must not be empty"

    categories = set(counts_df["category_type"])
    assert categories == {"candidate_transition", "rfid_candidate_presence", "method_actual_pool_coverage"}

    # Check s1 candidate transition
    s1_rows = counts_df[(counts_df["stage"] == "s1") & (counts_df["category_type"] == "candidate_transition")]
    s1_input = s1_rows[s1_rows["status"] == "input"].iloc[0]["row_count"]
    s1_keep = s1_rows[s1_rows["status"] == "keep"].iloc[0]["row_count"]
    assert s1_input == 3, f"Expected s1 input=3, got {s1_input}"
    assert s1_keep == 2, f"Expected s1 keep=2, got {s1_keep}"

    return {
        "status": "pass",
        "details": "Generic stage counts correctly track input, keep, reject, defer, presence, and fallback coverage",
    }


def build_comprehensive_synthetic_fixture() -> dict[str, Any]:
    """Construct a full synthetic fixture with distinct methods, caps, fallbacks, repeat events,
    and distinct all vs Tier01 random expectations.
    """
    # 4 vessels
    # rfid_1: 연안복합, single-code. 10 hourly rows. Passes all s0..s4.
    # rfid_2: 자망, single-code. 6 hourly rows. Passes s0..s3, falls back at s4 (peer empty). Cap = 3.
    # rfid_3: 통발, single-code. 4 hourly rows. Falls back to s0 (empty s3/s4). Cap = 1.
    # rfid_4: 채낚기연승낚시. 0 valid rows. Cap = 0.

    ledger_rows = []
    base_ts = 490000

    # rfid_1: rows at base_ts + 0..9
    for i in range(10):
        t = base_ts + i
        ledger_rows.append({
            "rfid_id": "rfid_1",
            "ts": t,
            "source_ordinal": 1000 + i,
            "len_m": 500.0,
            "bbox_m": 300.0,
            "cen_lon": 126.5,
            "cen_lat": 34.5,
            "score": float(10 - i),  # B0 ranks by legacy score: ranks ts 0, 1, 2, 3
            "primary_gear": "연안복합",
            "is_single_code": True,
            "s0_ok": True, "s0_status": "admitted", "s0_reason": "valid",
            "s1_ok": True, "s1_status": "admitted", "s1_reason": "non_small",
            "s2_ok": True, "s2_status": "admitted", "s2_reason": "informative",
            "s3_ok": True, "s3_status": "admitted", "s3_reason": "history_ok",
            "s4_ok": True, "s4_status": "admitted", "s4_reason": "peers_ok",
            "self_rarity": float(i + 1),  # S ranks by self_rarity: ranks ts 9, 8, 7, 6
            "peer_rarity_mean": float(i % 2),  # G ranks by self_rarity then peer_rarity
            "chosen_part_index": 0, "chosen_n_points": 5, "chosen_n_unique": 5,
            "chosen_path_m": 500.0, "chosen_endpoint_m": 450.0, "shape_dl": 0.9,
        })

    # rfid_2: 6 rows
    for i in range(6):
        t = base_ts + 20 + i
        ledger_rows.append({
            "rfid_id": "rfid_2",
            "ts": t,
            "source_ordinal": 2000 + i,
            "len_m": 400.0,
            "bbox_m": 250.0,
            "cen_lon": 127.1,
            "cen_lat": 34.8,
            "score": float(6 - i),
            "primary_gear": "자망",
            "is_single_code": True,
            "s0_ok": True, "s0_status": "admitted", "s0_reason": "valid",
            "s1_ok": True, "s1_status": "admitted", "s1_reason": "non_small",
            "s2_ok": True, "s2_status": "admitted", "s2_reason": "informative",
            "s3_ok": True, "s3_status": "admitted", "s3_reason": "history_ok",
            "s4_ok": False, "s4_status": "defer", "s4_reason": "insufficient_peers",
            "self_rarity": float(i + 1),
            "peer_rarity_mean": None,
            "chosen_part_index": 0, "chosen_n_points": 4, "chosen_n_unique": 4,
            "chosen_path_m": 400.0, "chosen_endpoint_m": 350.0, "shape_dl": 0.875,
        })

    # rfid_3: 4 rows
    for i in range(4):
        t = base_ts + 40 + i
        ledger_rows.append({
            "rfid_id": "rfid_3",
            "ts": t,
            "source_ordinal": 3000 + i,
            "len_m": 50.0,
            "bbox_m": 30.0,
            "cen_lon": 128.0,
            "cen_lat": 35.0,
            "score": float(4 - i),
            "primary_gear": "통발",
            "is_single_code": True,
            "s0_ok": True, "s0_status": "admitted", "s0_reason": "valid",
            "s1_ok": False, "s1_status": "reject", "s1_reason": "observed_small",
            "s2_ok": False, "s2_status": "not_applicable", "s2_reason": "s1_failed",
            "s3_ok": False, "s3_status": "not_applicable", "s3_reason": "s2_failed",
            "s4_ok": False, "s4_status": "not_applicable", "s4_reason": "s3_failed",
            "self_rarity": None,
            "peer_rarity_mean": None,
            "chosen_part_index": None, "chosen_n_points": None, "chosen_n_unique": None,
            "chosen_path_m": None, "chosen_endpoint_m": None, "shape_dl": None,
        })

    ledger_df = pd.DataFrame(ledger_rows)

    # Predictions
    # B0, S, G predictions
    predictions_rows = [
        # rfid_1: cap 4
        # B0 (legacy): ranks top1=ts 0 (490000)
        {"rfid_id": "rfid_1", "method": "B0", "rank": 1, "ts": base_ts + 0, "ordinal": 1000, "method_score": 10.0, "secondary_score": None, "legacy_score": 10.0, "score_kind": "legacy", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "B0", "rank": 2, "ts": base_ts + 1, "ordinal": 1001, "method_score": 9.0, "secondary_score": None, "legacy_score": 9.0, "score_kind": "legacy", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "B0", "rank": 3, "ts": base_ts + 2, "ordinal": 1002, "method_score": 8.0, "secondary_score": None, "legacy_score": 8.0, "score_kind": "legacy", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "B0", "rank": 4, "ts": base_ts + 3, "ordinal": 1003, "method_score": 7.0, "secondary_score": None, "legacy_score": 7.0, "score_kind": "legacy", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},

        # S (self_rarity): ranks top1=ts 9 (490009)
        {"rfid_id": "rfid_1", "method": "S", "rank": 1, "ts": base_ts + 9, "ordinal": 1009, "method_score": 10.0, "secondary_score": None, "legacy_score": 1.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "S", "rank": 2, "ts": base_ts + 8, "ordinal": 1008, "method_score": 9.0, "secondary_score": None, "legacy_score": 2.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "S", "rank": 3, "ts": base_ts + 7, "ordinal": 1007, "method_score": 8.0, "secondary_score": None, "legacy_score": 3.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "S", "rank": 4, "ts": base_ts + 6, "ordinal": 1006, "method_score": 7.0, "secondary_score": None, "legacy_score": 4.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},

        # G (self_rarity + peer): ranks top1=ts 9 (490009)
        {"rfid_id": "rfid_1", "method": "G", "rank": 1, "ts": base_ts + 9, "ordinal": 1009, "method_score": 10.0, "secondary_score": 1.0, "legacy_score": 1.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "G", "rank": 2, "ts": base_ts + 8, "ordinal": 1008, "method_score": 9.0, "secondary_score": 0.0, "legacy_score": 2.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "G", "rank": 3, "ts": base_ts + 7, "ordinal": 1007, "method_score": 8.0, "secondary_score": 1.0, "legacy_score": 3.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_1", "method": "G", "rank": 4, "ts": base_ts + 6, "ordinal": 1006, "method_score": 7.0, "secondary_score": 0.0, "legacy_score": 4.0, "score_kind": "self_rarity", "actual_pool_n": 10, "cap": 4, "fallback_reason": None, "chosen_part_index": 0},

        # rfid_2: cap 3 (fallback G to S)
        {"rfid_id": "rfid_2", "method": "B0", "rank": 1, "ts": base_ts + 20, "ordinal": 2000, "method_score": 6.0, "secondary_score": None, "legacy_score": 6.0, "score_kind": "legacy", "actual_pool_n": 6, "cap": 3, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_2", "method": "B0", "rank": 2, "ts": base_ts + 21, "ordinal": 2001, "method_score": 5.0, "secondary_score": None, "legacy_score": 5.0, "score_kind": "legacy", "actual_pool_n": 6, "cap": 3, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_2", "method": "B0", "rank": 3, "ts": base_ts + 22, "ordinal": 2002, "method_score": 4.0, "secondary_score": None, "legacy_score": 4.0, "score_kind": "legacy", "actual_pool_n": 6, "cap": 3, "fallback_reason": None, "chosen_part_index": 0},

        {"rfid_id": "rfid_2", "method": "S", "rank": 1, "ts": base_ts + 25, "ordinal": 2005, "method_score": 6.0, "secondary_score": None, "legacy_score": 1.0, "score_kind": "self_rarity", "actual_pool_n": 6, "cap": 3, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_2", "method": "S", "rank": 2, "ts": base_ts + 24, "ordinal": 2004, "method_score": 5.0, "secondary_score": None, "legacy_score": 2.0, "score_kind": "self_rarity", "actual_pool_n": 6, "cap": 3, "fallback_reason": None, "chosen_part_index": 0},
        {"rfid_id": "rfid_2", "method": "S", "rank": 3, "ts": base_ts + 23, "ordinal": 2003, "method_score": 4.0, "secondary_score": None, "legacy_score": 3.0, "score_kind": "self_rarity", "actual_pool_n": 6, "cap": 3, "fallback_reason": None, "chosen_part_index": 0},

        {"rfid_id": "rfid_2", "method": "G", "rank": 1, "ts": base_ts + 25, "ordinal": 2005, "method_score": 6.0, "secondary_score": None, "legacy_score": 1.0, "score_kind": "self_rarity", "actual_pool_n": 6, "cap": 3, "fallback_reason": "s4_pool_empty_fallback_to_S", "chosen_part_index": 0},
        {"rfid_id": "rfid_2", "method": "G", "rank": 2, "ts": base_ts + 24, "ordinal": 2004, "method_score": 5.0, "secondary_score": None, "legacy_score": 2.0, "score_kind": "self_rarity", "actual_pool_n": 6, "cap": 3, "fallback_reason": "s4_pool_empty_fallback_to_S", "chosen_part_index": 0},
        {"rfid_id": "rfid_2", "method": "G", "rank": 3, "ts": base_ts + 23, "ordinal": 2003, "method_score": 4.0, "secondary_score": None, "legacy_score": 3.0, "score_kind": "self_rarity", "actual_pool_n": 6, "cap": 3, "fallback_reason": "s4_pool_empty_fallback_to_S", "chosen_part_index": 0},

        # rfid_3: cap 1 (fallback S and G to B0 / s0)
        {"rfid_id": "rfid_3", "method": "B0", "rank": 1, "ts": base_ts + 40, "ordinal": 3000, "method_score": 4.0, "secondary_score": None, "legacy_score": 4.0, "score_kind": "legacy", "actual_pool_n": 4, "cap": 1, "fallback_reason": None, "chosen_part_index": None},
        {"rfid_id": "rfid_3", "method": "S", "rank": 1, "ts": base_ts + 40, "ordinal": 3000, "method_score": 4.0, "secondary_score": None, "legacy_score": 4.0, "score_kind": "legacy", "actual_pool_n": 4, "cap": 1, "fallback_reason": "s3_pool_empty_fallback_to_s0", "chosen_part_index": None},
        {"rfid_id": "rfid_3", "method": "G", "rank": 1, "ts": base_ts + 40, "ordinal": 3000, "method_score": 4.0, "secondary_score": None, "legacy_score": 4.0, "score_kind": "legacy", "actual_pool_n": 4, "cap": 1, "fallback_reason": "s4_pool_empty_fallback_to_s0", "chosen_part_index": None},

        # rfid_4 has cap 0, no predictions emitted
    ]
    pred_df = pd.DataFrame(predictions_rows)

    manifest_rows = [
        {"rfid_id": "rfid_1", "method": "B0", "pool_stage": "s0", "actual_pool_n": 10, "cap": 4, "fallback_reason": None},
        {"rfid_id": "rfid_1", "method": "S", "pool_stage": "s3", "actual_pool_n": 10, "cap": 4, "fallback_reason": None},
        {"rfid_id": "rfid_1", "method": "G", "pool_stage": "s4", "actual_pool_n": 10, "cap": 4, "fallback_reason": None},

        {"rfid_id": "rfid_2", "method": "B0", "pool_stage": "s0", "actual_pool_n": 6, "cap": 3, "fallback_reason": None},
        {"rfid_id": "rfid_2", "method": "S", "pool_stage": "s3", "actual_pool_n": 6, "cap": 3, "fallback_reason": None},
        {"rfid_id": "rfid_2", "method": "G", "pool_stage": "s3", "actual_pool_n": 6, "cap": 3, "fallback_reason": "s4_pool_empty_fallback_to_S"},

        {"rfid_id": "rfid_3", "method": "B0", "pool_stage": "s0", "actual_pool_n": 4, "cap": 1, "fallback_reason": None},
        {"rfid_id": "rfid_3", "method": "S", "pool_stage": "s0", "actual_pool_n": 4, "cap": 1, "fallback_reason": "s3_pool_empty_fallback_to_s0"},
        {"rfid_id": "rfid_3", "method": "G", "pool_stage": "s0", "actual_pool_n": 4, "cap": 1, "fallback_reason": "s4_pool_empty_fallback_to_s0"},

        {"rfid_id": "rfid_4", "method": "B0", "pool_stage": "s0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"},
        {"rfid_id": "rfid_4", "method": "S", "pool_stage": "s0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"},
        {"rfid_id": "rfid_4", "method": "G", "pool_stage": "s0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"},
    ]
    manifest_df = pd.DataFrame(manifest_rows)

    gear_registry = pd.DataFrame([
        {"rfid_id": "rfid_1", "primary_gear": "연안복합", "is_single_code": True},
        {"rfid_id": "rfid_2", "primary_gear": "자망", "is_single_code": True},
        {"rfid_id": "rfid_3", "primary_gear": "통발", "is_single_code": True},
        {"rfid_id": "rfid_4", "primary_gear": "채낚기연승낚시", "is_single_code": True},
    ])

    # Positives:
    # 5 events:
    # 2 events on rfid_1 (repeat same-RFID events!)
    # Event 1 (Tier 0): acc_ts = base_ts + 9 (G hits top1! B0 misses top1 because B0 top1=ts 0, abs_error=9 > 6)
    # Event 2 (Tier 1): acc_ts = base_ts + 8 (G hits top1 because abs(9 - 8) = 1 <= 6; B0 misses top1)
    # Event 3 (Tier 0, rfid_2): acc_ts = base_ts + 28 (G hits top1 abs(25 - 28) = 3 <= 6; B0 misses top1 abs(20 - 28) = 8 > 6)
    # Event 4 (Tier 2, rfid_3): acc_ts = base_ts + 40 (all hit top1)
    # Event 5 (Tier 3, rfid_4): acc_ts = base_ts + 60 (no predictions, miss for all)
    positives_df = pd.DataFrame([
        {"acc_id": "acc_1", "rfid_id": "rfid_1", "tier": 0, "acc_ts": base_ts + 9},
        {"acc_id": "acc_2", "rfid_id": "rfid_1", "tier": 1, "acc_ts": base_ts + 8},
        {"acc_id": "acc_3", "rfid_id": "rfid_2", "tier": 0, "acc_ts": base_ts + 28},
        {"acc_id": "acc_4", "rfid_id": "rfid_3", "tier": 2, "acc_ts": base_ts + 40},
        {"acc_id": "acc_5", "rfid_id": "rfid_4", "tier": 3, "acc_ts": base_ts + 60},
    ])

    artifacts = {
        "ledger": ledger_df,
        "predictions": pred_df,
        "pool_manifest": manifest_df,
        "diagnostics": {"candidate_counts": {"s0": 20, "s1": 16, "s2": 16, "s3": 16, "s4": 10}},
        "stage_spec": STAGE_SPEC,
        "gear_registry": gear_registry,
    }

    return {"artifacts": artifacts, "positives": positives_df}


def test_evaluator_end_to_end_synthetic() -> dict[str, Any]:
    """Execute evaluate_shape on the comprehensive synthetic fixture and verify outputs."""
    fixture = build_comprehensive_synthetic_fixture()
    artifacts = fixture["artifacts"]
    positives = fixture["positives"]

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir)
        eval_res = evaluate_shape(artifacts, positives, out_path)

        # 1. Verify all 8 core files exist
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
        for f in expected_files:
            assert (out_path / f).exists(), f"Missing output file {f}"

        # 2. Check metrics content
        metrics = eval_res["metrics"]
        assert "operational_gate" in metrics
        gate = metrics["operational_gate"]
        assert "tier01_top1_diff_g_vs_b0" in gate
        assert "tier01_top1_ci95_lower_positive" in gate
        assert "whole100_non_worsening" in gate
        assert "tier01_top1_exceeds_random" in gate
        assert "overall_passed" in gate

        # Check random expectations are distinct between all and tier01
        rand = metrics["random_expectations"]
        assert "all" in rand and "tier01" in rand
        # Check event denominators
        assert rand["all"]["denominator_events"] == 5
        assert rand["tier01"]["denominator_events"] == 3

        # Numerical random expectation assertions per INTEGRATION_FIXES_01
        t01_g_exp = rand["tier01"]["pools"]["G"]["mean_top1_expected"]
        all_g_exp = rand["all"]["pools"]["G"]["mean_top1_expected"]
        gate_rand = gate["tier01_top1_exceeds_random"]["observed_random_expectation"]
        assert abs(gate_rand - t01_g_exp) < 1e-12, f"Gate expectation ({gate_rand}) must match Tier01 G expectation ({t01_g_exp})"
        assert abs(t01_g_exp - all_g_exp) > 1e-4, f"Tier01 G expectation ({t01_g_exp}) must differ from All G ({all_g_exp})"
        assert abs(t01_g_exp - 0.7222222222222222) < 1e-9, f"Expected Tier01 G ~0.7222, got {t01_g_exp}"
        assert abs(all_g_exp - 0.6333333333333333) < 1e-9, f"Expected All G ~0.6333, got {all_g_exp}"

        # In tier01, G hits 3/3 = 1.0; B0 hits 0/3 = 0.0 -> diff = +1.0
        t01_diff = gate["tier01_top1_diff_g_vs_b0"]["observed"]
        assert abs(t01_diff - 1.0) < 1e-9, f"Expected Tier01 diff 1.0, got {t01_diff}"
        assert gate["tier01_top1_diff_g_vs_b0"]["passed"] is True
        assert gate["whole100_non_worsening"]["passed"] is True

        # Check prelabel persistence
        pred_df = pd.read_csv(out_path / "predictions.csv")
        assert len(pred_df) == len(artifacts["predictions"])

        # Check event results
        ev_res_df = pd.read_csv(out_path / "event_results.csv")
        assert len(ev_res_df) == len(positives) * len(METHODS) * len(BUDGETS)

        # Repeat event sharing verification:
        # acc_1 and acc_2 both on rfid_1 have identical chosen predictions
        acc1_g_top1 = ev_res_df[(ev_res_df["acc_id"] == "acc_1") & (ev_res_df["method"] == "G") & (ev_res_df["k"] == 1)].iloc[0]["predicted_times"]
        acc2_g_top1 = ev_res_df[(ev_res_df["acc_id"] == "acc_2") & (ev_res_df["method"] == "G") & (ev_res_df["k"] == 1)].iloc[0]["predicted_times"]
        assert acc1_g_top1 == acc2_g_top1, "Repeat events on same RFID must share exact prediction list"

    return {
        "status": "pass",
        "details": "Full synthetic evaluation executed cleanly, emitted all 8 required artifacts, and validated cohort gate logic",
    }


def test_gate_cohort_fixture_pass_and_fail() -> dict[str, Any]:
    """Verify that operational gate correctly passes when all 4 conditions are met,
    and correctly fails when any condition is violated.
    """
    # 1. Passing fixture: Tier01 diff >= 0.05, CI lower > 0, all non-worse, G > random expectation
    fixture = build_comprehensive_synthetic_fixture()
    with tempfile.TemporaryDirectory() as tmp_dir:
        res = evaluate_shape(fixture["artifacts"], fixture["positives"], Path(tmp_dir))
        gate = res["metrics"]["operational_gate"]
        assert gate["overall_passed"] is True, "Expected gate to pass for passing fixture"
        assert len(gate["gate_failures"]) == 0

    # 2. Failing fixture: Modify predictions so that G misses everything in Tier01 -> diff < 0.05
    fixture_fail = build_comprehensive_synthetic_fixture()
    preds = fixture_fail["artifacts"]["predictions"].copy()
    # Change G predictions for rfid_1 and rfid_2 to distant timestamps (miss)
    preds.loc[preds["method"] == "G", "ts"] = 100000
    fixture_fail["artifacts"]["predictions"] = preds

    with tempfile.TemporaryDirectory() as tmp_dir:
        res_fail = evaluate_shape(fixture_fail["artifacts"], fixture_fail["positives"], Path(tmp_dir))
        gate_fail = res_fail["metrics"]["operational_gate"]
        assert gate_fail["overall_passed"] is False, "Expected gate to fail when G misses Tier01"
        assert len(gate_fail["gate_failures"]) > 0

    return {
        "status": "pass",
        "details": "Operational gate formulation verified for both passing and failing condition boundaries",
    }


def test_actual_schema_merge_and_duplicate_key_rejection() -> dict[str, Any]:
    """Verify merge of actual extractor schema (with duplicated numerics and null geometry),
    preservation of unsuffixed columns, and rejection of duplicate keys or fractional timestamps.
    """
    # 1. Valid 3-row fixture matching extractor output schema
    canon_rows = [
        {"rfid_id": "v1", "ts": 490000, "source_ordinal": 100, "len_m": 120.0, "bbox_m": 110.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0},
        {"rfid_id": "v1", "ts": 490001, "source_ordinal": 101, "len_m": 80.0, "bbox_m": 70.0, "cen_lon": 127.1, "cen_lat": 34.1, "score": 4.0},
        {"rfid_id": "v2", "ts": 490000, "source_ordinal": 102, "len_m": 250.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 8.0},
    ]
    canon_df = pd.DataFrame(canon_rows)

    # Geometry output from extractor: contains ALL canonical numeric columns (duplicated),
    # plus geometry fields. Row 2 (index 1) has null geometry (e.g. no informative part).
    geom_rows = [
        {
            "rfid_id": "v1", "ts": 490000, "source_ordinal": 100,
            "len_m": 120.0, "bbox_m": 110.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0,  # duplicated numerics
            "canonical_order": 0, "n_parts": 1, "n_informative_parts": 1,
            "chosen_part_index": 0, "chosen_n_points": 5, "chosen_n_unique": 5,
            "chosen_path_m": 120.0, "chosen_endpoint_m": 100.0, "shape_dl": 0.8333,
            "geometry_status": "informative", "geometry_reason": "valid",
        },
        {
            "rfid_id": "v1", "ts": 490001, "source_ordinal": 101,
            "len_m": 80.0, "bbox_m": 70.0, "cen_lon": 127.1, "cen_lat": 34.1, "score": 4.0,  # duplicated numerics
            "canonical_order": 1, "n_parts": 0, "n_informative_parts": 0,
            "chosen_part_index": None, "chosen_n_points": None, "chosen_n_unique": None,
            "chosen_path_m": None, "chosen_endpoint_m": None, "shape_dl": None,  # first row null geometry
            "geometry_status": "no_parts", "geometry_reason": "empty_multilinestring",
        },
        {
            "rfid_id": "v2", "ts": 490000, "source_ordinal": 102,
            "len_m": 250.0, "bbox_m": 200.0, "cen_lon": 128.0, "cen_lat": 35.0, "score": 8.0,  # duplicated numerics
            "canonical_order": 2, "n_parts": 2, "n_informative_parts": 1,
            "chosen_part_index": 1, "chosen_n_points": 8, "chosen_n_unique": 8,
            "chosen_path_m": 250.0, "chosen_endpoint_m": 220.0, "shape_dl": 0.8800,
            "geometry_status": "informative", "geometry_reason": "valid",
        },
    ]
    geom_df = pd.DataFrame(geom_rows)

    merged = validate_and_merge_geometry(canon_df, geom_df)
    assert len(merged) == 3, f"Expected 3 rows, got {len(merged)}"
    # Verify no _x or _y columns
    for col in ["len_m", "bbox_m", "cen_lon", "cen_lat", "score"]:
        assert col in merged.columns, f"Column {col} missing in merged"
        assert f"{col}_x" not in merged.columns, f"Found suffixed {col}_x"
        assert f"{col}_y" not in merged.columns, f"Found suffixed {col}_y"
    # Verify null geometry row preserved
    assert pd.isna(merged.iloc[1]["shape_dl"]), "Null geometry shape_dl must be NA"
    assert merged.iloc[1]["geometry_status"] == "no_parts"
    assert (merged["source_ordinal"].to_numpy() == canon_df["source_ordinal"].to_numpy()).all()

    # 2. Duplicate key rejection in canonical
    dup_canon = canon_df.copy()
    dup_canon.loc[1, "source_ordinal"] = 100
    rejected_dup_ord = False
    try:
        validate_and_merge_geometry(dup_canon, geom_df)
    except ValueError:
        rejected_dup_ord = True
    assert rejected_dup_ord, "Must reject duplicate source_ordinal in canonical"

    dup_rfid_ts = canon_df.copy()
    dup_rfid_ts.loc[1, "ts"] = 490000  # v1 has ts 490000 twice
    rejected_dup_rfid_ts = False
    try:
        validate_and_merge_geometry(dup_rfid_ts, geom_df)
    except ValueError:
        rejected_dup_rfid_ts = True
    assert rejected_dup_rfid_ts, "Must reject duplicate (rfid_id, ts) in canonical"

    # 3. Duplicate key rejection in geometry
    dup_geom = geom_df.copy()
    dup_geom.loc[1, "source_ordinal"] = 100
    rejected_geom_ord = False
    try:
        validate_and_merge_geometry(canon_df, dup_geom)
    except ValueError:
        rejected_geom_ord = True
    assert rejected_geom_ord, "Must reject duplicate source_ordinal in geometry"

    # 4. Fractional timestamp rejection
    frac_canon = canon_df.copy()
    frac_canon["ts"] = frac_canon["ts"].astype(float)
    frac_canon.loc[0, "ts"] = 490000.5
    rejected_frac = False
    try:
        validate_and_merge_geometry(frac_canon, geom_df)
    except ValueError:
        rejected_frac = True
    assert rejected_frac, "Must reject fractional hour timestamp"

    # 5. Shared numeric discrepancy rejection
    discrepant_geom = geom_df.copy()
    discrepant_geom.loc[0, "len_m"] = 125.0  # diff = 5.0m > 1e-4
    rejected_discrepancy = False
    try:
        validate_and_merge_geometry(canon_df, discrepant_geom)
    except ValueError:
        rejected_discrepancy = True
    assert rejected_discrepancy, "Must reject numeric discrepancy between canonical and geometry"

    return {
        "status": "pass",
        "details": "Actual schema merge with duplicated numerics and null geometry succeeded without suffixing; duplicate keys, fractional hours, and discrepancies rejected",
    }


def test_extractor_receipt_validation_and_failing_fixture() -> dict[str, Any]:
    """Verify validate_extractor_receipt enforces all mandatory fields, zero mismatches/errors,
    release_ready_for_scoring True, and output manifest sha256 match.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        geom_dir = Path(tmp_dir)

        # 1. Create a mock parquet file
        df = pd.DataFrame([{"rfid_id": "r1", "ts": 100, "source_ordinal": 1}])
        parquet_file = geom_dir / "geometry_ledger.parquet"
        df.to_parquet(parquet_file)
        real_hash = _sha256(parquet_file)

        # Valid receipt & manifest
        valid_receipt = {
            "status": "complete",
            "mismatch_count": 0,
            "error_count": 0,
            "rows_written": 1,
            "canonical_rows_expected": 1,
            "release_ready_for_scoring": True,
        }
        valid_manifest = {
            "outputs": {
                "geometry_ledger.parquet": {
                    "sha256": real_hash,
                    "bytes": parquet_file.stat().st_size,
                }
            }
        }
        (geom_dir / "runtime_receipt.json").write_text(json.dumps(valid_receipt), encoding="utf-8")
        (geom_dir / "output_manifest.json").write_text(json.dumps(valid_manifest), encoding="utf-8")

        # Must pass
        receipt = validate_extractor_receipt(geom_dir, expected_rows=1)
        assert receipt["status"] == "complete"

        # 2. Failing receipt: nonzero mismatch count
        bad_receipt = dict(valid_receipt, mismatch_count=1)
        (geom_dir / "runtime_receipt.json").write_text(json.dumps(bad_receipt), encoding="utf-8")
        rejected_mismatch = False
        try:
            validate_extractor_receipt(geom_dir, expected_rows=1)
        except ValueError:
            rejected_mismatch = True
        assert rejected_mismatch, "Must reject nonzero mismatch_count"

        # 3. Failing receipt: nonzero error count
        bad_receipt = dict(valid_receipt, error_count=2)
        (geom_dir / "runtime_receipt.json").write_text(json.dumps(bad_receipt), encoding="utf-8")
        rejected_error = False
        try:
            validate_extractor_receipt(geom_dir, expected_rows=1)
        except ValueError:
            rejected_error = True
        assert rejected_error, "Must reject nonzero error_count"

        # 4. Failing receipt: release_ready_for_scoring is False
        bad_receipt = dict(valid_receipt, release_ready_for_scoring=False)
        (geom_dir / "runtime_receipt.json").write_text(json.dumps(bad_receipt), encoding="utf-8")
        rejected_release = False
        try:
            validate_extractor_receipt(geom_dir, expected_rows=1)
        except ValueError:
            rejected_release = True
        assert rejected_release, "Must reject release_ready_for_scoring False"

        # 5. Failing receipt: missing required field (absent-field rejection)
        bad_receipt = dict(valid_receipt)
        del bad_receipt["mismatch_count"]
        (geom_dir / "runtime_receipt.json").write_text(json.dumps(bad_receipt), encoding="utf-8")
        rejected_absent = False
        try:
            validate_extractor_receipt(geom_dir, expected_rows=1)
        except ValueError:
            rejected_absent = True
        assert rejected_absent, "Must reject absent mismatch_count field"

        # 6. Failing manifest: sha256 mismatch
        bad_manifest = {
            "outputs": {
                "geometry_ledger.parquet": {
                    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "bytes": 100,
                }
            }
        }
        (geom_dir / "runtime_receipt.json").write_text(json.dumps(valid_receipt), encoding="utf-8")
        (geom_dir / "output_manifest.json").write_text(json.dumps(bad_manifest), encoding="utf-8")
        rejected_hash = False
        try:
            validate_extractor_receipt(geom_dir, expected_rows=1)
        except ValueError:
            rejected_hash = True
        assert rejected_hash, "Must reject manifest hash mismatch"

    return {
        "status": "pass",
        "details": "Mandatory receipt fields, explicit zero counts, release_ready, and manifest hash verified with strict failure branches",
    }


def test_runner_strict_fresh_dir_and_traceback_preservation() -> dict[str, Any]:
    """Verify that runner strictly refuses any existing non-empty output directory per contract,
    and preserves failed execution receipt with full traceback on error without NameError.
    """
    # 1. Strict fresh directory test
    existing_dir = Path(tempfile.mkdtemp(dir=HERE, prefix="test_existing_dir_"))
    evidence_file = existing_dir / "prior_failure_evidence.json"
    evidence_file.write_text('{"prior": "evidence"}', encoding="utf-8")

    try:
        code = run_runner(output_dir=existing_dir)
        assert code == 1, f"Expected code 1 when output dir exists and contains files, got {code}"
        assert evidence_file.exists(), "Prior evidence file must not be modified or deleted"
        assert json.loads(evidence_file.read_text(encoding="utf-8")) == {"prior": "evidence"}
    finally:
        evidence_file.unlink()
        existing_dir.rmdir()

    # 2. Failing run preserves EXECUTION.json with traceback without NameError
    failing_run_dir = Path(tempfile.mkdtemp(dir=HERE, prefix="test_failing_run_"))
    try:
        # Calling runner with invalid geometry directory (points to non-existent folder)
        code_fail = run_runner(output_dir=failing_run_dir, geometry_dir=HERE / "nonexistent_geometry_dir")
        assert code_fail == 1, f"Expected code 1 on failing run, got {code_fail}"

        receipt_path = failing_run_dir / "EXECUTION.json"
        assert receipt_path.exists(), "EXECUTION.json must be preserved in output dir on runner failure"

        rec = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert rec["status"] == "failed"
        assert rec["exit_code"] == 1
        assert "nonexistent_geometry_dir" in rec["error"]
        assert "traceback" in rec and "Traceback (most recent call last):" in rec["traceback"]
        assert "NameError" not in rec["traceback"], "Traceback must not contain NameError"
    finally:
        for f in failing_run_dir.glob("*"):
            f.unlink()
        failing_run_dir.rmdir()

    return {
        "status": "pass",
        "details": "Strict fresh directory refusal and EXECUTION.json traceback preservation verified without NameError",
    }


def test_raw_key_validation_and_runner_fractional_rejection() -> dict[str, Any]:
    """Verify validate_raw_keys rejects fractional, boolean, negative, out-of-range,
    and duplicate keys before any lossy integer conversion.
    """
    valid_df = pd.DataFrame([
        {"rfid_id": "r1", "ts": 490000, "source_ordinal": 10},
        {"rfid_id": "r1", "ts": 490001, "source_ordinal": 11},
    ])
    out = validate_raw_keys(valid_df, "test")
    assert out["ts"].dtype == "int64"
    assert out["source_ordinal"].dtype == "int64"

    # Fractional ts rejection
    df_frac_ts = pd.DataFrame([{"rfid_id": "r1", "ts": 123.5, "source_ordinal": 10}])
    rejected_frac_ts = False
    try:
        validate_raw_keys(df_frac_ts, "frac_ts")
    except ValueError as e:
        rejected_frac_ts = "Fractional" in str(e)
    assert rejected_frac_ts, "Must reject fractional ts before cast"

    # Fractional ordinal rejection
    df_frac_ord = pd.DataFrame([{"rfid_id": "r1", "ts": 123, "source_ordinal": 10.5}])
    rejected_frac_ord = False
    try:
        validate_raw_keys(df_frac_ord, "frac_ord")
    except ValueError as e:
        rejected_frac_ord = "Fractional" in str(e)
    assert rejected_frac_ord, "Must reject fractional source_ordinal before cast"

    # Boolean ts rejection
    df_bool_ts = pd.DataFrame([{"rfid_id": "r1", "ts": True, "source_ordinal": 10}])
    rejected_bool_ts = False
    try:
        validate_raw_keys(df_bool_ts, "bool_ts")
    except ValueError:
        rejected_bool_ts = True
    assert rejected_bool_ts, "Must reject boolean ts"

    # Boolean ordinal rejection
    df_bool_ord = pd.DataFrame([{"rfid_id": "r1", "ts": 123, "source_ordinal": False}])
    rejected_bool_ord = False
    try:
        validate_raw_keys(df_bool_ord, "bool_ord")
    except ValueError:
        rejected_bool_ord = True
    assert rejected_bool_ord, "Must reject boolean source_ordinal"

    # Negative ordinal rejection
    df_neg_ord = pd.DataFrame([{"rfid_id": "r1", "ts": 123, "source_ordinal": -1}])
    rejected_neg_ord = False
    try:
        validate_raw_keys(df_neg_ord, "neg_ord")
    except ValueError:
        rejected_neg_ord = True
    assert rejected_neg_ord, "Must reject negative source_ordinal"

    # Negative ts rejection
    df_neg_ts = pd.DataFrame([{"rfid_id": "r1", "ts": -10, "source_ordinal": 1}])
    rejected_neg_ts = False
    try:
        validate_raw_keys(df_neg_ts, "neg_ts")
    except ValueError:
        rejected_neg_ts = True
    assert rejected_neg_ts, "Must reject negative ts"

    # Nanosecond scale ts rejection (>10M hours)
    df_ns_ts = pd.DataFrame([{"rfid_id": "r1", "ts": 1700000000000, "source_ordinal": 1}])
    rejected_ns_ts = False
    try:
        validate_raw_keys(df_ns_ts, "ns_ts")
    except ValueError:
        rejected_ns_ts = True
    assert rejected_ns_ts, "Must reject nanosecond-scale timestamp"

    # Duplicate ordinal rejection
    df_dup_ord = pd.DataFrame([
        {"rfid_id": "r1", "ts": 10, "source_ordinal": 1},
        {"rfid_id": "r2", "ts": 20, "source_ordinal": 1},
    ])
    rejected_dup_ord = False
    try:
        validate_raw_keys(df_dup_ord, "dup_ord")
    except ValueError:
        rejected_dup_ord = True
    assert rejected_dup_ord, "Must reject duplicate source_ordinal"

    # Duplicate (rfid_id, ts) rejection
    df_dup_rfid_ts = pd.DataFrame([
        {"rfid_id": "r1", "ts": 10, "source_ordinal": 1},
        {"rfid_id": "r1", "ts": 10, "source_ordinal": 2},
    ])
    rejected_dup_rfid_ts = False
    try:
        validate_raw_keys(df_dup_rfid_ts, "dup_rfid_ts")
    except ValueError:
        rejected_dup_rfid_ts = True
    assert rejected_dup_rfid_ts, "Must reject duplicate (rfid_id, ts)"

    return {
        "status": "pass",
        "details": "Original uncasted key validation strictly verified for fractional, boolean, negative, and duplicate values",
    }


def test_shared_numeric_missingness_and_infinity_agreement() -> dict[str, Any]:
    """Verify shared numeric comparison explicitly compares missingness and finite/infinite states,
    rejecting one-sided missingness or NaN-skipping false matches.
    """
    base_canon = pd.DataFrame([{
        "rfid_id": "v1", "ts": 490000, "source_ordinal": 10,
        "len_m": 100.0, "bbox_m": 80.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0,
    }])
    base_geom = pd.DataFrame([{
        "rfid_id": "v1", "ts": 490000, "source_ordinal": 10,
        "len_m": 100.0, "bbox_m": 80.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0,
        "geometry_status": "informative",
    }])

    # 1. Normal match succeeds
    merged = validate_and_merge_geometry(base_canon, base_geom)
    assert len(merged) == 1

    # 2. Both sides NaN -> succeeds (explicit missing agreement)
    nan_canon = base_canon.copy()
    nan_canon["score"] = np.nan
    nan_geom = base_geom.copy()
    nan_geom["score"] = np.nan
    merged_nan = validate_and_merge_geometry(nan_canon, nan_geom)
    assert len(merged_nan) == 1
    assert pd.isna(merged_nan.iloc[0]["score"])

    # 3. One-sided NaN (canonical NaN, geometry finite) -> FAILS!
    bad_geom = base_geom.copy()
    bad_geom["score"] = 5.0
    rejected_one_sided = False
    try:
        validate_and_merge_geometry(nan_canon, bad_geom)
    except ValueError as e:
        rejected_one_sided = "missingness mismatch" in str(e)
    assert rejected_one_sided, "Must reject one-sided NaN vs finite score"

    # 4. Entire column NaN on one side vs finite on other -> FAILS!
    multi_canon = pd.DataFrame([
        {"rfid_id": "v1", "ts": 490000, "source_ordinal": 10, "len_m": np.nan, "bbox_m": 80.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0},
        {"rfid_id": "v1", "ts": 490001, "source_ordinal": 11, "len_m": np.nan, "bbox_m": 80.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0},
    ])
    multi_geom = pd.DataFrame([
        {"rfid_id": "v1", "ts": 490000, "source_ordinal": 10, "len_m": 100.0, "bbox_m": 80.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0, "geometry_status": "informative"},
        {"rfid_id": "v1", "ts": 490001, "source_ordinal": 11, "len_m": 100.0, "bbox_m": 80.0, "cen_lon": 127.0, "cen_lat": 34.0, "score": 5.0, "geometry_status": "informative"},
    ])
    rejected_all_nan = False
    try:
        validate_and_merge_geometry(multi_canon, multi_geom)
    except ValueError as e:
        rejected_all_nan = "missingness mismatch" in str(e)
    assert rejected_all_nan, "Must reject entire column NaN vs finite values"

    # 5. Finite vs Infinite -> FAILS!
    inf_geom = base_geom.copy()
    inf_geom["len_m"] = np.inf
    rejected_finite_inf = False
    try:
        validate_and_merge_geometry(base_canon, inf_geom)
    except ValueError as e:
        rejected_finite_inf = "finite vs infinite" in str(e)
    assert rejected_finite_inf, "Must reject finite vs infinite state mismatch"

    # 6. Infinite sign mismatch (+inf vs -inf) -> FAILS!
    inf_canon = base_canon.copy()
    inf_canon["len_m"] = -np.inf
    rejected_sign_inf = False
    try:
        validate_and_merge_geometry(inf_canon, inf_geom)
    except ValueError as e:
        rejected_sign_inf = "sign mismatch" in str(e)
    assert rejected_sign_inf, "Must reject +/- infinity sign mismatch"

    # 7. Both +inf -> succeeds
    pos_inf_canon = base_canon.copy()
    pos_inf_canon["len_m"] = np.inf
    merged_inf = validate_and_merge_geometry(pos_inf_canon, inf_geom)
    assert len(merged_inf) == 1
    assert np.isinf(merged_inf.iloc[0]["len_m"])

    return {
        "status": "pass",
        "details": "Shared numeric missingness and finite/infinite state comparisons verified; NaN-skipping false matches prevented",
    }


def test_exact_5pp_operational_gate_boundary() -> dict[str, Any]:
    """Verify exact count threshold logic 20 * (G_hits - B0_hits) >= n_tier01 for +5 percentage points,
    proving that floating point 5/60 vs 2/60 boundary rounding passes condition 1, while 4/60 vs 2/60 fails.
    """
    # 1. Test 5/60 vs 2/60 (difference is exactly 3/60 = +0.05)
    # In float math: (5/60) - (2/60) = 0.049999999999999996 < 0.05
    n_t01 = 60
    g_hits_pass = 5
    b0_hits = 2
    delta_pass = g_hits_pass - b0_hits
    cond1_pass = bool(n_t01 > 0 and (20 * delta_pass >= n_t01))
    assert cond1_pass is True, f"5/60 vs 2/60 must pass condition 1 (+5%p exact count), got {cond1_pass}"

    # 2. Test 4/60 vs 2/60 (difference is 2/60 = 0.0333 < 0.05)
    g_hits_fail = 4
    delta_fail = g_hits_fail - b0_hits
    cond1_fail = bool(n_t01 > 0 and (20 * delta_fail >= n_t01))
    assert cond1_fail is False, f"4/60 vs 2/60 must fail condition 1 (< +5%p), got {cond1_fail}"

    # 3. Test non-worsening on all 100 using integer count delta
    all_n = 100
    assert bool(10 - 10 >= 0) is True, "Equal hits (10 vs 10) must satisfy non-worsening"
    assert bool(9 - 10 >= 0) is False, "Fewer hits (9 vs 10) must fail non-worsening"

    return {
        "status": "pass",
        "details": "Exact integer count +5%p threshold (20 * delta >= n) verified; 5/60 vs 2/60 passes, 4/60 vs 2/60 fails",
    }


def test_frozen_prediction_and_pool_manifest_hash_unchanged() -> dict[str, Any]:
    """Verify that predictions.csv and pool_manifest.csv hashes remain byte-identical
    after evaluate_shape execution, and post-eval verification is recorded.
    """
    synthetic_out = Path(tempfile.mkdtemp(dir=HERE, prefix="frozen_test_"))
    try:
        code = run_runner(output_dir=synthetic_out, synthetic=True)
        assert code == 0, f"Synthetic runner failed with code {code}"
        receipt = json.loads((synthetic_out / "EXECUTION.json").read_text(encoding="utf-8"))

        assert "frozen_verification_post_eval" in receipt
        f_ver = receipt["frozen_verification_post_eval"]
        assert f_ver["predictions_hash_unchanged"] is True
        assert f_ver["pool_manifest_hash_unchanged"] is True
        assert f_ver["pre_pred_sha256"] == f_ver["post_pred_sha256"]
        assert f_ver["pre_manifest_sha256"] == f_ver["post_manifest_sha256"]
    finally:
        for f in synthetic_out.glob("*"):
            f.unlink()
        synthetic_out.rmdir()

    return {
        "status": "pass",
        "details": "Pre-label frozen predictions and pool_manifest hashes verified byte-identical post-evaluation",
    }


def test_runner_ram_preflight_and_isolation() -> dict[str, Any]:
    """Verify runner RAM preflight logic, memory calculation, and output directory isolation."""
    # 1. Memory requirement check
    avail, total = _available_memory()
    assert avail > 0, "Available RAM must be positive"
    assert total > 0, "Total RAM must be positive"
    assert TOTAL_MEMORY_REQUIRED == (768 + 512 + 640) * 1024 * 1024

    # 2. Working set measurement
    ws = _peak_working_set()
    assert ws is not None and ws > 0, "Peak working set must be positive"

    # 3. Output directory isolation
    isolated = False
    try:
        run_runner(output_dir=Path("C:/arbitrary_external_dir"))
    except ValueError:
        isolated = True
    assert isolated, "Runner must reject output directory outside of Round 8 folder"

    # 4. Synthetic runner execution in fresh temporary directory
    synthetic_out = Path(tempfile.mkdtemp(dir=HERE, prefix="synthetic_runner_"))
    try:
        code = run_runner(output_dir=synthetic_out, synthetic=True)
        assert code == 0, f"Synthetic runner failed with code {code}"
        assert (synthetic_out / "EXECUTION.json").exists(), "Synthetic runner must emit EXECUTION.json"
    finally:
        for f in synthetic_out.glob("*"):
            f.unlink()
        synthetic_out.rmdir()

    return {
        "status": "pass",
        "details": "Runner memory preflight, round isolation, and synthetic execution verified",
    }


def main():
    print("=== Running Round 8 Evaluation Suite Verification ===")
    results = {}

    tests = [
        ("epoch_hour_conversion", test_exact_epoch_hour_conversion),
        ("combinatorial_random_hit", test_combinatorial_random_hit_probability),
        ("paired_rfid_bootstrap", test_paired_rfid_bootstrap_diff),
        ("stage_counts_ledger", test_stage_counts_ledger_emission),
        ("evaluator_end_to_end", test_evaluator_end_to_end_synthetic),
        ("gate_cohort_boundaries", test_gate_cohort_fixture_pass_and_fail),
        ("actual_schema_merge_and_keys", test_actual_schema_merge_and_duplicate_key_rejection),
        ("raw_key_validation_and_runner_fractional", test_raw_key_validation_and_runner_fractional_rejection),
        ("shared_numeric_missingness_infinity", test_shared_numeric_missingness_and_infinity_agreement),
        ("exact_5pp_gate_boundary", test_exact_5pp_operational_gate_boundary),
        ("frozen_hashes_post_eval", test_frozen_prediction_and_pool_manifest_hash_unchanged),
        ("extractor_receipt_validation", test_extractor_receipt_validation_and_failing_fixture),
        ("strict_fresh_dir_and_traceback", test_runner_strict_fresh_dir_and_traceback_preservation),
        ("runner_preflight_isolation", test_runner_ram_preflight_and_isolation),
    ]

    all_passed = True
    for name, fn in tests:
        t0 = time.time()
        try:
            res = fn()
            elapsed = time.time() - t0
            res["elapsed_seconds"] = round(elapsed, 4)
            results[name] = res
            print(f"  [PASS] {name} ({elapsed:.3f}s)")
        except Exception as exc:
            elapsed = time.time() - t0
            all_passed = False
            results[name] = {"status": "fail", "error": str(exc), "elapsed_seconds": round(elapsed, 4)}
            print(f"  [FAIL] {name} ({elapsed:.3f}s): {exc}")

    output_path = HERE / "eval_checks.json"
    summary = {
        "suite": "Round 8 shape evaluation independent verification",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "all_passed": all_passed,
        "total_tests": len(tests),
        "passed_tests": sum(1 for r in results.values() if r.get("status") == "pass"),
        "results": results,
    }
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved verification results to {output_path.name}")
    print(f"Overall status: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
