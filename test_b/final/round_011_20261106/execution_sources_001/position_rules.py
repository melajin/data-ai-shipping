"""Round11 one-tail own-distance CDF and distance-history peer rules."""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import importlib.util
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
R8_HISTORY_SWEEP_PATH = HERE.parent / "round_008_20261106" / "shape_rules.py"
R8_HISTORY_SWEEP_SHA256 = "6eb571aef12dc881b78dc4c93fd77683ba4068d22be654ee46c208eab78e4472"

R4_REQUIRED = ["rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "score"]
R10_REQUIRED = ["own_distance_eligible", "nearest_distance_m"]
REGISTRY_REQUIRED = ["rfid_id", "primary_gear", "is_single_code"]
KEY = ["rfid_id", "ts", "source_ordinal"]
STAGE_SPEC = [
    {"stage_id": "s0", "label": "finite nonnegative length/bbox and finite legacy score", "input_stage": None,
     "mask_column": "s0_ok", "status_column": "s0_status", "reason_column": "s0_reason"},
    {"stage_id": "s1", "label": "s0 plus raw R10 distance available", "input_stage": "s0",
     "mask_column": "s1_ok", "status_column": "s1_status", "reason_column": "s1_reason"},
    {"stage_id": "s2", "label": "s1 plus own past-distance distribution eligible", "input_stage": "s1",
     "mask_column": "s2_ok", "status_column": "s2_status", "reason_column": "s2_reason"},
    {"stage_id": "s3", "label": "s2 plus at least five other registered same-single-gear vessels", "input_stage": "s2",
     "mask_column": "s3_ok", "status_column": "s3_status", "reason_column": "s3_reason"},
    {"stage_id": "s4", "label": "s3 plus five other distance-history-eligible peers at query t", "input_stage": "s3",
     "mask_column": "s4_ok", "status_column": "s4_status", "reason_column": "s4_reason"},
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _load_history_sweep():
    digest = _sha256(R8_HISTORY_SWEEP_PATH)
    if digest != R8_HISTORY_SWEEP_SHA256:
        raise RuntimeError(f"read-only R8 HistorySweep source hash changed: {digest}")
    name = "r8_verified_history_sweep_for_r11_cdf_only"
    spec = importlib.util.spec_from_file_location(name, R8_HISTORY_SWEEP_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load read-only history sweep: {R8_HISTORY_SWEEP_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.HistorySweep


HistorySweep = _load_history_sweep()


def _truth(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _finite_nonnegative(value: Any) -> bool:
    try:
        x = float(value)
        return math.isfinite(x) and x >= 0.0
    except (TypeError, ValueError, OverflowError):
        return False


def _single_code(value: Any) -> bool:
    return _truth(value)


def _validate(frame: pd.DataFrame, registry: pd.DataFrame) -> None:
    if not isinstance(frame, pd.DataFrame) or not isinstance(registry, pd.DataFrame):
        raise TypeError("frame and registry must be pandas DataFrames")
    forbidden = [c for c in frame.columns if any(term in str(c).lower()
                 for term in ("event", "accident", "acc_id", "label", "positive", "incident"))]
    if forbidden:
        raise ValueError(f"event/label-like fields are forbidden in position-rule input: {forbidden}")
    missing = sorted((set(R4_REQUIRED) | set(R10_REQUIRED)) - set(frame.columns))
    if missing:
        raise ValueError(f"frame missing R4/R10 fields: {missing}")
    missing_registry = sorted(set(REGISTRY_REQUIRED) - set(registry.columns))
    if missing_registry:
        raise ValueError(f"registry missing required fields: {missing_registry}")
    if frame[["rfid_id", "ts", "source_ordinal"]].isna().any().any():
        raise ValueError("RFID/source hour/ordinal keys must be non-null")
    if not pd.api.types.is_integer_dtype(frame["ts"].dtype):
        raise ValueError("ts must be an integer source-clock epoch hour before casting")
    if not pd.api.types.is_integer_dtype(frame["source_ordinal"].dtype):
        raise ValueError("source_ordinal must be integer before casting")
    i64 = np.iinfo(np.int64)
    for name in ("ts", "source_ordinal"):
        if len(frame) and (int(frame[name].min()) < i64.min or int(frame[name].max()) > i64.max):
            raise ValueError(f"{name} is outside int64 range")
    if frame["rfid_id"].astype(str).str.strip().eq("").any():
        raise ValueError("rfid_id must be non-empty")
    if registry["rfid_id"].isna().any() or registry["rfid_id"].astype(str).str.strip().eq("").any():
        raise ValueError("registry RFID must be non-null/non-empty")
    if registry["rfid_id"].astype(str).duplicated().any():
        raise ValueError("registry RFID must be unique")
    key_frame = pd.DataFrame({"rfid_id": frame["rfid_id"].astype(str), "ts": frame["ts"],
                              "source_ordinal": frame["source_ordinal"]})
    if key_frame.duplicated(KEY).any():
        raise ValueError("(rfid_id, ts, source_ordinal) must be a unique key")


def _legacy_rank(ids: list[int], ledger: pd.DataFrame) -> list[int]:
    return sorted(ids, key=lambda i: (-float(ledger.at[i, "score"]), int(ledger.at[i, "ts"]),
                                      int(ledger.at[i, "source_ordinal"])))


def _self_rank(ids: list[int], ledger: pd.DataFrame) -> list[int]:
    return sorted(ids, key=lambda i: (-float(ledger.at[i, "self_distance_cdf"]),
                                      -float(ledger.at[i, "score"]), int(ledger.at[i, "ts"]),
                                      int(ledger.at[i, "source_ordinal"])))


def _g_rank(ids: list[int], ledger: pd.DataFrame) -> list[int]:
    return sorted(ids, key=lambda i: (-float(ledger.at[i, "self_distance_cdf"]),
                                      -float(ledger.at[i, "peer_distance_cdf_mean"]),
                                      -float(ledger.at[i, "score"]), int(ledger.at[i, "ts"]),
                                      int(ledger.at[i, "source_ordinal"])))


def build_position_rules(frame: pd.DataFrame, registry: pd.DataFrame) -> dict[str, Any]:
    """Build all-row R11 distance-CDF history ledger and B0/S/G candidate pools.

    R10 coordinate-history fields are preserved as input metadata. New
    distribution-history counts/eligibility are recomputed only from raw
    available R10 distance values, with strict past windows and no legacy-score
    filtering. R8 HistorySweep is reused only for its exact one-tail ``cdf``.
    """
    _validate(frame, registry)
    ledger = frame.copy(deep=True).reset_index(drop=True)
    row_n = len(ledger)
    ids = ledger["rfid_id"].astype(str).tolist()
    ts_values = ledger["ts"].to_numpy(dtype=np.int64)
    ord_values = ledger["source_ordinal"].to_numpy(dtype=np.int64)
    score_ok = np.asarray([_finite(v) for v in ledger["score"]], dtype=bool)
    geometry_ok = np.asarray([_finite_nonnegative(l) and _finite_nonnegative(b)
                              for l, b in zip(ledger["len_m"], ledger["bbox_m"])], dtype=bool)
    r10_distance_flag = np.asarray([_truth(v) for v in ledger["own_distance_eligible"]], dtype=bool)
    distance_values = np.asarray([float(v) if _finite(v) else np.nan for v in ledger["nearest_distance_m"]],
                                 dtype=np.float64)
    raw_distance_available = r10_distance_flag & np.isfinite(distance_values) & (distance_values >= 0.0)
    ledger["raw_distance_available"] = raw_distance_available

    reg = registry[REGISTRY_REQUIRED].copy()
    reg["rfid_id"] = reg["rfid_id"].astype(str)
    gear_map: dict[str, tuple[str | None, bool]] = {}
    for r in reg.itertuples(index=False):
        gear = None if pd.isna(r.primary_gear) or str(r.primary_gear).strip() == "" else str(r.primary_gear)
        gear_map[str(r.rfid_id)] = (gear, bool(gear is not None and _single_code(r.is_single_code)))
    # The registry is authoritative for gear eligibility. If upstream already
    # merged gear metadata, require it to agree so metadata is not silently changed.
    expected_gears = [gear_map.get(rid, (None, False))[0] for rid in ids]
    expected_single = [gear_map.get(rid, (None, False))[1] for rid in ids]
    if "primary_gear" in ledger:
        for observed, expected in zip(ledger["primary_gear"], expected_gears):
            observed_value = None if pd.isna(observed) or str(observed).strip() == "" else str(observed)
            if observed_value != expected:
                raise ValueError("merged primary_gear disagrees with R3 registry")
    else:
        ledger["primary_gear"] = expected_gears
    if "is_single_code" in ledger:
        for observed, expected in zip(ledger["is_single_code"], expected_single):
            if _single_code(observed) != expected:
                raise ValueError("merged is_single_code disagrees with R3 registry")
    else:
        ledger["is_single_code"] = expected_single

    all_rfids = sorted(set(ids) | set(gear_map))
    rows_by_rid: dict[str, list[int]] = defaultdict(list)
    rows_by_t: dict[int, list[int]] = defaultdict(list)
    distance_events: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
    raw_counts: dict[str, Counter[str]] = {rid: Counter() for rid in all_rfids}
    for i, (rid, t, ordinal) in enumerate(zip(ids, ts_values, ord_values)):
        rows_by_rid[rid].append(i)
        rows_by_t[int(t)].append(i)
        raw_counts[rid]["observed_n"] += 1
        if raw_distance_available[i]:
            distance_events[rid].append((int(t), int(ordinal), float(distance_values[i])))
            raw_counts[rid]["raw_distance_available_n"] += 1

    sweeps = {}
    for rid in all_rfids:
        events = sorted(distance_events.get(rid, []), key=lambda x: (x[0], x[1]))
        sweeps[rid] = HistorySweep([(t, d) for t, _, d in events])

    single_gear_members: dict[str, list[str]] = defaultdict(list)
    for rid, (gear, single) in gear_map.items():
        if gear is not None and single:
            single_gear_members[gear].append(rid)
    for members in single_gear_members.values():
        members.sort()
    potential_peer_n = {
        rid: (max(0, len(single_gear_members.get(gear, [])) - 1) if single and gear is not None else 0)
        for rid, (gear, single) in gear_map.items()
    }

    self_ref_n = np.zeros(row_n, dtype=np.int64)
    self_ref_dates = np.zeros(row_n, dtype=np.int64)
    self_cdf = np.full(row_n, np.nan, dtype=np.float64)
    self_history_ok = np.zeros(row_n, dtype=bool)
    peer_dist_n = np.zeros(row_n, dtype=np.int64)
    peer_cdf_mean = np.full(row_n, np.nan, dtype=np.float64)
    peer_history_ok = np.zeros(row_n, dtype=bool)
    for t in sorted(rows_by_t):
        for sweep in sweeps.values():
            sweep.advance(t)
        eligible_by_gear: dict[str, list[str]] = {}
        for gear, members in single_gear_members.items():
            eligible_by_gear[gear] = [rid for rid in members if sweeps[rid].eligible]

        for i in rows_by_t[t]:
            rid = ids[i]
            own = sweeps[rid]
            self_ref_n[i] = own.n
            self_ref_dates[i] = own.n_dates
            self_history_ok[i] = bool(raw_distance_available[i] and own.eligible)
            if self_history_ok[i]:
                value = own.cdf(float(distance_values[i]))
                self_cdf[i] = np.nan if value is None else float(value)

            gear, single = gear_map.get(rid, (None, False))
            eligible_members = eligible_by_gear.get(gear, []) if single and gear is not None else []
            eligible_peers = [peer for peer in eligible_members if peer != rid]
            peer_dist_n[i] = len(eligible_peers)
            if raw_distance_available[i] and eligible_peers:
                cdfs = [sweeps[peer].cdf(float(distance_values[i])) for peer in eligible_peers]
                valid_cdfs = [float(cdf) for cdf in cdfs if cdf is not None]
                if valid_cdfs:
                    peer_cdf_mean[i] = float(np.mean(valid_cdfs))
            peer_history_ok[i] = bool(self_history_ok[i] and single and gear is not None
                                      and len(eligible_peers) >= 5)

    ledger["self_distance_ref_n"] = self_ref_n
    ledger["self_distance_ref_dates"] = self_ref_dates
    ledger["self_distance_cdf"] = self_cdf
    ledger["self_distance_history_eligible"] = self_history_ok
    ledger["peer_distance_eligible_n"] = peer_dist_n
    ledger["peer_distance_cdf_mean"] = peer_cdf_mean
    ledger["peer_distance_history_eligible"] = peer_history_ok

    ledger["s0_ok"] = geometry_ok & score_ok
    ledger["s1_ok"] = ledger["s0_ok"].to_numpy(dtype=bool) & raw_distance_available
    ledger["s2_ok"] = ledger["s1_ok"].to_numpy(dtype=bool) & self_history_ok
    s3 = np.asarray([bool(ledger.at[i, "s2_ok"] and potential_peer_n.get(ids[i], 0) >= 5)
                     for i in range(row_n)], dtype=bool)
    ledger["s3_ok"] = s3
    ledger["s4_ok"] = s3 & (peer_dist_n >= 5)

    for stage in range(5):
        statuses, reasons = [], []
        for i in range(row_n):
            ok = bool(ledger.at[i, f"s{stage}_ok"])
            prior_failed = stage > 0 and not bool(ledger.at[i, f"s{stage - 1}_ok"])
            rid = ids[i]
            gear, single = gear_map.get(rid, (None, False))
            if ok:
                status, reason = "keep", "passed"
            elif prior_failed:
                status, reason = "not_applicable", f"upstream_s{stage - 1}_failed"
            elif stage == 0:
                status, reason = "defer", "invalid_length_bbox_or_nonfinite_legacy_score"
            elif stage == 1:
                status, reason = "defer", "raw_R10_distance_unavailable"
            elif stage == 2:
                status, reason = "defer", "insufficient_24_past_distance_values_or_3_dates"
            elif stage == 3:
                status = "defer"
                reason = "unknown_mixed_or_non_single_self_gear" if gear is None or not single else "fewer_than_5_other_registered_same_gear_vessels"
            else:
                status, reason = "defer", "fewer_than_5_other_distance_history_eligible_peers_at_query_t"
            statuses.append(status)
            reasons.append(reason)
        ledger[f"s{stage}_status"] = statuses
        ledger[f"s{stage}_reason"] = reasons

    # All-row, all-period raw distance-history counts independent of legacy score.
    per_vessel = []
    for rid in all_rfids:
        idx = rows_by_rid.get(rid, [])
        gear, _ = gear_map.get(rid, (None, False))
        per_vessel.append({
            "rfid_id": rid, "primary_gear": gear, "observed_n": int(len(idx)),
            "raw_distance_available_n": int(raw_distance_available[idx].sum()) if idx else 0,
            "self_distribution_eligible_n": int(self_history_ok[idx].sum()) if idx else 0,
            "peer_distribution_eligible_n": int(peer_history_ok[idx].sum()) if idx else 0,
        })
    per_gear_history: dict[str, dict[str, int]] = {}
    for row in per_vessel:
        gear = str(row["primary_gear"] or "unknown")
        agg = per_gear_history.setdefault(gear, {k: 0 for k in
            ("rfid_n", "observed_n", "raw_distance_available_n", "self_distribution_eligible_n", "peer_distribution_eligible_n")})
        agg["rfid_n"] += 1
        for k in ("observed_n", "raw_distance_available_n", "self_distribution_eligible_n", "peer_distribution_eligible_n"):
            agg[k] += row[k]

    per_gear_stage_counts = {}
    for gear in sorted(str(x) for x in ledger["primary_gear"].dropna().unique()) if "primary_gear" in ledger else []:
        subset = ledger[ledger["primary_gear"].astype(str) == gear]
        per_gear_stage_counts[gear] = {f"s{s}_n": int(subset[f"s{s}_ok"].sum()) for s in range(5)}

    # Candidate pools, method-specific ordering, and one shared cap from G's actual pool.
    predictions: list[dict[str, Any]] = []
    pool_manifest: list[dict[str, Any]] = []
    fallbacks: dict[str, Counter[str]] = {m: Counter() for m in ("B0", "S", "G")}
    top_sets: dict[tuple[str, str], dict[str, tuple[int, ...]]] = {}
    g_tie_rows = []
    for rid in all_rfids:
        ids_for_rid = rows_by_rid.get(rid, [])
        s0_ids = [i for i in ids_for_rid if bool(ledger.at[i, "s0_ok"])]
        s2_ids = [i for i in ids_for_rid if bool(ledger.at[i, "s2_ok"])]
        s4_ids = [i for i in ids_for_rid if bool(ledger.at[i, "s4_ok"])]
        s_pool = ("s2", s2_ids, None) if s2_ids else ("s0", s0_ids, "s2_empty_use_s0")
        g_pool = ("s4", s4_ids, None) if s4_ids else (s_pool[0], s_pool[1], f"s4_empty_use_{s_pool[0]}")
        pools = {"B0": ("s0", s0_ids, None), "S": s_pool, "G": g_pool}
        cap = min(4, len(g_pool[1]))
        for method, (pool_stage, pool_ids, fallback) in pools.items():
            if fallback:
                fallbacks[method][fallback] += 1
            pool_manifest.append({"rfid_id": rid, "method": method, "pool_stage": pool_stage,
                                  "actual_pool_n": len(pool_ids), "cap": cap, "fallback_reason": fallback})
            if pool_stage == "s4":
                ordered = _g_rank(pool_ids, ledger)
            elif pool_stage == "s2":
                ordered = _self_rank(pool_ids, ledger)
            else:
                ordered = _legacy_rank(pool_ids, ledger)
            selected = ordered[:cap]
            top_sets.setdefault((method, "top1"), {})[rid] = tuple(selected[:1])
            top_sets.setdefault((method, "top4"), {})[rid] = tuple(selected[:4])
            for rank, i in enumerate(selected, 1):
                if pool_stage == "s0":
                    score, kind, secondary = float(ledger.at[i, "score"]), "legacy", None
                else:
                    score = float(ledger.at[i, "self_distance_cdf"])
                    kind = "self_distance_cdf"
                    secondary = float(ledger.at[i, "peer_distance_cdf_mean"]) if pool_stage == "s4" else None
                predictions.append({
                    "rfid_id": rid, "method": method, "rank": rank, "ts": int(ledger.at[i, "ts"]),
                    "ordinal": int(ledger.at[i, "source_ordinal"]), "method_score": score,
                    "secondary_score": secondary, "legacy_score": float(ledger.at[i, "score"]),
                    "score_kind": kind, "actual_pool_n": len(pool_ids), "cap": cap,
                    "fallback_reason": fallback,
                })

        if s4_ids:
            values = [float(ledger.at[i, "self_distance_cdf"]) for i in s4_ids]
            tie_count = len(values) - len(set(values))
            top_cdf = max(values)
            top_group = [i for i in s4_ids if float(ledger.at[i, "self_distance_cdf"]) == top_cdf]
            without_peer = sorted(s4_ids, key=lambda i: (-float(ledger.at[i, "self_distance_cdf"]),
                                   -float(ledger.at[i, "score"]), int(ledger.at[i, "ts"]),
                                   int(ledger.at[i, "source_ordinal"])))
            with_peer = _g_rank(s4_ids, ledger)
            g_tie_rows.append({"rfid_id": rid, "s4_pool_n": len(s4_ids), "self_cdf_duplicate_excess_n": tie_count,
                               "top_self_cdf_group_n": len(top_group),
                               "peer_changed_top1_within_fixed_s4_pool": bool(without_peer[:1] != with_peer[:1]),
                               "peer_changed_top4_within_fixed_s4_pool": bool(without_peer[:4] != with_peer[:4])})

    def changed(method_a: str, method_b: str, depth: str) -> int:
        return sum(top_sets[(method_a, depth)].get(r, ()) != top_sets[(method_b, depth)].get(r, ()) for r in all_rfids)

    counts = {
        "observed_n": row_n,
        "raw_distance_available_n": int(raw_distance_available.sum()),
        "self_distribution_eligible_n": int(self_history_ok.sum()),
        "peer_distribution_eligible_n": int(peer_history_ok.sum()),
    }
    diagnostics = {
        "row_count": row_n, "rfid_count": len(set(ids)), "counts": counts,
        "per_vessel_distance_history": per_vessel, "per_gear_distance_history": per_gear_history,
        "per_gear_stage_counts": per_gear_stage_counts,
        "distance_history_definition": "all raw_distance_available values in strict past [t-720,t), independent of legacy score/geometry; at least 24 values and 3 floor(ts/24) dates",
        "raw_distance_available_definition": "R10 own_distance_eligible AND finite nearest_distance_m >= 0",
        "self_cdf_definition": "(#past distances < current + 0.5 * #exact-equal) / n; one-tail high CDF, no 1-CDF or two-tail rarity",
        "peer_cdf_definition": "equal-vessel mean of each eligible other same-known-single-gear peer's one-tail CDF at current distance and same query t",
        "reference_window": "[t-720,t); current and future excluded; each historical distance value may itself use coordinate history reaching back to t-1440",
        "fallback_counts_by_method": {m: dict(c) for m, c in fallbacks.items()},
        "G_vs_S_selected_changes": {"top1_rfids_changed": changed("G", "S", "top1"),
                                    "top4_rfids_changed": changed("G", "S", "top4"),
                                    "denominator_rfids": len(all_rfids)},
        "G_self_tie_diagnostics": {
            "rfid_with_any_self_cdf_ties": sum(r["self_cdf_duplicate_excess_n"] > 0 for r in g_tie_rows),
            "rfid_with_top_self_cdf_ties": sum(r["top_self_cdf_group_n"] > 1 for r in g_tie_rows),
            "peer_changed_top1_within_fixed_s4_pool": sum(r["peer_changed_top1_within_fixed_s4_pool"] for r in g_tie_rows),
            "peer_changed_top4_within_fixed_s4_pool": sum(r["peer_changed_top4_within_fixed_s4_pool"] for r in g_tie_rows),
            "rfid_denominator_with_nonempty_s4_pool": len(g_tie_rows), "by_rfid": g_tie_rows,
            "comparison": "same s4 pool; self_distance_cdf remains primary; compare with peer secondary enabled vs omitted",
        },
        "read_only_R8_history_sweep": {"path": str(R8_HISTORY_SWEEP_PATH),
            "sha256": R8_HISTORY_SWEEP_SHA256, "used_method": "HistorySweep.cdf",
            "old_rarity_method_called": False, "shape_features_used": False},
    }
    ledger = ledger.reset_index(drop=True)
    prediction_columns = ["rfid_id", "method", "rank", "ts", "ordinal", "method_score", "secondary_score",
                         "legacy_score", "score_kind", "actual_pool_n", "cap", "fallback_reason"]
    manifest_columns = ["rfid_id", "method", "pool_stage", "actual_pool_n", "cap", "fallback_reason"]
    return {"ledger": ledger, "predictions": pd.DataFrame(predictions, columns=prediction_columns),
            "pool_manifest": pd.DataFrame(pool_manifest, columns=manifest_columns),
            "diagnostics": diagnostics, "stage_spec": STAGE_SPEC}
