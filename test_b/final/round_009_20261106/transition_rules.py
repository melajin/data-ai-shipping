"""Frozen Round9 small-small-non-small transition rules; labels are never used."""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
import math
from typing import Any

import numpy as np
import pandas as pd

KEY = ["rfid_id", "ts", "source_ordinal"]
REQUIRED = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "score"]
STAGE_SPEC = [
    {"stage_id": "s0", "label": "valid current geometry and finite legacy score", "input_stage": None,
     "mask_column": "s0_ok", "status_column": "s0_status", "reason_column": "s0_reason"},
    {"stage_id": "s1", "label": "exact previous two valid geometry hours", "input_stage": "s0",
     "mask_column": "s1_ok", "status_column": "s1_status", "reason_column": "s1_reason"},
    {"stage_id": "s2", "label": "small-small-non-small current transition", "input_stage": "s1",
     "mask_column": "s2_ok", "status_column": "s2_status", "reason_column": "s2_reason"},
    {"stage_id": "s3", "label": "own strict-past transition history", "input_stage": "s2",
     "mask_column": "s3_ok", "status_column": "s3_status", "reason_column": "s3_reason"},
    {"stage_id": "s4", "label": "same-gear peer transition rates", "input_stage": "s3",
     "mask_column": "s4_ok", "status_column": "s4_status", "reason_column": "s4_reason"},
]
SELF_DEFINITION = "own transition rate = own_pattern_n / own_ref_n over all valid contiguous geometry triples ending u in [t-720,t); legacy score does not filter reference triples"
PEER_DEFINITION = "equal-vessel midrank rarity of the own exact rational rate among eligible same-single-gear peer rates at t; rate less/equal uses integer cross-products"


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _geometry_valid(length: Any, bbox: Any) -> bool:
    try:
        return math.isfinite(float(length)) and float(length) >= 0 and math.isfinite(float(bbox)) and float(bbox) >= 0
    except (TypeError, ValueError):
        return False


def _small(length: Any, bbox: Any) -> bool:
    return _geometry_valid(length, bbox) and float(length) <= 100 and float(bbox) <= 100


