"""Duration-history ranking rules for Round 6 (no labels or event data)."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

SMALL_MAX_M = 100.0
WINDOW_HOURS = 720
MIN_SELF_RUNS = 10
MIN_START_DATES = 3
MIN_PEERS = 5
TOP_CAP = 4

STAGE_SPEC = [
    {"stage_id": "d0", "label": "valid geometry and legacy score", "input_stage": None, "mask_column": "d0_ok", "status_column": "d0_status", "reason_column": "d0_reason"},
    {"stage_id": "d1", "label": "current observation is small", "input_stage": "d0", "mask_column": "d1_ok", "status_column": "d1_status", "reason_column": "d1_reason"},
    {"stage_id": "d2", "label": "observed continuation", "input_stage": "d1", "mask_column": "d2_ok", "status_column": "d2_status", "reason_column": "d2_reason"},
    {"stage_id": "d3", "label": "eligible self history", "input_stage": "d2", "mask_column": "d3_ok", "status_column": "d3_status", "reason_column": "d3_reason"},
    {"stage_id": "d4", "label": "eligible same-gear peer history", "input_stage": "d3", "mask_column": "d4_ok", "status_column": "d4_status", "reason_column": "d4_reason"},
]
PREDICTION_COLUMNS = ["rfid_id", "method", "rank", "ts", "ordinal", "method_score", "secondary_score", "legacy_score", "score_kind", "run_id", "actual_pool_n", "cap", "fallback_reason"]
POOL_COLUMNS = ["rfid_id", "method", "pool_stage", "actual_pool_n", "cap", "fallback_reason"]
RUN_COLUMNS = ["rfid_id", "run_id", "start_ts", "end_ts", "observed_length", "left_confirmed", "right_confirmed", "close_ts", "source_ordinals", "left_censor_reason", "right_censor_reason", "start_date"]


def _is_true(v: Any) -> bool:
    return v is True or str(v).strip().lower() in {"true", "1", "yes"}


def _finite_nonnegative(v: Any) -> bool:
    try:
        x = float(v)
        return math.isfinite(x) and x >= 0
    except (TypeError, ValueError):
        return False


def _normalize_hour_timestamps(values: pd.Series, index: pd.Index) -> tuple[pd.Series, pd.Series]:
    """Accept integer epoch-hours or aligned datetime values, never guess units."""
    raw = pd.Series(values, index=index, copy=False)
    if raw.isna().any():
        raise ValueError("ts contains missing or invalid timestamps")

    if pd.api.types.is_integer_dtype(raw.dtype) and not pd.api.types.is_bool_dtype(raw.dtype):
        try:
            normalized = pd.Series(pd.to_datetime(raw.tolist(), unit="h", errors="coerce"), index=index)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("integer ts must be in range as epoch-hours (unit='h')") from exc
        if normalized.isna().any():
            raise ValueError("integer ts must be in range as epoch-hours (unit='h')")
        source_hour = pd.Series([int(v) for v in raw.tolist()], index=index, dtype="int64")
        return normalized, source_hour

    if pd.api.types.is_datetime64_any_dtype(raw.dtype):
        try:
            normalized = pd.Series(pd.to_datetime(raw, errors="coerce"), index=index)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("datetime ts is invalid") from exc
        if normalized.isna().any():
            raise ValueError("ts contains missing or invalid timestamps")
        hour_ns = 3_600_000_000_000
        try:
            epoch_ns = pd.Series([pd.Timestamp(v).value for v in normalized], index=index, dtype="int64")
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("datetime ts is outside the supported epoch-hour range") from exc
        if (epoch_ns % hour_ns != 0).any():
            raise ValueError("datetime ts must be aligned to an exact epoch hour")
        source_hour = epoch_ns // hour_ns
        return normalized, source_hour.astype("int64")

    raise ValueError("ts must be integer epoch-hours or an hour-aligned datetime dtype")


def _gear_map(registry: pd.DataFrame) -> dict:
    if not isinstance(registry, pd.DataFrame):
        registry = pd.DataFrame(registry)
    required = {"rfid_id", "primary_gear", "is_single_code"}
    if not required.issubset(registry.columns):
        raise ValueError(f"gear_registry missing columns: {sorted(required - set(registry.columns))}")
    out = {}
    for rfid, group in registry.groupby("rfid_id", sort=False, dropna=False):
        if len(group) == 1 and _is_true(group.iloc[0]["is_single_code"]) and pd.notna(group.iloc[0]["primary_gear"]):
            out[rfid] = group.iloc[0]["primary_gear"]
        else:
            out[rfid] = None
    return out


def _cdf(lengths: list[int], current_l: int) -> float:
    return sum(x < current_l for x in lengths) / len(lengths) + 0.5 * sum(x == current_l for x in lengths) / len(lengths)


def build_duration_rules(frame: pd.DataFrame, gear_registry: pd.DataFrame) -> dict:
    """Build stage ledger, completed-run registry, ranked pools and diagnostics.

    Input is a unique (rfid_id, ts) canonical frame. Integer ``ts`` values are
    epoch-hours; datetime values must be exactly epoch-hour aligned. Input
    order/index is retained in ledger, with ``source_ts_hour`` lineage;
    source_ordinal supplies deterministic tie breaking.
    """
    required = {"rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"}
    if not required.issubset(frame.columns):
        raise ValueError(f"frame missing columns: {sorted(required - set(frame.columns))}")
    ledger = frame.copy()
    ledger["_input_pos"] = range(len(ledger))
    ledger["ts"], ledger["source_ts_hour"] = _normalize_hour_timestamps(ledger["ts"], ledger.index)
    if ledger.duplicated(["rfid_id", "ts"]).any():
        raise ValueError("frame must be unique by (rfid_id, ts)")
    ledger["_geom_valid"] = [
        _finite_nonnegative(a) and _finite_nonnegative(b)
        for a, b in zip(ledger["len_m"], ledger["bbox_m"])
    ]
    ledger["_small"] = ledger["_geom_valid"] & (pd.to_numeric(ledger["len_m"], errors="coerce") <= SMALL_MAX_M) & (pd.to_numeric(ledger["bbox_m"], errors="coerce") <= SMALL_MAX_M)
    ledger["_score_valid"] = pd.to_numeric(ledger["score"], errors="coerce").map(lambda x: math.isfinite(x) if pd.notna(x) else False)
    ledger["_row_valid"] = ledger["_geom_valid"] & ledger["ts"].notna()
    ledger["current_L"] = pd.Series([pd.NA] * len(ledger), dtype="Int64", index=ledger.index)
    ledger["current_L_is_lower_bound"] = False
    ledger["current_start_ts"] = pd.NaT
    ledger["run_id"] = None
    ledger["self_ref_n"] = 0
    ledger["self_ref_start_dates"] = 0
    ledger["self_cdf"] = float("nan")
    ledger["peer_eligible_n"] = 0
    ledger["peer_cdf_mean"] = float("nan")
    ledger["self_missing_reason"] = None
    ledger["peer_missing_reason"] = None
    for st in STAGE_SPEC:
        ledger[st["mask_column"]] = False
        ledger[st["status_column"]] = "not_applicable"
        ledger[st["reason_column"]] = "upstream_ineligible"

    # Completed runs and row-to-run current observations.
    runs = []
    row_run = {}
    ordered = ledger.sort_values(["rfid_id", "ts", "source_ordinal"], kind="mergesort")
    for rfid, group in ordered.groupby("rfid_id", sort=False, dropna=False):
        ids = list(group.index)
        for pos, idx in enumerate(ids):
            if not ledger.at[idx, "_small"]:
                continue
            prev_idx = ids[pos - 1] if pos else None
            if prev_idx is not None and ledger.at[prev_idx, "_small"] and ledger.at[prev_idx, "ts"] + pd.Timedelta(hours=1) == ledger.at[idx, "ts"]:
                continue
            run_ids = [idx]
            nxt = pos + 1
            while nxt < len(ids):
                ni = ids[nxt]
                if ledger.at[ni, "ts"] != ledger.at[run_ids[-1], "ts"] + pd.Timedelta(hours=1) or not ledger.at[ni, "_small"]:
                    break
                run_ids.append(ni); nxt += 1
            first, last = run_ids[0], run_ids[-1]
            prev = ids[pos - 1] if pos else None
            after_pos = pos + len(run_ids)
            after = ids[after_pos] if after_pos < len(ids) else None
            left = bool(prev is not None and ledger.at[prev, "_row_valid"] and not ledger.at[prev, "_small"] and ledger.at[prev, "ts"] + pd.Timedelta(hours=1) == ledger.at[first, "ts"])
            right = bool(after is not None and ledger.at[after, "_row_valid"] and not ledger.at[after, "_small"] and ledger.at[last, "ts"] + pd.Timedelta(hours=1) == ledger.at[after, "ts"])
            rid = f"{rfid}:{ledger.at[first, 'ts'].isoformat()}"
            for offset, ri in enumerate(run_ids, 1):
                row_run[ri] = (rid, offset, first)
            runs.append({"rfid_id": rfid, "run_id": rid, "start_ts": ledger.at[first, "ts"], "end_ts": ledger.at[last, "ts"], "observed_length": len(run_ids), "left_confirmed": left, "right_confirmed": right, "close_ts": ledger.at[after, "ts"] if right else pd.NaT, "source_ordinals": [ledger.at[x, "source_ordinal"] for x in run_ids], "left_censor_reason": None if left else ("no_previous_observation" if prev is None else ("invalid_or_missing_geometry" if not ledger.at[prev, "_row_valid"] else "gap_or_previous_small")), "right_censor_reason": None if right else ("end_of_data" if after is None else ("invalid_or_missing_geometry" if not ledger.at[after, "_row_valid"] else "gap_or_next_small")), "start_date": ledger.at[first, "ts"].date().isoformat()})
    run_df = pd.DataFrame(runs, columns=RUN_COLUMNS)
    completed = run_df[run_df.left_confirmed & run_df.right_confirmed].copy() if len(run_df) else run_df.copy()
    gears = _gear_map(gear_registry)

    completed_by_rfid = {k: g for k, g in completed.groupby("rfid_id", sort=False)} if len(completed) else {}
    row_lookup = {(r, t): i for i, r, t in zip(ledger.index, ledger.rfid_id, ledger.ts)}
    run_by_id = {row["run_id"]: row for _, row in run_df.iterrows()}

    # Per d2 row history is strictly past at t and close_ts < t; window anchors start.
    for idx, (rid, L, start_idx) in row_run.items():
        t = ledger.at[idx, "ts"]
        run = run_by_id[rid]
        ledger.at[idx, "current_L"] = L
        ledger.at[idx, "current_L_is_lower_bound"] = not bool(run.left_confirmed)
        ledger.at[idx, "current_start_ts"] = run.start_ts
        ledger.at[idx, "run_id"] = rid
        prev_ts = t - pd.Timedelta(hours=1)
        prev_idx = row_lookup.get((ledger.at[idx, "rfid_id"], prev_ts))
        prev_ok = prev_idx is not None and bool(ledger.at[prev_idx, "_small"])
        ledger.at[idx, "d2_ok"] = bool(prev_ok and L >= 2)
        if not prev_ok:
            defer = prev_idx is None or not bool(ledger.at[prev_idx, "_row_valid"])
            ledger.at[idx, "d2_status"] = "defer" if defer else "reject"
            ledger.at[idx, "d2_reason"] = "missing_or_invalid_previous_hour" if defer else "previous_hour_not_small"
        else:
            ledger.at[idx, "d2_status"] = "keep"; ledger.at[idx, "d2_reason"] = "observed_small_continuation"

        own_runs = completed_by_rfid.get(ledger.at[idx, "rfid_id"], completed.iloc[0:0])
        refs = own_runs[(own_runs.start_ts >= t - pd.Timedelta(hours=WINDOW_HOURS)) & (own_runs.close_ts < t)]
        dates = refs.start_date.nunique()
        ledger.at[idx, "self_ref_n"] = len(refs); ledger.at[idx, "self_ref_start_dates"] = dates
        if len(refs) >= MIN_SELF_RUNS and dates >= MIN_START_DATES:
            ledger.at[idx, "self_cdf"] = _cdf(list(refs.observed_length), L)
            ledger.at[idx, "d3_ok"] = bool(ledger.at[idx, "d2_ok"])
            if ledger.at[idx, "d2_ok"]:
                ledger.at[idx, "d3_status"] = "keep"; ledger.at[idx, "d3_reason"] = "self_history_eligible"
        else:
            ledger.at[idx, "self_missing_reason"] = "insufficient_self_runs" if len(refs) < MIN_SELF_RUNS else "insufficient_self_start_dates"
            if ledger.at[idx, "d2_ok"]:
                ledger.at[idx, "d3_status"] = "defer"; ledger.at[idx, "d3_reason"] = ledger.at[idx, "self_missing_reason"]

    # Stages d0/d1 and d2 status for all records, with explicit upstream state.
    for idx in ledger.index:
        d0 = bool(ledger.at[idx, "_row_valid"] and ledger.at[idx, "_score_valid"])
        ledger.at[idx, "d0_ok"] = d0
        ledger.at[idx, "d0_status"] = "keep" if d0 else "defer"
        ledger.at[idx, "d0_reason"] = "valid_geometry_and_legacy_score" if d0 else "invalid_geometry_ts_or_legacy_score"
        if not d0:
            continue
        if not bool(ledger.at[idx, "_small"]):
            ledger.at[idx, "d1_status"] = "reject"; ledger.at[idx, "d1_reason"] = "observed_not_small"
            continue
        ledger.at[idx, "d1_ok"] = True; ledger.at[idx, "d1_status"] = "keep"; ledger.at[idx, "d1_reason"] = "small_observation"
        t = ledger.at[idx, "ts"]
        prev_idx = row_lookup.get((ledger.at[idx, "rfid_id"], t - pd.Timedelta(hours=1)))
        if prev_idx is None:
            ledger.at[idx, "d2_status"] = "defer"; ledger.at[idx, "d2_reason"] = "missing_previous_hour"
        elif not bool(ledger.at[prev_idx, "_row_valid"]):
            ledger.at[idx, "d2_status"] = "defer"; ledger.at[idx, "d2_reason"] = "invalid_previous_hour"
        elif not bool(ledger.at[prev_idx, "_small"]):
            ledger.at[idx, "d2_status"] = "reject"; ledger.at[idx, "d2_reason"] = "previous_hour_not_small"
        elif not bool(ledger.at[idx, "d2_ok"]):
            ledger.at[idx, "d2_status"] = "defer"; ledger.at[idx, "d2_reason"] = "continuation_not_observed"

    # Candidate eligibility follows d0, while run construction above remains geometry-only so
    # historical observations with a missing legacy score still contribute valid run lengths.
    for idx in ledger.index:
        if not bool(ledger.at[idx, "d0_ok"]):
            for stage_no in range(1, 5):
                stage = f"d{stage_no}"
                ledger.at[idx, f"{stage}_ok"] = False
                ledger.at[idx, f"{stage}_status"] = "not_applicable"
                ledger.at[idx, f"{stage}_reason"] = "upstream_ineligible"

    # Peer CDF at the same t; eligible vessels each contribute one score.
    gear_vessels = {}
    for vessel, gear in gears.items():
        if gear is not None:
            gear_vessels.setdefault(gear, set()).add(vessel)
    for idx in ledger.index:
        if not bool(ledger.at[idx, "d3_ok"]):
            continue
        rfid, gear, t, L = ledger.at[idx, "rfid_id"], gears.get(ledger.at[idx, "rfid_id"]), ledger.at[idx, "ts"], int(ledger.at[idx, "current_L"])
        peer_scores = []
        if gear is not None:
            for peer in gear_vessels.get(gear, set()) - {rfid}:
                peer_runs = completed_by_rfid.get(peer, completed.iloc[0:0])
                pr = peer_runs[(peer_runs.start_ts >= t - pd.Timedelta(hours=WINDOW_HOURS)) & (peer_runs.close_ts < t)]
                if len(pr) >= MIN_SELF_RUNS and pr.start_date.nunique() >= MIN_START_DATES:
                    peer_scores.append(_cdf(list(pr.observed_length), L))
        ledger.at[idx, "peer_eligible_n"] = len(peer_scores)
        if len(peer_scores) >= MIN_PEERS:
            ledger.at[idx, "peer_cdf_mean"] = sum(peer_scores) / len(peer_scores)
            ledger.at[idx, "d4_ok"] = True; ledger.at[idx, "d4_status"] = "keep"; ledger.at[idx, "d4_reason"] = "peer_history_eligible"
        else:
            reason = "unknown_or_mixed_gear" if gear is None else ("singleton_gear" if len(gear_vessels.get(gear, set())) <= 1 else "insufficient_eligible_peers")
            ledger.at[idx, "peer_missing_reason"] = reason
            ledger.at[idx, "d4_status"] = "defer"; ledger.at[idx, "d4_reason"] = reason

    # Complete upstream status bookkeeping.
    for idx in ledger.index:
        for s_i in range(1, 5):
            st = f"d{s_i}"
            prevst = f"d{s_i-1}"
            if ledger.at[idx, f"{prevst}_status"] in ("reject", "defer", "not_applicable") and ledger.at[idx, f"{st}_status"] == "not_applicable":
                ledger.at[idx, f"{st}_reason"] = "upstream_ineligible"

    ledger["_legacy_num"] = pd.to_numeric(ledger.score, errors="coerce")
    predictions, pools = [], []
    for rfid in ledger.rfid_id.drop_duplicates().tolist():
        vessel = ledger[ledger.rfid_id == rfid]
        masks = {s: vessel[vessel[f"{s}_ok"]] for s in ("d0", "d2", "d3", "d4")}
        choices = {
            "B0": ("d0", masks["d0"], "no_observations" if not len(masks["d0"]) else None),
            "S": (("d3", masks["d3"], None) if len(masks["d3"]) else (("d2", masks["d2"], "no_self_history_candidates") if len(masks["d2"]) else (("d0", masks["d0"], "no_continuation_candidates") if len(masks["d0"]) else ("d0", masks["d0"], "no_observations")))),
        }
        s_stage, s_pool, s_reason = choices["S"]
        if len(masks["d4"]):
            choices["G"] = ("d4", masks["d4"], None)
        else:
            if s_stage == "d3":
                g_reason = "no_peer_history_candidates"
            elif s_stage == "d2":
                g_reason = "no_self_history_candidates"
            else:
                g_reason = "no_continuation_candidates" if len(s_pool) else "no_observations"
            choices["G"] = (s_stage, s_pool, g_reason)
        shared_cap = min(TOP_CAP, len(choices["G"][1]))
        for method, (stage, pool, fallback) in choices.items():
            n = len(pool); cap = shared_cap
            pools.append(dict(rfid_id=rfid, method=method, pool_stage=stage, actual_pool_n=n, cap=cap, fallback_reason=fallback))
            if stage in ("d0", "d2"):
                ranked = pool.sort_values(["_legacy_num", "ts", "source_ordinal"], ascending=[False, True, True], kind="mergesort")
                skind = "legacy"
            elif stage == "d3":
                ranked = pool.sort_values(["self_cdf", "_legacy_num", "ts", "source_ordinal"], ascending=[False, False, True, True], kind="mergesort")
                skind = "self_cdf"
            else:
                ranked = pool.sort_values(["self_cdf", "peer_cdf_mean", "_legacy_num", "ts", "source_ordinal"], ascending=[False, False, False, True, True], kind="mergesort")
                skind = "self_then_peer_cdf"
            for rank, (_, row) in enumerate(ranked.head(cap).iterrows(), 1):
                predictions.append(dict(rfid_id=rfid, method=method, rank=rank, ts=row.ts, ordinal=row.source_ordinal, method_score=(row["_legacy_num"] if skind == "legacy" else row.self_cdf), secondary_score=(row.peer_cdf_mean if stage == "d4" else float("nan")), legacy_score=row["_legacy_num"], score_kind=skind, run_id=row.run_id, actual_pool_n=n, cap=cap, fallback_reason=fallback))
    # Public contract spelling for score_kind.
    for p in predictions:
        if p["score_kind"] == "self_then_peer_cdf": p["score_kind"] = "self_then_peer_cdf"
    diag = {"input_rows": len(ledger), "run_count": len(run_df), "completed_run_count": len(completed), "candidate_counts": {c: int(ledger[c].sum()) for c in ["d0_ok", "d1_ok", "d2_ok", "d3_ok", "d4_ok"]}, "stage_status_counts": {st["stage_id"]: ledger[st["status_column"]].value_counts(dropna=False).to_dict() for st in STAGE_SPEC}}
    ledger = ledger.sort_values("_input_pos", kind="mergesort").drop(columns=["_input_pos", "_geom_valid", "_small", "_score_valid", "_row_valid", "_legacy_num"])
    return {"ledger": ledger, "predictions": pd.DataFrame(predictions, columns=PREDICTION_COLUMNS), "pool_manifest": pd.DataFrame(pools, columns=POOL_COLUMNS), "run_registry": run_df, "diagnostics": diag, "stage_spec": [dict(x) for x in STAGE_SPEC]}



