"""Round 4 evaluation module: deterministic event evaluation, paired cluster bootstrap,
and random expectation over retrospective sequence patterns.

This module is descriptive and evaluative only. It does not assign accident probabilities,
conduct online anomaly detection, or rerank model predictions.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
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


def _build_stage_counts(ledger: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    """Create a detailed stage transition, rejection, and fallback ledger."""
    records: list[dict[str, Any]] = []

    # 1. Sequential stage candidates and explicit reasons
    n_total = len(ledger)
    n_rfid_total = ledger["rfid_id"].nunique()
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage0",
        "status": "input",
        "reason": "canonical_input_rows",
        "row_count": n_total,
        "rfid_count": n_rfid_total,
        "description": "Total canonical hourly observations presented for Stage 0",
    })

    s0_ok = ledger["stage0_ok"].to_numpy()
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage0",
        "status": "keep",
        "reason": "geometry_valid_and_score_finite",
        "row_count": int(s0_ok.sum()),
        "rfid_count": int(ledger.loc[s0_ok, "rfid_id"].nunique()),
        "description": "Rows with finite non-negative length/bbox and finite legacy score",
    })

    geom_valid = ledger["geometry_valid"].to_numpy() if "geometry_valid" in ledger else np.ones(n_total, dtype=bool)
    invalid_geom = int((~geom_valid).sum())
    if invalid_geom > 0:
        records.append({
            "category_type": "candidate_transition",
            "stage": "stage0",
            "status": "reject",
            "reason": "invalid_geometry",
            "row_count": invalid_geom,
            "rfid_count": int(ledger.loc[~geom_valid, "rfid_id"].nunique()),
            "description": "Rows rejected due to non-finite or negative length/bbox",
        })

    invalid_score = int((geom_valid & ~s0_ok).sum())
    if invalid_score > 0:
        records.append({
            "category_type": "candidate_transition",
            "stage": "stage0",
            "status": "reject",
            "reason": "non_finite_legacy_score",
            "row_count": invalid_score,
            "rfid_count": int(ledger.loc[geom_valid & ~s0_ok, "rfid_id"].nunique()),
            "description": "Rows with valid geometry but missing or non-finite legacy score",
        })

    # Stage 1: Onset from larger to small
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage1",
        "status": "input",
        "reason": "stage0_ok",
        "row_count": int(s0_ok.sum()),
        "rfid_count": int(ledger.loc[s0_ok, "rfid_id"].nunique()),
        "description": "Input rows admitted from Stage 0",
    })

    s1_ok = ledger["stage1_ok"].to_numpy()
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage1",
        "status": "keep",
        "reason": "observed_onset_large_to_small",
        "row_count": int(s1_ok.sum()),
        "rfid_count": int(ledger.loc[s1_ok, "rfid_id"].nunique()),
        "description": "Exact observed t-1 geometry valid and NOT small, current small (<=100m)",
    })

    if "stage1_reason" in ledger:
        s1_rejects = ledger[s0_ok & ~s1_ok]
        for reason, grp in s1_rejects.groupby("stage1_reason", sort=True):
            r_str = str(reason)
            is_defer = r_str in ("missing_previous", "invalid_previous")
            status = "defer" if is_defer else "reject"
            desc = (
                f"Stage 1 deferral (observation gap): {r_str}"
                if is_defer
                else f"Stage 1 rejection: {r_str}"
            )
            records.append({
                "category_type": "candidate_transition",
                "stage": "stage1",
                "status": status,
                "reason": r_str,
                "row_count": int(len(grp)),
                "rfid_count": int(grp["rfid_id"].nunique()),
                "description": desc,
            })

    # Stage 2: 2-hour persistence
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage2",
        "status": "input",
        "reason": "stage1_ok",
        "row_count": int(s1_ok.sum()),
        "rfid_count": int(ledger.loc[s1_ok, "rfid_id"].nunique()),
        "description": "Input rows admitted from Stage 1",
    })

    s2_ok = ledger["stage2_ok"].to_numpy()
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage2",
        "status": "keep",
        "reason": "observed_persistence_at_t_plus_1",
        "row_count": int(s2_ok.sum()),
        "rfid_count": int(ledger.loc[s2_ok, "rfid_id"].nunique()),
        "description": "Exact observed t+1 geometry valid and small (<=100m)",
    })

    if "stage2_reason" in ledger:
        s2_rejects = ledger[s1_ok & ~s2_ok]
        for reason, grp in s2_rejects.groupby("stage2_reason", sort=True):
            r_str = str(reason)
            is_defer = r_str in ("missing_next", "invalid_next")
            status = "defer" if is_defer else "reject"
            desc = (
                f"Stage 2 deferral (observation gap): {r_str}"
                if is_defer
                else f"Stage 2 rejection: {r_str}"
            )
            records.append({
                "category_type": "candidate_transition",
                "stage": "stage2",
                "status": status,
                "reason": r_str,
                "row_count": int(len(grp)),
                "rfid_count": int(grp["rfid_id"].nunique()),
                "description": desc,
            })

    # Stage 3: Peer gear transition baseline comparison
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage3",
        "status": "input",
        "reason": "stage2_ok",
        "row_count": int(s2_ok.sum()),
        "rfid_count": int(ledger.loc[s2_ok, "rfid_id"].nunique()),
        "description": "Common Stage 2 transition candidates evaluated for peer gear comparison",
    })

    s3_ok = ledger["stage3_ok"].to_numpy()
    records.append({
        "category_type": "candidate_transition",
        "stage": "stage3",
        "status": "keep",
        "reason": "gear_peer_baseline_eligible",
        "row_count": int(s3_ok.sum()),
        "rfid_count": int(ledger.loc[s3_ok, "rfid_id"].nunique()),
        "description": "Own >=24 triples/3 days, single-code gear, and >=5 eligible peers with known rates",
    })

    if "gear_missing_reason" in ledger:
        s3_defers = ledger[s2_ok & ~s3_ok]
        for reason, grp in s3_defers.groupby("gear_missing_reason", sort=True):
            records.append({
                "category_type": "candidate_transition",
                "stage": "stage3",
                "status": "defer",
                "reason": str(reason) if pd.notna(reason) else "unspecified_deferral",
                "row_count": int(len(grp)),
                "rfid_count": int(grp["rfid_id"].nunique()),
                "description": f"Stage 3 deferral (not confirmed normal): {reason}",
            })

    # 2. Strict vessel-level candidate presence
    for stg, mask in [("stage0", s0_ok), ("stage1", s1_ok), ("stage2", s2_ok), ("stage3", s3_ok)]:
        n_rfid = int(ledger.loc[mask, "rfid_id"].nunique())
        records.append({
            "category_type": "rfid_candidate_presence",
            "stage": stg,
            "status": "presence",
            "reason": f"vessels_with_ge_1_{stg}_candidate",
            "row_count": int(mask.sum()),
            "rfid_count": n_rfid,
            "description": f"Number of distinct vessels with at least one {stg} candidate",
        })

    # 3. Actual fallback method coverage (from manifest)
    for method in METHODS:
        m_rows = manifest[manifest["method"] == method]
        for (pool_stage, fb_reason), grp in m_rows.groupby(["pool_stage", "fallback_reason"], dropna=False):
            fb_str = str(fb_reason) if pd.notna(fb_reason) and fb_reason is not None else "strict_stage"
            records.append({
                "category_type": "method_actual_pool_coverage",
                "stage": str(pool_stage),
                "status": "fallback" if fb_str != "strict_stage" else "strict",
                "reason": fb_str,
                "row_count": int(grp["actual_pool_n"].sum()),
                "rfid_count": int(len(grp)),
                "description": f"Method {method} actual pool assigned: {pool_stage} (fallback: {fb_str})",
            })

    return pd.DataFrame(records)


def evaluate_rules(artifacts: dict[str, Any], positives: pd.DataFrame, output_dir: Path) -> dict[str, Any]:
    """Evaluate sequential candidate rules against devset positive events.

    Writes predictions and pool_manifest before label join, candidate_ledger.parquet,
    stage_counts.csv, stage_event_coverage.csv, event_results.csv, metrics.json,
    and diagnostics.json.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    required_artifacts = {"ledger", "predictions", "pool_manifest", "diagnostics"}
    missing_artifacts = required_artifacts - set(artifacts.keys())
    if missing_artifacts:
        raise ValueError(f"artifacts missing required keys: {sorted(missing_artifacts)}")

    ledger: pd.DataFrame = artifacts["ledger"].copy()
    predictions: pd.DataFrame = artifacts["predictions"].copy()
    pool_manifest: pd.DataFrame = artifacts["pool_manifest"].copy()
    rule_diagnostics: dict[str, Any] = artifacts["diagnostics"]
    gear_registry: pd.DataFrame | None = artifacts.get("gear_registry", None)

    # 1. Write predictions and pool_manifest strictly before label join
    predictions.to_csv(output_dir / "predictions.csv", index=False)
    pool_manifest.to_csv(output_dir / "pool_manifest.csv", index=False)
    ledger.to_parquet(output_dir / "candidate_ledger.parquet", engine="pyarrow", index=False)

    # 2. Stage transition and count ledger
    stage_counts_df = _build_stage_counts(ledger, pool_manifest)
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
    events["acc_ts"] = pd.to_numeric(events["acc_ts"], errors="raise").astype("int64")
    if "conflict" not in events.columns:
        events["conflict"] = None

    # Pre-index predictions by (rfid_id, method)
    pred_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in predictions.itertuples(index=False):
        pred_index[(str(p.rfid_id), str(p.method))].append(p._asdict())
    for k in pred_index:
        pred_index[k].sort(key=lambda x: int(x["rank"]))

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

    # Pre-group ledger by vessel
    ledger["rfid_id"] = ledger["rfid_id"].map(_norm_id)
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

        if v is not None and len(v) > 0:
            in_win = v["ts"].between(acc_ts - TOLERANCE_HOURS, acc_ts + TOLERANCE_HOURS)
            obs_win = bool(in_win.any())
            s0_win = bool((in_win & v["stage0_ok"]).any())
            s1_win = bool((in_win & v["stage1_ok"]).any())
            s2_win = bool((in_win & v["stage2_ok"]).any())
            s3_win = bool((in_win & v["stage3_ok"]).any())
            v_s0 = bool(v["stage0_ok"].any())
            v_s1 = bool(v["stage1_ok"].any())
            v_s2 = bool(v["stage2_ok"].any())
            v_s3 = bool(v["stage3_ok"].any())
        else:
            obs_win = s0_win = s1_win = s2_win = s3_win = False
            v_s0 = v_s1 = v_s2 = v_s3 = False

        b0_meta = manifest_index.get((rid, "B0"), {"pool_stage": "stage0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})
        s_meta = manifest_index.get((rid, "S"), {"pool_stage": "stage0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})
        g_meta = manifest_index.get((rid, "G"), {"pool_stage": "stage0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})

        method_hits: dict[tuple[str, int], bool] = {}
        for method in METHODS:
            meta = manifest_index.get((rid, method), {"pool_stage": "none", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})
            preds = pred_index.get((rid, method), [])
            for k in BUDGETS:
                chosen = [p for p in preds if int(p["rank"]) <= k]
                times = [int(p["ts"]) for p in chosen]
                if times:
                    err = int(min(abs(t - acc_ts) for t in times))
                    hit = bool(err <= TOLERANCE_HOURS)
                else:
                    err = None
                    hit = False
                method_hits[(method, k)] = hit
                event_result_rows.append({
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
                    "window_observable_stage0": s0_win,
                    "window_observable_stage2": s2_win,
                    "window_observable_stage3": s3_win,
                })

        coverage_rows.append({
            "acc_id": str(ev.acc_id),
            "rfid_id": rid,
            "tier": int(ev.tier),
            "conflict": getattr(ev, "conflict", None),
            "acc_ts": acc_ts,
            "primary_gear": g_name,
            "is_single_code": s_code,
            "gear_stratum": gear_stratum,
            "observed_in_window": obs_win,
            "stage0_in_window": s0_win,
            "stage1_in_window": s1_win,
            "stage2_in_window": s2_win,
            "stage3_in_window": s3_win,
            "vessel_has_stage0": v_s0,
            "vessel_has_stage1": v_s1,
            "vessel_has_stage2": v_s2,
            "vessel_has_stage3": v_s3,
            "B0_pool_stage": b0_meta["pool_stage"],
            "B0_fallback_reason": b0_meta["fallback_reason"],
            "S_pool_stage": s_meta["pool_stage"],
            "S_fallback_reason": s_meta["fallback_reason"],
            "G_pool_stage": g_meta["pool_stage"],
            "G_fallback_reason": g_meta["fallback_reason"],
            "actual_G_cap": g_meta["cap"],
            "B0_hit_top1": method_hits[("B0", 1)],
            "B0_hit_top4": method_hits[("B0", 4)],
            "S_hit_top1": method_hits[("S", 1)],
            "S_hit_top4": method_hits[("S", 4)],
            "G_hit_top1": method_hits[("G", 1)],
            "G_hit_top4": method_hits[("G", 4)],
        })

    event_results_df = pd.DataFrame(event_result_rows)
    event_results_df.to_csv(output_dir / "event_results.csv", index=False)

    stage_event_coverage_df = pd.DataFrame(coverage_rows)
    stage_event_coverage_df.to_csv(output_dir / "stage_event_coverage.csv", index=False)

    # 5. Method-specific Random Expectations (strictly over each method's ACTUAL pool and cap)
    random_expectations: dict[str, Any] = {}
    for scope_name, sub_events in [("all", events), ("tier01", events[events["tier"] <= 1])]:
        scope_pools: dict[str, Any] = {}
        for method in METHODS:
            m_records: list[dict[str, Any]] = []
            for ev in sub_events.itertuples(index=False):
                rid = str(ev.rfid_id)
                acc_ts = int(ev.acc_ts)
                meta = manifest_index.get((rid, method), {"pool_stage": "stage0", "actual_pool_n": 0, "cap": 0, "fallback_reason": "no_observations"})
                v = vessels.get(rid, None)
                pool_stg = meta["pool_stage"]
                cap = meta["cap"]

                # Obtain actual pool directly from ledger using manifest's assigned boolean stage mask
                if v is not None and f"{pool_stg}_ok" in v:
                    pool = v[v[f"{pool_stg}_ok"]]
                    n = len(pool)
                    h = int(pool["ts"].between(acc_ts - TOLERANCE_HOURS, acc_ts + TOLERANCE_HOURS).sum())
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
                    "window_observable_stage0_events": int(grp["window_observable_stage0"].sum()),
                    "window_observable_stage2_events": int(grp["window_observable_stage2"].sum()),
                    "window_observable_stage3_events": int(grp["window_observable_stage3"].sum()),
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
    t01_g_top1 = denominators_summary["tier01"]["G_top1"]["hit_rate"]
    t01_b0_top1 = denominators_summary["tier01"]["B0_top1"]["hit_rate"]
    t01_diff = float(t01_g_top1 - t01_b0_top1)

    all_g_top1 = denominators_summary["all"]["G_top1"]["hit_rate"]
    all_b0_top1 = denominators_summary["all"]["B0_top1"]["hit_rate"]
    all_diff = float(all_g_top1 - all_b0_top1)

    ci95 = bootstrap_results["tier01"]["G-vs-B0-top1"]["ci95"]
    ci95_lower = ci95[0] if ci95 and ci95[0] is not None else None

    rand_expected_g = random_expectations["tier01"]["pools"]["G"]["mean_top1_expected"]

    gate_cond1_improvement = bool(t01_diff >= 0.05)
    gate_cond2_ci_positive = bool(ci95_lower is not None and ci95_lower > 0.0)
    gate_cond3_non_worsening = bool(all_diff >= 0.0)
    gate_cond4_exceeds_random = bool(t01_g_top1 > rand_expected_g)

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
        gate_failures.append(f"tier01_top1 hit rate ({t01_g_top1:.4f}) does not exceed random expectation ({rand_expected_g:.4f})")

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
            "target": "G Tier01 top1 > actual pool random expectation",
            "observed_hit_rate": t01_g_top1,
            "expected_random_rate": rand_expected_g,
            "passed": gate_cond4_exceeds_random,
        },
        "overall_passed": overall_gate_passed,
        "gate_failures": gate_failures,
    }

    # 9. Write metrics.json
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
        "shared_numerical_helpers": {
            "source": "testB/final/round_002_20261105/data_eval.py",
            "functions": ["_random_hit_probability", "_bootstrap_diff"],
            "sha256": round2_hash,
        },
    }
    _write_json(output_dir / "metrics.json", metrics)

    # 10. Write diagnostics.json
    diagnostics = {
        "events_total": int(len(events)),
        "events_tier01": int((events["tier"] <= 1).sum()),
        "rfids_total": int(events["rfid_id"].nunique()),
        "rfids_tier01": int(events.loc[events["tier"] <= 1, "rfid_id"].nunique()),
        "ledger_rows": int(len(ledger)),
        "predictions_rows": int(len(predictions)),
        "pool_manifest_rows": int(len(pool_manifest)),
        "event_result_rows": int(len(event_result_rows)),
        "stage_event_coverage_rows": int(len(coverage_rows)),
        "unresolved_positive_rfids": sorted(set(events["rfid_id"]) - set(ledger["rfid_id"])),
        "rule_diagnostics": rule_diagnostics,
        "gate_evaluation_summary": {
            "overall_passed": overall_gate_passed,
            "failures": gate_failures,
        },
    }
    _write_json(output_dir / "diagnostics.json", diagnostics)

    return {
        "metrics": metrics,
        "diagnostics": diagnostics,
        "stage_counts": stage_counts_df,
        "stage_event_coverage": stage_event_coverage_df,
        "event_results": event_results_df,
    }
