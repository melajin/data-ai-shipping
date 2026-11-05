#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 007 / S1 — 2026 사고기록 167건을 2026 학습 항적에 연결해 평가 가능 단위를 만든다.

핵심 판단 (이번에 새로 넣은 것):
  - 사고기록의 `어업면허`(자망/연안복합/통발/연승)는 항적의 `fishing_code`
    (자망/연안복합/통발/채낚기연승낚시)와 1:1 대응한다. 선박당 어구는 단일이다
    (7,372척 중 다중 1척). 따라서 어구는 시공간과 독립된 **신원 제약**으로 쓸 수 있다.
  - 후보 선택에 이상점수를 절대 쓰지 않는다. 점수로 후보를 고르면 그 뒤의 성능 측정이
    순환논증이 된다. 여기서 쓰는 정보는 시각·좌표·어구뿐이다.

출력: links_candidates.csv (사고×후보 전체), links_summary.json (조건별 분모)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
CACHE = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과\outputs\remeasure_20261031")
ACC_XLSX = HERE.parent / "intake/1103_v2/inspection_001/reference_01_26년 1~6월 어선 사고현황(테스트 데이터).xlsx"

# 사고기록 어업면허 -> 항적 fishing_code
GEAR_MAP = {"자망": "자망", "연안복합": "연안복합", "통발": "통발", "연승": "채낚기연승낚시"}

EARTH_R = 6_371_000.0
WINDOWS_H = (0, 1, 2, 3, 6)          # |행 시각 - 사고 시각| 허용 시간
RADII_KM = (2.0, 5.0, 10.0, 20.0)    # 중심점 거리 허용
BASE = (1, 5.0)                      # 기준 조건 (선행 감사와 동일)


def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def load_train_rows() -> pd.DataFrame:
    cols = ["rfid_id", "part_dt", "rfid_time", "cen_lon", "cen_lat", "len_m",
            "fishing_code", "key_valid", "wkt_valid"]
    frames = []
    for m in range(1, 7):
        d = pq.read_table(CACHE / f"rows_train_{m}.parquet", columns=cols).to_pandas()
        d = d[d["key_valid"].to_numpy() & d["wkt_valid"].to_numpy()]
        d = d.drop(columns=["key_valid", "wkt_valid"])
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    del frames
    df["rfid_id"] = pd.to_numeric(df["rfid_id"], errors="coerce")
    df = df[df["rfid_id"].notna()].copy()
    df["rfid_id"] = df["rfid_id"].astype(np.int64)
    dt = pd.to_datetime(df["part_dt"].astype(str), format="%Y%m%d", errors="coerce")
    df = df[dt.notna()].copy()
    df["ts"] = (dt[dt.notna()].values.astype("datetime64[h]").astype(np.int64)
                + df["rfid_time"].to_numpy().astype(np.int64))
    return df[["rfid_id", "ts", "cen_lon", "cen_lat", "len_m", "fishing_code"]]


