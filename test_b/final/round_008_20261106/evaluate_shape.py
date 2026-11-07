"""Round 8 evaluation module: deterministic event evaluation, paired cluster bootstrap,
and separate cohort random expectation over shape-history ranking rules.

This module is descriptive and evaluative only. It does not conduct online anomaly
detection, train models, or rerank predictions after label exposure.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

# Reuse verified Round 2 pure numerical helpers.
HERE = Path(__file__).resolve().parent
ROUND2_DIR = HERE.parent / "round_002_20261105"
if str(ROUND2_DIR) not in sys.path:
    sys.path.insert(0, str(ROUND2_DIR))

try:
    from data_eval import _bootstrap_diff as r2_bootstrap_diff
    from data_eval import _random_hit_probability as r2_random_hit_probability
except ImportError:
    r2_bootstrap_diff = None
    r2_random_hit_probability = None

METHODS = ("B0", "S", "G")
BUDGETS = (1, 4)
TOLERANCE_HOURS = 6
BOOTSTRAP_B = 4000
BOOTSTRAP_SEED = 20261105
HOUR_NS = 3600 * 1_000_000_000

STAGE_SPEC = [
    {
        "stage_id": "s0",
        "label": "valid geometry and finite legacy score",
        "input_stage": None,
        "mask_column": "s0_ok",
        "status_column": "s0_status",
        "reason_column": "s0_reason",
    },
    {
        "stage_id": "s1",
        "label": "non-small observation (len>100 or bbox>100)",
        "input_stage": "s0",
        "mask_column": "s1_ok",
        "status_column": "s1_status",
        "reason_column": "s1_reason",
    },
    {
        "stage_id": "s2",
        "label": "valid informative chosen-part shape",
        "input_stage": "s1",
        "mask_column": "s2_ok",
        "status_column": "s2_status",
        "reason_column": "s2_reason",
    },
    {
        "stage_id": "s3",
        "label": "eligible self shape history (>=24 valid s2 rows, >=3 dates)",
        "input_stage": "s2",
        "mask_column": "s3_ok",
        "status_column": "s3_status",
        "reason_column": "s3_reason",
    },
    {
        "stage_id": "s4",
        "label": "eligible same-gear peer history (>=5 other vessels)",
        "input_stage": "s3",
        "mask_column": "s4_ok",
        "status_column": "s4_status",
        "reason_column": "s4_reason",
    },
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _norm_id(value: Any) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def to_epoch_hour(val: Any, allow_nat: bool = False, context: str = "timestamp") -> int | None:
    """Explicitly convert an integer epoch hour or hour-aligned datetime to integer epoch hour.

    Rejects unaligned/fractional hours, NaT/nulls on active predictions, and wrongly
    interpreted nanosecond timestamps without silent heuristics.
    Permits NaT only when allow_nat is True.
    """
    if pd.isna(val) or val is pd.NaT:
        if allow_nat:
            return None
        raise ValueError(f"Invalid {context}: NaT or null is not permitted for selected prediction/event timestamp")

    if isinstance(val, (int, np.integer)):
        return int(val)

    if isinstance(val, (float, np.floating)):
        if not math.isfinite(val):
            if allow_nat:
                return None
            raise ValueError(f"Invalid {context}: non-finite numeric timestamp {val}")
        if val != math.floor(val):
            raise ValueError(f"Invalid {context}: fractional hour {val} is not permitted")
        return int(val)

    if isinstance(val, pd.Timestamp):
        ns = val.value
        if ns % HOUR_NS != 0:
            raise ValueError(
                f"Invalid {context}: timestamp {val} is not hour-aligned (sub-hour remainder: {ns % HOUR_NS} ns)"
            )
        return int(ns // HOUR_NS)

    if isinstance(val, str):
        try:
            f = float(val)
            if not math.isfinite(f):
                if allow_nat:
                    return None
                raise ValueError(f"Invalid {context}: non-finite string timestamp {val}")
            if f != math.floor(f):
                raise ValueError(f"Invalid {context}: fractional hour string {val} is not permitted")
            return int(f)
        except ValueError:
            dt = pd.to_datetime(val)
            return to_epoch_hour(dt, allow_nat=allow_nat, context=context)

    raise TypeError(f"Invalid {context}: unsupported timestamp type {type(val).__name__} for {val}")


def random_hit_probability(n: int, h: int, k: int) -> float:
    """Exact combinatorial top-k hit probability from drawing k without replacement."""
    if r2_random_hit_probability is not None:
        return float(r2_random_hit_probability(n, h, k))
    if n <= 0 or h <= 0 or k <= 0:
        return 0.0
    k = min(k, n)
    h = min(h, n)
    return 1.0 - (math.comb(n - h, k) / math.comb(n, k) if n - h >= k else 0.0)


def paired_rfid_bootstrap_diff(
    events: pd.DataFrame,
    method: str,
    comparator: str,
    k: int,
    repetitions: int = BOOTSTRAP_B,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Paired cluster bootstrap over distinct vessels (RFIDs), preserving all events."""
    if r2_bootstrap_diff is not None:
        return r2_bootstrap_diff(events, method, comparator, k, repetitions=repetitions, seed=seed)
    if events.empty:
        return {"n_events": 0, "n_rfid": 0, "mean_difference": None, "ci95": [None, None]}
    wide = events.pivot_table(index=["acc_id", "rfid_id"], columns=["method", "k"], values="hit", aggfunc="first")
    a, b = (method, k), (comparator, k)
    if a not in wide or b not in wide:
        return {"n_events": int(len(events)), "n_rfid": int(events["rfid_id"].nunique()), "mean_difference": None, "ci95": [None, None]}
    paired = wide[[a, b]].dropna().reset_index()
    paired["d"] = paired[a].astype(float) - paired[b].astype(float)
    groups = {rfid: g["d"].to_numpy(dtype=float) for rfid, g in paired.groupby("rfid_id", sort=True)}
    rfids = list(groups)
    if not rfids:
        return {"n_events": 0, "n_rfid": 0, "mean_difference": None, "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    vals = np.empty(repetitions, dtype=float)
    for ix in range(repetitions):
        draw = rng.choice(rfids, size=len(rfids), replace=True)
        concatenated = [groups[r] for r in draw]
        vals[ix] = np.concatenate(concatenated).mean()
    return {
        "n_events": int(len(paired)),
        "n_rfid": len(rfids),
        "mean_difference": float(paired["d"].mean()),
        "ci95": [float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))],
        "bootstrap_repetitions": repetitions,
        "seed": seed,
    }


