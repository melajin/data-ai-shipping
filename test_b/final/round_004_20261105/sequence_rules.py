from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from typing import Any
import math

import numpy as np
import pandas as pd


_REQUIRED_FRAME = ("rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score")
_REQUIRED_GEAR = ("rfid_id", "primary_gear", "is_single_code")


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(value))
    except (TypeError, ValueError):
        return False


def _truth(value: Any) -> bool:
    return bool(value) if not pd.isna(value) else False


def _geometry(row: pd.Series) -> bool:
    length, bbox = row["len_m"], row["bbox_m"]
    return _finite(length) and _finite(bbox) and float(length) >= 0 and float(bbox) >= 0


def _small(row: pd.Series) -> bool:
    return _geometry(row) and float(row["len_m"]) <= 100 and float(row["bbox_m"]) <= 100


def _single_code(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer, float, np.floating)):
        return bool(np.isfinite(value) and value == 1)
    return isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}


def _known_label(value: Any) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().lower() not in {"", "unknown", "mixed", "unknown/mixed", "nan", "none"}


def _row_key(rfid: Any, ts: Any) -> tuple[str, int]:
    return str(rfid), int(ts)


def _triples(rows: pd.DataFrame) -> tuple[list[int], list[int], list[int]]:
    """Return centers, center-days, and transition flags for observed valid triples."""
    by_ts = {int(r.ts): r for r in rows.itertuples(index=False)}
    valid = {}
    small = {}
    for ts, row in by_ts.items():
        valid[ts] = _finite(row.len_m) and _finite(row.bbox_m) and row.len_m >= 0 and row.bbox_m >= 0
        small[ts] = bool(valid[ts] and row.len_m <= 100 and row.bbox_m <= 100)
    centers: list[int] = []
    days: list[int] = []
    transition: list[int] = []
    for s in sorted(by_ts):
        if s - 1 in by_ts and s + 1 in by_ts and valid[s - 1] and valid[s] and valid[s + 1]:
            centers.append(s)
            days.append(s // 24)
            transition.append(int(not small[s - 1] and small[s] and small[s + 1]))
    return centers, days, transition


def build_rules(frame: pd.DataFrame, gear_registry: pd.DataFrame) -> dict[str, Any]:
    """Build sequential stage masks and equally capped B0/S/G candidate lists.

    This is a retrospective observed-pattern ranking. It does not identify a physical
    stop, an accident, or an online alert.
    """
    if not isinstance(frame, pd.DataFrame) or not isinstance(gear_registry, pd.DataFrame):
        raise TypeError("frame and gear_registry must be pandas DataFrames")
    missing = sorted(set(_REQUIRED_FRAME) - set(frame.columns))
    if missing:
        raise ValueError(f"frame missing required columns: {missing}")
    missing_gear = sorted(set(_REQUIRED_GEAR) - set(gear_registry.columns))
    if missing_gear:
        raise ValueError(f"gear_registry missing required columns: {missing_gear}")
    if frame["rfid_id"].isna().any() or frame["ts"].isna().any():
        raise ValueError("rfid_id and ts must be non-null")
    if frame.duplicated(["rfid_id", "ts"]).any():
        raise ValueError("frame must contain exactly one row per rfid_id/ts")
    if gear_registry["rfid_id"].duplicated().any():
        raise ValueError("gear_registry must contain at most one row per rfid_id")

    ledger = frame.copy()
    ledger["_input_order"] = np.arange(len(ledger), dtype=np.int64)
    ledger["rfid_id"] = ledger["rfid_id"].astype(str)
    if not pd.api.types.is_integer_dtype(ledger["ts"]):
        numeric_ts = pd.to_numeric(ledger["ts"], errors="coerce")
        if numeric_ts.isna().any() or not np.equal(numeric_ts, np.floor(numeric_ts)).all():
            raise ValueError("ts must contain integer hours")
        ledger["ts"] = numeric_ts.astype("int64")
    ledger["ts"] = ledger["ts"].astype("int64")

    geom = ledger.apply(_geometry, axis=1)
    small = ledger.apply(_small, axis=1)
    score_ok = ledger["score"].map(_finite)
    ledger["geometry_valid"] = geom.astype(bool)
    ledger["small"] = small.astype(bool)
    ledger["stage0_ok"] = (geom & score_ok).astype(bool)
    ledger["stage0_reason"] = ["keep" if ok else "invalid_geometry_and_score" if not g and not sc else "invalid_geometry" if not g else "invalid_legacy_score" for ok, g, sc in zip(ledger["stage0_ok"], geom, score_ok)]
    ledger["stage1_ok"] = False
    ledger["stage2_ok"] = False
    ledger["stage3_ok"] = False

    # Lookup only observations in the supplied frame; missing hours are never imputed.
    row_lookup: dict[tuple[str, int], int] = {
        _row_key(r[0], r[1]): int(i)
        for i, r in enumerate(ledger[["rfid_id", "ts"]].itertuples(index=False, name=None))
    }
    # Positional arrays avoid dependence on input DataFrame index labels.
    prev_present, next_present, prev_valid, next_valid = [], [], [], []
    prev_small, next_small = [], []
    for r in ledger[["rfid_id", "ts"]].itertuples(index=False):
        pi = row_lookup.get((r.rfid_id, int(r.ts) - 1))
        ni = row_lookup.get((r.rfid_id, int(r.ts) + 1))
        prev_present.append(pi is not None)
        next_present.append(ni is not None)
        prev_valid.append(bool(pi is not None and geom.iloc[pi]))
        next_valid.append(bool(ni is not None and geom.iloc[ni]))
        prev_small.append(bool(pi is not None and small.iloc[pi]))
        next_small.append(bool(ni is not None and small.iloc[ni]))
    ledger["previous_observed"] = prev_present
    ledger["next_observed"] = next_present
    ledger["previous_geometry_valid"] = prev_valid
    ledger["next_geometry_valid"] = next_valid
    ledger["previous_small"] = prev_small
    ledger["next_small"] = next_small
    ledger["left_censored"] = ~ledger["previous_observed"]
    ledger["right_censored"] = ~ledger["next_observed"]
    ledger["previous_gap_reason"] = ["missing_observation" if not p else ("invalid_geometry" if not v else ("small" if s else "ok")) for p, v, s in zip(prev_present, prev_valid, prev_small)]
    ledger["next_gap_reason"] = ["missing_observation" if not p else ("invalid_geometry" if not v else ("small" if s else "ok")) for p, v, s in zip(next_present, next_valid, next_small)]

    stage1 = ledger["stage0_ok"].to_numpy() & np.asarray(prev_valid) & ~np.asarray(prev_small) & ledger["small"].to_numpy()
    stage2 = stage1 & np.asarray(next_valid) & np.asarray(next_small)
    ledger["stage1_ok"] = stage1
    ledger["stage2_ok"] = stage2
    ledger["stage1_reason"] = ["keep" if ok else ("stage0_reject" if not s0 else "missing_previous" if not p else "invalid_previous" if not pv else "previous_not_large" if ps else "current_not_small") for ok, s0, p, pv, ps in zip(stage1, ledger["stage0_ok"], prev_present, prev_valid, prev_small)]
    ledger["stage2_reason"] = ["keep" if ok else ("stage1_reject" if not s1 else "missing_next" if not n else "invalid_next" if not nv else "next_not_small") for ok, s1, n, nv, ns in zip(stage2, stage1, next_present, next_valid, next_small)]

    gear = gear_registry.loc[:, list(_REQUIRED_GEAR)].copy()
    gear["rfid_id"] = gear["rfid_id"].astype(str)
    ledger = ledger.merge(gear, on="rfid_id", how="left", sort=False, validate="many_to_one")
    ledger["gear_known"] = ledger["primary_gear"].map(_known_label) & ledger["is_single_code"].map(_single_code)
    gear_groups: dict[str, list[str]] = defaultdict(list)
    for r in gear.itertuples(index=False):
        if _known_label(r.primary_gear) and _single_code(r.is_single_code):
            gear_groups[str(r.primary_gear)].append(str(r.rfid_id))

    # Per-RFID sorted sequence state and strictly-past triple summaries.
    groups = {str(rid): g.sort_values(["ts", "source_ordinal"], kind="mergesort") for rid, g in ledger.groupby("rfid_id", sort=False)}
    seq_rows = {rid: g for rid, g in groups.items()}
    triple_summary = {rid: _triples(g) for rid, g in groups.items()}
    baseline_cache: dict[tuple[str, int], tuple[int, int, int, float | None, str | None]] = {}

    def baseline(rid: str, t: int):
        key = (rid, t)
        if key in baseline_cache:
            return baseline_cache[key]
        centers, days, flags = triple_summary.get(rid, ([], [], []))
        lo, hi = bisect_left(centers, t - 719), bisect_left(centers, t - 1)  # center <= t-2
        n = hi - lo
        ntrans = sum(flags[lo:hi])
        ndays = len(set(days[lo:hi]))
        reason = None if n >= 24 and ndays >= 3 else "insufficient_triples" if n < 24 else "insufficient_center_dates"
        rate = ntrans / n if n else None
        baseline_cache[key] = (n, ndays, ntrans, rate, reason)
        return baseline_cache[key]

    own_n, own_days, own_trans, own_rate, own_reason = [], [], [], [], []
    peer_n, peer_pct, gear_priority, gear_reason = [], [], [], []
    for row in ledger.itertuples(index=False):
        rid, t = str(row.rfid_id), int(row.ts)
        n, nd, nt, rate, reason = baseline(rid, t)
        own_n.append(n); own_days.append(nd); own_trans.append(nt); own_rate.append(rate); own_reason.append(reason)
        peer_n.append(0); peer_pct.append(None); gear_priority.append(None)
        if not bool(row.stage2_ok):
            gear_reason.append("not_stage2")
            continue
        if not bool(row.gear_known):
            gear_reason.append("unknown_or_mixed_gear")
            continue
        if reason:
            gear_reason.append(f"own_{reason}")
            continue
        group = gear_groups.get(str(row.primary_gear), [])
        peers = [p for p in group if p != rid]
        rates = []
        for peer in peers:
            pn, pdays, _, prate, preason = baseline(peer, t)
            if preason is None and prate is not None:
                rates.append(prate)
        peer_n[-1] = len(rates)
        if len(group) == 1:
            gear_reason.append("singleton_no_peer_rule")
            continue
        if len(rates) < 5:
            gear_reason.append("insufficient_eligible_peers")
            continue
        pct = (sum(x < rate for x in rates) + 0.5 * sum(x == rate for x in rates)) / len(rates)
        peer_pct[-1] = pct
        gear_priority[-1] = 1.0 - pct
        gear_reason.append(None)

    ledger["own_baseline_triples"] = own_n
    ledger["own_baseline_center_dates"] = own_days
    ledger["own_baseline_transitions"] = own_trans
    ledger["own_transition_rate"] = own_rate
    ledger["own_baseline_missing_reason"] = own_reason
    ledger["eligible_peer_count"] = peer_n
    ledger["peer_percentile"] = peer_pct
    ledger["gear_priority"] = gear_priority
    ledger["gear_missing_reason"] = gear_reason
    stage3 = ledger["stage2_ok"].to_numpy() & ledger["gear_priority"].notna().to_numpy()
    ledger["stage3_ok"] = stage3

    # Explanations: t+2 state and past valid-position share in t's 30-day window.
    t2_status, cell_count, cell_fraction = [], [], []
    position_history = {}
    for rid, g in seq_rows.items():
        valid_pos = g[g["geometry_valid"] & g["cen_lon"].map(_finite) & g["cen_lat"].map(_finite)]
        position_history[rid] = (
            valid_pos["ts"].astype("int64").tolist(),
            [(math.floor(float(x) / 0.05), math.floor(float(y) / 0.05)) for x, y in zip(valid_pos["cen_lon"], valid_pos["cen_lat"])],
        )
    for i, row in enumerate(ledger.itertuples(index=False)):
        rid, t = str(row.rfid_id), int(row.ts)
        i2 = row_lookup.get((rid, t + 2))
        if i2 is None:
            t2_status.append("missing")
        elif not bool(geom.iloc[i2]):
            t2_status.append("invalid")
        elif bool(small.iloc[i2]):
            t2_status.append("still_small")
        else:
            t2_status.append("condition_exit")
        lon, lat = row.cen_lon, row.cen_lat
        if not (_finite(lon) and _finite(lat)):
            cell_count.append(0); cell_fraction.append(None); continue
        cell = (math.floor(float(lon) / 0.05), math.floor(float(lat) / 0.05))
        pos_ts, pos_cells = position_history[rid]
        left, right = bisect_left(pos_ts, t - 720), bisect_left(pos_ts, t)
        prior_cells = pos_cells[left:right]
        count = len(prior_cells)
        same = sum(value == cell for value in prior_cells)
        cell_count.append(count); cell_fraction.append(same / count if count else None)
    ledger["t_plus_2_status"] = t2_status
    ledger["past30d_valid_position_count"] = cell_count
    ledger["past30d_same_cell_fraction"] = cell_fraction

    # Methods: own pools preserved; a shared cap is determined from actual G pool.
    prediction_rows = []
    manifest_rows = []
    for rid, g in groups.items():
        # _input_order identifies original rows after merge; select and rank in stable order.
        full = ledger.loc[ledger["rfid_id"].eq(rid)]
        stage0_pool = full[full["stage0_ok"]]
        stage2_pool = full[full["stage2_ok"]]
        stage3_pool = full[full["stage3_ok"]]
        if len(stage3_pool):
            g_pool, g_stage, g_fb = stage3_pool, "stage3", None
        elif len(stage2_pool):
            g_pool, g_stage, g_fb = stage2_pool, "stage2", "no_gear_eligible_candidates"
        elif len(stage0_pool):
            g_pool, g_stage, g_fb = stage0_pool, "stage0", "no_common_transitions"
        else:
            g_pool, g_stage, g_fb = full.iloc[0:0], "stage0", "no_observations"
        cap = min(4, len(g_pool))
        method_pools = {
            "B0": (stage0_pool, "stage0", None, "legacy_score"),
            "S": (stage2_pool if len(stage2_pool) else stage0_pool, "stage2" if len(stage2_pool) else "stage0", None if len(stage2_pool) else "no_common_transitions", "legacy_score"),
            "G": (g_pool, g_stage, g_fb, "gear_priority" if g_stage == "stage3" else "legacy_score"),
        }
        for method, (pool, pool_stage, fallback, score_kind) in method_pools.items():
            manifest_rows.append({"rfid_id": rid, "method": method, "pool_stage": pool_stage, "actual_pool_n": len(pool), "cap": cap, "fallback_reason": fallback})
            if pool.empty or cap == 0:
                continue
            sort_cols = ["gear_priority", "score", "ts", "source_ordinal"] if method == "G" and pool_stage == "stage3" else ["score", "ts", "source_ordinal"]
            ascending = [False, False, True, True] if len(sort_cols) == 4 else [False, True, True]
            ranked = pool.sort_values(sort_cols, ascending=ascending, kind="mergesort").head(cap)
            for rank, item in enumerate(ranked.itertuples(index=False), start=1):
                used = item.gear_priority if method == "G" and pool_stage == "stage3" else item.score
                prediction_rows.append({
                    "rfid_id": rid, "method": method, "rank": rank, "ts": int(item.ts),
                    "ordinal": item.source_ordinal, "method_score": float(used),
                    "legacy_score": float(item.score), "score_kind": score_kind,
                    "actual_pool_n": int(len(pool)), "cap": int(cap), "fallback_reason": fallback,
                })

    # Restore original row order and index; internal helper is not part of the public ledger.
    ledger = ledger.sort_values("_input_order", kind="mergesort")
    ledger.index = frame.index.copy()
    ledger = ledger.drop(columns=["_input_order"])
    predictions = pd.DataFrame(prediction_rows, columns=["rfid_id", "method", "rank", "ts", "ordinal", "method_score", "legacy_score", "score_kind", "actual_pool_n", "cap", "fallback_reason"])
    manifest = pd.DataFrame(manifest_rows, columns=["rfid_id", "method", "pool_stage", "actual_pool_n", "cap", "fallback_reason"])
    diagnostics = {
        "input_rows": int(len(frame)), "rfid_count": int(frame["rfid_id"].nunique()),
        "stage0_rows": int(ledger["stage0_ok"].sum()), "stage1_rows": int(ledger["stage1_ok"].sum()),
        "stage2_rows": int(ledger["stage2_ok"].sum()), "stage3_rows": int(ledger["stage3_ok"].sum()),
        "duplicate_rfid_ts": False, "physical_stop_claim": False,
        "baseline_window_hours": 720, "baseline_min_triples": 24, "baseline_min_center_dates": 3,
        "min_eligible_peers": 5, "shared_cap_rule": "min(4, G actual pool size)",
        "singleton_rule": "no peer-based Stage3 eligibility; G uses documented fallback",
    }
    return {"ledger": ledger, "predictions": predictions, "pool_manifest": manifest, "diagnostics": diagnostics}