def _single_code(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


class _ReferenceSweep:
    """Rolling valid-triple history for the exact end-time interval [t-718,t)."""
    def __init__(self, events: list[tuple[int, bool]]):
        self.events = events
        self.next_i = 0
        self.left_i = 0
        self.n = 0
        self.pattern_n = 0
        self.dates: Counter[int] = Counter()
        self.last_t: int | None = None

    def advance(self, t: int) -> None:
        if self.last_t is not None and t < self.last_t:
            raise ValueError("reference sweep must advance in nondecreasing source hours")
        # A reference triple ends u only when u<t; all three timestamps must be
        # in [t-720,t), hence its start u-2 >= t-720, or u >= t-718.
        while self.next_i < len(self.events) and self.events[self.next_i][0] < t:
            u, pattern = self.events[self.next_i]
            self.n += 1
            self.pattern_n += int(pattern)
            self.dates[u // 24] += 1
            self.next_i += 1
        low_end = t - 718
        while self.left_i < self.next_i and self.events[self.left_i][0] < low_end:
            u, pattern = self.events[self.left_i]
            self.n -= 1
            self.pattern_n -= int(pattern)
            day = u // 24
            self.dates[day] -= 1
            if self.dates[day] == 0:
                del self.dates[day]
            self.left_i += 1
        self.last_t = t

    @property
    def n_dates(self) -> int:
        return len(self.dates)

    @property
    def eligible(self) -> bool:
        return self.n >= 24 and self.n_dates >= 3


def _legacy_rank(ids: list[int], frame: pd.DataFrame) -> list[int]:
    return sorted(ids, key=lambda i: (-float(frame.at[i, "score"]), int(frame.at[i, "ts"]), int(frame.at[i, "source_ordinal"])))


def _g_rank(ids: list[int], frame: pd.DataFrame) -> list[int]:
    # Fraction comparison is exact; the legacy score resolves only an exact
    # peer-rarity tie, then source time and ordinal are ascending.
    return sorted(ids, key=lambda i: (-Fraction(int(frame.at[i, "peer_rate_rarity_num"]),
                                               int(frame.at[i, "peer_rate_rarity_den"])),
                                      -float(frame.at[i, "score"]), int(frame.at[i, "ts"]),
                                      int(frame.at[i, "source_ordinal"])))


def build_transition_rules(frame: pd.DataFrame, gear_registry: pd.DataFrame) -> dict[str, Any]:
    """Build the Round9 all-row ledger and B0/S/G candidate lists.

    ``triplet_valid`` and ``pattern`` are raw geometry-only masks, independent
    of current legacy-score validity. Rule stages additionally require s0.
    No event, accident, label, R6 run-length, or R8 shape-rarity input is used.
    """
    if not isinstance(frame, pd.DataFrame) or not isinstance(gear_registry, pd.DataFrame):
        raise TypeError("frame and gear_registry must be pandas DataFrames")
    forbidden = [c for c in frame.columns if any(term in str(c).lower()
                 for term in ("acc_id", "accident", "event", "label", "positive", "incident"))]
    if forbidden:
        raise ValueError(f"event/label columns are forbidden in transition-rule input: {forbidden}")
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"missing required input columns: {missing}")
    if not {"rfid_id", "primary_gear", "is_single_code"}.issubset(gear_registry.columns):
        raise ValueError("gear_registry requires rfid_id,primary_gear,is_single_code")
    if frame["rfid_id"].isna().any() or frame["ts"].isna().any():
        raise ValueError("rfid_id and source-clock ts cannot be null")
    if not pd.api.types.is_integer_dtype(frame["ts"].dtype):
        raise ValueError("ts must be integer source-clock epoch-hours; fractional/float columns are rejected")
    if not pd.api.types.is_integer_dtype(frame["source_ordinal"].dtype):
        raise ValueError("source_ordinal must be integer")
    if gear_registry["rfid_id"].isna().any() or gear_registry["rfid_id"].astype(str).duplicated().any():
        raise ValueError("gear_registry RFID must be non-null and unique")

    ledger = frame.copy(deep=True).reset_index(drop=True)
    ledger["rfid_id"] = ledger["rfid_id"].astype(str)
    ledger["ts"] = ledger["ts"].astype("int64")
    ledger["source_ordinal"] = ledger["source_ordinal"].astype("int64")
    if ledger.duplicated(["rfid_id", "ts"]).any():
        raise ValueError("input must contain unique (rfid_id, ts) keys")
    if ledger.duplicated(KEY).any():
        raise ValueError("input must contain unique (rfid_id, ts, source_ordinal) keys")
    ledger["_order"] = np.arange(len(ledger), dtype=np.int64)

    registry = gear_registry[["rfid_id", "primary_gear", "is_single_code"]].copy()
    registry["rfid_id"] = registry["rfid_id"].astype(str)
    gear_map: dict[str, tuple[Any, bool]] = {}
    for row in registry.itertuples(index=False):
        gear_value = None if pd.isna(row.primary_gear) or str(row.primary_gear).strip() == "" else str(row.primary_gear)
        gear_map[str(row.rfid_id)] = (gear_value, bool(gear_value is not None and _single_code(row.is_single_code)))
    ledger["primary_gear"] = [gear_map.get(r, (None, False))[0] for r in ledger["rfid_id"]]
    ledger["is_single_code"] = [gear_map.get(r, (None, False))[1] for r in ledger["rfid_id"]]

    n_rows = len(ledger)
    geometry_ok = [_geometry_valid(l, b) for l, b in zip(ledger["len_m"], ledger["bbox_m"])]
    small = [_small(l, b) for l, b in zip(ledger["len_m"], ledger["bbox_m"])]
    score_ok = [_finite(s) for s in ledger["score"]]
    groups: dict[str, list[int]] = defaultdict(list)
    time_maps: dict[str, dict[int, int]] = defaultdict(dict)
    for i, (rid, t) in enumerate(zip(ledger["rfid_id"], ledger["ts"])):
        rid, t = str(rid), int(t)
        groups[rid].append(i)
        time_maps[rid][t] = i
    for rid in groups:
        groups[rid].sort(key=lambda i: int(ledger.at[i, "ts"]))

    # Raw triplet masks are entirely geometry/time based, including rows whose
    # current or prior legacy scores are NaN.
    prev2_observed = [False] * n_rows
    prev1_observed = [False] * n_rows
    prev2_valid = [False] * n_rows
    prev1_valid = [False] * n_rows
    prev2_small = [False] * n_rows
    prev1_small = [False] * n_rows
    prev2_ordinal: list[int | None] = [None] * n_rows
    prev1_ordinal: list[int | None] = [None] * n_rows
    triplet_valid = [False] * n_rows
    pattern = [False] * n_rows
    history_events: dict[str, list[tuple[int, bool]]] = {}
    raw_counts: dict[str, dict[str, int]] = {rid: {"valid_triple_n": 0, "pattern_n": 0} for rid in gear_map}
    for rid, indices in groups.items():
        by_time = time_maps[rid]
        events: list[tuple[int, bool]] = []
        for i in indices:
            t = int(ledger.at[i, "ts"])
            j2, j1 = by_time.get(t - 2), by_time.get(t - 1)
            prev2_observed[i] = j2 is not None
            prev1_observed[i] = j1 is not None
            if j2 is not None:
                prev2_valid[i] = geometry_ok[j2]
                prev2_small[i] = small[j2] if geometry_ok[j2] else False
                prev2_ordinal[i] = int(ledger.at[j2, "source_ordinal"])
            if j1 is not None:
                prev1_valid[i] = geometry_ok[j1]
                prev1_small[i] = small[j1] if geometry_ok[j1] else False
                prev1_ordinal[i] = int(ledger.at[j1, "source_ordinal"])
            valid = j2 is not None and j1 is not None and geometry_ok[j2] and geometry_ok[j1] and geometry_ok[i]
            trans = bool(valid and small[j2] and small[j1] and not small[i])
            triplet_valid[i] = bool(valid)
            pattern[i] = trans
            if valid:
                events.append((t, trans))
                raw_counts.setdefault(rid, {"valid_triple_n": 0, "pattern_n": 0})["valid_triple_n"] += 1
                raw_counts[rid]["pattern_n"] += int(trans)
        history_events[rid] = events

    ledger["prev2_observed"] = prev2_observed
    ledger["prev2_geometry_valid"] = prev2_valid
    ledger["prev2_small"] = prev2_small
    ledger["prev2_source_ordinal"] = prev2_ordinal
    ledger["prev1_observed"] = prev1_observed
    ledger["prev1_geometry_valid"] = prev1_valid
    ledger["prev1_small"] = prev1_small
    ledger["prev1_source_ordinal"] = prev1_ordinal
    ledger["triplet_valid"] = triplet_valid
    ledger["pattern"] = pattern
    ledger["self_definition"] = SELF_DEFINITION
    ledger["peer_definition"] = PEER_DEFINITION

    ledger["s0_ok"] = [bool(geometry_ok[i] and score_ok[i]) for i in range(n_rows)]
    ledger["s1_ok"] = [bool(ledger.at[i, "s0_ok"] and prev2_observed[i] and prev1_observed[i] and prev2_valid[i] and prev1_valid[i]) for i in range(n_rows)]
    ledger["s2_ok"] = [bool(ledger.at[i, "s1_ok"] and pattern[i]) for i in range(n_rows)]
    ledger["s3_ok"] = False
    ledger["s4_ok"] = False
    ledger["own_ref_n"] = 0
    ledger["own_ref_dates"] = 0
    ledger["own_pattern_n"] = 0
    ledger["own_transition_rate"] = np.nan
    ledger["own_rate_num"] = 0
    ledger["own_rate_den"] = 0
    ledger["peer_eligible_n"] = 0
    ledger["peer_rate_less_n"] = 0
    ledger["peer_rate_equal_n"] = 0
    ledger["peer_rate_midrank"] = np.nan
    ledger["peer_rate_rarity"] = np.nan
    ledger["peer_rate_rarity_num"] = 0
    ledger["peer_rate_rarity_den"] = 1

    sweeps = {rid: _ReferenceSweep(events) for rid, events in history_events.items()}
    gear_vessels: dict[str, list[str]] = defaultdict(list)
    for rid, (gear, single) in gear_map.items():
        if single and gear is not None:
            gear_vessels[gear].append(rid)
    for vessels in gear_vessels.values():
        vessels.sort()
    rows_by_time: dict[int, list[int]] = defaultdict(list)
    for i, t in enumerate(ledger["ts"].tolist()):
        rows_by_time[int(t)].append(i)

    # One sorted global sweep advances all vessels' bounded history windows.
    for t in sorted(rows_by_time):
        for sweep in sweeps.values():
            sweep.advance(t)
        for i in rows_by_time[t]:
            rid = str(ledger.at[i, "rfid_id"])
            own = sweeps[rid]
            ledger.at[i, "own_ref_n"] = own.n
            ledger.at[i, "own_ref_dates"] = own.n_dates
            ledger.at[i, "own_pattern_n"] = own.pattern_n
            ledger.at[i, "own_rate_num"] = own.pattern_n
            ledger.at[i, "own_rate_den"] = own.n
            if own.n:
                ledger.at[i, "own_transition_rate"] = own.pattern_n / own.n
            if ledger.at[i, "s2_ok"] and own.eligible:
                ledger.at[i, "s3_ok"] = True
            if not ledger.at[i, "s3_ok"]:
                continue
            gear, single = gear_map.get(rid, (None, False))
            if gear is None or not single:
                continue
            less = equal = peer_n = 0
            for peer_rid in gear_vessels.get(gear, []):
                if peer_rid == rid:
                    continue
                peer = sweeps.get(peer_rid)
                if peer is None or not peer.eligible:
                    continue
                peer_n += 1
                left = peer.pattern_n * own.n
                right = own.pattern_n * peer.n
                if left < right:
                    less += 1
                elif left == right:
                    equal += 1
            ledger.at[i, "peer_eligible_n"] = peer_n
            ledger.at[i, "peer_rate_less_n"] = less
            ledger.at[i, "peer_rate_equal_n"] = equal
            if peer_n:
                midrank_num = 2 * less + equal
                midrank_den = 2 * peer_n
                rarity_num = midrank_den - midrank_num
                rarity_fraction = Fraction(rarity_num, midrank_den)
                ledger.at[i, "peer_rate_midrank"] = midrank_num / midrank_den
                ledger.at[i, "peer_rate_rarity"] = float(rarity_fraction)
                ledger.at[i, "peer_rate_rarity_num"] = rarity_num
                ledger.at[i, "peer_rate_rarity_den"] = midrank_den
            if peer_n >= 5:
                ledger.at[i, "s4_ok"] = True

    # Status distinguishes branch rejection from unavailable evidence.
    for stage in range(5):
        statuses, reasons = [], []
        for i in range(n_rows):
            ok = bool(ledger.at[i, f"s{stage}_ok"])
            prior_failed = stage > 0 and not bool(ledger.at[i, f"s{stage-1}_ok"])
            if ok:
                status, reason = "keep", "passed"
            elif prior_failed:
                status, reason = "not_applicable", f"upstream_s{stage-1}_failed"
            elif stage == 0:
                status, reason = "defer", "invalid_current_geometry_or_nonfinite_legacy_score"
            elif stage == 1:
                status, reason = "defer", "missing_or_invalid_exact_t_minus_2_or_t_minus_1_geometry"
            elif stage == 2:
                status, reason = "reject", "current_triplet_is_not_small_small_non_small"
            elif stage == 3:
                status, reason = "defer", "insufficient_24_valid_reference_triples_or_3_end_dates"
            else:
                gear, single = gear_map.get(str(ledger.at[i, "rfid_id"]), (None, False))
                if gear is None or not single:
                    reason = "unknown_or_non_single_gear"
                elif int(ledger.at[i, "peer_eligible_n"]) < 5:
                    reason = "fewer_than_5_other_same_gear_history_eligible_vessels"
                else:
                    reason = "peer_rarity_unavailable"
                status = "defer"
            statuses.append(status)
            reasons.append(reason)
        ledger[f"s{stage}_status"] = statuses
        ledger[f"s{stage}_reason"] = reasons

    # Keep all observed RFID rows in raw inventory, including registry-only zeroes.
    per_vessel_raw = []
    for rid in sorted(set(raw_counts) | set(ledger["rfid_id"])):
        counts = raw_counts.get(rid, {"valid_triple_n": 0, "pattern_n": 0})
        gear, _ = gear_map.get(rid, (None, False))
        per_vessel_raw.append({"rfid_id": rid, "primary_gear": gear,
                               "valid_triple_n": int(counts["valid_triple_n"]), "pattern_n": int(counts["pattern_n"])})
    per_gear_inventory: dict[str, dict[str, int]] = {}
    for item in per_vessel_raw:
        gear = str(item["primary_gear"] or "unknown")
        agg = per_gear_inventory.setdefault(gear, {"vessel_n": 0, "valid_triple_n": 0, "pattern_n": 0})
        agg["vessel_n"] += 1
        agg["valid_triple_n"] += item["valid_triple_n"]
        agg["pattern_n"] += item["pattern_n"]
    raw_valid_total = sum(x["valid_triple_n"] for x in per_vessel_raw)
    raw_pattern_total = sum(x["pattern_n"] for x in per_vessel_raw)
    per_gear_stages = {}
    for gear in sorted(str(x) for x in ledger["primary_gear"].dropna().unique()):
        subset = ledger[ledger["primary_gear"] == gear]
        per_gear_stages[gear] = {f"s{s}_{name}": int(subset[f"s{s}_ok"].sum()) for s in range(5) for name in ("keep",)}

    # Exact fixed-stage pools and one shared per-RFID cap.
    predictions: list[dict[str, Any]] = []
    pool_manifest: list[dict[str, Any]] = []
    all_rfids = list(dict.fromkeys(ledger["rfid_id"].tolist()))
    top_sets: dict[tuple[str, str], dict[str, tuple[int, ...]]] = {}
    fallback_counts: dict[str, Counter[str]] = {m: Counter() for m in ("B0", "S", "G")}
    for rid in all_rfids:
        ids = ledger.index[ledger["rfid_id"] == rid].tolist()
        s0_ids = [i for i in ids if bool(ledger.at[i, "s0_ok"])]
        s2_ids = [i for i in ids if bool(ledger.at[i, "s2_ok"])]
        s4_ids = [i for i in ids if bool(ledger.at[i, "s4_ok"])]
        pools: dict[str, tuple[str, list[int], str | None]] = {
            "B0": ("s0", s0_ids, None),
            "S": ("s2", s2_ids, None),
            "G": ("s4", s4_ids, None),
        }
        if not s2_ids:
            pools["S"] = ("s0", s0_ids, "s2_empty_use_s0")
        if not s4_ids:
            pools["G"] = (pools["S"][0], pools["S"][1], f"s4_empty_use_{pools['S'][0]}")
        cap = min(4, len(pools["G"][1]))
        for method, (pool_stage, pool_ids, fallback) in pools.items():
            if fallback:
                fallback_counts[method][fallback] += 1
            pool_manifest.append({"rfid_id": rid, "method": method, "pool_stage": pool_stage,
                                  "actual_pool_n": len(pool_ids), "cap": cap, "fallback_reason": fallback})
            ordered = _g_rank(pool_ids, ledger) if pool_stage == "s4" else _legacy_rank(pool_ids, ledger)
            selected = ordered[:cap]
            top_sets.setdefault((method, "top1"), {})[rid] = tuple(selected[:1])
            top_sets.setdefault((method, "top4"), {})[rid] = tuple(selected[:4])
            for rank, i in enumerate(selected, 1):
                uses_peer = pool_stage == "s4"
                method_score = float(ledger.at[i, "peer_rate_rarity"]) if uses_peer else float(ledger.at[i, "score"])
                predictions.append({"rfid_id": rid, "method": method, "rank": rank, "ts": int(ledger.at[i, "ts"]),
                    "ordinal": int(ledger.at[i, "source_ordinal"]), "method_score": method_score,
                    "secondary_score": None, "legacy_score": float(ledger.at[i, "score"]),
                    "score_kind": "peer_rate_rarity" if uses_peer else "legacy",
                    "actual_pool_n": len(pool_ids), "cap": cap, "fallback_reason": fallback})

    def n_changed(a: str, b: str, depth: str) -> int:
        return sum(top_sets[(a, depth)].get(r, ()) != top_sets[(b, depth)].get(r, ()) for r in all_rfids)
    g_s_changes = {"top1_rfids_changed": n_changed("G", "S", "top1"),
                   "top4_rfids_changed": n_changed("G", "S", "top4"), "denominator_rfids": len(all_rfids)}
    diagnostics = {
        "row_count": n_rows, "rfid_count": len(all_rfids),
        "inventory_counts": {"valid_triple_n": raw_valid_total, "pattern_n": raw_pattern_total,
            "per_gear": per_gear_inventory, "per_vessel": per_vessel_raw,
            "definition": "all exact contiguous geometry-valid triples; pattern mask independent of current legacy-score validity"},
        "per_gear_stage_counts": per_gear_stages,
        "reference_history": {"valid_triple_unit": "one exact (u-2,u-1,u) with finite nonnegative len_m/bbox_m at all three hours",
            "window": "all three hours in [t-720,t); end u in [t-718,t)", "endpoints_inclusive": True,
            "pattern_counts_are_subset_of_valid_reference_triples": True,
            "min_valid_triples": 24, "min_distinct_end_dates": 3},
        "fallback_counts_by_method": {m: dict(v) for m, v in fallback_counts.items()},
        "G_vs_S_selected_changes": g_s_changes,
        "rate_definitions": {"self": SELF_DEFINITION, "peer": PEER_DEFINITION},
    }
    ledger = ledger.sort_values("_order", kind="stable").drop(columns=["_order"]).reset_index(drop=True)
    pred_cols = ["rfid_id", "method", "rank", "ts", "ordinal", "method_score", "secondary_score", "legacy_score",
                 "score_kind", "actual_pool_n", "cap", "fallback_reason"]
    pool_cols = ["rfid_id", "method", "pool_stage", "actual_pool_n", "cap", "fallback_reason"]
    return {"ledger": ledger, "predictions": pd.DataFrame(predictions, columns=pred_cols),
            "pool_manifest": pd.DataFrame(pool_manifest, columns=pool_cols),
            "diagnostics": diagnostics, "stage_spec": STAGE_SPEC}
