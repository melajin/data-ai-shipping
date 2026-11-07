"""Small deterministic contract checks; no archived data or model run is used."""
from __future__ import annotations

import csv
import math
import tempfile
from pathlib import Path

import pandas as pd

from data_eval import _random_hit_probability, evaluate
from run_experiment import _copy_input_diagnostics, _persist_featured_rows


def main() -> None:
    assert _random_hit_probability(4, 1, 2) == 0.5
    assert _random_hit_probability(0, 0, 4) == 0.0
    rows = [
        # For A, baseline, U, and C deliberately have different winning hours.
        # U/C ties must resolve to the earlier hour, then lower ordinal for duplicate hour.
        ("A", 6, 2, .99, True, True, .20, .20),
        ("A", 6, 1, .99, True, True, .20, .20),
        ("A", 8, 3, .70, True, True, .95, .30),
        ("A", 12, 4, .50, True, True, .95, .40),
        ("A", 10, 5, .60, True, True, .50, .98),
        ("A", 14, 6, .40, True, True, .40, .98),
        # B has no common row, so U/C use the B0_full pool and B0_common is empty.
        ("B", 9, 1, .8, False, False, float("nan"), float("nan")),
        ("B", 11, 2, .7, False, False, float("nan"), float("nan")),
    ]
    frame = pd.DataFrame(rows, columns=["rfid_id", "ts", "source_ordinal", "score", "geometry_valid",
                                       "history_eligible", "U", "C"])
    positives = pd.DataFrame([
        ("a1", "A", 1, False, 8), ("a2", "A", 1, False, 10), ("b1", "B", 1, True, 10)
    ], columns=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"])
    with tempfile.TemporaryDirectory(prefix="round2_fixture_", dir=Path(__file__).resolve().parent) as tmp:
        result = evaluate(frame, positives, Path(tmp))
        assert result["diagnostics"]["event_result_rows"] == 3 * 4 * 2
        with (Path(tmp) / "predictions.csv").open(encoding="utf-8", newline="") as f:
            predictions = list(csv.DictReader(f))
        a_rows = {(x["method"], int(x["rank"])): x for x in predictions if x["rfid_id"] == "A"}
        assert int(a_rows[("B0_full", 1)]["ts"]) == 6
        assert float(a_rows[("B0_full", 1)]["score"]) == .99
        assert int(a_rows[("B0_full", 1)]["source_ordinal"]) == 1
        assert int(a_rows[("U", 1)]["ts"]) == 8
        assert float(a_rows[("U", 1)]["score"]) == .95
        assert int(a_rows[("C", 1)]["ts"]) == 10
        assert float(a_rows[("C", 1)]["score"]) == .98
        assert [int(a_rows[("U", i)]["ts"]) for i in (1, 2)] == [8, 12]
        assert [int(a_rows[("C", i)]["ts"]) for i in (1, 2)] == [10, 14]
        assert [int(x["ts"]) for x in predictions if x["rfid_id"] == "A" and x["method"] == "B0_common"] == [6, 8, 10, 12]
        b_common = [x for x in predictions if x["rfid_id"] == "B" and x["method"] == "B0_common"]
        assert b_common == []
        b_u = [x for x in predictions if x["rfid_id"] == "B" and x["method"] == "U"]
        b_c = [x for x in predictions if x["rfid_id"] == "B" and x["method"] == "C"]
        assert b_u and b_c and all(x["fallback"] == "True" for x in b_u + b_c)
        assert [x["score"] for x in b_u] == [x["score"] for x in b_c] == ["0.8", "0.7"]
        with (Path(tmp) / "event_results.csv").open(encoding="utf-8", newline="") as f:
            events = list(csv.DictReader(f))
        a1 = next(x for x in events if x["acc_id"] == "a1" and x["method"] == "C" and x["k"] == "4")
        a2 = next(x for x in events if x["acc_id"] == "a2" and x["method"] == "C" and x["k"] == "4")
        assert a1["predicted_times"] == a2["predicted_times"]
        b_common_result = next(x for x in events if x["acc_id"] == "b1" and x["method"] == "B0_common")
        assert int(b_common_result["candidate_count"]) == 0
        assert "probability" not in (Path(tmp) / "metrics.json").read_text(encoding="utf-8").lower() or \
            '"probability_outputs": false' in (Path(tmp) / "metrics.json").read_text(encoding="utf-8").lower()
        source_diag = Path(tmp) / "source_diagnostics.json"
        source_diag.write_text('{"fixture": true}\n', encoding="utf-8")
        artifact_dir = Path(tmp) / "artifacts"
        artifact_dir.mkdir()
        copied = _copy_input_diagnostics(source_diag, artifact_dir)
        assert copied.read_text(encoding="utf-8") == source_diag.read_text(encoding="utf-8")
        feature_frame = frame.iloc[:2].copy()
        artifact = _persist_featured_rows(feature_frame, artifact_dir)
        persisted = pd.read_parquet(artifact["path"])
        assert len(persisted) == len(feature_frame)
        assert persisted["ts"].tolist() == feature_frame["ts"].tolist()
        assert artifact["bytes"] > 0 and len(artifact["sha256"]) == 64
    check_random_pool_aggregation()
    print("small data_eval checks passed")


def check_random_pool_aggregation() -> None:
    """Hand-calculated pool expectations for common sizes 1, 3, and 0 fallback."""
    rows = []

    def add(rfid: str, timestamps: list[int], common_timestamps: set[int]):
        for ordinal, ts in enumerate(timestamps, 1):
            is_common = ts in common_timestamps
            rows.append((rfid, ts, ordinal, 1.0 / ordinal, is_common, is_common,
                         .5 if is_common else float("nan"), .5 if is_common else float("nan")))

    add("R1", [0, 10, 20, 30, 40], {0})
    add("R3", [0, 20, 21, 22, 23], {0, 20, 21})
    add("RF", [0, 10, 20, 30, 40], set())
    add("D", [10, 20, 30, 40, 50], set())
    frame = pd.DataFrame(rows, columns=["rfid_id", "ts", "source_ordinal", "score", "geometry_valid",
                                       "history_eligible", "U", "C"])
    positives = pd.DataFrame([
        ("r1", "R1", 1, False, 0), ("r3", "R3", 1, False, 0),
        ("rf", "RF", 1, False, 0), ("d", "D", 2, False, 0),
    ], columns=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"])
    with tempfile.TemporaryDirectory(prefix="round2_random_fixture_", dir=Path(__file__).resolve().parent) as tmp:
        result = evaluate(frame, positives, Path(tmp))
        metrics = result["metrics"]["same_budget_random_expectation"]
        all_scope = metrics["all"]
        tier01 = metrics["tier01"]

        # Base records use the B0_full Kcap: 1, 3, 4, 4, yielding top4 .2,.6,.8,0.
        base = all_scope["pools"]["base"]
        assert [r["kcap"] for r in base["event_probabilities"]] == [1, 3, 4, 4]
        assert [r["n"] for r in base["event_probabilities"]] == [5, 5, 5, 5]
        assert math.isclose(base["mean_top1_expected"], .15)
        assert math.isclose(base["mean_top4_hit_probability"], .4)
        assert math.isclose(tier01["pools"]["base"]["mean_top1_expected"], .2)
        assert math.isclose(tier01["pools"]["base"]["mean_top4_hit_probability"], 8/15)

        # Common has n=1,3,0,0; zero-pool events stay in the unconditional denominator.
        common = all_scope["pools"]["common"]
        assert [r["n"] for r in common["event_probabilities"]] == [1, 3, 0, 0]
        assert math.isclose(common["mean_top1_expected"], 1/3)
        assert math.isclose(common["mean_top4_hit_probability"], .5)
        conditional = all_scope["common_exists_conditional"]
        assert conditional["denominator_events"] == 2
        assert math.isclose(conditional["mean_top1_expected"], 2/3)
        assert math.isclose(conditional["mean_top4_hit_probability"], 1.0)

        # C_matched is common for R1/R3 and base for RF/D; means are separate from both pools.
        matched = all_scope["pools"]["C_matched"]
        assert [r["source_pool"] for r in matched["event_probabilities"]] == ["common", "common", "base", "base"]
        assert [r["fallback"] for r in matched["event_probabilities"]] == [False, False, True, True]
        assert math.isclose(matched["mean_top1_expected"], 23/60)
        assert math.isclose(matched["mean_top4_hit_probability"], .7)
        assert math.isclose(tier01["pools"]["C_matched"]["mean_top1_expected"], 23/45)
        assert math.isclose(tier01["pools"]["C_matched"]["mean_top4_hit_probability"], 14/15)
        gate = tier01["primary_random_gate"]
        assert gate["denominator_events"] == 3
        assert math.isclose(gate["expected_hit_rate"], 23/45)

        event_results = pd.read_csv(Path(tmp) / "event_results.csv")
        b0_common_absent = event_results[(event_results.acc_id == "rf") &
                                         (event_results.method == "B0_common")]
        assert (b0_common_absent.candidate_count == 0).all()
        assert set(b0_common_absent.candidate_count) == {0}


if __name__ == "__main__":
    main()
