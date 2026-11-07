"""Small independent fixture verifying metadata classification of transition reasons.

Tests:
1. missing_previous -> status 'defer'
2. invalid_previous -> status 'defer'
3. previous_not_large -> status 'reject'
4. current_not_small -> status 'reject'
5. missing_next -> status 'defer'
6. invalid_next -> status 'defer'
7. next_not_small -> status 'reject'
8. Stage keep/candidate counts remain strictly identical between classifications.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROUND4_DIR = HERE.parent
if str(ROUND4_DIR) not in sys.path:
    sys.path.insert(0, str(ROUND4_DIR))

from evaluate_sequence import _build_stage_counts


def run_fixture() -> dict[str, Any]:
    # Construct synthetic ledger covering all Stage 1 & Stage 2 reasons
    rows = [
        # Stage 0 valid rows
        # 1. keep at stage 1 and stage 2
        {"rfid_id": "V1", "stage0_ok": True, "geometry_valid": True, "stage1_ok": True, "stage1_reason": "keep",
         "stage2_ok": True, "stage2_reason": "keep", "stage3_ok": True, "gear_missing_reason": None},
        # 2. missing_previous -> defer
        {"rfid_id": "V1", "stage0_ok": True, "geometry_valid": True, "stage1_ok": False, "stage1_reason": "missing_previous",
         "stage2_ok": False, "stage2_reason": "stage1_reject", "stage3_ok": False, "gear_missing_reason": None},
        # 3. invalid_previous -> defer
        {"rfid_id": "V1", "stage0_ok": True, "geometry_valid": True, "stage1_ok": False, "stage1_reason": "invalid_previous",
         "stage2_ok": False, "stage2_reason": "stage1_reject", "stage3_ok": False, "gear_missing_reason": None},
        # 4. previous_not_large -> reject
        {"rfid_id": "V1", "stage0_ok": True, "geometry_valid": True, "stage1_ok": False, "stage1_reason": "previous_not_large",
         "stage2_ok": False, "stage2_reason": "stage1_reject", "stage3_ok": False, "gear_missing_reason": None},
        # 5. current_not_small -> reject
        {"rfid_id": "V1", "stage0_ok": True, "geometry_valid": True, "stage1_ok": False, "stage1_reason": "current_not_small",
         "stage2_ok": False, "stage2_reason": "stage1_reject", "stage3_ok": False, "gear_missing_reason": None},
        # 6. stage1 keep, missing_next -> defer
        {"rfid_id": "V2", "stage0_ok": True, "geometry_valid": True, "stage1_ok": True, "stage1_reason": "keep",
         "stage2_ok": False, "stage2_reason": "missing_next", "stage3_ok": False, "gear_missing_reason": None},
        # 7. stage1 keep, invalid_next -> defer
        {"rfid_id": "V2", "stage0_ok": True, "geometry_valid": True, "stage1_ok": True, "stage1_reason": "keep",
         "stage2_ok": False, "stage2_reason": "invalid_next", "stage3_ok": False, "gear_missing_reason": None},
        # 8. stage1 keep, next_not_small -> reject
        {"rfid_id": "V2", "stage0_ok": True, "geometry_valid": True, "stage1_ok": True, "stage1_reason": "keep",
         "stage2_ok": False, "stage2_reason": "next_not_small", "stage3_ok": False, "gear_missing_reason": None},
    ]
    ledger = pd.DataFrame(rows)

    manifest_rows = [
        {"rfid_id": "V1", "method": "B0", "pool_stage": "stage0", "actual_pool_n": 5, "cap": 1, "fallback_reason": None},
        {"rfid_id": "V1", "method": "S", "pool_stage": "stage2", "actual_pool_n": 1, "cap": 1, "fallback_reason": None},
        {"rfid_id": "V1", "method": "G", "pool_stage": "stage3", "actual_pool_n": 1, "cap": 1, "fallback_reason": None},
        {"rfid_id": "V2", "method": "B0", "pool_stage": "stage0", "actual_pool_n": 3, "cap": 0, "fallback_reason": None},
        {"rfid_id": "V2", "method": "S", "pool_stage": "stage0", "actual_pool_n": 3, "cap": 0, "fallback_reason": "no_common_transitions"},
        {"rfid_id": "V2", "method": "G", "pool_stage": "stage0", "actual_pool_n": 3, "cap": 0, "fallback_reason": "no_common_transitions"},
    ]
    manifest = pd.DataFrame(manifest_rows)

    df_counts = _build_stage_counts(ledger, manifest)

    # Verification map
    expected_status = {
        ("stage1", "missing_previous"): "defer",
        ("stage1", "invalid_previous"): "defer",
        ("stage1", "previous_not_large"): "reject",
        ("stage1", "current_not_small"): "reject",
        ("stage2", "missing_next"): "defer",
        ("stage2", "invalid_next"): "defer",
        ("stage2", "next_not_small"): "reject",
    }

    verified_cases = []
    for (stg, rsn), exp_stat in expected_status.items():
        sub = df_counts[(df_counts["stage"] == stg) & (df_counts["reason"] == rsn)]
        assert len(sub) == 1, f"Expected 1 entry for ({stg}, {rsn}), found {len(sub)}"
        actual_stat = sub.iloc[0]["status"]
        assert actual_stat == exp_stat, f"Mismatch for ({stg}, {rsn}): expected {exp_stat}, got {actual_stat}"
        verified_cases.append({
            "stage": stg,
            "reason": rsn,
            "expected_status": exp_stat,
            "actual_status": actual_stat,
            "row_count": int(sub.iloc[0]["row_count"]),
            "status": "passed",
        })

    # Verify keep counts stay intact
    s0_keep = df_counts[(df_counts["stage"] == "stage0") & (df_counts["status"] == "keep")].iloc[0]["row_count"]
    s1_keep = df_counts[(df_counts["stage"] == "stage1") & (df_counts["status"] == "keep")].iloc[0]["row_count"]
    s2_keep = df_counts[(df_counts["stage"] == "stage2") & (df_counts["status"] == "keep")].iloc[0]["row_count"]

    assert s0_keep == 8, f"Stage 0 keep count mismatch: {s0_keep}"
    assert s1_keep == 4, f"Stage 1 keep count mismatch: {s1_keep}"
    assert s2_keep == 1, f"Stage 2 keep count mismatch: {s2_keep}"

    result = {
        "status": "passed",
        "verified_cases": verified_cases,
        "keep_counts": {
            "stage0_keep": int(s0_keep),
            "stage1_keep": int(s1_keep),
            "stage2_keep": int(s2_keep),
        },
    }

    out_file = HERE / "fixture_result.json"
    out_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Fixture passed: verified {len(verified_cases)} cases. Result written to {out_file.name}")
    return result


if __name__ == "__main__":
    run_fixture()
