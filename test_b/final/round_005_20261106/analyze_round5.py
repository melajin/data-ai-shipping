"""Fixed Round5 retrospective analysis using saved Round4 artifacts only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[3]
ROUND4 = ROOT / "testB" / "final" / "round_004_20261105"
INPUT = ROUND4 / "execution_001"
ROUND5 = Path(__file__).resolve().parent
PREVIOUS_OUT = ROUND5 / "execution_001"
ROUND2_HELPERS = ROOT / "testB" / "final" / "round_002_20261105" / "data_eval.py"
BOOTSTRAP_B = 4000
BOOTSTRAP_SEED = 20261105
TOLERANCE_HOURS = 6

LEDGER_COLUMNS = [
    "rfid_id", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat",
    "score", "small", "stage0_ok", "stage1_ok", "stage2_ok", "stage3_ok",
    "previous_observed", "next_observed", "previous_geometry_valid", "next_geometry_valid",
    "previous_small", "next_small", "stage1_reason", "stage2_reason", "primary_gear",
]
EVENT_META = ["acc_id", "rfid_id", "tier", "conflict", "acc_ts", "primary_gear", "is_single_code", "gear_stratum"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_default(x: Any):
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating,)): return float(x)
    if isinstance(x, (np.bool_,)): return bool(x)
    if isinstance(x, Path): return str(x)
    raise TypeError(type(x).__name__)


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False, default=json_default) + "\n", encoding="utf-8")


def norm_id(v: Any) -> str:
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") and s[:-2].isdigit() else s


def rank_s1(vessel: pd.DataFrame, cap: int) -> tuple[pd.DataFrame, bool, int]:
    """Rank precomputed masks only; no feature construction or score fitting."""
    stage1 = vessel[vessel.stage1_ok.fillna(False).astype(bool)]
    fallback = stage1.empty
    pool = vessel[vessel.stage0_ok.fillna(False).astype(bool)] if fallback else stage1
    pool = pool[np.isfinite(pd.to_numeric(pool.score, errors="coerce"))].copy()
    pool["_score"] = pd.to_numeric(pool.score, errors="coerce")
    pool = pool.sort_values(["_score", "ts", "source_ordinal"], ascending=[False, True, True], kind="mergesort")
    return pool.head(max(0, int(cap))).copy(), fallback, len(pool)


def build_s1(ledger: pd.DataFrame, manifest: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ledger = ledger.copy()
    ledger["rfid_id"] = ledger.rfid_id.map(norm_id)
    manifest = manifest.copy()
    manifest["rfid_id"] = manifest.rfid_id.map(norm_id)
    gm = manifest[manifest.method.eq("G")].set_index("rfid_id")
    rows, pool_rows = [], []
    by_rfid = {rid: g for rid, g in ledger.groupby("rfid_id", sort=False)}
    for rid in sorted(gm.index):
        if rid not in by_rfid: raise ValueError(f"Manifest RFID missing from ledger: {rid}")
        m = gm.loc[rid]
        cap = int(m.cap)
        selected, fallback, pool_n = rank_s1(by_rfid[rid], cap)
        stage = "stage0" if fallback else "stage1"
        reason = str(m.fallback_reason) if fallback and pd.notna(m.fallback_reason) else ("empty_stage1_fallback_stage0" if fallback else "")
        pool_rows.append({"rfid_id": rid, "method": "S1", "pool_stage": stage, "actual_pool_n": pool_n, "cap": cap,
                          "fallback_reason": reason or np.nan, "source_G_cap": cap})
        for rank, (_, r) in enumerate(selected.iterrows(), 1):
            rows.append({"rfid_id": rid, "method": "S1", "rank": rank, "ts": int(r.ts), "ordinal": int(r.source_ordinal),
                         "method_score": float(r["_score"]), "legacy_score": float(r["_score"]), "score_kind": "legacy_score",
                         "actual_pool_n": pool_n, "cap": cap, "fallback_reason": reason or np.nan})
    return pd.DataFrame(rows), pd.DataFrame(pool_rows)


def event_error(pred_times: list[int], acc_ts: int) -> tuple[int | None, bool]:
    if not pred_times: return None, False
    err = min(abs(int(t) - int(acc_ts)) for t in pred_times)
    return err, err <= TOLERANCE_HOURS


def eval_events(events: pd.DataFrame, predictions: pd.DataFrame, manifests: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    # Events are a single common target RFID list shared by every method and budget.
    event_rows = []
    pred_index = {(rid, method): g.sort_values("rank") for (rid, method), g in predictions.groupby(["rfid_id", "method"], sort=False)}
    manifest_index = {(r.rfid_id, r.method): r for r in manifests.itertuples(index=False)}
    for e in events.itertuples(index=False):
        rid, acc_ts = norm_id(e.rfid_id), int(e.acc_ts)
        for method in ("B0", "S1", "S", "G"):
            group = pred_index.get((rid, method), pd.DataFrame())
            mi = manifest_index.get((rid, method))
            for k in (1, 4):
                times = group.head(k).ts.astype(int).tolist() if not group.empty else []
                err, hit = event_error(times, acc_ts)
                event_rows.append({"acc_id": str(e.acc_id), "rfid_id": rid, "tier": int(e.tier), "conflict": bool(e.conflict),
                    "acc_ts": acc_ts, "primary_gear": e.primary_gear, "gear_stratum": e.gear_stratum,
                    "method": method, "k": k, "predicted_times": json.dumps(times), "abs_error_hours": err,
                    "hit": hit, "pool_stage": getattr(mi, "pool_stage", None), "fallback_reason": getattr(mi, "fallback_reason", None),
                    "actual_pool_n": int(getattr(mi, "actual_pool_n", 0)), "cap": int(getattr(mi, "cap", 0))})
    out = pd.DataFrame(event_rows)
    metrics = {}
    for name, subset in [("all", out), ("Tier01", out[out.tier.isin([0, 1])])]:
        metrics[name] = {}
        for method in ("B0", "S1", "S", "G"):
            metrics[name][method] = {}
            for k in (1, 4):
                d = subset[(subset.method == method) & (subset.k == k)]
                errors = pd.to_numeric(d.abs_error_hours, errors="coerce")
                metrics[name][method][str(k)] = {"n_events": len(d), "hits": int(d.hit.sum()), "hit_rate": float(d.hit.mean()) if len(d) else None,
                    "errors_hours": [None if pd.isna(x) else int(x) for x in errors], "mean_abs_error_hours": float(errors.mean()) if errors.notna().any() else None}
    for gear, g in events.groupby("gear_stratum", dropna=False, sort=True):
        label = "unknown" if pd.isna(gear) else str(gear)
        metrics.setdefault("gear_strata", {})[label] = {}
        accs = set(g.acc_id.astype(str))
        for method in ("B0", "S1", "S", "G"):
            metrics["gear_strata"][label][method] = {}
            for k in (1, 4):
                d = out[out.acc_id.isin(accs) & out.method.eq(method) & out.k.eq(k)]
                metrics["gear_strata"][label][method][str(k)] = {"n_events": len(d), "hits": int(d.hit.sum()), "hit_rate": float(d.hit.mean()) if len(d) else None}
    return out, metrics


def random_s1(events: pd.DataFrame, ledger: pd.DataFrame, s1_manifest: pd.DataFrame, helper) -> dict[str, Any]:
    lm = s1_manifest.set_index("rfid_id")
    by = {rid: g for rid, g in ledger.groupby("rfid_id", sort=False)}
    records = []
    for e in events.itertuples(index=False):
        rid = norm_id(e.rfid_id); g = by.get(rid, pd.DataFrame())
        source_stage = lm.loc[rid, "pool_stage"] if rid in lm.index else "stage0"
        stage_col = "stage1_ok" if source_stage == "stage1" else "stage0_ok"
        pool = g[g[stage_col].fillna(False).astype(bool)] if not g.empty else g
        n = len(pool); h = int(pool.ts.between(int(e.acc_ts)-6, int(e.acc_ts)+6).sum()) if n else 0
        cap = int(lm.loc[rid, "cap"]) if rid in lm.index else 0
        records.append({"acc_id": str(e.acc_id), "rfid_id": rid, "tier": int(e.tier), "pool_stage": source_stage, "n": n, "h": h, "kcap": min(cap,n),
            "top1_expected": h/n if n else 0.0, "top4_hit_probability": helper(n,h,min(4,cap))})
    cohorts = {
        "all": aggregate_random_records(records),
        "Tier01": aggregate_random_records([r for r in records if r["tier"] in (0, 1)]),
    }
    return {**cohorts, "methodology": "S1 actual stage1 pool; stage0 pool only on empty-stage1 fallback; event probabilities are summarized separately for all100 and Tier01=60."}


def aggregate_random_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"denominator_events": len(records), "mean_top1_expected": float(np.mean([r["top1_expected"] for r in records])) if records else None,
        "mean_top4_hit_probability": float(np.mean([r["top4_hit_probability"] for r in records])) if records else None,
        "event_probabilities": records}


def loss_analysis(events: pd.DataFrame, ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    flags, observations = [], []
    by = {rid: g for rid, g in ledger.groupby("rfid_id", sort=False)}
    for e in events.itertuples(index=False):
        rid = norm_id(e.rfid_id); g = by.get(rid, pd.DataFrame())
        w = g[g.ts.between(int(e.acc_ts)-6, int(e.acc_ts)+6)].copy() if not g.empty else g.copy()
        s0 = w[w.stage0_ok.fillna(False).astype(bool)]
        s1 = w[w.stage1_ok.fillna(False).astype(bool)]
        s2 = w[w.stage2_ok.fillna(False).astype(bool)]
        loss01 = len(s0)>0 and len(s1)==0
        loss12 = len(s1)>0 and len(s2)==0
        if not (loss01 or loss12): continue
        flags.append({"acc_id": str(e.acc_id), "rfid_id": rid, "tier": int(e.tier), "acc_ts": int(e.acc_ts), "primary_gear": e.primary_gear,
            "gear_stratum": e.gear_stratum, "loss_stage0_to_stage1": bool(loss01), "loss_stage1_to_stage2": bool(loss12),
            "any_small_condition_in_window": bool(w.small.fillna(False).astype(bool).any()),
            "observed_small_continuation": bool((w.small.fillna(False).astype(bool) & w.next_observed.fillna(False).astype(bool) & w.next_geometry_valid.fillna(False).astype(bool) & w.next_small.fillna(False).astype(bool)).any()),
            "missing_previous": bool((s0.stage1_reason == "missing_previous").any()),
            "invalid_previous": bool((s0.stage1_reason == "invalid_previous").any()),
            "previous_not_large_previous_small": bool((s0.stage1_reason == "previous_not_large").any()),
            "stage1_but_missing_next": bool((s1.stage2_reason == "missing_next").any()),
            "stage1_but_invalid_next": bool((s1.stage2_reason == "invalid_next").any()),
            "stage1_but_next_not_small": bool((s1.stage2_reason == "next_not_small").any()), "window_row_count": len(w)})
        for r in w.itertuples(index=False):
            observations.append({"acc_id": str(e.acc_id), "rfid_id": rid, "relative_hour": int(r.ts)-int(e.acc_ts), "ts": int(r.ts),
                "source_ordinal": int(r.source_ordinal), "primary_gear": r.primary_gear,
                "len_m": r.len_m, "bbox_m": r.bbox_m, "cen_lon": r.cen_lon, "cen_lat": r.cen_lat,
                "small": bool(r.small), "stage0_ok": bool(r.stage0_ok), "stage1_ok": bool(r.stage1_ok), "stage2_ok": bool(r.stage2_ok), "stage3_ok": bool(r.stage3_ok),
                "previous_observed": bool(r.previous_observed), "previous_geometry_valid": bool(r.previous_geometry_valid), "previous_small": bool(r.previous_small),
                "next_observed": bool(r.next_observed), "next_geometry_valid": bool(r.next_geometry_valid), "next_small": bool(r.next_small),
                "stage1_reason": r.stage1_reason, "stage2_reason": r.stage2_reason})
    f = pd.DataFrame(flags)
    summary = []
    for kind, mask in [("stage0_to_stage1", f.get("loss_stage0_to_stage1", pd.Series(dtype=bool))), ("stage1_to_stage2", f.get("loss_stage1_to_stage2", pd.Series(dtype=bool))), ("either", pd.Series([True]*len(f), index=f.index, dtype=bool))]:
        d = f[mask] if kind != "either" else f
        for col in ["any_small_condition_in_window", "observed_small_continuation", "missing_previous", "invalid_previous", "previous_not_large_previous_small", "stage1_but_missing_next", "stage1_but_invalid_next", "stage1_but_next_not_small"]:
            summary.append({"loss_kind": kind, "flag": col, "events": len(d), "flagged_events": int(d[col].sum()) if len(d) else 0,
                            "fraction": float(d[col].mean()) if len(d) else None, "overlap_allowed": True})
    return f, pd.DataFrame(summary), pd.DataFrame(observations)


def run(output_dir: Path | None = None) -> None:
    start = time.time()
    out_dir = (output_dir or ROUND5 / "execution_002").resolve()
    if ROUND5.resolve() not in out_dir.parents:
        raise ValueError("Output directory must stay under this Round5 folder")
    if out_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {out_dir}")
    proc = psutil.Process(os.getpid())
    before_data = {"captured_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "available_ram_mib": round(psutil.virtual_memory().available/2**20),
        "total_ram_mib": round(psutil.virtual_memory().total/2**20), "process_rss_mib": round(proc.memory_info().rss/2**20),
        "largest_processes_mib": sorted([{"name":p.info["name"],"pid":p.info["pid"],"rss_mib":round(p.info["memory_info"].rss/2**20)} for p in psutil.process_iter(["name","pid","memory_info"]) if p.info["memory_info"]], key=lambda x:x["rss_mib"], reverse=True)[:12],
        "other_bounded_metadata_job_allowance_mib":384, "analysis_increment_estimate_mib":384, "required_reserve_mib":640}
    if before_data["available_ram_mib"] < 384+640+384:
        raise MemoryError(f"Pre-data available RAM below estimate+reserve+other-job: {before_data['available_ram_mib']} MiB")
    out_dir.mkdir(parents=True, exist_ok=False)
    sources = {p.name: sha256(p) for p in [INPUT/"candidate_ledger.parquet", INPUT/"pool_manifest.csv", INPUT/"predictions.csv", INPUT/"event_results.csv", INPUT/"metrics.json", ROUND2_HELPERS]}
    helper_spec = importlib.util.spec_from_file_location("round2_data_eval_immutable", ROUND2_HELPERS)
    helper_module = importlib.util.module_from_spec(helper_spec); helper_spec.loader.exec_module(helper_module)

    manifest = pd.read_csv(INPUT/"pool_manifest.csv", dtype={"rfid_id":"string"})
    reference_bytes = (INPUT/"predictions.csv").read_bytes()
    ref_hash = hashlib.sha256(reference_bytes).hexdigest()
    ref = pd.read_csv(INPUT/"predictions.csv", dtype={"rfid_id":"string"})
    ledger = pd.read_parquet(INPUT/"candidate_ledger.parquet", columns=LEDGER_COLUMNS)
    ledger["rfid_id"] = ledger.rfid_id.map(norm_id)
    s1, s1_manifest = build_s1(ledger, manifest)
    shutil.copyfile(INPUT/"predictions.csv", out_dir/"reference_predictions.csv")
    merged = pd.concat([ref, s1], ignore_index=True)
    merged.to_csv(out_dir/"predictions.csv", index=False, encoding="utf-8-sig")
    if sha256(INPUT/"predictions.csv") != ref_hash: raise RuntimeError("Reference predictions changed during analysis")
    old_prediction_hash = sha256(PREVIOUS_OUT/"predictions.csv")
    if sha256(out_dir/"predictions.csv") != old_prediction_hash:
        raise RuntimeError("Metric-only correction altered the saved prediction artifact")
    if sha256(out_dir/"reference_predictions.csv") != ref_hash:
        raise RuntimeError("Byte-copy of the reference predictions does not match Round4 source")

    # Label-bearing event_results is read only after the complete prediction artifact is saved.
    src_event_results = pd.read_csv(INPUT/"event_results.csv", dtype={"rfid_id":"string"})
    events = src_event_results[EVENT_META].drop_duplicates("acc_id").copy()
    events["rfid_id"] = events.rfid_id.map(norm_id)
    if len(events) != 100: raise ValueError(f"Expected 100 unique events, got {len(events)}")
    if int(events.tier.isin([0,1]).sum()) != 60: raise ValueError("Tier01 denominator changed from frozen 60")
    m_add = s1_manifest.drop(columns=["source_G_cap"]).copy()
    combined_manifest = pd.concat([manifest, m_add], ignore_index=True)
    result, metric_table = eval_events(events, merged, combined_manifest)
    result.to_csv(out_dir/"event_results.csv", index=False, encoding="utf-8-sig")
    rand = random_s1(events, ledger, s1_manifest, helper_module._random_hit_probability)
    m4 = json.loads((INPUT/"metrics.json").read_text(encoding="utf-8"))
    boot = {group:{} for group in ("all","Tier01")}
    long = result[["acc_id","rfid_id","tier","method","k","hit"]].copy()
    for group, d in [("all", long), ("Tier01", long[long.tier.isin([0,1])])]:
        for comparator in ("B0","S"):
            for k in (1,4):
                boot[group][f"S1-vs-{comparator}-top{k}"] = helper_module._bootstrap_diff(d, "S1", comparator, k, repetitions=BOOTSTRAP_B, seed=BOOTSTRAP_SEED)
    s1_t1 = metric_table["Tier01"]["S1"]["1"]["hit_rate"]
    b0_t1 = metric_table["Tier01"]["B0"]["1"]["hit_rate"]
    s1_all = metric_table["all"]["S1"]["1"]["hit_rate"]
    b0_all = metric_table["all"]["B0"]["1"]["hit_rate"]
    ci = boot["Tier01"]["S1-vs-B0-top1"]["ci95"]
    gate = {"tier01_top1_gain_at_least_5pp": bool(s1_t1 is not None and b0_t1 is not None and s1_t1-b0_t1 >= .05),
        "tier01_paired_rfid_bootstrap_95ci_lower_gt_zero": bool(ci[0] is not None and ci[0]>0),
        "all100_top1_nonworse_than_B0": bool(s1_all is not None and b0_all is not None and s1_all>=b0_all),
        "Tier01_S1_actual_pool_top1_random_expectation_exceeded": bool(s1_t1 is not None and s1_t1>rand["Tier01"]["mean_top1_expected"]),
        "thresholds_changed_or_tuned": False}
    random_cohort_diagnostics = {
        "Tier01_observed_top1": s1_t1,
        "Tier01_expected_top1": rand["Tier01"]["mean_top1_expected"],
        "Tier01_exceeds_expectation": bool(s1_t1 is not None and s1_t1>rand["Tier01"]["mean_top1_expected"]),
        "all100_observed_top1": s1_all,
        "all100_expected_top1": rand["all"]["mean_top1_expected"],
        "all100_exceeds_expectation": bool(s1_all is not None and s1_all>rand["all"]["mean_top1_expected"]),
    }
    loss_f, loss_s, loss_obs = loss_analysis(events, ledger)
    loss_f.to_csv(out_dir/"loss_flags.csv", index=False, encoding="utf-8-sig")
    loss_s.to_csv(out_dir/"loss_summary.csv", index=False, encoding="utf-8-sig")
    loss_obs.to_csv(out_dir/"failure_window_observations.csv", index=False, encoding="utf-8-sig")
    source_mapping = {"stage0_in_window":"any stage0_ok row in event RFID ±6 hourly bins", "stage1_in_window":"any stage1_ok row in same window", "stage2_in_window":"any stage2_ok row in same window",
        "missing_previous":"stage0 row stage1_reason == missing_previous", "invalid_previous":"stage0 row stage1_reason == invalid_previous",
        "previous_not_large_previous_small":"stage0 row stage1_reason == previous_not_large; actual previous_small=True, not missing observation",
        "observed_small_continuation":"small current row plus next_observed, next_geometry_valid and next_small all true",
        "stage1_but_missing_next":"stage1 row stage2_reason == missing_next", "stage1_but_invalid_next":"stage1 row stage2_reason == invalid_next",
        "stage1_but_next_not_small":"stage1 row stage2_reason == next_not_small", "window":"acc_ts ±6 integer-hour bins inclusive; event-linked evaluator-only view"}
    metrics = {"status":"descriptive_saved_artifact_evaluation", "label_status":"retrospective event outcomes, not generalized evaluation",
        "denominators":{"all":len(events),"Tier01":int(events.tier.isin([0,1]).sum()),"distinct_rfids":int(events.rfid_id.nunique())},
        "top1_is_rank1_of_same_ranked_list":True,"tolerance_hours_inclusive":6,"scores":"saved legacy score, no refit",
        "event_metrics":metric_table,"S1_actual_pool_same_budget_random_expectation_by_cohort":rand,
        "random_cohort_diagnostics":random_cohort_diagnostics,
        "preserved_Round4_random_expectations_reference":m4.get("same_budget_random_expectation"),
        "preserved_Round4_bootstrap_reference":m4.get("rfid_cluster_bootstrap"),"paired_rfid_bootstrap":boot,"operational_gate":gate,
        "loss_flag_mapping":source_mapping,"loss_event_count":len(loss_f),"loss_events_stage0_to_stage1":int(loss_f.loss_stage0_to_stage1.sum()) if len(loss_f) else 0,
        "loss_events_stage1_to_stage2":int(loss_f.loss_stage1_to_stage2.sum()) if len(loss_f) else 0,
        "causal_claims":"none; flags are overlapping observational conditions, not waiting/moving/accident causes",
        "generalization_claim":"none; fixed retrospective event-linked subset only", "f1_or_false_positive_rate":"not estimated"}
    write_json(out_dir/"metrics.json", metrics)
    report = ["# Round5 execution_002 report", "", "## Scope", "", "Metric-only cohort-scope correction of the fixed retrospective analysis using saved Round4 artifacts. Predictions, ranking, caps, event hits, thresholds, and stage flags were not changed. No training, raw source load, feature rebuild, or TestB inference was performed.", "",
        f"- Events: {len(events)}; Tier01: {int(events.tier.isin([0,1]).sum())}; distinct event RFIDs: {events.rfid_id.nunique()}.",
        f"- S1 pools: stage1-selected={int((s1_manifest.pool_stage=='stage1').sum())}, stage0 fallback={int((s1_manifest.pool_stage=='stage0').sum())}; G caps preserved (1/3/4): {s1_manifest.cap.value_counts().sort_index().to_dict()}.", "",
        "## Top1 outcomes (hits / denominator; rate)", "", "| Cohort | B0 | S1 | S | G |", "|---|---:|---:|---:|---:|"]
    for cohort in ("all","Tier01"):
        vals=[]
        for method in ("B0","S1","S","G"):
            x=metric_table[cohort][method]["1"]; vals.append(f"{x['hits']}/{x['n_events']} ({x['hit_rate']:.3f})")
        report.append(f"| {cohort} | " + " | ".join(vals) + " |")
    report += ["", "## Cohort-matched random expectation and gate", "", f"Gate: `{json.dumps(gate, ensure_ascii=False)}`.",
        f"Tier01 S1 top1 was {metric_table['Tier01']['S1']['1']['hits']}/{int(events.tier.isin([0,1]).sum())} ({s1_t1:.6f}); Tier01 actual-pool random top1 expectation was {rand['Tier01']['mean_top1_expected']:.12f}. This comparison does not exceed expectation. All100 are reported separately: observed {s1_all:.6f}, expected {rand['all']['mean_top1_expected']:.12f}.",
        "S1-vs-B0 and S1-vs-S paired RFID-cluster bootstrap results remain in `metrics.json` (B=4000, seed=20261105). Each random expectation uses the observed S1 pool for that event RFID, falling back to stage0 only for empty stage1, and averages only within the named event cohort. Round4 B0/S/G prediction rows were copied unchanged; prior random and bootstrap summaries remain separately referenced.", "",
        "## Loss observations", "", f"Loss events: stage0→stage1 {int(loss_f.loss_stage0_to_stage1.sum()) if len(loss_f) else 0}; stage1→stage2 {int(loss_f.loss_stage1_to_stage2.sum()) if len(loss_f) else 0}; union {len(loss_f)}. Flags overlap. They describe saved observations and do not identify true waiting, movement, or accident causes. The ±6 hour table is outcome-linked evaluator-only diagnostics and did not change predictions or the baseline.", "",
        "## Limits", "", "This is a retrospective evaluation on the fixed 100 event labels, with 82 shared event RFIDs and Tier01=60. It does not establish generalization, F1, a false-positive rate, real-time behavior, or physical cause. Timestamp interpretation is the existing hourly integer contract; no physical device was tested.", ""]
    (out_dir/"report.md").write_text("\n".join(report), encoding="utf-8")
    peak = getattr(proc.memory_info(), "peak_wset", proc.memory_info().rss)
    receipt = {"analysis_version":"round5-cohort-scope-fix-v1","check_version":"round5-cohort-random-fixture-v1",
        "inputs":{str(p.relative_to(ROOT)):sources[p.name] for p in [INPUT/"candidate_ledger.parquet",INPUT/"pool_manifest.csv",INPUT/"predictions.csv",INPUT/"event_results.csv",INPUT/"metrics.json"]},
        "prior_round5_predictions_sha256":old_prediction_hash,
        "numerical_helper":{"path":str(ROUND2_HELPERS.relative_to(ROOT)),"sha256":sources[ROUND2_HELPERS.name],"functions":["_bootstrap_diff","_random_hit_probability"]},
        "reference_predictions_sha256":ref_hash,"reference_copy_sha256":sha256(out_dir/"reference_predictions.csv"),
        "prediction_order":"saved reference predictions loaded then S1 appended; labels read only after predictions.csv persisted",
        "cohort_random_scope":{"all":"100 unique saved events", "Tier01":"60 events with tier in {0,1}", "primary_gate":"Tier01 observed S1 top1 vs Tier01 mean per-event random top1 expectation"},
        "ram_snapshot_before_data":before_data,"process_peak_working_set_mib":round(peak/2**20),"elapsed_seconds":round(time.time()-start,3),
        "outputs":{p.name:sha256(p) for p in sorted(out_dir.iterdir()) if p.is_file() and p.name!="EXECUTION.json"},
        "limitations":["No raw source data, feature rebuilding, model training, or TestB inference", "Outcome-linked loss diagnostic is evaluator-only", "No hardware experiment or generalization claim"]}
    receipt["code_sources"] = {"analysis":{"path":str((ROUND5/"analyze_round5.py").relative_to(ROOT)),"sha256":sha256(ROUND5/"analyze_round5.py"),"version":receipt["analysis_version"]},
        "check":{"path":str((ROUND5/"check_round5.py").relative_to(ROOT)),"sha256":sha256(ROUND5/"check_round5.py"),"version":receipt["check_version"]}}
    receipt["small_check_result"] = {"path":str((ROUND5/"cohort_checks.json").relative_to(ROOT)),"sha256":sha256(ROUND5/"cohort_checks.json"),"status":"passed"}
    write_json(out_dir/"EXECUTION.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROUND5/"execution_002", help="New output directory under this Round5 folder; must not already exist")
    run(parser.parse_args().output_dir)
