"""Frozen Round8 B0/S/G shape-history rule builder; no labels/events are used."""
from __future__ import annotations

import bisect
import math
from collections import Counter, defaultdict
from typing import Any

import numpy as np
import pandas as pd

KEY = ["rfid_id", "ts", "source_ordinal"]
GEOMETRY_FIELDS = ["n_parts", "n_informative_parts", "chosen_part_index", "chosen_n_points",
                   "chosen_n_unique", "chosen_path_m", "chosen_endpoint_m", "shape_dl",
                   "geometry_status", "geometry_reason"]
REQUIRED = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "score", *GEOMETRY_FIELDS]
STAGES = [
    {"stage_id": "s0", "label": "finite nonnegative base features", "input_stage": None,
     "mask_column": "s0_ok", "status_column": "s0_status", "reason_column": "s0_reason"},
    {"stage_id": "s1", "label": "non-small observation", "input_stage": "s0",
     "mask_column": "s1_ok", "status_column": "s1_status", "reason_column": "s1_reason"},
    {"stage_id": "s2", "label": "informative chosen-part shape", "input_stage": "s1",
     "mask_column": "s2_ok", "status_column": "s2_status", "reason_column": "s2_reason"},
    {"stage_id": "s3", "label": "own strict-past shape history", "input_stage": "s2",
     "mask_column": "s3_ok", "status_column": "s3_status", "reason_column": "s3_reason"},
    {"stage_id": "s4", "label": "same-code peer history", "input_stage": "s3",
     "mask_column": "s4_ok", "status_column": "s4_status", "reason_column": "s4_reason"},
]


class Fenwick:
    """Small integer frequency tree over a vessel's compressed historical shapes."""
    def __init__(self, n: int):
        self.tree = [0] * (n + 1)

    def add(self, i: int, delta: int) -> None:
        i += 1
        while i < len(self.tree):
            self.tree[i] += delta
            i += i & -i

    def prefix(self, stop: int) -> int:
        # Sum of compressed values with index < stop.
        out = 0
        i = stop
        while i:
            out += self.tree[i]
            i -= i & -i
        return out

    def total(self) -> int:
        return self.prefix(len(self.tree) - 1)


