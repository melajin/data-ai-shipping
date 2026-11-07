"""Round 6 evaluation module: deterministic event evaluation, paired cluster bootstrap,
and separate cohort random expectation over duration-history ranking rules.

This module is descriptive and evaluative only. It does not assign accident probabilities,
conduct online anomaly detection, or rerank model predictions.
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

STAGE_SPEC = [
    {"stage_id": "d0", "label": "valid geometry and legacy score", "input_stage": None, "mask_column": "d0_ok", "status_column": "d0_status", "reason_column": "d0_reason"},
    {"stage_id": "d1", "label": "current observation is small", "input_stage": "d0", "mask_column": "d1_ok", "status_column": "d1_status", "reason_column": "d1_reason"},
    {"stage_id": "d2", "label": "observed continuation", "input_stage": "d1", "mask_column": "d2_ok", "status_column": "d2_status", "reason_column": "d2_reason"},
    {"stage_id": "d3", "label": "eligible self history", "input_stage": "d2", "mask_column": "d3_ok", "status_column": "d3_status", "reason_column": "d3_reason"},
    {"stage_id": "d4", "label": "eligible same-gear peer history", "input_stage": "d3", "mask_column": "d4_ok", "status_column": "d4_status", "reason_column": "d4_reason"},
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


def _to_hour_val(val: Any) -> int:
    """Normalize integer hours, timestamps, or strings into integer hours."""
    if pd.isna(val):
        return 0
    if isinstance(val, pd.Timestamp):
        # If timestamp value is small (within first year: value < 1e9),
        # it was created from integer hours without unit
        if val.value < 1_000_000_000:
            return int(val.value)
        # Standard epoch nanoseconds -> hours
        return int(val.value // (3600 * 1_000_000_000))
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        return int(val)
    try:
        return int(val)
    except (ValueError, TypeError):
        dt = pd.to_datetime(val)
        return int(dt.value // (3600 * 1_000_000_000))


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
        stat_col = stg["status_column"]
        rsn_col = stg["reason_column"]

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


def evaluate_duration(artifacts: dict[str, Any], positives: pd.DataFrame, output_dir: Path | str) -> dict[str, Any]:
    """Evaluate duration-based candidate rules against positive events.

    Writes predictions, pool_manifest, run_registry, and candidate_ledger strictly before
    parsing/joining labels. Outputs stage_counts.csv, stage_event_coverage.csv, event_results.csv,
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
    run_registry: pd.DataFrame = artifacts.get("run_registry", pd.DataFrame()).copy()
    rule_diagnostics: dict[str, Any] = artifacts.get("diagnostics", {})
    stage_spec: list[dict[str, Any]] = artifacts.get("stage_spec", STAGE_SPEC)
    gear_registry: pd.DataFrame | None = artifacts.get("gear_registry", None)

    # 1. SAVE PREDICTIONS, POOL_MANIFEST, RUN_REGISTRY, AND LEDGER BEFORE LABELS ARE JOINED
    predictions.to_csv(output_dir / "predictions.csv", index=False)
    pool_manifest.to_csv(output_dir / "pool_manifest.csv", index=False)
    if isinstance(run_registry, pd.DataFrame) and not run_registry.empty:
        run_registry.to_csv(output_dir / "run_registry.csv", index=False)
    ledger.to_parquet(output_dir / "candidate_ledger.parquet", engine="pyarrow", index=False)

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
    events["acc_ts"] = events["acc_ts"].map(_to_hour_val).astype("int64")
    if "conflict" not in events.columns:
        events["conflict"] = None

    # Pre-index predictions by (rfid_id, method)
    pred_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in predictions.itertuples(index=False):
        pred_index[(str(p.rfid_id), str(p.method))].append(p._asdict())
    for k in pred_index:
        pred_index[k].sort(key=lambda x: int(x["rank"]))

    # Pre-calculate explanatory distinct run count and top4 time span per (rfid_id, method)
    rfid_method_explanation: dict[tuple[str, str], dict[str, Any]] = {}
    for (rid, method), plist in pred_index.items():
        top4 = [p for p in plist if int(p["rank"]) <= 4]
        runs = [p.get("run_id") for p in top4 if p.get("run_id") is not None and str(p.get("run_id")) != ""]
        distinct_runs = len(set(runs))
        times = [_to_hour_val(p.get("ts")) for p in top4]
        time_span = float(max(times) - min(times)) if len(times) >= 2 else 0.0
        rfid_method_explanation[(rid, method)] = {
            "distinct_runs": distinct_runs,
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

    # Pre-group ledger by vessel with normalized ts
    ledger["rfid_id"] = ledger["rfid_id"].map(_norm_id)
    ledger["_hour_int"] = ledger["ts"].map(_to_hour_val).astype("int64")
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
            exp = rfid_method_explanation.get((rid, method), {"distinct_runs": 0, "time_span_hours": 0.0})
            cov_entry[f"{method}_top4_distinct_runs"] = exp["distinct_runs"]
            cov_entry[f"{method}_top4_time_span_hours"] = exp["time_span_hours"]

            preds = pred_index.get((rid, method), [])
            for k in BUDGETS:
                chosen = [p for p in preds if int(p["rank"]) <= k]
                times = [_to_hour_val(p["ts"]) for p in chosen]
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
                    "top4_distinct_runs": exp["distinct_runs"],
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
                meta = manifest_index.get((rid, method), {"pool_stage": "d0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})
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
    t01_g_top1 = denominators_summary["tier01"]["G_top1"]["hit_rate"]
    t01_b0_top1 = denominators_summary["tier01"]["B0_top1"]["hit_rate"]
    t01_diff = float(t01_g_top1 - t01_b0_top1)

    all_g_top1 = denominators_summary["all"]["G_top1"]["hit_rate"]
    all_b0_top1 = denominators_summary["all"]["B0_top1"]["hit_rate"]
    all_diff = float(all_g_top1 - all_b0_top1)

    ci95 = bootstrap_results["tier01"]["G-vs-B0-top1"]["ci95"]
    ci95_lower = ci95[0] if ci95 and ci95[0] is not None else None

    # CRITICAL: Match scope! Tier01 G hit rate vs Tier01 G actual-pool random expectation
    rand_expected_g_t01 = random_expectations["tier01"]["pools"]["G"]["mean_top1_expected"]

    gate_cond1_improvement = bool(t01_diff >= 0.05)
    gate_cond2_ci_positive = bool(ci95_lower is not None and ci95_lower > 0.0)
    gate_cond3_non_worsening = bool(all_diff >= 0.0)
    gate_cond4_exceeds_random = bool(t01_g_top1 > rand_expected_g_t01)

    overall_gate_passed = bool(
        gate_cond1_improvement and gate_cond2_ci_positive and gate_cond3_non_worsening and gate_cond4_exceeds_random
    )

    gate_failures: list[str] = []
    if not gate_cond1_improvement:
        gate_failures.append(f"tier01_top1_diff ({t01_diff:+.4f}) < +0.05 requirement")
    if not gate_cond2_ci_positive:
        gate_failures.append(f"tier01_top1 paired bootstrap 95% CI lower bound ({ci95_lower}) <= 0.0")
    if not gate_cond3_non_worsening:
        gate_failures.append(f"whole100_top1 difference ({all_diff:+.4f}) < 0.0 (worsened vs B0)")
    if not gate_cond4_exceeds_random:
        gate_failures.append(f"tier01_top1 hit rate ({t01_g_top1:.4f}) does not exceed Tier01 random expectation ({rand_expected_g_t01:.4f})")

    operational_gate = {
        "tier01_top1_diff_g_vs_b0": {
            "target": ">= +0.05 (+5.0 percentage points)",
            "threshold": 0.05,
            "g_hit_rate": t01_g_top1,
            "b0_hit_rate": t01_b0_top1,
            "observed_difference": t01_diff,
            "passed": gate_cond1_improvement,
        },
        "tier01_top1_paired_bootstrap_ci95_lower": {
            "target": "> 0.0",
            "threshold": 0.0,
            "observed_ci95": ci95,
            "ci95_lower": ci95_lower,
            "passed": gate_cond2_ci_positive,
        },
        "whole100_top1_non_worsening": {
            "target": "G >= B0 on all 100 events",
            "g_hit_rate": all_g_top1,
            "b0_hit_rate": all_b0_top1,
            "observed_difference": all_diff,
            "passed": gate_cond3_non_worsening,
        },
        "tier01_top1_exceeds_random": {
            "target": "G Tier01 top1 > actual pool random expectation (Tier01 scope)",
            "observed_hit_rate": t01_g_top1,
            "expected_random_rate": rand_expected_g_t01,
            "passed": gate_cond4_exceeds_random,
        },
        "overall_passed": overall_gate_passed,
        "gate_failures": gate_failures,
    }

    # 9. Explanatory reporting: current run lower bounds, reference censoring, distinct runs, time span
    # CONTRACT: Report current run lower bounds, reference censoring, selected distinct run count/time span as explanation, no normal-truth claims.
    tot_small_obs = int(ledger["d1_ok"].sum()) if "d1_ok" in ledger else 0
    tot_lower_bound_obs = int(ledger["current_L_is_lower_bound"].sum()) if "current_L_is_lower_bound" in ledger else 0
    lower_bound_fraction = float(tot_lower_bound_obs / tot_small_obs) if tot_small_obs > 0 else 0.0

    runs_total = int(len(run_registry)) if isinstance(run_registry, pd.DataFrame) else 0
    runs_left_conf = int(run_registry["left_confirmed"].sum()) if isinstance(run_registry, pd.DataFrame) and "left_confirmed" in run_registry else 0
    runs_right_conf = int(run_registry["right_confirmed"].sum()) if isinstance(run_registry, pd.DataFrame) and "right_confirmed" in run_registry else 0
    runs_both_conf = int((run_registry["left_confirmed"] & run_registry["right_confirmed"]).sum()) if isinstance(run_registry, pd.DataFrame) and "left_confirmed" in run_registry and "right_confirmed" in run_registry else 0

    left_censor_dict = run_registry["left_censor_reason"].value_counts(dropna=False).to_dict() if isinstance(run_registry, pd.DataFrame) and "left_censor_reason" in run_registry else {}
    right_censor_dict = run_registry["right_censor_reason"].value_counts(dropna=False).to_dict() if isinstance(run_registry, pd.DataFrame) and "right_censor_reason" in run_registry else {}

    top4_characteristics = {}
    for m in METHODS:
        m_exps = [exp for (rid, meth), exp in rfid_method_explanation.items() if meth == m]
        top4_characteristics[m] = {
            "vessel_count": len(m_exps),
            "mean_distinct_runs": float(np.mean([x["distinct_runs"] for x in m_exps])) if m_exps else 0.0,
            "mean_time_span_hours": float(np.mean([x["time_span_hours"] for x in m_exps])) if m_exps else 0.0,
        }

    explanatory_summary = {
        "disclaimer_no_normal_truth_claims": "Observed duration, continuation, and peer CDFs are ranking statistics and computational filter conditions only. They do not constitute ground truth of normal waiting or accident occurrence.",
        "current_run_lower_bounds": {
            "total_small_observations": tot_small_obs,
            "lower_bound_observations": tot_lower_bound_obs,
            "lower_bound_fraction": lower_bound_fraction,
            "interpretation": "Observations without confirmed left boundary represent lower bounds on run length, not exact completed durations.",
        },
        "run_registry_censoring": {
            "total_runs": runs_total,
            "left_confirmed_runs": runs_left_conf,
            "right_confirmed_runs": runs_right_conf,
            "both_confirmed_completed_runs": runs_both_conf,
            "left_censor_reasons": {str(k): int(v) for k, v in left_censor_dict.items()},
            "right_censor_reasons": {str(k): int(v) for k, v in right_censor_dict.items()},
            "interpretation": "Only runs with both boundaries confirmed by non-small observations qualify as completed references. Gaps and end-of-data censor runs.",
        },
        "top4_prediction_characteristics": top4_characteristics,
    }

    # 10. Write metrics.json
    round2_eval_path = ROUND2_DIR / "data_eval.py"
    round2_hash = _sha256(round2_eval_path) if round2_eval_path.is_file() else None

    metrics = {
        "status": "provisional_descriptive_evaluation",
        "label_status": "provisional; not ground-truth validated",
        "probability_outputs": False,
        "prediction_methods": list(METHODS),
        "budgets": list(BUDGETS),
        "top1_definition": "rank 1 of the same ranked top4 list",
        "tolerance_hours_inclusive": TOLERANCE_HOURS,
        "shared_cap_rule": "min(4, len(actual G pool))",
        "denominators": denominators_summary,
        "same_budget_random_expectation": random_expectations,
        "rfid_cluster_bootstrap": bootstrap_results,
        "bootstrap_repetitions": BOOTSTRAP_B,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "operational_gate": operational_gate,
        "explanatory_duration_and_runs": explanatory_summary,
        "shared_numerical_helpers": {
            "source": "testB/final/round_002_20261105/data_eval.py",
            "functions": ["_random_hit_probability", "_bootstrap_diff"],
            "sha256": round2_hash,
        },
    }
    _write_json(output_dir / "metrics.json", metrics)

    # 11. Write diagnostics.json
    diagnostics = {
        "events_total": int(len(events)),
        "events_tier01": int((events["tier"] <= 1).sum()),
        "rfids_total": int(events["rfid_id"].nunique()),
        "rfids_tier01": int(events.loc[events["tier"] <= 1, "rfid_id"].nunique()),
        "ledger_rows": int(len(ledger)),
        "predictions_rows": int(len(predictions)),
        "pool_manifest_rows": int(len(pool_manifest)),
        "run_registry_rows": runs_total,
        "event_result_rows": int(len(event_result_rows)),
        "stage_event_coverage_rows": int(len(coverage_rows)),
        "unresolved_positive_rfids": sorted(set(events["rfid_id"]) - set(ledger["rfid_id"])),
        "rule_diagnostics": rule_diagnostics,
        "gate_evaluation_summary": {
            "overall_passed": overall_gate_passed,
            "failures": gate_failures,
        },
        "explanatory_duration_and_runs": explanatory_summary,
    }
    _write_json(output_dir / "diagnostics.json", diagnostics)

    return {
        "metrics": metrics,
        "diagnostics": diagnostics,
        "stage_counts": stage_counts_df,
        "stage_event_coverage": stage_event_coverage_df,
        "event_results": event_results_df,
    }
