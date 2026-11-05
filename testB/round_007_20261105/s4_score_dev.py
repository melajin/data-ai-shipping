#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 007 / S4 — dev(2026) 선박에 2025와 같은 scorer를 적용한다. leave-self-out 밀도 적용.

같은 원본 함수(score_vessel)와 같은 저장 참조(harbors.json/density.pkl/gap·jump npy)를 쓴다.
차이는 하나뿐이다: dev 선박은 밀도지도에 자기 자신이 들어 있으므로 셀별 유니크 선박 수에서
자기 기여 1을 빼고 점수를 낸다(S3에서 멤버십을 전수 대조로 확인).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
CACHE = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과\outputs\remeasure_20261031")
FIRST = HERE.parent / "first_results"
SOURCE = Path(r"D:\repos\fishing-track-classification\code\tools\run_008_testB_20261101.py")


def module():
    spec = importlib.util.spec_from_file_location("testb_original_008", SOURCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_target_rows(targets: set[int]) -> pd.DataFrame:
    cols = ["row_index", "rfid_id", "part_dt", "rfid_time", "len_m", "bbox_m",
            "cen_lon", "cen_lat", "key_valid", "wkt_valid"]
    frames, offset = [], 0
    for m in range(1, 7):
        t = pq.read_table(CACHE / f"rows_train_{m}.parquet", columns=cols)
        n_month = t.num_rows
        d = t.to_pandas()
        del t
        d["source_month"] = m
        d["source_ordinal"] = offset + d["row_index"].to_numpy()
        offset += n_month
        d = d[d.key_valid.to_numpy() & d.wkt_valid.to_numpy()]
        rid = pd.to_numeric(d.rfid_id, errors="coerce")
        d = d[rid.notna() & rid.astype("Int64").isin(list(targets))]
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["rfid_id_int"] = df.rfid_id.astype(np.int64)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-out", dest="self_out", action="store_true", default=True)
    ap.add_argument("--no-self-out", dest="self_out", action="store_false")
    ap.add_argument("--out", default="dev_hourly_scores.parquet")
    args = ap.parse_args()

    s = module()
    pos = pd.read_csv(HERE / "devset_positives.csv")
    neg = pd.read_csv(HERE / "devset_negative_sample.csv")
    targets = sorted(set(pos.rfid_id.astype(int)) | set(neg.rfid_id.astype(int)))
    print(f"targets={len(targets)} (pos={pos.rfid_id.nunique()} neg={len(neg)})", flush=True)

    df = load_target_rows(set(targets))
    df["ts"] = s.remeasure._ts_hours(df["part_dt"].astype(str).astype(np.int64).to_numpy()
                                     if df["part_dt"].dtype == object else df["part_dt"].to_numpy(),
                                     df["rfid_time"].to_numpy())
    print(f"rows={len(df)} vessels_present={df.rfid_id_int.nunique()}", flush=True)

    hb = json.loads((FIRST / "harbors.json").read_text(encoding="utf-8"))
    pts = np.asarray(hb["points"], dtype=float)
    mx = 111320.0 * np.cos(np.radians(hb["meta"]["ref_lat"])); my = 110540.0
    tree = cKDTree(pts * np.array([mx, my]))

    def nearest(lons, lats):
        lons, lats = np.asarray(lons, float), np.asarray(lats, float)
        if not len(lons):
            return np.full(0, np.inf)
        _, idx = tree.query(np.column_stack([lons * mx, lats * my]), k=1)
        hp = pts[idx]
        return s.haversine_vec(lons, lats, hp[:, 0], hp[:, 1])

    with (FIRST / "density.pkl").open("rb") as f:
        fine, coarse = pickle.load(f)
    with (HERE / "own_density_cells.pkl").open("rb") as f:
        own = pickle.load(f)

    norm_gap, _ = s.build_quantile_normalizer(np.load(FIRST / "gap_reference.npy"))
    norm_jump, _ = s.build_quantile_normalizer(np.load(FIRST / "jump_reference.npy"))

    groups = {k: g for k, g in df.groupby("rfid_id_int", sort=False)}
    out, meta, t0 = [], [], time.monotonic()
    for i, rid in enumerate(targets):
        sub = groups.get(rid)
        if sub is None or not len(sub):
            meta.append({"rfid_id": rid, "n_rows": 0})
            continue
        sub = sub.sort_values(["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
        touched = []
        if args.self_out:
            for c in own["fine"].get(rid, []):
                if c in fine:
                    fine[c] -= 1.0
                    touched.append(("f", c))
            for c in own["coarse"].get(rid, []):
                if c in coarse:
                    coarse[c] -= 1.0
                    touched.append(("c", c))
        try:
            scored = s.score_vessel(sub, nearest, None, fine, coarse, norm_gap, norm_jump)
        finally:
            for kind, c in touched:
                (fine if kind == "f" else coarse)[c] += 1.0
        scored["rfid_id_int"] = rid
        out.append(scored[["rfid_id_int", "ts", "part_dt", "rfid_time", "source_ordinal",
                           "len_m", "bbox_m", "cen_lon", "cen_lat", "state",
                           "s_zone", "s_change", "s_gap", "score"]])
        meta.append({"rfid_id": rid, "n_rows": len(sub)})
        if (i + 1) % 100 == 0:
            print(f"{i+1}/{len(targets)} elapsed={time.monotonic()-t0:.0f}s "
                  f"rss={psutil.Process().memory_info().rss/2**20:.0f}MiB", flush=True)

    allsc = pd.concat(out, ignore_index=True)
    allsc.to_parquet(HERE / args.out, index=False)
    pd.DataFrame(meta).to_csv(HERE / f"{Path(args.out).stem}_rowcounts.csv", index=False)
    rep = {"self_out": args.self_out, "vessels_requested": len(targets),
           "vessels_scored": int(allsc.rfid_id_int.nunique()), "rows_scored": int(len(allsc)),
           "elapsed_seconds": round(time.monotonic() - t0, 1),
           "peak_rss_mib": round(psutil.Process().memory_info().peak_wset / 2**20, 1)}
    (HERE / f"{Path(args.out).stem}_receipt.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                                              encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