class HistorySweep:
    """Rolling [t-720,t) s2 history, advanced in ascending source-clock hour."""
    def __init__(self, rows: list[tuple[int, float]]):
        self.times = [t for t, _ in rows]
        self.values = [x for _, x in rows]
        self.days = [t // 24 for t, _ in rows]
        self.coords = sorted(set(self.values))
        self.coord_index = {x: i for i, x in enumerate(self.coords)}
        self.tree = Fenwick(len(self.coords))
        self.day_counts: Counter[int] = Counter()
        self.lo = self.hi = 0
        self.last_t: int | None = None

    def advance(self, t: int) -> None:
        if self.last_t is not None and t < self.last_t:
            raise ValueError("HistorySweep times must be nondecreasing")
        while self.hi < len(self.times) and self.times[self.hi] < t:
            self.tree.add(self.coord_index[self.values[self.hi]], 1)
            self.day_counts[self.days[self.hi]] += 1
            self.hi += 1
        low_t = t - 720
        while self.lo < self.hi and self.times[self.lo] < low_t:
            self.tree.add(self.coord_index[self.values[self.lo]], -1)
            self.day_counts[self.days[self.lo]] -= 1
            if not self.day_counts[self.days[self.lo]]:
                del self.day_counts[self.days[self.lo]]
            self.lo += 1
        self.last_t = t

    @property
    def n(self) -> int:
        return self.hi - self.lo

    @property
    def n_dates(self) -> int:
        return len(self.day_counts)

    @property
    def eligible(self) -> bool:
        return self.n >= 24 and self.n_dates >= 3

    def cdf(self, x: float) -> float | None:
        if not self.n:
            return None
        left = bisect.bisect_left(self.coords, x)
        right = bisect.bisect_right(self.coords, x)
        below = self.tree.prefix(left)
        equal = self.tree.prefix(right) - below
        return (below + 0.5 * equal) / self.n

    def rarity(self, x: float) -> tuple[float | None, float | None]:
        p = self.cdf(x)
        return p, (1.0 - 2.0 * min(p, 1.0 - p)) if p is not None else None


def _finite_nonnegative(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) >= 0
    except (TypeError, ValueError):
        return False


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _single_code(v: Any) -> bool:
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return str(v).strip().lower() in {"true", "1", "yes", "y"}


def _shape_valid(row: Any) -> bool:
    try:
        return (row.geometry_status == "informative" and bool(row.n_informative_parts >= 1)
                and int(row.chosen_n_unique) >= 3 and float(row.chosen_path_m) > 0
                and math.isfinite(float(row.shape_dl)) and 0 <= float(row.shape_dl) <= 1)
    except (TypeError, ValueError):
        return False


def _rank_indices(indices: list[int], frame: pd.DataFrame, *, stage: str) -> list[int]:
    if stage == "s0":
        return sorted(indices, key=lambda i: (-float(frame.at[i, "score"]), int(frame.at[i, "ts"]), int(frame.at[i, "source_ordinal"])))
    if stage == "s3":
        return sorted(indices, key=lambda i: (-float(frame.at[i, "self_rarity"]), -float(frame.at[i, "score"]), int(frame.at[i, "ts"]), int(frame.at[i, "source_ordinal"])))
    if stage == "s4":
        return sorted(indices, key=lambda i: (-float(frame.at[i, "self_rarity"]), -float(frame.at[i, "peer_rarity_mean"]),
                                               -float(frame.at[i, "score"]), int(frame.at[i, "ts"]), int(frame.at[i, "source_ordinal"])))
    raise ValueError(stage)


def build_shape_rules(frame: pd.DataFrame, gear_registry: pd.DataFrame) -> dict[str, Any]:
    """Build rule ledger and same-budget B0/S/G pools.

    Input order is retained in ledger. Event/label columns are rejected and never
    consulted. ``ts`` must already be integer naive source-clock epoch-hours.
    """
    if not isinstance(frame, pd.DataFrame) or not isinstance(gear_registry, pd.DataFrame):
        raise TypeError("frame and gear_registry must be pandas DataFrames")
    forbidden = [c for c in frame.columns if any(s in str(c).lower() for s in ("acc_id", "accident", "event", "label", "positive", "incident"))]
    if forbidden:
        raise ValueError(f"event/label columns are forbidden in rule input: {forbidden}")
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"missing required input columns: {missing}")
    if not {"rfid_id", "primary_gear", "is_single_code"}.issubset(gear_registry.columns):
        raise ValueError("gear_registry requires rfid_id,primary_gear,is_single_code")
    if gear_registry["rfid_id"].astype(str).duplicated().any():
        raise ValueError("gear_registry RFID must be unique")
    if frame["rfid_id"].isna().any() or frame["ts"].isna().any():
        raise ValueError("rfid_id and ts cannot be null")
    ledger = frame.copy(deep=True).reset_index(drop=True)
    ledger["rfid_id"] = ledger["rfid_id"].astype(str)
    if not pd.api.types.is_integer_dtype(ledger["ts"].dtype):
        raise ValueError("ts must be an integer source-clock epoch-hour column; fractional/float dtype rejected")
    if ledger.duplicated(["rfid_id", "ts"]).any():
        raise ValueError("input must have unique (rfid_id, ts)")
    if ledger.duplicated(KEY).any():
        raise ValueError("input must have unique (rfid_id, ts, source_ordinal)")
    if not pd.api.types.is_integer_dtype(ledger["source_ordinal"].dtype):
        raise ValueError("source_ordinal must be integer")
    ledger["_order"] = np.arange(len(ledger), dtype=np.int64)
    if gear_registry["rfid_id"].isna().any():
        raise ValueError("gear_registry RFID cannot be null")
    registry = gear_registry[["rfid_id", "primary_gear", "is_single_code"]].copy()
    registry["rfid_id"] = registry["rfid_id"].astype(str)
    gear_map = {r.rfid_id: (r.primary_gear, _single_code(r.is_single_code)) for r in registry.itertuples(index=False)}
    ledger["primary_gear"] = [gear_map.get(r, (None, False))[0] for r in ledger["rfid_id"]]
    ledger["is_single_code"] = [gear_map.get(r, (None, False))[1] for r in ledger["rfid_id"]]

    n = len(ledger)
    ledger["s0_ok"] = [bool(_finite_nonnegative(l) and _finite_nonnegative(b) and _finite(s))
                       for l, b, s in zip(ledger["len_m"], ledger["bbox_m"], ledger["score"])]
    ledger["s1_ok"] = [ok and not (float(l) <= 100 and float(b) <= 100) for ok, l, b in zip(ledger["s0_ok"], ledger["len_m"], ledger["bbox_m"])]
    ledger["s2_ok"] = [_shape_valid(r) for r in ledger.itertuples(index=False)]
    ledger["s2_ok"] = ledger["s2_ok"] & ledger["s1_ok"]
    ledger["s3_ok"] = False
    ledger["s4_ok"] = False
    ledger["self_ref_n"] = 0
    ledger["self_ref_dates"] = 0
    ledger["self_cdf"] = np.nan
    ledger["self_rarity"] = np.nan
    ledger["peer_eligible_n"] = 0
    ledger["peer_rarity_mean"] = np.nan

    s2_by_vessel: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for r in ledger.loc[ledger["s2_ok"], ["rfid_id", "ts", "shape_dl"]].itertuples(index=False):
        s2_by_vessel[r.rfid_id].append((int(r.ts), float(r.shape_dl)))
    for values in s2_by_vessel.values():
        values.sort()
    sweeps = {rid: HistorySweep(values) for rid, values in s2_by_vessel.items()}
    # Sweep once over all source times. Every vessel window is updated in O(rows * vessels),
    # with O(log history) rank queries and no quadratic history rescans.
    code_groups: dict[Any, list[str]] = defaultdict(list)
    for rid, (gear, single) in gear_map.items():
        if single and gear is not None:
            code_groups[gear].append(rid)
    rows_by_ts: dict[int, list[int]] = defaultdict(list)
    for i, t in enumerate(ledger["ts"].astype("int64").tolist()):
        rows_by_ts[int(t)].append(i)
    for t in sorted(rows_by_ts):
        for sweep in sweeps.values():
            sweep.advance(t)
        for i in rows_by_ts[t]:
            if not ledger.at[i, "s2_ok"]:
                continue
            rid = ledger.at[i, "rfid_id"]
            own = sweeps.get(rid)
            if own is None:
                continue
            p, rarity = own.rarity(float(ledger.at[i, "shape_dl"]))
            ledger.at[i, "self_ref_n"] = own.n
            ledger.at[i, "self_ref_dates"] = own.n_dates
            if p is not None:
                ledger.at[i, "self_cdf"] = p
                ledger.at[i, "self_rarity"] = rarity
            if own.eligible and p is not None:
                ledger.at[i, "s3_ok"] = True
            gear = gear_map.get(rid, (None, False))[0]
            if gear is None or not gear_map.get(rid, (None, False))[1]:
                continue
            peer_rarities = []
            for peer in code_groups.get(gear, []):
                if peer == rid:
                    continue
                peer_sweep = sweeps.get(peer)
                if peer_sweep is None or not peer_sweep.eligible:
                    continue
                _, peer_rarity = peer_sweep.rarity(float(ledger.at[i, "shape_dl"]))
                if peer_rarity is not None:
                    peer_rarities.append(peer_rarity)
            ledger.at[i, "peer_eligible_n"] = len(peer_rarities)
            if peer_rarities:
                ledger.at[i, "peer_rarity_mean"] = float(sum(peer_rarities) / len(peer_rarities))
            if ledger.at[i, "s3_ok"] and len(peer_rarities) >= 5:
                ledger.at[i, "s4_ok"] = True

    # Monotone statuses make missing-data states distinguishable from branch rejection.
    for stage in range(5):
        ok_col = f"s{stage}_ok"
        status_col, reason_col = f"s{stage}_status", f"s{stage}_reason"
        statuses, reasons = [], []
        for i in range(n):
            prior_failed = stage > 0 and not bool(ledger.at[i, f"s{stage-1}_ok"])
            ok = bool(ledger.at[i, ok_col])
            if ok:
                statuses.append("keep"); reasons.append("passed")
            elif prior_failed:
                statuses.append("not_applicable"); reasons.append(f"upstream_s{stage-1}_failed")
            elif stage == 0:
                statuses.append("defer"); reasons.append("invalid_len_bbox_or_legacy_score")
            elif stage == 1:
                statuses.append("reject"); reasons.append("observed_small_branch")
            elif stage == 2:
                statuses.append("defer"); reasons.append("no_informative_chosen_part")
            elif stage == 3:
                statuses.append("defer"); reasons.append("insufficient_own_past_24_rows_3_dates")
            else:
                statuses.append("defer"); reasons.append("insufficient_5_other_same_code_peer_histories")
        ledger[status_col] = statuses
        ledger[reason_col] = reasons

    # Build fixed pools and same per-vessel cap; ties are deterministic by source key.
    predictions = []
    pool_manifest = []
    all_rfids = list(dict.fromkeys(ledger["rfid_id"].tolist()))
    methods = {"B0": "s0", "S": "s3", "G": "s4"}
    per_method: dict[str, dict[str, list[int]]] = {m: {} for m in methods}
    top_sets: dict[tuple[str, str], dict[str, tuple[int, ...]]] = {}
    g_actual_sizes: dict[str, int] = {}
    for rid in all_rfids:
        idx_all = ledger.index[ledger["rfid_id"] == rid].tolist()
        s0_ids = [i for i in idx_all if bool(ledger.at[i, "s0_ok"])]
        s3_ids = [i for i in idx_all if bool(ledger.at[i, "s3_ok"])]
        s4_ids = [i for i in idx_all if bool(ledger.at[i, "s4_ok"])]
        pools = {"B0": ("s0", s0_ids, None),
                 "S": ("s3", s3_ids, "s3_empty_use_s0" if not s3_ids else None),
                 "G": ("s4", s4_ids, None)}
        if not s3_ids:
            pools["S"] = ("s0", s0_ids, "s3_empty_use_s0")
        if not s4_ids:
            gstage = pools["S"][0]
            pools["G"] = (gstage, pools["S"][1], "s4_empty_use_" + gstage)
        g_actual_sizes[rid] = len(pools["G"][1])
        cap = min(4, len(pools["G"][1]))
        for method, (pool_stage, ids, fallback) in pools.items():
            per_method[method][rid] = ids
            pool_manifest.append({"rfid_id": rid, "method": method, "pool_stage": pool_stage,
                                  "actual_pool_n": len(ids), "cap": cap, "fallback_reason": fallback})
            ordered = _rank_indices(ids, ledger, stage=pool_stage)
            selected = ordered[:cap]
            # Fill top-set comparison maps safely for this RFID.
            top_sets.setdefault((method, "top1"), {})[rid] = tuple(selected[:1])
            top_sets.setdefault((method, "top4"), {})[rid] = tuple(selected[:4])
            for rank, i in enumerate(selected, start=1):
                method_score = float(ledger.at[i, "score"]) if pool_stage == "s0" else float(ledger.at[i, "self_rarity"])
                secondary = float(ledger.at[i, "peer_rarity_mean"]) if pool_stage == "s4" else np.nan
                predictions.append({"rfid_id": rid, "method": method, "rank": rank, "ts": int(ledger.at[i, "ts"]),
                    "ordinal": int(ledger.at[i, "source_ordinal"]), "method_score": method_score,
                    "secondary_score": secondary, "legacy_score": float(ledger.at[i, "score"]),
                    "score_kind": "legacy" if pool_stage == "s0" else "self_rarity",
                    "actual_pool_n": len(ids), "cap": cap, "fallback_reason": fallback,
                    "chosen_part_index": ledger.at[i, "chosen_part_index"]})
    # Peer activation is measured against the SAME G s4 pools before/after peer tie-break.
    tie_groups = tied_candidates = differing_groups = 0
    peer_rank1_changed = peer_top4_changed = 0
    for rid in all_rfids:
        g_pool = per_method["G"][rid]
        g_manifest = next(x for x in pool_manifest if x["rfid_id"] == rid and x["method"] == "G")
        if g_manifest["pool_stage"] != "s4" or not g_pool:
            continue
        by_rarity: dict[float, list[int]] = defaultdict(list)
        for i in g_pool:
            by_rarity[float(ledger.at[i, "self_rarity"])].append(i)
        ties = [ids for ids in by_rarity.values() if len(ids) > 1]
        tie_groups += len(ties)
        tied_candidates += sum(map(len, ties))
        differing_groups += sum(1 for ids in ties if len({float(ledger.at[i, "peer_rarity_mean"]) for i in ids}) > 1)
        without_peer = sorted(g_pool, key=lambda i: (-float(ledger.at[i, "self_rarity"]), -float(ledger.at[i, "score"]), int(ledger.at[i, "ts"]), int(ledger.at[i, "source_ordinal"])))[:min(4, g_actual_sizes[rid])]
        with_peer = _rank_indices(g_pool, ledger, stage="s4")[:min(4, g_actual_sizes[rid])]
        peer_rank1_changed += int((without_peer[:1] != with_peer[:1]))
        peer_top4_changed += int(set(without_peer) != set(with_peer))
    def changed(a: str, b: str, key: str) -> int:
        return sum(top_sets[(a, key)].get(r, ()) != top_sets[(b, key)].get(r, ()) for r in all_rfids)
    diagnostics = {
        "per_gear_stage_counts": {str(gear): {f"s{i}_keep": int((ledger.loc[ledger["primary_gear"] == gear, f"s{i}_ok"]).sum()) for i in range(5)}
                                  for gear in sorted(x for x in ledger["primary_gear"].dropna().unique())},
        "G_vs_S_selected_changes": {"top1_rfids_changed": changed("G", "S", "top1"), "top4_rfids_changed": changed("G", "S", "top4"), "denominator_rfids": len(all_rfids)},
        "peer_tie_activation_within_same_G_s4_pools": {
            "definition": "exact self_rarity tie groups (size>=2) among each RFID's actual s4 candidates; peer values vary if tied rows have >1 exact peer_rarity_mean",
            "rfids_with_actual_s4_pool": sum(next(x for x in pool_manifest if x["rfid_id"] == r and x["method"] == "G")["pool_stage"] == "s4" for r in all_rfids),
            "tie_groups": tie_groups, "tied_candidates": tied_candidates, "groups_with_differing_peer_values": differing_groups,
            "rfids_rank1_changed_by_peer_within_same_pool": peer_rank1_changed,
            "rfids_top4_set_changed_by_peer_within_same_pool": peer_top4_changed,
            "denominator": "RFIDs whose G actual pool is s4; comparison ranks same s4 candidates with self_rarity, legacy, ts, ordinal versus contract G self_rarity, peer_rarity, legacy, ts, ordinal"},
        "row_count": n, "rfid_count": len(all_rfids), "history_definition": "strict prior source-clock hours [t-720,t); 24 valid s2 rows and >=3 floor(ts/24) dates"}
    ledger = ledger.sort_values("_order", kind="stable").drop(columns=["_order"]).reset_index(drop=True)
    return {"ledger": ledger, "predictions": pd.DataFrame(predictions, columns=["rfid_id", "method", "rank", "ts", "ordinal", "method_score", "secondary_score", "legacy_score", "score_kind", "actual_pool_n", "cap", "fallback_reason", "chosen_part_index"]),
            "pool_manifest": pd.DataFrame(pool_manifest, columns=["rfid_id", "method", "pool_stage", "actual_pool_n", "cap", "fallback_reason"]),
            "diagnostics": diagnostics, "stage_spec": STAGES}
