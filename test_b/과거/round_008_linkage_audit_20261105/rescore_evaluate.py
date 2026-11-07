"""Fill only missing scores with unchanged Round 007 scorer, then reevaluate."""
from __future__ import annotations

import gc
import importlib.util
import json
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "round_007_20261105"
FIRST = HERE.parent / "first_results"
sys.dont_write_bytecode = True


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                      allow_nan=False), encoding="utf-8")


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, OLD / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def memory_gate(stage):
    available = psutil.virtual_memory().available / 2**20
    active = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        if "python" in (p.info["name"] or "").lower():
            active.append({"pid": p.pid, "rss_mib": round(p.info["memory_info"].rss / 2**20, 1)})
    rec = {"stage": stage, "checked_at": datetime.now().astimezone().isoformat(),
           "available_mib": round(available, 1), "estimated_additional_peak_mib": 1024,
           "reserve_mib": 1024, "active_python_processes": active,
           "estimate_basis": "sequential 65,536-row source batches; 34 missing vessels; score parquet approximately 50MiB compressed; one evaluation at a time",
           "allowed": available >= 2048}
    save(f"memory_{stage}.json", rec)
    if not rec["allowed"]:
        raise SystemExit(f"Deferred {stage}: insufficient RAM; recheck before retry.")


def missing_scores(missing):
    memory_gate("additional_scoring")
    s4 = load_module("round007_s4", "s4_score_dev.py")
    scorer = s4.module()
    columns = ["row_index", "rfid_id", "part_dt", "rfid_time", "len_m", "bbox_m",
               "cen_lon", "cen_lat", "key_valid", "wkt_valid"]
    frames, offset = [], 0
    for month in range(1, 7):
        pf = pq.ParquetFile(s4.CACHE / f"rows_train_{month}.parquet")
        for batch in pf.iter_batches(batch_size=65536, columns=columns):
            d = batch.to_pandas()
            rid = pd.to_numeric(d.rfid_id, errors="coerce")
            d = d.loc[d.key_valid & d.wkt_valid & rid.isin(missing)].copy()
            if len(d):
                d["source_ordinal"] = offset + d.row_index.to_numpy()
                d["rfid_id_int"] = pd.to_numeric(d.rfid_id).astype(np.int64)
                frames.append(d)
        offset += pf.metadata.num_rows
    df = pd.concat(frames, ignore_index=True)
    del frames
    df["ts"] = scorer.remeasure._ts_hours(df.part_dt.astype(str).astype(np.int64).to_numpy(),
                                           df.rfid_time.to_numpy())
    hb = json.loads((FIRST / "harbors.json").read_text(encoding="utf-8"))
    pts = np.asarray(hb["points"], dtype=float)
    scale = np.array([111320.0 * np.cos(np.radians(hb["meta"]["ref_lat"])), 110540.0])
    tree = cKDTree(pts * scale)

    def nearest(lons, lats):
        lons, lats = np.asarray(lons, float), np.asarray(lats, float)
        if not len(lons):
            return np.full(0, np.inf)
        _, idx = tree.query(np.column_stack([lons * scale[0], lats * scale[1]]), k=1)
        hp = pts[idx]
        return scorer.haversine_vec(lons, lats, hp[:, 0], hp[:, 1])

    with (FIRST / "density.pkl").open("rb") as f:
        fine, coarse = pickle.load(f)
    with (OLD / "own_density_cells.pkl").open("rb") as f:
        own = pickle.load(f)
    norm_gap, _ = scorer.build_quantile_normalizer(np.load(FIRST / "gap_reference.npy"))
    norm_jump, _ = scorer.build_quantile_normalizer(np.load(FIRST / "jump_reference.npy"))
    output = []
    cols = ["rfid_id_int", "ts", "part_dt", "rfid_time", "source_ordinal", "len_m",
            "bbox_m", "cen_lon", "cen_lat", "state", "s_zone", "s_change", "s_gap", "score"]
    for i, (rid, g) in enumerate(df.groupby("rfid_id_int", sort=True)):
        g = g.sort_values(["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
        touched = []
        for kind, density in (("fine", fine), ("coarse", coarse)):
            for cell in own[kind].get(rid, []):
                if cell in density:
                    density[cell] -= 1.0
                    touched.append((density, cell))
        try:
            scored = scorer.score_vessel(g, nearest, None, fine, coarse, norm_gap, norm_jump)
        finally:
            for density, cell in touched:
                density[cell] += 1.0
        scored["rfid_id_int"] = rid
        output.append(scored[cols])
        if (i + 1) % 5 == 0:
            print(f"additional vessels scored={i+1}/{len(missing)}", flush=True)
    result = pd.concat(output, ignore_index=True)
    assert set(result.rfid_id_int.astype(int)) == set(missing)
    result.to_parquet(HERE / "additional_hourly_scores.parquet", index=False)
    return result


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if not len(pos) or not len(neg):
        return None
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def exact_tail(probabilities, hits):
    distribution = np.array([1.0])
    for p in probabilities:
        distribution = np.convolve(distribution, [1 - p, p])
    return float(distribution[hits:].sum())


def supplements(s5):
    memory_gate("supplementary_evaluation")
    sc = pd.read_parquet(HERE / "dev_hourly_scores.parquet")
    pos = pd.read_csv(HERE / "devset_positives.csv")
    neg = pd.read_csv(HERE / "devset_negative_sample.csv").rfid_id.astype(int).tolist()
    groups = {int(rid): g.sort_values(["ts", "source_ordinal"], kind="stable")
              for rid, g in sc.groupby("rfid_id_int", sort=False)}
    rule_cache = {rid: s5.rule_times(g) for rid, g in groups.items() if rid in set(pos.rfid_id)}
    stats = {rid: {"n_rows": len(g), "peak": float(g.score.max()),
                   "mean": float(g.score.mean()), "q95": float(g.score.quantile(.95))}
             for rid, g in groups.items()}

    def evaluate(events):
        truth = events.groupby("rfid_id").acc_ts.agg(list).to_dict()
        probs, peak_hits, union_hits, oracle, missing_score = [], 0, 0, 0, []
        for rid, times in truth.items():
            g = groups.get(int(rid))
            if g is None:
                missing_score.append(int(rid))
                continue
            errors = np.min(np.abs(g.ts.to_numpy()[:, None] - np.asarray(times)[None, :]), axis=1)
            probs.append(float((errors <= 6).mean()))
            oracle += int((errors <= 6).any())
            rt = rule_cache[int(rid)]
            peak_hits += int("A_peak" in rt and min(abs(rt["A_peak"] - t) for t in times) <= 6)
            union_hits += int(any(min(abs(t - a) for a in times) <= 6 for t in rt.values()))
        assert not missing_score, missing_score
        ids = sorted(int(r) for r in truth)
        return {"events": len(events), "vessels": len(ids), "oracle_vessels": oracle,
                "A_peak_hits": peak_hits, "A_peak_hit_rate": peak_hits / len(ids) if ids else None,
                "any_rule_hits": union_hits, "any_rule_hit_rate": union_hits / len(ids) if ids else None,
                "random_row_hit_rate": float(np.mean(probs)) if probs else None,
                "random_expected_hits": float(np.sum(probs)),
                "p_value_one_sided_exact_poisson_binomial": exact_tail(probs, peak_hits) if probs else None,
                "auc_peak": auc([stats[r]["peak"] for r in ids], [stats[r]["peak"] for r in neg]),
                "auc_n_rows": auc([stats[r]["n_rows"] for r in ids], [stats[r]["n_rows"] for r in neg])}

    multi = set(pos.groupby("rfid_id").acc_id.nunique().loc[lambda s: s > 1].index)
    sensitivity = {"all": evaluate(pos), "exclude_conflict_events": evaluate(pos.loc[~pos.conflict]),
                   "exclude_multiple_event_vessels": evaluate(pos.loc[~pos.rfid_id.isin(multi)])}
    save("sensitivity_significance.json", sensitivity)
    posids = sorted(set(pos.rfid_id.astype(int)))
    available_neg = set(neg)
    matched = []
    for rid in posids:
        match = min(available_neg, key=lambda n: (abs(stats[n]["n_rows"] - stats[rid]["n_rows"]), n))
        available_neg.remove(match)
        matched.append(match)
    confound = {"auc_n_rows": sensitivity["all"]["auc_n_rows"],
                "auc_peak": sensitivity["all"]["auc_peak"],
                "auc_mean": auc([stats[r]["mean"] for r in posids], [stats[r]["mean"] for r in neg]),
                "auc_q95": auc([stats[r]["q95"] for r in posids], [stats[r]["q95"] for r in neg]),
                "matched_n": len(matched),
                "auc_peak_rowcount_matched": auc([stats[r]["peak"] for r in posids], [stats[r]["peak"] for r in matched]),
                "auc_nrows_matched_check": auc([stats[r]["n_rows"] for r in posids], [stats[r]["n_rows"] for r in matched]),
                "method": "greedy nearest absolute row count, positive ID order, unique negative, ties by ID; original matching code unavailable"}
    save("confound_rowcount.json", confound)
    pd.DataFrame({"positive_rfid_id": posids, "matched_negative_rfid_id": matched}).to_csv(HERE / "rowcount_matches.csv", index=False)

    rng = np.random.default_rng(20261105)
    recs = []
    for a in pos.sort_values("acc_id").itertuples():
        g = groups[int(a.rfid_id)]
        ts = g.ts.to_numpy()
        centers = [("accident", int(a.acc_ts))] + [("random", int(t)) for t in rng.integers(int(ts.min()), int(ts.max()) + 1, size=10)]
        for c in ("s_zone", "s_change", "s_gap", "score"):
            values = g[c].to_numpy()
            reference = np.sort(values[np.isfinite(values)])
            for kind, t in centers:
                values_in_window = values[(np.abs(ts - t) <= 6) & np.isfinite(values)]
                pct = float(np.searchsorted(reference, np.max(values_in_window), side="right") / len(reference)) if len(reference) and len(values_in_window) else None
                recs.append({"acc_id": a.acc_id, "rfid_id": a.rfid_id, "component": c,
                             "kind": kind, "center_ts": t, "percentile": pct})
    windows = pd.DataFrame(recs)
    windows.to_csv(HERE / "window_percentiles.csv", index=False)
    table = []
    for c, g in windows.groupby("component"):
        actual = g.loc[g.kind == "accident", "percentile"].dropna()
        random = g.loc[g.kind == "random", "percentile"].dropna()
        table.append({"component": c, "accident_count": len(actual), "random_count": len(random),
                      "accident_expected_count": len(pos), "random_expected_count": 10 * len(pos),
                      "accident_empty_or_nonfinite": len(pos) - len(actual),
                      "random_empty_or_nonfinite": 10 * len(pos) - len(random),
                      "accident_mean": float(actual.mean()), "random_mean": float(random.mean()),
                      "difference": float(actual.mean() - random.mean())})
    save("accident_hour_percentile.json", {"method": "available-window pooled means of maxima percentiles, right empirical CDF, uniform integer centers min(ts)..max(ts), 10 per event, seed20261105; empty windows omitted with counts; explicitly specified rerun, not original RNG reconstruction", "table": table})
    print(json.dumps({"sensitivity": sensitivity, "confound": confound, "percentiles": table}, indent=2), flush=True)


def main():
    started = time.monotonic()
    summary = json.loads((HERE / "devset_summary.json").read_text(encoding="utf-8"))
    missing = set(summary["score_cache_missing_positive_vessels"])
    reused_additional = (HERE / "additional_hourly_scores.parquet").exists()
    if missing:
        if (HERE / "additional_hourly_scores.parquet").exists():
            memory_gate("additional_score_cache_loading")
            extra = pd.read_parquet(HERE / "additional_hourly_scores.parquet")
            assert set(extra.rfid_id_int.astype(int)) == missing
        else:
            extra = missing_scores(missing)
    else:
        extra = pd.DataFrame()
    gc.collect()
    memory_gate("score_assembly")
    pos = pd.read_csv(HERE / "devset_positives.csv")
    neg = pd.read_csv(HERE / "devset_negative_sample.csv")
    targets = set(pos.rfid_id.astype(int)) | set(neg.rfid_id.astype(int))
    cached = pd.read_parquet(OLD / "dev_hourly_scores.parquet")
    cached = cached.loc[cached.rfid_id_int.isin(targets)].copy()
    sc = pd.concat([cached, extra], ignore_index=True)
    assert set(sc.rfid_id_int.astype(int)) == targets
    assert not sc.duplicated(["rfid_id_int", "source_ordinal"]).any()
    sc.to_parquet(HERE / "dev_hourly_scores.parquet", index=False)
    rows = len(sc)
    del sc, cached, extra
    gc.collect()
    memory_gate("s5_evaluation")
    s5 = load_module("round007_s5", "s5_evaluate.py")
    s5.HERE = HERE
    s5.main()
    # Update inherited explanatory prose only; numerical S5 output is unchanged.
    evaluation = json.loads((HERE / "evaluation_summary.json").read_text(encoding="utf-8"))
    evaluation["threshold"]["curve_note"] = (
        f"precision_devmix는 잠정 연결 양성 {pos.rfid_id.nunique()}척과 사고 목록 연결 근거 없는 표본 {len(neg)}척의 혼합비에서 계산한다. "
        "2025 Test B 사고 비율로 직접 해석할 수 없다. 신원과 음성은 확정 정답이 아니다.")
    save("evaluation_summary.json", evaluation)
    gc.collect()
    supplements(s5)
    save("score_evaluation_receipt.json", {"finished_at": datetime.now().astimezone().isoformat(),
                                          "elapsed_seconds": round(time.monotonic() - started, 2),
                                          "vessels": len(targets), "positive_vessels": pos.rfid_id.nunique(),
                                          "additional_score_vessels": len(missing),
                                          "additional_score_cache_reused": reused_additional, "rows": rows,
                                          "peak_rss_mib": round(getattr(psutil.Process().memory_info(), "peak_wset", psutil.Process().memory_info().rss) / 2**20, 1),
                                          "original_s5_note": "Numerical S5 unchanged; inherited curve prose updated to actual n_pos. Pool6127 unchanged.",
                                          "full_corrected_score_evaluation_ready": True})
    summary["full_corrected_score_evaluation_ready"] = True
    summary["corrected_score_rows"] = rows
    save("devset_summary.json", summary)


if __name__ == "__main__":
    main()