def main():
    acc = pd.read_excel(ACC_XLSX)
    acc = acc.reset_index().rename(columns={"index": "acc_id"})
    acc["acc_ts"] = (acc["발생일시"].values.astype("datetime64[h]").astype(np.int64))
    acc["gear_code"] = acc["어업면허"].map(GEAR_MAP)
    assert acc["gear_code"].notna().all(), "어업면허 매핑 실패"

    df = load_train_rows()
    print(f"train rows={len(df)} vessels={df['rfid_id'].nunique()}", flush=True)

    # 선박 단위 어구 (다중 어구 선박은 어구 제약에서 제외하지 않고 보유 어구 집합으로 판정)
    gear_by_vessel = df.groupby("rfid_id")["fishing_code"].agg(lambda s: set(s.dropna()))

    order = np.argsort(df["ts"].to_numpy(), kind="stable")
    ts = df["ts"].to_numpy()[order]
    vid = df["rfid_id"].to_numpy()[order]
    lon = df["cen_lon"].to_numpy()[order]
    lat = df["cen_lat"].to_numpy()[order]
    lenm = df["len_m"].to_numpy()[order]
    del df

    rows = []
    for _, a in acc.iterrows():
        at, alon, alat = int(a["acc_ts"]), float(a["경도(변환)"]), float(a["위도(변환)"])
        wmax = max(WINDOWS_H)
        lo = np.searchsorted(ts, at - wmax, "left")
        hi = np.searchsorted(ts, at + wmax, "right")
        if hi <= lo:
            continue
        sl = slice(lo, hi)
        d_m = haversine_m(alon, alat, lon[sl], lat[sl])
        dt_h = np.abs(ts[sl] - at)
        keep = d_m <= max(RADII_KM) * 1000.0
        if not keep.any():
            continue
        sub = pd.DataFrame({"rfid_id": vid[sl][keep], "dt_h": dt_h[keep],
                            "dist_km": d_m[keep] / 1000.0, "row_len_m": lenm[sl][keep],
                            "row_ts": ts[sl][keep]})
        # 선박별 최근접 관측 하나로 축약
        sub = sub.sort_values(["rfid_id", "dist_km", "dt_h"]).groupby("rfid_id", as_index=False).first()
        sub["acc_id"] = int(a["acc_id"])
        sub["gear_match"] = [a["gear_code"] in gear_by_vessel.get(v, set()) for v in sub["rfid_id"]]
        rows.append(sub)

    links = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    links.to_csv(HERE / "links_candidates.csv", index=False, encoding="utf-8-sig")

    # 조건별 후보 수 집계
    grid = {}
    for w in WINDOWS_H:
        for r in RADII_KM:
            for gear in (False, True):
                sel = links[(links.dt_h <= w) & (links.dist_km <= r)]
                if gear:
                    sel = sel[sel.gear_match]
                n_cand = sel.groupby("acc_id")["rfid_id"].nunique()
                key = f"w{w}_r{int(r)}" + ("_gear" if gear else "")
                grid[key] = {
                    "events_with_candidate": int(len(n_cand)),
                    "events_single_candidate": int((n_cand == 1).sum()),
                    "median_candidates": float(n_cand.median()) if len(n_cand) else None,
                }

    # 기준조건 단일 후보, 그리고 격자 전반에서 안정적으로 단일인 사건
    w0, r0 = BASE
    base_sel = links[(links.dt_h <= w0) & (links.dist_km <= r0) & links.gear_match]
    base_n = base_sel.groupby("acc_id")["rfid_id"].nunique()
    single_ids = base_n[base_n == 1].index.tolist()
    single_map = base_sel[base_sel.acc_id.isin(single_ids)].set_index("acc_id")["rfid_id"].to_dict()

    stable = []
    for aid, v in single_map.items():
        ok = True
        for w in WINDOWS_H:
            for r in RADII_KM:
                s = links[(links.acc_id == aid) & (links.dt_h <= w) & (links.dist_km <= r) & links.gear_match]
                vs = set(s["rfid_id"])
                if vs and vs != {v}:
                    ok = False
        if ok:
            stable.append(aid)

    out = {
        "accidents_total": int(len(acc)),
        "accidents_single_vessel_record": int((acc["사고선박수"] == 1).sum()),
        "grid": grid,
        "base_condition": {"window_h": w0, "radius_km": r0, "gear_filter": True},
        "base_single_candidate_events": len(single_map),
        "base_single_candidate_map": {int(k): int(v) for k, v in single_map.items()},
        "grid_stable_single_events": sorted(int(x) for x in stable),
        "note": ("후보 선택에 이상점수를 사용하지 않았다. 단일 후보는 신원 확정이 아니다. "
                 "어구 제약은 사고기록 어업면허와 항적 fishing_code의 1:1 대응을 사용한다."),
    }
    (HERE / "links_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "base_single_candidate_map"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
