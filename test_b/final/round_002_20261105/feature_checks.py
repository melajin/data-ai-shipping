"""Deterministic synthetic verification checks for context_features.py.

Owned by Gemini.
Adheres strictly to CONTRACT.md and PROTOCOL.md:
- No actual Parquet data loads or Test B inference.
- Validates 720h inclusive boundary, [t-720, t) window, future invariance,
  minimum history thresholds (24 rows, 3 days), 0.05-deg cell fallback (8 rows),
  constant ties (score == 0.0), invalid coordinates/geometries, RFID isolation,
  input row order and index preservation, and forbidden column isolation.
- Emits machine-readable feature_checks.json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from context_features import compute_features

HERE = Path(__file__).resolve().parent
JSON_OUTPUT = HERE / "feature_checks.json"


def _build_history_series(
    rfid: str,
    n_days: int = 4,
    hours_per_day: int = 10,
    base_len: float = 50.0,
    base_bbox: float = 80.0,
    base_lon: float = 126.0,
    base_lat: float = 35.0,
    start_day: int = 0,
) -> list[dict[str, Any]]:
    """Helper to generate deterministic regular vessel rows."""
    rows = []
    ordinal = 1
    for day in range(start_day, start_day + n_days):
        for h in range(hours_per_day):
            ts = day * 24 + h
            rows.append({
                "rfid_id": rfid,
                "ts": ts,
                "source_ordinal": ordinal,
                "len_m": base_len + float(h % 5),
                "bbox_m": base_bbox + float(h % 7),
                "cen_lon": base_lon + (0.01 * (h % 3)),
                "cen_lat": base_lat + (0.01 * (h % 2)),
                "score": 0.5,
            })
            ordinal += 1
    return rows


def check_future_invariance() -> dict[str, Any]:
    """Verify that appending future rows does NOT change features of prior rows."""
    rows = _build_history_series("V_INV", n_days=5, hours_per_day=8)
    df_base = pd.DataFrame(rows)
    feat_base = compute_features(df_base)

    # Append 15 future rows at a later timestamp
    max_ts = int(df_base["ts"].max())
    future_rows = [
        {
            "rfid_id": "V_INV",
            "ts": max_ts + 1 + i,
            "source_ordinal": 1000 + i,
            "len_m": 120.0 + i,
            "bbox_m": 200.0 + i,
            "cen_lon": 126.0,
            "cen_lat": 35.0,
            "score": 0.9,
        }
        for i in range(15)
    ]
    df_extended = pd.concat([df_base, pd.DataFrame(future_rows)], ignore_index=True)
    feat_extended = compute_features(df_extended)

    sub_feat = feat_extended.iloc[:len(df_base)].copy()
    feature_cols = [
        "n_history",
        "history_days",
        "history_eligible",
        "n_cell_history",
        "context_used",
    ]
    for col in feature_cols:
        assert (sub_feat[col].values == feat_base[col].values).all(), f"Mismatch in {col}"

    # Float columns check (including NaNs)
    for col in ("U", "C"):
        b_vals = feat_base[col].to_numpy()
        e_vals = sub_feat[col].to_numpy()
        np.testing.assert_array_equal(
            np.isnan(b_vals), np.isnan(e_vals), err_msg=f"NaN mismatch in {col}"
        )
        mask = ~np.isnan(b_vals)
        np.testing.assert_allclose(
            b_vals[mask], e_vals[mask], rtol=1e-12, atol=1e-12, err_msg=f"Value mismatch in {col}"
        )

    return {"status": "passed", "base_rows": len(df_base), "extended_rows": len(df_extended)}


def check_720h_boundary() -> dict[str, Any]:
    """Verify [t-720, t) rolling window with inclusive left boundary."""
    # Place rows at ts = 100, 200, 300, ..., 900
    # At t = 820: left bound is 820 - 720 = 100. ts=100 MUST be included (inclusive left bound).
    # At t = 821: left bound is 821 - 720 = 101. ts=100 MUST be evicted.
    records = [
        {"rfid_id": "V_BOUND", "ts": 100, "source_ordinal": 1, "len_m": 50.0, "bbox_m": 80.0, "cen_lon": 126.0, "cen_lat": 35.0},
        {"rfid_id": "V_BOUND", "ts": 300, "source_ordinal": 2, "len_m": 50.0, "bbox_m": 80.0, "cen_lon": 126.0, "cen_lat": 35.0},
        {"rfid_id": "V_BOUND", "ts": 500, "source_ordinal": 3, "len_m": 50.0, "bbox_m": 80.0, "cen_lon": 126.0, "cen_lat": 35.0},
        {"rfid_id": "V_BOUND", "ts": 820, "source_ordinal": 4, "len_m": 50.0, "bbox_m": 80.0, "cen_lon": 126.0, "cen_lat": 35.0},
        {"rfid_id": "V_BOUND", "ts": 821, "source_ordinal": 5, "len_m": 50.0, "bbox_m": 80.0, "cen_lon": 126.0, "cen_lat": 35.0},
    ]
    df = pd.DataFrame(records)
    feat = compute_features(df)

    # At row 3 (ts=820): past rows are ts=100, 300, 500. All 3 are in [820-720, 820) = [100, 820).
    n_at_820 = feat.loc[3, "n_history"]
    assert n_at_820 == 3, f"Expected 3 history rows at ts=820, got {n_at_820}"

    # At row 4 (ts=821): left bound is 821-720 = 101. ts=100 evicted!
    # Past rows in [101, 821) are ts=300, 500, 820. Count is 3.
    n_at_821 = feat.loc[4, "n_history"]
    assert n_at_821 == 3, f"Expected 3 history rows at ts=821, got {n_at_821}"

    # Verify right boundary exclusion: row at t=100 has n_history=0 (does not see itself)
    assert feat.loc[0, "n_history"] == 0
    return {"status": "passed", "n_at_820": int(n_at_820), "n_at_821": int(n_at_821)}


def check_history_minima() -> dict[str, Any]:
    """Verify minimum history thresholds: n >= 24 and distinct(ts // 24) >= 3."""
    # Case A: 24 rows, but only across 2 distinct days -> ineligible
    rows_2days = []
    ord_counter = 1
    for day in (0, 1):
        for h in range(12):  # 12 * 2 = 24 rows
            rows_2days.append({
                "rfid_id": "V_MIN_2D",
                "ts": day * 24 + h,
                "source_ordinal": ord_counter,
                "len_m": 50.0,
                "bbox_m": 80.0,
                "cen_lon": 126.0,
                "cen_lat": 35.0,
            })
            ord_counter += 1
    # Evaluation row on Day 1
    rows_2days.append({
        "rfid_id": "V_MIN_2D",
        "ts": 1 * 24 + 13,
        "source_ordinal": ord_counter,
        "len_m": 50.0,
        "bbox_m": 80.0,
        "cen_lon": 126.0,
        "cen_lat": 35.0,
    })
    df_2d = pd.DataFrame(rows_2days)
    feat_2d = compute_features(df_2d)
    last_row_2d = feat_2d.iloc[-1]
    assert last_row_2d["n_history"] == 24
    assert last_row_2d["history_days"] == 2
    assert not last_row_2d["history_eligible"], "Should be ineligible due to history_days < 3"
    assert math.isnan(last_row_2d["U"]) and math.isnan(last_row_2d["C"])

    # Case B: 23 rows across 3 distinct days -> ineligible (n < 24)
    rows_23 = []
    ord_counter = 1
    # Day 0: 8 rows, Day 1: 8 rows, Day 2: 7 rows = 23 rows
    for day, count in ((0, 8), (1, 8), (2, 7)):
        for h in range(count):
            rows_23.append({
                "rfid_id": "V_MIN_23",
                "ts": day * 24 + h,
                "source_ordinal": ord_counter,
                "len_m": 50.0,
                "bbox_m": 80.0,
                "cen_lon": 126.0,
                "cen_lat": 35.0,
            })
            ord_counter += 1
    rows_23.append({
        "rfid_id": "V_MIN_23",
        "ts": 2 * 24 + 8,
        "source_ordinal": ord_counter,
        "len_m": 50.0,
        "bbox_m": 80.0,
        "cen_lon": 126.0,
        "cen_lat": 35.0,
    })
    df_23 = pd.DataFrame(rows_23)
    feat_23 = compute_features(df_23)
    last_row_23 = feat_23.iloc[-1]
    assert last_row_23["n_history"] == 23
    assert last_row_23["history_days"] == 3
    assert not last_row_23["history_eligible"], "Should be ineligible due to n_history < 24"
    assert math.isnan(last_row_23["U"]) and math.isnan(last_row_23["C"])

    # Case C: Exactly 24 rows across 3 distinct days -> ELIGIBLE
    rows_24 = []
    ord_counter = 1
    for day, count in ((0, 8), (1, 8), (2, 8)):
        for h in range(count):
            rows_24.append({
                "rfid_id": "V_MIN_24",
                "ts": day * 24 + h,
                "source_ordinal": ord_counter,
                "len_m": 50.0 + h,
                "bbox_m": 80.0 + h,
                "cen_lon": 126.0,
                "cen_lat": 35.0,
            })
            ord_counter += 1
    rows_24.append({
        "rfid_id": "V_MIN_24",
        "ts": 2 * 24 + 10,
        "source_ordinal": ord_counter,
        "len_m": 55.0,
        "bbox_m": 85.0,
        "cen_lon": 126.0,
        "cen_lat": 35.0,
    })
    df_24 = pd.DataFrame(rows_24)
    feat_24 = compute_features(df_24)
    last_row_24 = feat_24.iloc[-1]
    assert last_row_24["n_history"] == 24
    assert last_row_24["history_days"] == 3
    assert last_row_24["history_eligible"], "Should be eligible with n=24 and days=3"
    assert not math.isnan(last_row_24["U"]) and not math.isnan(last_row_24["C"])

    return {"status": "passed", "n_history_checked": [24, 23, 24], "days_checked": [2, 3, 3]}


def check_cell_fallback_and_conditioning() -> dict[str, Any]:
    """Verify 0.05-deg cell conditioning and fallback when n_cell < 8."""
    # Build 28 rows across 4 days (7 per day)
    # Put 7 rows in Cell A (lon=126.01, lat=35.01 -> cell (2520, 700))
    # Put remaining 21 rows in Cell B (lon=126.20, lat=35.20 -> cell (2524, 704))
    rows = []
    ord_counter = 1
    for day in range(4):
        for h in range(7):
            ts = day * 24 + h
            # First 7 rows are in Cell A, rest in Cell B
            in_cell_a = (ord_counter <= 7)
            lon = 126.01 if in_cell_a else 126.20
            lat = 35.01 if in_cell_a else 35.20
            rows.append({
                "rfid_id": "V_CELL",
                "ts": ts,
                "source_ordinal": ord_counter,
                "len_m": 20.0 if in_cell_a else 100.0,
                "bbox_m": 40.0 if in_cell_a else 150.0,
                "cen_lon": lon,
                "cen_lat": lat,
            })
            ord_counter += 1

    # Row 28: In Cell A, where n_cell_history = 7 (< 8) -> MUST FALLBACK TO U
    rows.append({
        "rfid_id": "V_CELL",
        "ts": 4 * 24,
        "source_ordinal": ord_counter,
        "len_m": 20.0,
        "bbox_m": 40.0,
        "cen_lon": 126.01,
        "cen_lat": 35.01,
    })
    ord_counter += 1

    # Row 29: Also in Cell A, now n_cell_history = 8 (>= 8) -> MUST USE CONTEXT
    rows.append({
        "rfid_id": "V_CELL",
        "ts": 4 * 24 + 1,
        "source_ordinal": ord_counter,
        "len_m": 20.0,
        "bbox_m": 40.0,
        "cen_lon": 126.01,
        "cen_lat": 35.01,
    })

    df = pd.DataFrame(rows)
    feat = compute_features(df)

    row_fb = feat.iloc[28]
    assert row_fb["n_cell_history"] == 7
    assert not row_fb["context_used"], "context_used should be False for n_cell=7"
    assert row_fb["C"] == row_fb["U"], "C must equal U on fallback"

    row_ctx = feat.iloc[29]
    assert row_ctx["n_cell_history"] == 8
    assert row_ctx["context_used"], "context_used should be True for n_cell=8"
    # In Cell A, all 8 prior rows had len=20, bbox=40; current row also has len=20, bbox=40
    # Thus in Cell A, current row has constant tie -> r_cell = 0.0 -> C = 0.0
    # But overall history includes 21 rows of len=100, bbox=150, so U is significantly > 0!
    assert row_ctx["C"] == 0.0, f"Expected C=0.0 due to cell ties, got {row_ctx['C']}"
    assert row_ctx["U"] > 0.0, f"Expected U > 0.0, got {row_ctx['U']}"

    return {"status": "passed", "fallback_n_cell": 7, "conditioned_n_cell": 8, "C_fallback": float(row_fb["C"]), "C_context": float(row_ctx["C"]), "U_context": float(row_ctx["U"])}


def check_constant_ties() -> dict[str, Any]:
    """Verify that constant ties return rarity exactly 0.0 per contract."""
    rows = []
    ord_counter = 1
    for day in range(4):
        for h in range(8):  # 32 rows
            rows.append({
                "rfid_id": "V_TIE",
                "ts": day * 24 + h,
                "source_ordinal": ord_counter,
                "len_m": 60.0,
                "bbox_m": 100.0,
                "cen_lon": 126.0,
                "cen_lat": 35.0,
            })
            ord_counter += 1

    # Current row with identical constant values
    rows.append({
        "rfid_id": "V_TIE",
        "ts": 4 * 24 + 1,
        "source_ordinal": ord_counter,
        "len_m": 60.0,
        "bbox_m": 100.0,
        "cen_lon": 126.0,
        "cen_lat": 35.0,
    })

    df = pd.DataFrame(rows)
    feat = compute_features(df)
    last = feat.iloc[-1]

    assert last["history_eligible"]
    assert last["U"] == 0.0, f"Constant tie U should be 0.0, got {last['U']}"
    assert last["C"] == 0.0, f"Constant tie C should be 0.0, got {last['C']}"
    assert last["context_used"], "Context should be used with 32 cell rows"

    return {"status": "passed", "U_tie": float(last["U"]), "C_tie": float(last["C"])}


def check_invalid_coords_and_geometries() -> dict[str, Any]:
    """Verify handling of invalid geometries and invalid geographic coordinates."""
    base_rows = _build_history_series("V_INV_TEST", n_days=4, hours_per_day=8)

    # 1. Past row with invalid geometry (-10 len) should NOT enter history
    base_rows[5]["len_m"] = -10.0  # Invalid!
    # 2. Past row with invalid bbox (NaN) should NOT enter history
    base_rows[10]["bbox_m"] = float("nan")

    # 3. Current row with invalid location (lat = 95.0 > 90)
    # Should still compute U if eligible, but n_cell=0 and fallback C=U
    current_row_bad_loc = {
        "rfid_id": "V_INV_TEST",
        "ts": 4 * 24 + 1,
        "source_ordinal": 500,
        "len_m": 50.0,
        "bbox_m": 80.0,
        "cen_lon": 126.0,
        "cen_lat": 95.0,  # Invalid latitude!
    }

    # 4. Current row with invalid geometry (len = -1.0)
    # Must be ineligible: U=NaN, C=NaN
    current_row_bad_geom = {
        "rfid_id": "V_INV_TEST",
        "ts": 4 * 24 + 2,
        "source_ordinal": 501,
        "len_m": -1.0,  # Invalid geometry!
        "bbox_m": 80.0,
        "cen_lon": 126.0,
        "cen_lat": 35.0,
    }

    df = pd.DataFrame(base_rows + [current_row_bad_loc, current_row_bad_geom])
    feat = compute_features(df)

    row_bad_loc = feat.iloc[len(base_rows)]
    # Original 32 rows minus 2 invalid past rows = 30 valid history rows
    assert row_bad_loc["n_history"] == 30
    assert row_bad_loc["history_eligible"], "Eligible because len/bbox are valid"
    assert row_bad_loc["n_cell_history"] == 0, "Invalid coord gives 0 cell history"
    assert not row_bad_loc["context_used"]
    assert not math.isnan(row_bad_loc["U"])
    assert row_bad_loc["C"] == row_bad_loc["U"]

    row_bad_geom = feat.iloc[len(base_rows) + 1]
    assert not row_bad_geom["history_eligible"], "Negative len makes row ineligible"
    assert math.isnan(row_bad_geom["U"])
    assert math.isnan(row_bad_geom["C"])

    return {"status": "passed", "valid_history_retained": int(row_bad_loc["n_history"])}


def check_rfid_separation() -> dict[str, Any]:
    """Verify that multiple vessels never leak history to each other."""
    v1_rows = _build_history_series("V1", n_days=4, hours_per_day=8, base_len=50.0)
    # V2 has only 3 rows -> ineligible
    v2_rows = [
        {"rfid_id": "V2", "ts": 10 + i, "source_ordinal": i, "len_m": 200.0, "bbox_m": 300.0, "cen_lon": 126.0, "cen_lat": 35.0}
        for i in range(3)
    ]
    df = pd.concat([pd.DataFrame(v1_rows), pd.DataFrame(v2_rows)], ignore_index=True)
    feat = compute_features(df)

    v1_feat = feat[feat["rfid_id"] == "V1"]
    v2_feat = feat[feat["rfid_id"] == "V2"]

    assert v1_feat.iloc[-1]["history_eligible"]
    assert (v2_feat["n_history"] <= 2).all()
    assert (~v2_feat["history_eligible"]).all(), "V2 must be ineligible"
    assert v2_feat["U"].isna().all()
    assert v2_feat["C"].isna().all()

    return {"status": "passed", "v1_rows": len(v1_feat), "v2_rows": len(v2_feat)}


def check_order_and_index_preservation() -> dict[str, Any]:
    """Verify that row order, index, and non-feature columns are strictly preserved."""
    rows = _build_history_series("V_ORD", n_days=4, hours_per_day=8)
    df = pd.DataFrame(rows, index=[f"row_{i:03d}" for i in range(len(rows))])

    # Shuffle DataFrame arbitrarily
    shuffled = df.sample(frac=1.0, random_state=42)
    feat = compute_features(shuffled)

    assert feat.index.equals(shuffled.index), "Index must be strictly preserved"
    assert len(feat) == len(shuffled), "Row count must match exactly"
    assert list(feat.columns) == list(shuffled.columns) + [
        "n_history",
        "history_days",
        "history_eligible",
        "n_cell_history",
        "context_used",
        "U",
        "C",
    ]

    # Verify features computed on shuffled match features computed on sorted
    feat_sorted = compute_features(df)
    for col in ("n_history", "history_days", "history_eligible", "n_cell_history", "context_used"):
        assert (feat.loc[df.index, col] == feat_sorted[col]).all()

    return {"status": "passed", "rows_tested": len(df)}


def check_time_deduplication() -> dict[str, Any]:
    """Verify that multiple rows at same ts see same history and only representative enters."""
    rows = [
        # History setup: 25 rows on day 0, 1, 2
    ]
    ord_c = 1
    for day in range(3):
        for h in range(8):
            rows.append({
                "rfid_id": "V_DEDUP",
                "ts": day * 24 + h,
                "source_ordinal": ord_c,
                "len_m": 50.0,
                "bbox_m": 80.0,
                "cen_lon": 126.0,
                "cen_lat": 35.0,
            })
            ord_c += 1

    # At ts = 100, add 3 rows with different ordinals
    rows.append({"rfid_id": "V_DEDUP", "ts": 100, "source_ordinal": 20, "len_m": 55.0, "bbox_m": 85.0, "cen_lon": 126.0, "cen_lat": 35.0})
    rows.append({"rfid_id": "V_DEDUP", "ts": 100, "source_ordinal": 10, "len_m": 50.0, "bbox_m": 80.0, "cen_lon": 126.0, "cen_lat": 35.0})
    rows.append({"rfid_id": "V_DEDUP", "ts": 100, "source_ordinal": 30, "len_m": 60.0, "bbox_m": 90.0, "cen_lon": 126.0, "cen_lat": 35.0})

    # At ts = 101, add 1 row
    rows.append({"rfid_id": "V_DEDUP", "ts": 101, "source_ordinal": 40, "len_m": 50.0, "bbox_m": 80.0, "cen_lon": 126.0, "cen_lat": 35.0})

    df = pd.DataFrame(rows)
    feat = compute_features(df)

    # All 3 rows at ts=100 must have n_history == 24
    sub_100 = feat[feat["ts"] == 100]
    assert len(sub_100) == 3
    assert (sub_100["n_history"] == 24).all(), "All rows at ts=100 must see same history"

    # Row at ts=101 should see n_history == 25 (only 1 representative row from ts=100 entered!)
    row_101 = feat[feat["ts"] == 101].iloc[0]
    assert row_101["n_history"] == 25, f"Expected 25 history rows, got {row_101['n_history']}"

    return {"status": "passed", "n_history_at_100": 24, "n_history_at_101": 25}


def check_forbidden_columns_isolation() -> dict[str, Any]:
    """Verify that score, state, or accident columns do NOT affect features."""
    rows = _build_history_series("V_ISO", n_days=4, hours_per_day=8)
    df1 = pd.DataFrame(rows)
    df1["score"] = 0.1
    df1["state"] = "underway"
    df1["acc_id"] = "ACC_001"

    df2 = pd.DataFrame(rows)
    df2["score"] = 0.999
    df2["state"] = "moored"
    df2["acc_id"] = "ACC_999"

    f1 = compute_features(df1)
    f2 = compute_features(df2)

    for col in ("n_history", "history_days", "history_eligible", "n_cell_history", "context_used", "U", "C"):
        if f1[col].dtype == float:
            np.testing.assert_allclose(f1[col].to_numpy(), f2[col].to_numpy())
        else:
            assert (f1[col] == f2[col]).all()

    return {"status": "passed"}


def check_empty_frame() -> dict[str, Any]:
    """Verify graceful handling of empty DataFrame."""
    empty_df = pd.DataFrame(columns=["rfid_id", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat"])
    feat = compute_features(empty_df)
    assert len(feat) == 0
    assert "U" in feat.columns
    assert "C" in feat.columns
    assert feat["n_history"].dtype == np.int64
    assert feat["history_eligible"].dtype == bool
    return {"status": "passed", "columns_returned": list(feat.columns)}


def run_all_checks() -> dict[str, Any]:
    """Execute complete deterministic check suite and persist feature_checks.json."""
    checks = {
        "future_invariance": check_future_invariance(),
        "history_720h_boundary": check_720h_boundary(),
        "history_minima_24rows_3days": check_history_minima(),
        "cell_fallback_and_conditioning": check_cell_fallback_and_conditioning(),
        "constant_ties": check_constant_ties(),
        "invalid_coords_and_geometries": check_invalid_coords_and_geometries(),
        "rfid_separation": check_rfid_separation(),
        "order_and_index_preservation": check_order_and_index_preservation(),
        "time_deduplication": check_time_deduplication(),
        "forbidden_columns_isolation": check_forbidden_columns_isolation(),
        "empty_frame": check_empty_frame(),
    }

    all_passed = all(c.get("status") == "passed" for c in checks.values())

    receipt: dict[str, Any] = {
        "suite": "round_002_context_features_verification",
        "timestamp_local": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "overall_status": "succeeded" if all_passed else "failed",
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks.values() if c.get("status") == "passed"),
        "checks": checks,
        "spec_compliance": {
            "rolling_history_window": "[t-720, t) inclusive left bound",
            "future_invariance": "verified",
            "history_row_minimum": "n >= 24 verified",
            "history_days_minimum": "distinct(ts // 24) >= 3 verified",
            "cell_size": "0.05 degree verified",
            "cell_fallback_minimum": "n_cell < 8 fallback to U verified",
            "constant_ties_score": "0.0 verified",
            "forbidden_columns_isolated": "score, state, accident info never used",
            "data_preservation": "input columns, order, and index preserved",
        },
    }

    JSON_OUTPUT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    receipt = run_all_checks()
    print(f"feature_checks: {receipt['passed_checks']}/{receipt['total_checks']} passed -> overall_status: {receipt['overall_status']}")
