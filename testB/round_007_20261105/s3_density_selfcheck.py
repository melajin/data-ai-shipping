#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 007 / S3 — 밀도지도의 의미를 독립 재구성으로 확인하고, leave-self-out 멤버십을 만든다.

왜 필요한가:
  2025 Test 선박은 2026 Train으로 만든 밀도지도에 자기 자신이 들어 있지 않다.
  2026 dev 선박은 자기 자신이 들어 있다. comp_b = 1 - min(density/3, 1) 이므로
  density가 1~3인 희소 셀에서 자기 포함 여부가 s_zone을 직접 바꾼다.
  보정하지 않으면 dev에서 정한 임계값이 2025에서 체계적으로 낮게(=과다탐지) 작동한다.

따라서 셀별 '유니크 선박 수' 의미를 저장된 density.pkl과 대조해 확인하고,
dev 선박별 자기 기여 셀 집합을 저장한다.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
CACHE = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과\outputs\remeasure_20261031")
FIRST = HERE.parent / "first_results"

EARTH_R = 6_371_000.0
GRID_HARBOR, GRID_FINE, GRID_COARSE = 0.005, 0.01, 0.05
STOP_LEN_M, STOP_BBOX_M = 50.0, 100.0
HARBOR_NEAR_M = MOORING_NEAR_M = 1000.0
NIGHT = (20, 21, 22, 23, 0, 1, 2, 3)


def hav(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def main():
    cols = ["rfid_id", "cen_lon", "cen_lat", "len_m", "bbox_m", "rfid_time", "key_valid", "wkt_valid"]
    fr = []
    for m in range(1, 7):
        d = pq.read_table(CACHE / f"rows_train_{m}.parquet", columns=cols).to_pandas()
        d = d[d.key_valid.to_numpy() & d.wkt_valid.to_numpy()].drop(columns=["key_valid", "wkt_valid"])
        fr.append(d)
    df = pd.concat(fr, ignore_index=True)
    del fr
    df["rfid_id"] = pd.to_numeric(df["rfid_id"], errors="coerce")
    df = df[df.rfid_id.notna()]
    rid = df.rfid_id.to_numpy().astype(np.int64)
    lon = df.cen_lon.to_numpy(); lat = df.cen_lat.to_numpy()
    lenm = df.len_m.to_numpy(); bbox = df.bbox_m.to_numpy()
    rtime = df.rfid_time.to_numpy()
    del df

    # 1) 항구 거리 (저장된 harbors.json 재사용 — 2025 점수와 같은 참조)
    hb = json.loads((FIRST / "harbors.json").read_text(encoding="utf-8"))
    pts = np.asarray(hb["points"], dtype=float)
    mx = 111320.0 * np.cos(np.radians(hb["meta"]["ref_lat"])); my = 110540.0
    tree = cKDTree(pts * np.array([mx, my]))
    _, idx = tree.query(np.column_stack([lon * mx, lat * my]), k=1)
    hp = pts[idx]
    harbor_dist = hav(lon, lat, hp[:, 0], hp[:, 1])
    del hp, idx

    # 2) 선박별 정박지 상위 3셀 (remeasure._build_own_moorings 재현) + 벡터화 거리
    stop = (lenm <= STOP_LEN_M) & (bbox <= STOP_BBOX_M)
    night = np.isin(rtime, NIGHT)
    ns = stop & night
    mc = pd.DataFrame({"rfid_id": rid[ns],
                       "ix": np.floor(lon[ns] / GRID_HARBOR).astype(np.int64),
                       "iy": np.floor(lat[ns] / GRID_HARBOR).astype(np.int64)})
    cnt = mc.value_counts(["rfid_id", "ix", "iy"]).rename("n").reset_index()
    cnt = cnt.sort_values(["rfid_id", "n"], ascending=[True, False])
    top3 = cnt.groupby("rfid_id", sort=False).head(3).copy()
    top3["slot"] = top3.groupby("rfid_id", sort=False).cumcount()
    top3["mlon"] = (top3.ix + 0.5) * GRID_HARBOR
    top3["mlat"] = (top3.iy + 0.5) * GRID_HARBOR
    wide = top3.pivot(index="rfid_id", columns="slot", values=["mlon", "mlat"])
    mooring_dist = np.full(len(rid), np.inf)
    for s in range(3):
        if ("mlon", s) not in wide.columns:
            continue
        ml = pd.Series(rid).map(wide[("mlon", s)]).to_numpy(dtype=float)
        ma = pd.Series(rid).map(wide[("mlat", s)]).to_numpy(dtype=float)
        ok = ~np.isnan(ml)
        d = np.full(len(rid), np.inf)
        d[ok] = hav(lon[ok], lat[ok], ml[ok], ma[ok])
        mooring_dist = np.minimum(mooring_dist, d)
    del mc, cnt, top3, wide

    fishing = (lenm > STOP_LEN_M) & (harbor_dist > HARBOR_NEAR_M) & (mooring_dist > MOORING_NEAR_M)
    print(f"fishing rows reconstructed = {int(fishing.sum())}", flush=True)

    # 3) 셀별 유니크 선박 수 재구성 후 저장된 density.pkl과 대조
    with (FIRST / "density.pkl").open("rb") as f:
        dens01, dens05 = pickle.load(f)

    def cellcount(grid):
        ix = np.floor(lon[fishing] / grid).astype(np.int64)
        iy = np.floor(lat[fishing] / grid).astype(np.int64)
        tri = np.unique(np.column_stack([ix, iy, rid[fishing]]), axis=0)
        cells, cts = np.unique(tri[:, :2], axis=0, return_counts=True)
        return {(int(a), int(b)): int(c) for (a, b), c in zip(cells, cts)}, tri

    rec01, tri01 = cellcount(GRID_FINE)
    rec05, tri05 = cellcount(GRID_COARSE)

    def compare(rec, saved):
        keys = set(rec) | set(saved)
        diff = [(k, rec.get(k, 0), saved.get(k, 0)) for k in keys if rec.get(k, 0) != saved.get(k, 0)]
        return {"n_cells_reconstructed": len(rec), "n_cells_saved": len(saved),
                "n_cells_mismatch": len(diff), "examples": diff[:5]}

    report = {"fine": compare(rec01, dens01), "coarse": compare(rec05, dens05),
              "fishing_rows_reconstructed": int(fishing.sum()),
              "fishing_rows_saved_meta": json.loads((FIRST / "density_meta.json").read_text())["n_fishing_rows"]}

    # 4) 선박별 자기 기여 셀 (leave-self-out 용)
    own = {"fine": {}, "coarse": {}}
    for name, tri in (("fine", tri01), ("coarse", tri05)):
        o = pd.DataFrame(tri, columns=["ix", "iy", "rid"]).groupby("rid")
        own[name] = {int(k): [(int(a), int(b)) for a, b in g[["ix", "iy"]].to_numpy()] for k, g in o}
    with (HERE / "own_density_cells.pkl").open("wb") as f:
        pickle.dump(own, f, protocol=pickle.HIGHEST_PROTOCOL)

    (HERE / "density_selfcheck.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                                                 encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
