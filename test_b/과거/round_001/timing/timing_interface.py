"""A/B/C timing-selection interface for synthetic checks and later approved use.

This module has no file I/O and does not fit scores, thresholds, or calibrators.
Calling it on real rows is gated by parameters that are intentionally unresolved.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Any, Iterable, Mapping


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class TimingParams:
    threshold: float
    exceedance: str  # "gt" or "ge"; strictness is a decision, never inferred.
    max_gap_hours: float
    persistence_min_hours: float
    persistence_min_rows: int
    threshold_source: str

    def validate(self) -> None:
        for name in ("threshold", "max_gap_hours", "persistence_min_hours"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ContractError(f"{name} must be a finite numeric parameter")
        if self.exceedance not in {"gt", "ge"}:
            raise ContractError("exceedance must be explicitly 'gt' or 'ge'")
        if self.max_gap_hours <= 0:
            raise ContractError("max_gap_hours must be positive")
        if self.max_gap_hours > 1:
            raise ContractError("hourly input cannot set max_gap_hours above 1")
        if self.persistence_min_hours < 0:
            raise ContractError("persistence_min_hours cannot be negative")
        if isinstance(self.persistence_min_rows, bool) or not isinstance(self.persistence_min_rows, int) or self.persistence_min_rows < 1:
            raise ContractError("persistence_min_rows must be a positive integer")
        if not isinstance(self.threshold_source, str) or not self.threshold_source.strip():
            raise ContractError("threshold_source is required; no score-derived default exists")


@dataclass
class Estimate:
    status: str
    reason: str | None
    a_ts: int | None = None
    a_score: float | None = None
    a_source_row: str | None = None
    b_ts: int | None = None
    b_score: float | None = None
    b_source_row: str | None = None
    c_ts: int | None = None
    c_score: float | None = None
    c_source_row: str | None = None
    c_passed: bool | None = None
    segment_source_rows: list[str] | None = None
    duplicate_timestamp_rows: int = 0
    conflict_source_rows: list[str] | None = None


def _validated_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict], list[dict], int, list[str] | None]:
    clean: list[dict] = []
    for ordinal, raw in enumerate(rows):
        if "ts" not in raw or "score" not in raw:
            raise ContractError("each row needs ts (integer hour) and score")
        ts = raw["ts"]
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or int(ts) != ts:
            raise ContractError("ts must be a finite integer hour index")
        score = raw["score"]
        if score is not None:
            try:
                score = float(score)
            except (TypeError, ValueError) as exc:
                raise ContractError("score must be numeric or null/NaN") from exc
            if not math.isfinite(score):
                score = None
        source = raw.get("source_row_id", raw.get("source_row", ordinal))
        clean.append({"ts": int(ts), "score": score, "source": str(source), "ordinal": ordinal})
    # Keep input order for A/idxmax semantics. The time-sorted view is used only for B/C runs.
    time_sorted = sorted(clean, key=lambda r: (r["ts"], r["ordinal"]))
    duplicate_count = sum(1 for i in range(1, len(time_sorted)) if time_sorted[i]["ts"] == time_sorted[i - 1]["ts"])
    conflicts: list[str] = []
    by_ts: dict[int, list[dict]] = {}
    for row in time_sorted:
        by_ts.setdefault(row["ts"], []).append(row)
    for same_time in by_ts.values():
        if len(same_time) < 2:
            continue
        values = {row["score"] for row in same_time}  # None represents both None and non-finite/NaN.
        if len(values) > 1:
            conflicts.extend(row["source"] for row in same_time)
    return clean, time_sorted, duplicate_count, conflicts or None


def estimate_vessel(rows: Iterable[Mapping[str, Any]], params: TimingParams) -> Estimate:
    """Compute A, B and C for one vessel using explicit, externally fixed parameters.

    A picks the first maximum in the original input order, matching idxmax semantics.
    A time-sorted view is used only to find B/C. B is the onset of the anomalous
    segment containing A. A segment consists only of finite above-threshold rows whose
    adjacent timestamps are no farther apart than max_gap_hours; a NaN row breaks it.
    C tests persistence of that same segment and, on pass, returns exactly B.
    """
    params.validate()
    data, time_sorted, n_dups, conflict_sources = _validated_rows(rows)
    if conflict_sources is not None:
        return Estimate("data_conflict", "duplicate_timestamp_scores_conflict",
                        duplicate_timestamp_rows=n_dups, conflict_source_rows=conflict_sources)
    valid = [r for r in data if r["score"] is not None]
    if not valid:
        return Estimate("insufficient_data", "no_finite_scores", duplicate_timestamp_rows=n_dups)
    peak = max(r["score"] for r in valid)
    a = next(r for r in data if r["score"] is not None and r["score"] == peak)  # first input-order max / idxmax
    over = lambda x: x > params.threshold if params.exceedance == "gt" else x >= params.threshold
    if not over(a["score"]):
        return Estimate("threshold_not_crossed", "peak_does_not_exceed_threshold",
                        a["ts"], a["score"], a["source"], duplicate_timestamp_rows=n_dups)

    segments: list[list[dict]] = []
    current: list[dict] = []
    previous: dict | None = None
    for row in time_sorted:
        if row["score"] is None or not over(row["score"]):
            if current:
                segments.append(current)
            current, previous = [], None
            continue
        if previous is not None and row["ts"] - previous["ts"] > params.max_gap_hours:
            if current:
                segments.append(current)
            current = []
        current.append(row)
        previous = row
    if current:
        segments.append(current)
    segment = next((s for s in segments if any(r is a for r in s)), None)
    if segment is None:  # defensive contract check
        return Estimate("calculation_error", "peak_not_in_anomaly_segment", a["ts"], a["score"], a["source"], duplicate_timestamp_rows=n_dups)
    b = segment[0]
    span = segment[-1]["ts"] - segment[0]["ts"]
    # Duplicate rows are retained for traceability but never masquerade as extra
    # independent timestamps when the persistence row minimum is evaluated.
    unique_timestamp_count = len({r["ts"] for r in segment})
    c_ok = unique_timestamp_count >= params.persistence_min_rows and span >= params.persistence_min_hours
    return Estimate(
        "candidate_ready" if c_ok else "persistence_not_met",
        None if c_ok else "same_peak_segment_failed_persistence",
        a["ts"], a["score"], a["source"], b["ts"], b["score"], b["source"],
        b["ts"] if c_ok else None, b["score"] if c_ok else None,
        b["source"] if c_ok else None, c_ok,
        [r["source"] for r in segment], n_dups,
    )


def estimate_to_dict(result: Estimate) -> dict:
    return asdict(result)


def synthetic_self_check() -> dict:
    """Boundary checks only; values below are synthetic and not candidate thresholds."""
    p = TimingParams(0.5, "gt", 1, 2, 3, "synthetic-only")
    rows = [
        {"ts": 4, "score": .6, "source_row_id": "r4"},
        {"ts": 1, "score": .5, "source_row_id": "eq"},
        {"ts": 2, "score": .7, "source_row_id": "r2"},
        {"ts": 3, "score": .7, "source_row_id": "r3"},
    ]
    r = estimate_vessel(rows, p)
    assert (r.a_ts, r.a_source_row, r.b_ts, r.c_ts, r.c_passed) == (2, "r2", 2, 2, True)
    assert r.segment_source_rows == ["r2", "r3", "r4"]  # C=B in the same run

    # A tie follows unsorted source order (idxmax); time sorting is only for segment search.
    tie_order = estimate_vessel([
        {"ts": 9, "score": .9, "source_row_id": "input_first_late"},
        {"ts": 2, "score": .9, "source_row_id": "input_second_early"},
        {"ts": 1, "score": .4, "source_row_id": "low"},
    ], TimingParams(.5, "gt", 1, 0, 1, "synthetic-only"))
    assert (tie_order.a_ts, tie_order.a_source_row, tie_order.b_ts) == (9, "input_first_late", 9)

    # A missing hourly bin splits the segment; a wider configured tolerance is invalid.
    gap = estimate_vessel([
        {"ts": 0, "score": .8, "source_row_id": "early"},
        {"ts": 2, "score": .9, "source_row_id": "peak"},
    ], p)
    assert gap.b_ts == 2 and gap.segment_source_rows == ["peak"]
    assert gap.status == "persistence_not_met"

    try:
        TimingParams(.5, "gt", 2, 0, 1, "synthetic-only").validate()
    except ContractError:
        pass
    else:
        raise AssertionError("max_gap_hours > 1 must be rejected for hourly input")

    two_hour_gap = estimate_vessel([
        {"ts": 0, "score": .8, "source_row_id": "hour0"},
        {"ts": 2, "score": .9, "source_row_id": "hour2"},
    ], TimingParams(.5, "gt", 1, 0, 1, "synthetic-only"))
    assert two_hour_gap.b_ts == 2 and two_hour_gap.segment_source_rows == ["hour2"]

    # NaN breaks a run even when the timestamps around it are close.
    nan_break = estimate_vessel([
        {"ts": 0, "score": .8, "source_row_id": "before"},
        {"ts": 1, "score": float("nan"), "source_row_id": "nan"},
        {"ts": 2, "score": .9, "source_row_id": "peak"},
    ], p)
    assert nan_break.b_ts == 2 and nan_break.segment_source_rows == ["peak"]

    # Duplicate timestamps stay traceable and do not imply elapsed persistence.
    dup = estimate_vessel([
        {"ts": 1, "score": .9, "source_row_id": "first"},
        {"ts": 1, "score": .9, "source_row_id": "second"},
    ], TimingParams(.5, "gt", 1, 0, 2, "synthetic-only"))
    assert dup.a_source_row == "first" and dup.duplicate_timestamp_rows == 1
    assert dup.status == "persistence_not_met" and dup.c_ts is None

    same_duplicate = estimate_vessel([
        {"ts": 1, "score": .9, "source_row_id": "same_a"},
        {"ts": 1, "score": .9, "source_row_id": "same_b"},
    ], TimingParams(.5, "gt", 1, 0, 1, "synthetic-only"))
    assert same_duplicate.status == "candidate_ready" and same_duplicate.c_ts == same_duplicate.b_ts == 1
    assert same_duplicate.segment_source_rows == ["same_a", "same_b"]
    assert same_duplicate.duplicate_timestamp_rows == 1

    conflict = estimate_vessel([
        {"ts": 1, "score": .8, "source_row_id": "conflict_a"},
        {"ts": 1, "score": .9, "source_row_id": "conflict_b"},
    ], TimingParams(.5, "gt", 1, 0, 1, "synthetic-only"))
    assert conflict.status == "data_conflict"
    assert conflict.reason == "duplicate_timestamp_scores_conflict"
    assert all(v is None for v in (conflict.a_ts, conflict.a_score, conflict.a_source_row,
                                    conflict.b_ts, conflict.b_score, conflict.b_source_row,
                                    conflict.c_ts, conflict.c_score, conflict.c_source_row, conflict.c_passed))
    assert conflict.conflict_source_rows == ["conflict_a", "conflict_b"]

    missing_duplicates = estimate_vessel([
        {"ts": 1, "score": None, "source_row_id": "missing_none"},
        {"ts": 1, "score": float("nan"), "source_row_id": "missing_nan"},
    ], TimingParams(.5, "gt", 1, 0, 1, "synthetic-only"))
    assert missing_duplicates.status == "insufficient_data" and missing_duplicates.duplicate_timestamp_rows == 1
    missing_conflict = estimate_vessel([
        {"ts": 1, "score": None, "source_row_id": "missing"},
        {"ts": 1, "score": .9, "source_row_id": "valid"},
    ], TimingParams(.5, "gt", 1, 0, 1, "synthetic-only"))
    assert missing_conflict.status == "data_conflict"
    assert missing_conflict.conflict_source_rows == ["missing", "valid"]

    ge = estimate_vessel([{"ts": 0, "score": .5}], TimingParams(.5, "ge", 1, 0, 1, "synthetic-only"))
    assert ge.status == "candidate_ready"
    strict = estimate_vessel([{"ts": 0, "score": .5}], TimingParams(.5, "gt", 1, 0, 1, "synthetic-only"))
    assert strict.status == "threshold_not_crossed"
    empty = estimate_vessel([{"ts": 0, "score": None}], p)
    assert empty.status == "insufficient_data"
    return {"status": "passed", "checks": 14, "synthetic_only": True}


if __name__ == "__main__":
    import json
    print(json.dumps(synthetic_self_check(), ensure_ascii=False, sort_keys=True))