def _build_stage_counts(
    ledger: pd.DataFrame,
    manifest: pd.DataFrame,
    stage_spec: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """Create a detailed stage transition, rejection, and fallback ledger looping stage_spec."""
    if stage_spec is None:
        stage_spec = STAGE_SPEC
    records: list[dict[str, Any]] = []

    stage_masks = {}
    for stg in stage_spec:
        s_id = stg["stage_id"]
        m_col = stg["mask_column"]
        stage_masks[s_id] = ledger[m_col].to_numpy() if m_col in ledger else np.zeros(len(ledger), dtype=bool)

    # 1. Sequential stage candidates and explicit reasons
    for stg in stage_spec:
        s_id = stg["stage_id"]
        in_id = stg.get("input_stage")
        m_col = stg["mask_column"]
        stat_col = stg.get("status_column", f"{s_id}_status")
        rsn_col = stg.get("reason_column", f"{s_id}_reason")

        # Input rows to this stage
        if in_id is None:
            in_mask = np.ones(len(ledger), dtype=bool)
            in_reason = "canonical_input_rows"
            in_desc = f"Total canonical hourly observations presented for {s_id}"
        else:
            in_mask = stage_masks.get(in_id, np.ones(len(ledger), dtype=bool))
            in_reason = f"{in_id}_ok"
            in_desc = f"Input rows admitted from {in_id}"

        in_cnt = int(in_mask.sum())
        in_rfid = int(ledger.loc[in_mask, "rfid_id"].nunique()) if in_cnt > 0 else 0
        records.append({
            "category_type": "candidate_transition",
            "stage": s_id,
            "status": "input",
            "reason": in_reason,
            "row_count": in_cnt,
            "rfid_count": in_rfid,
            "description": in_desc,
        })

        # Keep rows admitted by this stage
        keep_mask = in_mask & stage_masks[s_id]
        keep_cnt = int(keep_mask.sum())
        keep_rfid = int(ledger.loc[keep_mask, "rfid_id"].nunique()) if keep_cnt > 0 else 0
        records.append({
            "category_type": "candidate_transition",
            "stage": s_id,
            "status": "keep",
            "reason": f"{s_id}_admitted",
            "row_count": keep_cnt,
            "rfid_count": keep_rfid,
            "description": f"Rows meeting stage condition: {stg.get('label', s_id)}",
        })

        # Rejected or deferred rows (missing observations MUST defer)
        not_admitted_mask = in_mask & ~stage_masks[s_id]
        if not_admitted_mask.any() and stat_col in ledger and rsn_col in ledger:
            sub = ledger[not_admitted_mask]
            for (status, reason), grp in sub.groupby([stat_col, rsn_col], dropna=False):
                stat_str = str(status) if pd.notna(status) else "defer"
                rsn_str = str(reason) if pd.notna(reason) else "unspecified"
                records.append({
                    "category_type": "candidate_transition",
                    "stage": s_id,
                    "status": stat_str,
                    "reason": rsn_str,
                    "row_count": int(len(grp)),
                    "rfid_count": int(grp["rfid_id"].nunique()),
                    "description": f"Stage {s_id} {stat_str}: {rsn_str}",
                })

    # 2. Strict vessel-level candidate presence
    for stg in stage_spec:
        s_id = stg["stage_id"]
        mask = stage_masks.get(s_id, np.zeros(len(ledger), dtype=bool))
        n_rfid = int(ledger.loc[mask, "rfid_id"].nunique()) if mask.any() else 0
        records.append({
            "category_type": "rfid_candidate_presence",
            "stage": s_id,
            "status": "presence",
            "reason": f"vessels_with_ge_1_{s_id}_candidate",
            "row_count": int(mask.sum()),
            "rfid_count": n_rfid,
            "description": f"Number of distinct vessels with at least one {s_id} candidate ({stg.get('label', '')})",
        })

    # 3. Actual fallback method coverage (from manifest)
    for method in METHODS:
        m_rows = manifest[manifest["method"] == method] if "method" in manifest else manifest.iloc[0:0]
        if not m_rows.empty and "pool_stage" in m_rows and "fallback_reason" in m_rows:
            for (pool_stage, fb_reason), grp in m_rows.groupby(["pool_stage", "fallback_reason"], dropna=False):
                fb_str = str(fb_reason) if pd.notna(fb_reason) and fb_reason is not None else "strict_stage"
                records.append({
                    "category_type": "method_actual_pool_coverage",
                    "stage": str(pool_stage),
                    "status": "fallback" if fb_str != "strict_stage" else "strict",
                    "reason": fb_str,
                    "row_count": int(grp["actual_pool_n"].sum()) if "actual_pool_n" in grp else 0,
                    "rfid_count": int(len(grp)),
                    "description": f"Method {method} actual pool assigned: {pool_stage} (fallback: {fb_str})",
                })

    return pd.DataFrame(records)


def evaluate_shape(artifacts: dict[str, Any], positives: pd.DataFrame, output_dir: Path | str) -> dict[str, Any]:
    """Evaluate shape-based candidate rules against positive events.

    Writes predictions, pool_manifest, and candidate_ledger BEFORE parsing/joining labels.
    Outputs stage_counts.csv, stage_event_coverage.csv, event_results.csv,
    metrics.json, and diagnostics.json.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    required_artifacts = {"ledger", "predictions", "pool_manifest"}
    missing_artifacts = required_artifacts - set(artifacts.keys())
    if missing_artifacts:
        raise ValueError(f"artifacts missing required keys: {sorted(missing_artifacts)}")

    ledger: pd.DataFrame = artifacts["ledger"].copy()
    predictions: pd.DataFrame = artifacts["predictions"].copy()
    pool_manifest: pd.DataFrame = artifacts["pool_manifest"].copy()
    rule_diagnostics: dict[str, Any] = artifacts.get("diagnostics", {})
    stage_spec: list[dict[str, Any]] = artifacts.get("stage_spec", STAGE_SPEC)
    gear_registry: pd.DataFrame | None = artifacts.get("gear_registry", None)

    # 1. SAVE PREDICTIONS, POOL_MANIFEST, AND CANDIDATE_LEDGER BEFORE LABELS ARE PARSED/JOINED
    pred_path = output_dir / "predictions.csv"
    if not pred_path.exists():
        predictions.to_csv(pred_path, index=False)
    manifest_path = output_dir / "pool_manifest.csv"
    if not manifest_path.exists():
        pool_manifest.to_csv(manifest_path, index=False)
    ledger_path = output_dir / "candidate_ledger.parquet"
    if not ledger_path.exists():
        ledger.to_parquet(ledger_path, engine="pyarrow", index=False)

    # 2. Build generic stage transition counts
    stage_counts_df = _build_stage_counts(ledger, pool_manifest, stage_spec)
    stage_counts_df.to_csv(output_dir / "stage_counts.csv", index=False)

    # 3. Canonical positive events schema validation
    pos_req = ["acc_id", "rfid_id", "tier", "acc_ts"]
    missing_pos = set(pos_req) - set(positives.columns)
    if missing_pos:
        raise ValueError(f"positives missing required columns: {sorted(missing_pos)}")

    events = positives.copy()
    events["acc_id"] = events["acc_id"].astype(str)
    events["rfid_id"] = events["rfid_id"].map(_norm_id)
    events["tier"] = pd.to_numeric(events["tier"], errors="raise").astype(int)
    events["acc_ts"] = events["acc_ts"].map(lambda x: to_epoch_hour(x, allow_nat=False, context="positive event acc_ts")).astype("int64")
    if "conflict" not in events.columns:
        events["conflict"] = None

    # Pre-index predictions by (rfid_id, method) with validated epoch hours
    pred_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in predictions.itertuples(index=False):
        p_dict = p._asdict()
        p_dict["_ts_hour"] = to_epoch_hour(p_dict["ts"], allow_nat=False, context="prediction ts")
        pred_index[(str(p.rfid_id), str(p.method))].append(p_dict)
    for k in pred_index:
        pred_index[k].sort(key=lambda x: int(x["rank"]))

    # Pre-calculate top4 time span per (rfid_id, method)
    rfid_method_explanation: dict[tuple[str, str], dict[str, Any]] = {}
    for (rid, method), plist in pred_index.items():
        top4 = [p for p in plist if int(p["rank"]) <= 4]
        times = [p["_ts_hour"] for p in top4]
        time_span = float(max(times) - min(times)) if len(times) >= 2 else 0.0
        rfid_method_explanation[(rid, method)] = {
            "top4_count": len(top4),
            "time_span_hours": time_span,
        }

    # Pre-index manifest by (rfid_id, method)
    manifest_index: dict[tuple[str, str], dict[str, Any]] = {}
    for m in pool_manifest.itertuples(index=False):
        manifest_index[(str(m.rfid_id), str(m.method))] = {
            "pool_stage": str(m.pool_stage),
            "actual_pool_n": int(m.actual_pool_n),
            "cap": int(m.cap),
            "fallback_reason": str(m.fallback_reason) if pd.notna(m.fallback_reason) and m.fallback_reason is not None else None,
        }

    # Pre-index gear info
    gear_info: dict[str, tuple[str, bool]] = {}
    if "primary_gear" in ledger.columns and "is_single_code" in ledger.columns:
        gear_subset = ledger.drop_duplicates("rfid_id")[["rfid_id", "primary_gear", "is_single_code"]]
        for r in gear_subset.itertuples(index=False):
            g_name = str(r.primary_gear) if pd.notna(r.primary_gear) and r.primary_gear is not None else "unknown"
            s_code = bool(r.is_single_code) if pd.notna(r.is_single_code) and r.is_single_code is not None else False
            gear_info[str(r.rfid_id)] = (g_name, s_code)
    if gear_registry is not None:
        for r in gear_registry.itertuples(index=False):
            rid = _norm_id(r.rfid_id)
            g_name = str(r.primary_gear) if pd.notna(r.primary_gear) and r.primary_gear is not None else "unknown"
            s_code = bool(r.is_single_code) if pd.notna(r.is_single_code) and r.is_single_code is not None else False
            gear_info[rid] = (g_name, s_code)

    # Pre-group ledger by vessel with explicit epoch hour
    ledger["rfid_id"] = ledger["rfid_id"].map(_norm_id)
    ledger["_hour_int"] = ledger["ts"].map(lambda x: to_epoch_hour(x, allow_nat=False, context="ledger ts")).astype("int64")
    vessels: dict[str, pd.DataFrame] = {str(rid): g for rid, g in ledger.groupby("rfid_id", sort=False)}

    # 4. Event-level evaluation and stage coverage
    event_result_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for ev in events.itertuples(index=False):
        rid = str(ev.rfid_id)
        acc_ts = int(ev.acc_ts)
        v = vessels.get(rid, None)
        g_name, s_code = gear_info.get(rid, ("unknown", False))
        gear_stratum = g_name if s_code else ("mixed" if g_name not in ("unknown", "unobserved") else "unknown")

        # Generic stage window observability
        stage_window_obs = {}
        stage_vessel_has = {}
        if v is not None and len(v) > 0:
            in_win = v["_hour_int"].between(acc_ts - TOLERANCE_HOURS, acc_ts + TOLERANCE_HOURS)
            obs_win = bool(in_win.any())
            for stg in stage_spec:
                sid = stg["stage_id"]
                m_col = stg["mask_column"]
                stage_window_obs[sid] = bool((in_win & v[m_col]).any()) if m_col in v else False
                stage_vessel_has[sid] = bool(v[m_col].any()) if m_col in v else False
        else:
            obs_win = False
            for stg in stage_spec:
                sid = stg["stage_id"]
                stage_window_obs[sid] = False
                stage_vessel_has[sid] = False

        cov_entry: dict[str, Any] = {
            "acc_id": str(ev.acc_id),
            "rfid_id": rid,
            "tier": int(ev.tier),
            "conflict": getattr(ev, "conflict", None),
            "acc_ts": acc_ts,
            "primary_gear": g_name,
            "is_single_code": s_code,
            "gear_stratum": gear_stratum,
            "observed_in_window": obs_win,
        }
        for sid, val in stage_window_obs.items():
            cov_entry[f"{sid}_in_window"] = val
        for sid, val in stage_vessel_has.items():
            cov_entry[f"vessel_has_{sid}"] = val

        for method in METHODS:
            meta = manifest_index.get((rid, method), {"pool_stage": "none", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})
            cov_entry[f"{method}_pool_stage"] = meta["pool_stage"]
            cov_entry[f"{method}_fallback_reason"] = meta["fallback_reason"]
            exp = rfid_method_explanation.get((rid, method), {"top4_count": 0, "time_span_hours": 0.0})
            cov_entry[f"{method}_top4_count"] = exp["top4_count"]
            cov_entry[f"{method}_top4_time_span_hours"] = exp["time_span_hours"]

            preds = pred_index.get((rid, method), [])
            for k in BUDGETS:
                chosen = [p for p in preds if int(p["rank"]) <= k]
                times = [int(p["_ts_hour"]) for p in chosen]
                if times:
                    err = int(min(abs(t - acc_ts) for t in times))
                    hit = bool(err <= TOLERANCE_HOURS)
                else:
                    err = None
                    hit = False
                cov_entry[f"{method}_hit_top{k}"] = hit

                res_row = {
                    "acc_id": str(ev.acc_id),
                    "rfid_id": rid,
                    "tier": int(ev.tier),
                    "conflict": getattr(ev, "conflict", None),
                    "acc_ts": acc_ts,
                    "primary_gear": g_name,
                    "is_single_code": s_code,
                    "gear_stratum": gear_stratum,
                    "method": method,
                    "k": k,
                    "predicted_times": json.dumps(times),
                    "abs_error": err,
                    "hit": hit,
                    "pool_stage": meta["pool_stage"],
                    "fallback_reason": meta["fallback_reason"],
                    "actual_pool_n": meta["actual_pool_n"],
                    "cap": meta["cap"],
                    "top4_count": exp["top4_count"],
                    "top4_time_span_hours": exp["time_span_hours"],
                }
                for sid, val in stage_window_obs.items():
                    res_row[f"window_observable_{sid}"] = val
                event_result_rows.append(res_row)

        coverage_rows.append(cov_entry)

    event_results_df = pd.DataFrame(event_result_rows)
    event_results_df.to_csv(output_dir / "event_results.csv", index=False)

    stage_event_coverage_df = pd.DataFrame(coverage_rows)
    stage_event_coverage_df.to_csv(output_dir / "stage_event_coverage.csv", index=False)

    # 5. Method-specific Random Expectations (strictly over each method's ACTUAL pool and cap)
    # CONTRACT: Keep separate random event records/means for each method AND all100/Tier01=60 scopes.
    random_expectations: dict[str, Any] = {}
    for scope_name, sub_events in [("all", events), ("tier01", events[events["tier"] <= 1])]:
        scope_pools: dict[str, Any] = {}
        for method in METHODS:
            m_records: list[dict[str, Any]] = []
            for ev in sub_events.itertuples(index=False):
                rid = str(ev.rfid_id)
                acc_ts = int(ev.acc_ts)
                meta = manifest_index.get((rid, method), {"pool_stage": "s0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})
                v = vessels.get(rid, None)
                pool_stg = meta["pool_stage"]
                cap = meta["cap"]

                mask_col = f"{pool_stg}_ok"
                if v is not None and mask_col in v:
                    pool = v[v[mask_col]]
                    n = len(pool)
                    h = int(pool["_hour_int"].between(acc_ts - TOLERANCE_HOURS, acc_ts + TOLERANCE_HOURS).sum())
                else:
                    n = 0
                    h = 0
                h = min(h, n)
                kcap = min(cap, n)
                top1_exp = (h / n) if n > 0 else 0.0
                top4_prob = random_hit_probability(n, h, kcap)

                m_records.append({
                    "acc_id": str(ev.acc_id),
                    "rfid_id": rid,
                    "method": method,
                    "pool_stage": pool_stg,
                    "fallback_reason": meta["fallback_reason"],
                    "n": n,
                    "h": h,
                    "kcap": kcap,
                    "top1_expected": top1_exp,
                    "top4_hit_probability": top4_prob,
                })

            denom = len(m_records)
            scope_pools[method] = {
                "denominator_events": denom,
                "mean_top1_expected": float(np.mean([r["top1_expected"] for r in m_records])) if denom else 0.0,
                "mean_top4_hit_probability": float(np.mean([r["top4_hit_probability"] for r in m_records])) if denom else 0.0,
                "event_probabilities": m_records,
            }
        random_expectations[scope_name] = {
            "denominator_events": int(len(sub_events)),
            "unique_rfids": int(sub_events["rfid_id"].nunique()),
            "pools": scope_pools,
        }

    # 6. Paired RFID cluster bootstrap (B=4000, seed=20261105)
    bootstrap_results: dict[str, Any] = {}
    for scope_name, sub_events in [("all", events), ("tier01", events[events["tier"] <= 1])]:
        sub_acc_ids = set(sub_events["acc_id"].astype(str))
        sub_results = event_results_df[event_results_df["acc_id"].isin(sub_acc_ids)]
        scope_boot: dict[str, Any] = {}
        for m_a, m_b in [("G", "B0"), ("G", "S"), ("S", "B0")]:
            for k in BUDGETS:
                boot_key = f"{m_a}-vs-{m_b}-top{k}"
                scope_boot[boot_key] = paired_rfid_bootstrap_diff(
                    sub_results, m_a, m_b, k, repetitions=BOOTSTRAP_B, seed=BOOTSTRAP_SEED
                )
        bootstrap_results[scope_name] = scope_boot

    # 7. Denominators and hit rate summaries
    denominators_summary: dict[str, Any] = {}
    for scope_name, sub_events in [("all", events), ("tier01", events[events["tier"] <= 1])]:
        sub_acc_ids = set(sub_events["acc_id"].astype(str))
        sub_res = event_results_df[event_results_df["acc_id"].isin(sub_acc_ids)]
        scope_summary: dict[str, Any] = {
            "events": int(len(sub_events)),
            "unique_rfids": int(sub_events["rfid_id"].nunique()),
        }
        for method in METHODS:
            for k in BUDGETS:
                grp = sub_res[(sub_res["method"] == method) & (sub_res["k"] == k)]
                d_cnt = len(grp)
                h_cnt = int(grp["hit"].sum())
                scope_summary[f"{method}_top{k}"] = {
                    "events": d_cnt,
                    "hits": h_cnt,
                    "hit_rate": float(h_cnt / d_cnt) if d_cnt > 0 else 0.0,
                }
        denominators_summary[scope_name] = scope_summary

    # Stratified gear summaries
    gear_strata_summary: dict[str, Any] = {}
    for stratum, grp_cov in stage_event_coverage_df.groupby("gear_stratum"):
        s_acc = set(grp_cov["acc_id"])
        s_res = event_results_df[event_results_df["acc_id"].isin(s_acc)]
        s_info: dict[str, Any] = {
            "events": len(grp_cov),
            "tier01_events": int((grp_cov["tier"] <= 1).sum()),
            "unique_rfids": int(grp_cov["rfid_id"].nunique()),
        }
        for method in METHODS:
            for k in BUDGETS:
                g_k = s_res[(s_res["method"] == method) & (s_res["k"] == k)]
                d = len(g_k)
                h = int(g_k["hit"].sum())
                s_info[f"{method}_top{k}"] = {
                    "events": d,
                    "hits": h,
                    "hit_rate": float(h / d) if d > 0 else 0.0,
                }
        gear_strata_summary[str(stratum)] = s_info
    denominators_summary["gear_strata"] = gear_strata_summary

    # 8. Fixed Operational Gate Formulation
    # CONTRACT: Tier01 G-B0 top1 >= .05 (5 percentage points), that paired CI lower > 0,
    # all100 nonworse, and Tier01 G hitrate > Tier01 G actual-pool random expectation.
    # Four booleans and values explicit.
    t01_events = int(denominators_summary["tier01"]["events"])
    t01_g_hits = int(denominators_summary["tier01"]["G_top1"]["hits"])
    t01_b0_hits = int(denominators_summary["tier01"]["B0_top1"]["hits"])
    t01_hit_delta = t01_g_hits - t01_b0_hits

    t01_g_top1 = float(t01_g_hits / t01_events) if t01_events > 0 else 0.0
    t01_b0_top1 = float(t01_b0_hits / t01_events) if t01_events > 0 else 0.0
    t01_diff = float(t01_hit_delta / t01_events) if t01_events > 0 else 0.0

    all_events = int(denominators_summary["all"]["events"])
    all_g_hits = int(denominators_summary["all"]["G_top1"]["hits"])
    all_b0_hits = int(denominators_summary["all"]["B0_top1"]["hits"])
    all_hit_delta = all_g_hits - all_b0_hits

    all_g_top1 = float(all_g_hits / all_events) if all_events > 0 else 0.0
    all_b0_top1 = float(all_b0_hits / all_events) if all_events > 0 else 0.0
    all_diff = float(all_hit_delta / all_events) if all_events > 0 else 0.0

    ci95 = bootstrap_results["tier01"]["G-vs-B0-top1"]["ci95"]
    ci95_lower = ci95[0] if ci95 and ci95[0] is not None else None

    # CRITICAL: Match scope! Tier01 G hit rate vs Tier01 G actual-pool random expectation
    rand_expected_g_t01 = random_expectations["tier01"]["pools"]["G"]["mean_top1_expected"]

    # Condition 1: Exact integer count threshold 20 * (G_hits - B0_hits) >= n_tier01 (exactly +5 percentage points)
    # Avoids binary floating-point rounding errors (e.g. 5/60 - 2/60 = 0.049999999999999996 < 0.05)
    gate_cond1_improvement = bool(t01_events > 0 and (20 * t01_hit_delta >= t01_events))
    gate_cond2_ci_positive = bool(ci95_lower is not None and ci95_lower > 0.0)
    # Condition 3: Whole 100 non-worsening using equal-denominator integer counts: all_g_hits >= all_b0_hits
    gate_cond3_non_worsening = bool(all_hit_delta >= 0)
    gate_cond4_exceeds_random = bool(t01_g_top1 > rand_expected_g_t01)

    overall_gate_passed = bool(
        gate_cond1_improvement and gate_cond2_ci_positive and gate_cond3_non_worsening and gate_cond4_exceeds_random
    )

    gate_failures: list[str] = []
    if not gate_cond1_improvement:
        gate_failures.append(f"tier01_top1 exact count 20 * (G - B0) ({20 * t01_hit_delta}) < n ({t01_events}) [diff={t01_diff:+.4f}]")
    if not gate_cond2_ci_positive:
        gate_failures.append(f"tier01_top1 paired bootstrap 95% CI lower bound ({ci95_lower}) <= 0.0")
    if not gate_cond3_non_worsening:
        gate_failures.append(f"whole100_top1 hit delta ({all_hit_delta}) < 0 (worsened vs B0) [diff={all_diff:+.4f}]")
    if not gate_cond4_exceeds_random:
        gate_failures.append(f"tier01_top1 hit rate ({t01_g_top1:.4f}) does not exceed Tier01 random expectation ({rand_expected_g_t01:.4f})")

    operational_gate = {
        "tier01_top1_diff_g_vs_b0": {
            "target": ">= +0.05 (+5.0 percentage points, exact count 20 * (G_hits - B0_hits) >= n)",
            "threshold": 0.05,
            "observed": t01_diff,
            "observed_hits_g": t01_g_hits,
            "observed_hits_b0": t01_b0_hits,
            "observed_n": t01_events,
            "passed": gate_cond1_improvement,
        },
        "tier01_top1_ci95_lower_positive": {
            "target": "> 0.0 (paired cluster bootstrap 95% CI lower bound)",
            "threshold": 0.0,
            "observed_ci95": ci95,
            "observed_lower": ci95_lower,
            "passed": gate_cond2_ci_positive,
        },
        "whole100_non_worsening": {
            "target": ">= 0.0 (all100 top1 difference G vs B0, exact count G_hits >= B0_hits)",
            "threshold": 0.0,
            "observed": all_diff,
            "observed_hits_g": all_g_hits,
            "observed_hits_b0": all_b0_hits,
            "observed_n": all_events,
            "passed": gate_cond3_non_worsening,
        },
        "tier01_top1_exceeds_random": {
            "target": "Tier01 G top1 hit rate > Tier01 G actual-pool random expectation",
            "observed_hit_rate": t01_g_top1,
            "observed_random_expectation": rand_expected_g_t01,
            "passed": gate_cond4_exceeds_random,
        },
        "overall_passed": overall_gate_passed,
        "gate_failures": gate_failures,
    }

    # 9. Assembly of Metrics and Diagnostics
    metrics = {
        "status": "deterministic_shape_evaluation",
        "description": "Round 8 shape-based candidate rules and event evaluation",
        "methods": list(METHODS),
        "budgets": list(BUDGETS),
        "tolerance_hours_inclusive": TOLERANCE_HOURS,
        "operational_gate": operational_gate,
        "denominators": denominators_summary,
        "random_expectations": random_expectations,
        "rfid_cluster_bootstrap": bootstrap_results,
        "rule_diagnostics": rule_diagnostics,
    }
    _write_json(output_dir / "metrics.json", metrics)

    diagnostics = {
        "total_events": int(len(events)),
        "tier01_events": int((events["tier"] <= 1).sum()),
        "rfid_count": int(events["rfid_id"].nunique()),
        "canonical_ledger_rows": int(len(ledger)),
        "prediction_rows": int(len(predictions)),
        "pool_manifest_rows": int(len(pool_manifest)),
        "event_result_rows": int(len(event_result_rows)),
        "coverage_rows": int(len(coverage_rows)),
        "operational_gate_passed": overall_gate_passed,
        "operational_gate_failures": gate_failures,
        "rule_diagnostics": rule_diagnostics,
    }
    _write_json(output_dir / "diagnostics.json", diagnostics)

    return {
        "metrics": metrics,
        "diagnostics": diagnostics,
        "event_results": event_results_df,
        "stage_event_coverage": stage_event_coverage_df,
        "stage_counts": stage_counts_df,
    }
