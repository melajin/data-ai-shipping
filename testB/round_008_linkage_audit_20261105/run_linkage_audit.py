"""Rebuild candidate observations in bounded batches; never write Round 007."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
import time

import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq

from linkage import CASCADE, candidates, choose_event

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "round_007_20261105"
# Imported historical sources must not acquire bytecode files beside artifacts.
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("round007_link", OLD / "s1_link_accidents.py")
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
COLS = ["acc_id", "rfid_id", "dt_h", "dist_km", "row_len_m", "row_ts",
        "source_month", "source_row_index", "gear_match"]


def save(name, obj):
    (HERE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                      allow_nan=False), encoding="utf-8")


def preflight():
    vm = psutil.virtual_memory()
    active = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        if "python" in (p.info["name"] or "").lower():
            active.append({"pid": p.pid, "name": p.info["name"],
                           "rss_mib": round(p.info["memory_info"].rss / 2**20, 1)})
    receipt = {"checked_at": datetime.now().astimezone().isoformat(),
               "available_mib": round(vm.available / 2**20, 1),
               "estimated_additional_peak_mib": 768, "reserve_mib": 1024,
               "estimate_basis": "65,536 row sequential batches, numeric arrays, small nearby candidate table; no full train concat",
               "active_python_processes": active,
               "agent_work": "independent reviewers read small source/documents only",
               "allowed": vm.available >= (768 + 1024) * 2**20}
    save("memory_preflight.json", receipt)
    if not receipt["allowed"]:
        raise SystemExit("Deferred: insufficient available RAM; recheck immediately before retry.")


def stream_links(acc):
    pieces, vessels, gear_by_vessel = [], set(), {}
    read_columns = ["row_index", "rfid_id", "part_dt", "rfid_time", "cen_lon",
                    "cen_lat", "len_m", "fishing_code", "key_valid", "wkt_valid"]
    for month in range(1, 7):
        pf = pq.ParquetFile(original.CACHE / f"rows_train_{month}.parquet")
        for batch in pf.iter_batches(batch_size=65536, columns=read_columns):
            d = batch.to_pandas()
            rid = pd.to_numeric(d.rfid_id, errors="coerce")
            key = d.key_valid.to_numpy() & rid.notna().to_numpy()
            vessels.update(rid[key].astype(np.int64).tolist())
            d = d.loc[key & d.wkt_valid.to_numpy()].copy()
            d["rfid_id"] = rid.loc[d.index].astype(np.int64)
            dates = pd.to_datetime(d.part_dt.astype(str), format="%Y%m%d", errors="coerce")
            d = d.loc[dates.notna()].copy()
            d["row_ts"] = (dates.loc[d.index].to_numpy().astype("datetime64[h]").astype(np.int64)
                           + d.rfid_time.to_numpy().astype(np.int64))
            for v, g in d.groupby("rfid_id").fishing_code:
                gear_by_vessel.setdefault(int(v), set()).update(g.dropna().unique())
            d = d.sort_values("row_ts", kind="stable")
            ts = d.row_ts.to_numpy()
            for _, a in acc.iterrows():
                lo = np.searchsorted(ts, int(a.acc_ts) - 6, side="left")
                hi = np.searchsorted(ts, int(a.acc_ts) + 6, side="right")
                if hi <= lo:
                    continue
                sub = d.iloc[lo:hi]
                dist = original.haversine_m(float(a["경도(변환)"]), float(a["위도(변환)"]),
                                            sub.cen_lon.to_numpy(), sub.cen_lat.to_numpy()) / 1000
                mask = dist <= 20.0
                if not mask.any():
                    continue
                near = sub.loc[mask]
                pieces.append(pd.DataFrame({
                    "acc_id": int(a.acc_id), "rfid_id": near.rfid_id.to_numpy(),
                    "dt_h": np.abs(near.row_ts.to_numpy() - int(a.acc_ts)),
                    "dist_km": dist[mask], "row_len_m": near.len_m.to_numpy(),
                    "row_ts": near.row_ts.to_numpy(), "source_month": month,
                    "source_row_index": near.row_index.to_numpy()}))
        print(f"month={month} candidate_pieces={len(pieces)}", flush=True)
    links = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=COLS[:-1])
    event_gear = acc.set_index("acc_id").gear_code.to_dict()
    links["gear_match"] = [event_gear[int(a)] in gear_by_vessel.get(int(v), set())
                           for a, v in zip(links.acc_id, links.rfid_id)]
    return links, vessels


def condition_grid(links, old_links, accidents):
    grid, changes = {}, []
    for w in original.WINDOWS_H:
        for r in original.RADII_KM:
            for gear in (False, True):
                cond = f"w{w}_r{int(r)}" + ("_gear" if gear else "")
                # Each event independently retains one witness per vessel.
                mask = (links.dt_h <= w) & (links.dist_km <= r)
                omask = (old_links.dt_h <= w) & (old_links.dist_km <= r)
                if gear:
                    mask &= links.gear_match
                    omask &= old_links.gear_match
                newsets = links.loc[mask].groupby("acc_id").rfid_id.agg(set).to_dict()
                oldsets = old_links.loc[omask].groupby("acc_id").rfid_id.agg(set).to_dict()
                ns = pd.Series({a: len(s) for a, s in newsets.items()}, dtype="int64")
                grid[cond] = {"events_with_candidate": len(ns),
                              "events_single_candidate": int((ns == 1).sum()),
                              "median_candidates": float(ns.median()) if len(ns) else None}
                for aid in accidents:
                    before, after = oldsets.get(aid, set()), newsets.get(aid, set())
                    assert before <= after, (cond, aid, "lost old candidate")
                    if w == 6 and r == 20:
                        assert before == after, (cond, aid, "widest candidate set changed")
                    if before != after:
                        changes.append({"condition": cond, "acc_id": int(aid),
                                        "old_n": len(before), "new_n": len(after),
                                        "old_spurious_single": len(before) == 1 and len(after) > 1,
                                        "added_vessels": ";".join(map(str, sorted(after - before)))})
    return grid, changes


def main():
    preflight()
    started = time.monotonic()
    acc = pd.read_excel(original.ACC_XLSX).reset_index().rename(columns={"index": "acc_id"})
    acc["acc_ts"] = acc["발생일시"].to_numpy().astype("datetime64[h]").astype(np.int64)
    acc["gear_code"] = acc["어업면허"].map(original.GEAR_MAP)
    assert acc.gear_code.notna().all()
    links, vessels = stream_links(acc)
    links.to_csv(HERE / "links_observations.csv", index=False, encoding="utf-8-sig")
    old_links = pd.read_csv(OLD / "links_candidates.csv")
    grid, changes = condition_grid(links, old_links, acc.acc_id)
    pd.DataFrame(changes).to_csv(HERE / "condition_changes.csv", index=False, encoding="utf-8-sig")
    save("links_summary.json", {"accidents_total": len(acc), "observation_rows": len(links),
                                "event_vessel_pairs": len(links[["acc_id", "rfid_id"]].drop_duplicates()),
                                "grid": grid, "candidate_set_invariants_passed": True})
    recs = []
    for aid, grp in links.groupby("acc_id"):
        chosen = choose_event(grp)
        if chosen is not None:
            recs.append({"acc_id": int(aid), **chosen})
    dev = pd.DataFrame(recs, columns=["acc_id", "rfid_id", "tier", "cascade_cond", "conflict",
                                     "dt_h", "dist_km", "row_ts", "source_month",
                                     "source_row_index", "n_cand_base_gear"])
    dev["conflict"] = dev.conflict.astype(bool)
    info = ["acc_id", "acc_ts", "발생일시", "발생유형", "어업면허", "톤수",
            "사고선박수", "위도(변환)", "경도(변환)"]
    dev = dev.merge(acc[info], on="acc_id", how="left")
    multi = dev.groupby("rfid_id").acc_id.nunique()
    dev["vessel_multi_accident"] = dev.rfid_id.map(multi) > 1
    dev.to_csv(HERE / "devset_positives.csv", index=False, encoding="utf-8-sig")
    loose = set(links.rfid_id.astype(int))
    negatives = sorted(vessels - loose)
    old_summary = json.loads((OLD / "devset_summary.json").read_text(encoding="utf-8"))
    assert len(vessels) == old_summary["vessels_total_train"]
    assert len(negatives) == old_summary["negative_pool"]
    rng = np.random.default_rng(20261105)
    sample = sorted(rng.choice(np.array(negatives), min(1500, len(negatives)), replace=False).tolist())
    pd.DataFrame({"rfid_id": sample}).to_csv(HERE / "devset_negative_sample.csv", index=False)
    old_sample = pd.read_csv(OLD / "devset_negative_sample.csv").rfid_id.astype(int).tolist()
    assert sample == old_sample, "negative sample changed"
    olddev = pd.read_csv(OLD / "devset_positives.csv")
    before, after = olddev.set_index("acc_id"), dev.set_index("acc_id")
    comparison = []
    counts = {"added": 0, "removed": 0, "reassigned": 0, "retained_identity": 0}
    for aid in sorted(set(before.index) | set(after.index)):
        b = before.loc[aid] if aid in before.index else None
        a = after.loc[aid] if aid in after.index else None
        state = ("added" if b is None else "removed" if a is None else
                 "reassigned" if int(b.rfid_id) != int(a.rfid_id) else "retained_identity")
        counts[state] += 1
        comparison.append({"acc_id": int(aid), "status": state,
                           "old_rfid_id": int(b.rfid_id) if b is not None else None,
                           "new_rfid_id": int(a.rfid_id) if a is not None else None,
                           "old_tier": int(b.tier) if b is not None else None,
                           "new_tier": int(a.tier) if a is not None else None,
                           "old_conflict": bool(b.conflict) if b is not None else None,
                           "new_conflict": bool(a.conflict) if a is not None else None})
    pd.DataFrame(comparison).to_csv(HERE / "event_changes.csv", index=False, encoding="utf-8-sig")
    cached = set(pq.read_table(OLD / "dev_hourly_scores.parquet", columns=["rfid_id_int"])
                 .column(0).to_numpy().astype(int))
    posids = set(dev.rfid_id.astype(int))
    summary = {"vessels_total_train": len(vessels), "accidents_total": len(acc),
               "events_with_candidate_identity": len(dev), "distinct_vessels": len(posids),
               "events_with_conflict": int(dev.conflict.sum()),
               "events_without_conflict": int((~dev.conflict).sum()),
               "distinct_vessels_without_conflict": int(dev.loc[~dev.conflict].rfid_id.nunique()),
               "vessels_with_multiple_events": int((multi > 1).sum()),
               "events_by_tier": {str(CASCADE[int(t)]): int(c) for t, c in dev.tier.value_counts().sort_index().items()},
               "accident_adjacent_vessels_loose": len(loose), "negative_pool": len(negatives),
               "negative_sample": len(sample), "negative_sample_unchanged": True,
               "negative_pool_count_unchanged": True,
               "event_changes": counts,
               "conditions_with_changed_candidates": len(set(c["condition"] for c in changes)),
               "condition_event_changes": len(changes),
               "condition_event_spurious_single_resolved": sum(c["old_spurious_single"] for c in changes),
               "score_cache_positive_vessels_present": len(posids & cached),
               "score_cache_missing_positive_vessels": sorted(posids - cached),
               "full_corrected_score_evaluation_ready": posids <= cached,
               "caveat": "Candidate identities are heuristic, not confirmed vessel ground truth; cascade/conflict policy unchanged."}
    save("devset_summary.json", summary)
    save("execution_receipt.json", {"finished_at": datetime.now().astimezone().isoformat(),
                                     "elapsed_seconds": round(time.monotonic() - started, 2),
                                     "peak_rss_mib": round(getattr(psutil.Process().memory_info(), "peak_wset", psutil.Process().memory_info().rss) / 2**20, 1)})
    print(json.dumps(summary, ensure_ascii=True, indent=2), flush=True)


if __name__ == "__main__":
    main()
