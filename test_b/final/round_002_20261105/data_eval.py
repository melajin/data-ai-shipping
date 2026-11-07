"""Round 2 data loading, deterministic prediction, and event level evaluation.

This module deliberately emits descriptive exploratory results only. It does not
fit a model or assign accident probabilities.
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

METHODS = ("B0_full", "B0_common", "U", "C")
BOOTSTRAP_B = 4000
BOOTSTRAP_SEED = 20261105
TOLERANCE_HOURS = 6


def _json_default(value: Any):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False,
                               default=_json_default) + "\n", encoding="utf-8")


def _norm_id(value: Any) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _input_dir(root: Path) -> Path:
    matches = sorted((root / "testB").glob("*/round_008_linkage_audit_20261105"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one archived round_008 input directory, found {len(matches)}")
    return matches[0]


def load_dev(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load canonical hourly frame and positive events from archived round 008.

    Only selected Arrow columns are read, with an Arrow-side RFID membership
    filter. Input Parquets are never modified. Diagnostics are written beside
    this module as ``input_diagnostics.json``.
    """
    import pyarrow as pa
    import pyarrow.dataset as ds

    root = Path(root).resolve()
    source_dir = _input_dir(root)
    positives_path = source_dir / "devset_positives.csv"
    positives = pd.read_csv(positives_path, usecols=["acc_id", "rfid_id", "tier", "conflict", "acc_ts"],
                            encoding="utf-8-sig")
    positives["rfid_id"] = positives["rfid_id"].map(_norm_id)
    positives["acc_id"] = positives["acc_id"].astype(str)
    positives["tier"] = pd.to_numeric(positives["tier"], errors="raise").astype(int)
    positives["acc_ts"] = pd.to_numeric(positives["acc_ts"], errors="raise").astype("int64")
    ids = sorted(set(positives["rfid_id"]) - {""})
    if not ids:
        raise ValueError("Positive file contains no usable RFID identifiers")
    selected = ["rfid_id_int", "ts", "source_ordinal", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
    tables = []
    parquet_paths = [source_dir / "dev_hourly_scores.parquet", source_dir / "additional_hourly_scores.parquet"]
    for path in parquet_paths:
        dataset = ds.dataset(path, format="parquet")
        schema_names = set(dataset.schema.names)
        absent = set(selected) - schema_names
        if absent:
            raise ValueError(f"{path.name}: missing required columns {sorted(absent)}")
        # int64 source IDs are retained in Arrow's filter; no unrelated rows or columns enter memory.
        table = dataset.to_table(columns=selected, filter=ds.field("rfid_id_int").isin([int(x) for x in ids]))
        tables.append(table)
    raw = pa.concat_tables(tables, promote_options="default").to_pandas()
    raw = raw.rename(columns={"rfid_id_int": "rfid_id"})
    raw["rfid_id"] = raw["rfid_id"].map(_norm_id)
    for col in ("ts", "source_ordinal"):
        raw[col] = pd.to_numeric(raw[col], errors="raise").astype("int64")
    for col in ("len_m", "bbox_m", "cen_lon", "cen_lat", "score"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce").astype(float)

    key = ["rfid_id", "source_ordinal"]
    value_cols = ["ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "score"]
    raw_exact_unique = raw.drop_duplicates()
    conflicts = []
    for (rfid, ordinal), group in raw_exact_unique.groupby(key, sort=False, dropna=False):
        if len(group[value_cols].drop_duplicates()) > 1:
            conflicts.append({"rfid_id": rfid, "source_ordinal": int(ordinal),
                              "variants": group[value_cols].replace({np.nan: None}).to_dict("records")})
    diagnostic: dict[str, Any] = {
        "sources": [str(p) for p in parquet_paths], "positive_event_count": int(len(positives)),
        "positive_rfid_count": int(len(ids)), "filtered_rows_before_dedup": int(len(raw)),
        "exact_duplicate_rows_removed": int(len(raw) - len(raw_exact_unique)),
        "source_ordinal_conflict_count": len(conflicts), "source_ordinal_conflicts": conflicts,
        "hourly_duplicate_rows_removed": 0, "canonical_rows": 0,
    }
    if conflicts:
        _write_json(Path(__file__).resolve().parent / "input_diagnostics.json", diagnostic)
        raise ValueError(f"Conflicting rows share (rfid_id, source_ordinal); see input_diagnostics.json ({len(conflicts)} conflicts)")
    # Identical keys may still be present in both files; exact duplicate rows are already removed.
    raw_exact_unique = raw_exact_unique.sort_values(["rfid_id", "ts", "source_ordinal"], kind="mergesort")
    before_hourly = len(raw_exact_unique)
    canonical = raw_exact_unique.drop_duplicates(["rfid_id", "ts"], keep="first").copy()
    diagnostic["hourly_duplicate_rows_removed"] = int(before_hourly - len(canonical))
    canonical = canonical.sort_values(["rfid_id", "ts", "source_ordinal"], kind="mergesort").reset_index(drop=True)
    finite_geometry = np.isfinite(canonical["len_m"]) & np.isfinite(canonical["bbox_m"])
    canonical["geometry_valid"] = finite_geometry & (canonical["len_m"] >= 0) & (canonical["bbox_m"] >= 0)
    loc_finite = np.isfinite(canonical["cen_lon"]) & np.isfinite(canonical["cen_lat"])
    canonical["location_valid"] = (loc_finite & canonical["cen_lon"].between(-180, 180) &
                                   canonical["cen_lat"].between(-90, 90))
    diagnostic["canonical_rows"] = int(len(canonical))
    diagnostic["canonical_rfid_count"] = int(canonical["rfid_id"].nunique())
    diagnostic["geometry_valid_rows"] = int(canonical["geometry_valid"].sum())
    _write_json(Path(__file__).resolve().parent / "input_diagnostics.json", diagnostic)
    return canonical, positives


def _rank(pool: pd.DataFrame, method: str, fallback: bool, cap: int,
          score_col: str) -> list[dict[str, Any]]:
    if pool.empty or cap <= 0:
        return []
    if score_col not in pool:
        raise ValueError(f"Prediction score column {score_col!r} is missing for {method}")
    score_values = pd.to_numeric(pool[score_col], errors="coerce")
    ordered = pool.loc[np.isfinite(score_values)].copy()
    ordered["ranking_score"] = pd.to_numeric(ordered[score_col], errors="coerce")
    ordered = ordered.sort_values(["ranking_score", "ts", "source_ordinal"],
                                  ascending=[False, True, True], kind="mergesort")
    ordered = ordered.drop_duplicates("ts", keep="first").head(cap)
    return [{"rfid_id": str(row.rfid_id), "method": method, "rank": rank,
             "ts": int(row.ts), "score": float(row.ranking_score),
             "source_ordinal": int(row.source_ordinal),
             "fallback": bool(fallback), "candidate_count": int(len(pool))}
            for rank, row in enumerate(ordered.itertuples(index=False), 1)]


def _random_hit_probability(n: int, h: int, k: int) -> float:
    if n <= 0 or h <= 0 or k <= 0:
        return 0.0
    k = min(k, n)
    h = min(h, n)
    return 1.0 - (math.comb(n - h, k) / math.comb(n, k) if n - h >= k else 0.0)


def _random_event_record(event: Any, rfid: str, pool_name: str, source_pool: str,
                        pool: pd.DataFrame, kcap: int, fallback: bool) -> dict[str, Any]:
    n = int(len(pool))
    h = int(pool.ts.between(int(event.acc_ts) - TOLERANCE_HOURS,
                            int(event.acc_ts) + TOLERANCE_HOURS).sum())
    h = min(h, n)
    return {"acc_id": str(event.acc_id), "rfid_id": rfid, "pool": pool_name,
            "source_pool": source_pool, "fallback": bool(fallback), "n": n, "h": h,
            "kcap": int(kcap), "top1_expected": h / n if n else 0.0,
            "top4_hit_probability": _random_hit_probability(n, h, kcap)}


def _aggregate_random_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(records)
    return {"denominator_events": denominator,
            "mean_top1_expected": float(np.mean([r["top1_expected"] for r in records])) if denominator else None,
            "mean_top4_hit_probability": float(np.mean([r["top4_hit_probability"] for r in records])) if denominator else None,
            "event_probabilities": records}


def _bootstrap_diff(events: pd.DataFrame, method: str, comparator: str, k: int,
                    repetitions: int = BOOTSTRAP_B, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    if events.empty:
        return {"n_events": 0, "n_rfid": 0, "mean_difference": None, "ci95": [None, None]}
    wide = events.pivot_table(index=["acc_id", "rfid_id"], columns=["method", "k"], values="hit", aggfunc="first")
    a, b = (method, k), (comparator, k)
    if a not in wide or b not in wide:
        return {"n_events": int(len(events)), "n_rfid": int(events.rfid_id.nunique()), "mean_difference": None, "ci95": [None, None]}
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
    return {"n_events": int(len(paired)), "n_rfid": len(rfids), "mean_difference": float(paired.d.mean()),
            "ci95": [float(np.quantile(vals, .025)), float(np.quantile(vals, .975))],
            "bootstrap_repetitions": repetitions, "seed": seed}


def evaluate(frame_with_features: pd.DataFrame, positives: pd.DataFrame, output_dir: Path) -> dict[str, Any]:
    """Write per-RFID predictions, event results, and descriptive summaries."""
    output_dir = Path(output_dir).resolve()
    module_dir = Path(__file__).resolve().parent
    if output_dir != module_dir and module_dir not in output_dir.parents:
        raise ValueError("Evaluation outputs must stay inside this round folder")
    output_dir.mkdir(parents=True, exist_ok=True)
    required = {"rfid_id", "ts", "source_ordinal", "score", "geometry_valid", "history_eligible", "U", "C"}
    missing = required - set(frame_with_features.columns)
    if missing:
        raise ValueError(f"Frame missing required feature columns: {sorted(missing)}")
    frame = frame_with_features.copy()
    frame["rfid_id"] = frame["rfid_id"].map(_norm_id)
    frame["base_ok"] = np.isfinite(pd.to_numeric(frame.score, errors="coerce"))
    frame["common_ok"] = (frame.geometry_valid.astype(bool) & frame.history_eligible.astype(bool) &
                          np.isfinite(pd.to_numeric(frame.U, errors="coerce")) &
                          np.isfinite(pd.to_numeric(frame.C, errors="coerce")) & frame.base_ok)
    predictions: list[dict[str, Any]] = []
    pred_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    pool_info = {}
    for rfid, vessel in frame.groupby("rfid_id", sort=True):
        base, common = vessel[vessel.base_ok], vessel[vessel.common_ok]
        fallback = common.empty
        cap = min(4, len(common) if len(common) else len(base))
        full_pool = base
        common_pool = common
        # Full comparison and common methods share Kcap; common-only has no fallback.
        ranked = {
            "B0_full": _rank(full_pool, "B0_full", False, cap, "score"),
            "B0_common": _rank(common_pool, "B0_common", False, min(4, len(common)), "score"),
            "U": _rank(common if not fallback else base, "U", fallback, cap,
                       "score" if fallback else "U"),
            "C": _rank(common if not fallback else base, "C", fallback, cap,
                       "score" if fallback else "C"),
        }
        for method, rows in ranked.items():
            predictions.extend(rows)
            pred_index[(rfid, method)] = rows
        pool_info[rfid] = {"base_count": int(len(base)), "common_count": int(len(common)),
                           "fallback": bool(fallback), "full_kcap": int(cap),
                           "common_exists": bool(len(common))}
    pred_fields = ["rfid_id", "method", "rank", "ts", "score", "source_ordinal", "fallback", "candidate_count"]
    pd.DataFrame(predictions, columns=pred_fields).to_csv(output_dir / "predictions.csv", index=False)

    events = positives.copy()
    events["rfid_id"] = events["rfid_id"].map(_norm_id)
    rows: list[dict[str, Any]] = []
    for event in events.itertuples(index=False):
        pinfo = pool_info.get(str(event.rfid_id), {"base_count": 0, "common_count": 0, "fallback": True,
                                                    "full_kcap": 0, "common_exists": False})
        base_n, common_n = pinfo["base_count"], pinfo["common_count"]
        vessel = frame[frame.rfid_id == str(event.rfid_id)]
        in_window = vessel.ts.between(int(event.acc_ts)-6, int(event.acc_ts)+6)
        observed_base = bool((in_window & vessel.base_ok).any())
        observed_common = bool((in_window & vessel.common_ok).any())
        for method in METHODS:
            preds = pred_index.get((str(event.rfid_id), method), [])
            for k in (1, 4):
                chosen = [p for p in preds if p["rank"] <= k]
                times = [p["ts"] for p in chosen]
                error = min((abs(t-int(event.acc_ts)) for t in times), default=None)
                hit = bool(error is not None and error <= TOLERANCE_HOURS)
                if method == "B0_common":
                    candidate_count = common_n
                elif method == "B0_full" or pinfo["fallback"]:
                    candidate_count = base_n
                else:
                    candidate_count = common_n
                rows.append({"acc_id": str(event.acc_id), "rfid_id": str(event.rfid_id), "tier": int(event.tier),
                             "conflict": getattr(event, "conflict", None), "acc_ts": int(event.acc_ts),
                             "method": method, "k": k, "predicted_times": json.dumps(times),
                             "abs_error": error, "hit": hit, "coverage_base": base_n > 0,
                             "coverage_common": common_n > 0, "coverage_observable": observed_base,
                             "coverage_common_observable": observed_common,
                             "fallback": bool(pinfo["fallback"]), "candidate_count": int(candidate_count)})
    result = pd.DataFrame(rows)
    event_fields = ["acc_id", "rfid_id", "tier", "conflict", "acc_ts", "method", "k", "predicted_times",
                    "abs_error", "hit", "coverage_base", "coverage_common", "coverage_observable",
                    "coverage_common_observable", "fallback", "candidate_count"]
    result.to_csv(output_dir / "event_results.csv", index=False, columns=event_fields)

    metric_summary = {}
    for scope, subset in [("all", result), ("tier01", result[result.tier <= 1]),
                          ("common_exists", result[result.coverage_common]),
                          ("tier01_common_exists", result[(result.tier <= 1) & result.coverage_common]),
                          ("observable", result[result.coverage_observable]),
                          ("tier01_observable", result[(result.tier <= 1) & result.coverage_observable])]:
        key_metrics = {}
        for method in METHODS:
            for k in (1, 4):
                group = subset[(subset.method == method) & (subset.k == k)]
                denom = len(group)
                key_metrics[f"{method}_top{k}"] = {"events": denom, "hits": int(group.hit.sum()),
                                                    "hit_rate": float(group.hit.mean()) if denom else None,
                                                    "coverage_base_events": int(group.coverage_base.sum()),
                                                    "coverage_common_events": int(group.coverage_common.sum()),
                                                    "observable_events": int(group.coverage_observable.sum())}
        metric_summary[scope] = key_metrics

    random_expectation = {}
    for scope, subset in [("all", events), ("tier01", events[events.tier <= 1])]:
        random_by_pool = {name: [] for name in ("base", "common", "C_matched")}
        for ev in subset.itertuples(index=False):
            rfid = str(ev.rfid_id)
            info = pool_info.get(rfid, {"base_count": 0, "common_count": 0, "full_kcap": 0})
            vessel = frame[frame.rfid_id == rfid]
            base = vessel[vessel.base_ok]
            common = vessel[vessel.common_ok]
            common_exists = not common.empty
            base_cap = int(info["full_kcap"])
            common_cap = min(4, len(common))
            random_by_pool["base"].append(
                _random_event_record(ev, rfid, "base", "base", base, base_cap, False))
            random_by_pool["common"].append(
                _random_event_record(ev, rfid, "common", "common", common, common_cap, False))
            matched_pool = common if common_exists else base
            matched_source = "common" if common_exists else "base"
            matched_cap = common_cap if common_exists else base_cap
            random_by_pool["C_matched"].append(
                _random_event_record(ev, rfid, "C_matched", matched_source, matched_pool,
                                     matched_cap, not common_exists))
        pool_summaries = {name: _aggregate_random_records(records)
                          for name, records in random_by_pool.items()}
        common_conditional_records = [record for record in random_by_pool["common"]
                                      if record["n"] > 0]
        random_expectation[scope] = {
            "event_denominator_events": int(len(subset)),
            "pools": pool_summaries,
            "common_exists_conditional": _aggregate_random_records(common_conditional_records),
        }
    random_expectation["tier01"]["primary_random_gate"] = {
        "target": "Tier01 C_matched top1 expected hit rate",
        "denominator_events": random_expectation["tier01"]["pools"]["C_matched"]["denominator_events"],
        "expected_hit_rate": random_expectation["tier01"]["pools"]["C_matched"]["mean_top1_expected"],
    }

    bootstrap = {}
    for scope, subset in [("all", result), ("tier01", result[result.tier <= 1]),
                          ("common_exists", result[result.coverage_common]),
                          ("tier01_common_exists", result[(result.tier <= 1) & result.coverage_common])]:
        bootstrap[scope] = {}
        for method, comparator in (("C", "B0_full"), ("C", "U"), ("C", "B0_common")):
            if comparator == "B0_common":
                comp_subset = subset[subset.coverage_common]
            else:
                comp_subset = subset
            for k in (1, 4):
                bootstrap[scope][f"{method}-vs-{comparator}-top{k}"] = _bootstrap_diff(comp_subset, method, comparator, k)
    metrics = {"status": "provisional_descriptive_evaluation", "label_status": "provisional; not ground-truth validated",
               "probability_outputs": False, "prediction_methods": list(METHODS), "budgets": [1, 4],
               "top1_definition": "rank 1 of the same ranked top4 list", "tolerance_hours_inclusive": TOLERANCE_HOURS,
               "denominators": metric_summary, "same_budget_random_expectation": random_expectation,
               "rfid_cluster_bootstrap": bootstrap, "bootstrap_repetitions": BOOTSTRAP_B,
               "bootstrap_seed": BOOTSTRAP_SEED}
    _write_json(output_dir / "metrics.json", metrics)
    diagnostics = {"events": int(len(events)), "rfid_count": int(events.rfid_id.nunique()),
                   "tier01_events": int((events.tier <= 1).sum()), "canonical_frame_rows": int(len(frame)),
                   "rfid_pools": pool_info, "prediction_rows": len(predictions), "event_result_rows": len(rows),
                   "unresolved_positive_rfid": sorted(set(events.rfid_id) - set(frame.rfid_id))}
    _write_json(output_dir / "diagnostics.json", diagnostics)
    return {"metrics": metrics, "diagnostics": diagnostics}
