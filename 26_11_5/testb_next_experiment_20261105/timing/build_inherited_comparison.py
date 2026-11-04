"""Copy the already submitted A baseline into a preparation-only comparison table.

Reads the existing CSV as data only; it never recalculates A or selects a timestamp.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[3]
CANONICAL = Path(r"D:/repos/fishing-track-classification")
SOURCE = CANONICAL / "results/submission_20261101/testB_submission.csv"
TARGET = HERE / "comparison_readiness_100.csv"
FIELDS = [
    "rfid_id", "baseline_A_timestamp", "baseline_A_score", "A_source_status",
    "B_timestamp", "B_score", "B_source_row", "B_status", "B_unavailable_reason",
    "C_timestamp", "C_score", "C_source_row", "C_status", "C_unavailable_reason",
    "internal_decision_status", "baseline_source_path",
]


def main() -> int:
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as f:
        source_rows = list(csv.DictReader(f))
    if len(source_rows) != 100:
        raise ValueError(f"expected existing 100-row baseline, found {len(source_rows)}")
    if len({r["rfid_id"] for r in source_rows}) != 100:
        raise ValueError("source baseline has duplicate vessel IDs")
    with TARGET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in source_rows:
            writer.writerow({
                "rfid_id": row["rfid_id"],
                "baseline_A_timestamp": row["사고시각"],
                "baseline_A_score": row["이상항적 점수"],
                "A_source_status": "inherited_existing_baseline",
                "B_timestamp": "", "B_score": "", "B_source_row": "",
                "B_status": "not_computed", "B_unavailable_reason": (
                    "2026 점수 입력 없음; 임계값 출처·초과 경계·최대간격 미확정"
                ),
                "C_timestamp": "", "C_score": "", "C_source_row": "",
                "C_status": "not_computed", "C_unavailable_reason": (
                    "2026 점수 입력 없음; 임계값 출처·초과 경계·최대간격·지속 최소 조건 미확정"
                ),
                "internal_decision_status": "not_assessed_not_accident_label",
                "baseline_source_path": str(SOURCE),
            })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
