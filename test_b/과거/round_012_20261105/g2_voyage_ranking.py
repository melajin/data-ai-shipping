# -*- coding: utf-8 -*-
"""Round012 선행 관문 G2 — 항차 순위화로 ±6h 적중률이 움직이는가.
G1에서 "사고 항차를 맞히면 ±6h 적중 천장 57~69%"를 실측했다.
따라서 남은 문제는 선박 내 약 43개 항차 중 사고 항차를 고르는 순위화다.
종점은 사전 고정: top-1 항차의 중앙 시각이 사고시각 ±6h 안인가.
기준선은 무작위 행 2.26%, 무작위 항차 선택 5.18%x천장.
읽기 전용. 새 모델·제출물 생성 없음.
"""
import json
import numpy as np
import pandas as pd

ROOT = "testB/round_007_20261105"
OUT = "testB/round_012_20261105"
THR = 6  # 주 분할. G1에서 천장이 가장 높고 1h 샘플링과 정합적.

pos = pd.read_csv(f"{ROOT}/devset_positives.csv")
pos["rfid_id"] = pos["rfid_id"].astype(str)
cols = ["rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "state"]
trk = pd.read_parquet(f"{ROOT}/dev_hourly_scores.parquet", columns=cols)
trk = trk.rename(columns={"rfid_id_int": "rfid_id"})
trk["rfid_id"] = trk["rfid_id"].astype(str)
trk = trk[trk.rfid_id.isin(set(pos.rfid_id))].sort_values(["rfid_id", "ts"])

# 사전 등록 특징 목록 (항차 단위). 부호는 양쪽 모두 평가하고 max-T로 보정한다.
FEATS = [
    "voy_hours",        # 항차 관측시간 (조기 종료 가설)
    "voy_span",
    "len_sum",          # 총 경로장
    "len_mean",         # 시간당 경로장 = 속력 대용
    "len_last3",        # 종료 직전 3시간 경로장 (추진력 상실 가설)
    "lin_voy",          # 항차 전체 bbox/len (제자리 선회 가설)
    "lin_last3",
    "disp_max",         # 출발점 대비 최대 이탈거리
    "frac_sea_stop",    # 해상정지 비율
    "frac_slowturn",    # 저속굴곡 비율
    "frac_move",        # 이동 비율
    "gap_after",        # 항차 직후 공백 길이 (사후 중단 가설)
]

def haversine(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))

voy_rows = []
for vid, g in trk.groupby("rfid_id"):
    ts = g["ts"].to_numpy()
    seg = np.concatenate([[0], np.cumsum(np.diff(ts) >= THR)])
    g = g.assign(voy=seg)
    nvoy = int(seg.max()) + 1
    for v, h in g.groupby("voy"):
        t = h["ts"].to_numpy()
        ln = h["len_m"].to_numpy(dtype=float)
        bb = h["bbox_m"].to_numpy(dtype=float)
        lo = h["cen_lon"].to_numpy(dtype=float)
        la = h["cen_lat"].to_numpy(dtype=float)
        st = h["state"].to_numpy()
        nxt = g.loc[g.voy == v + 1, "ts"]
        gap_after = float(nxt.iloc[0] - t[-1]) if len(nxt) else np.nan
        last3 = slice(max(0, len(t) - 3), len(t))
        voy_rows.append(dict(
            rfid_id=vid, voy=int(v), n_voyages=nvoy,
            t_start=int(t[0]), t_end=int(t[-1]),
            t_mid=int(t[len(t) // 2]),
            voy_hours=float(len(t)), voy_span=float(t[-1] - t[0] + 1),
            len_sum=float(np.nansum(ln)), len_mean=float(np.nanmean(ln)),
            len_last3=float(np.nanmean(ln[last3])),
            lin_voy=float(np.nansum(bb) / max(np.nansum(ln), 1.0)),
            lin_last3=float(np.nanmean(bb[last3]) / max(np.nanmean(ln[last3]), 1.0)),
            disp_max=float(np.nanmax(haversine(lo[0], la[0], lo, la))) if len(t) > 1 else 0.0,
            frac_sea_stop=float((st == "해상정지").mean()),
            frac_slowturn=float((st == "저속굴곡").mean()),
            frac_move=float((st == "이동").mean()),
            gap_after=gap_after,
        ))
V = pd.DataFrame(voy_rows)
V.to_csv(f"{OUT}/g2_voyages.csv", index=False, encoding="utf-8-sig")

# 각 사건에 대해: 선박 내 항차를 특징별로 정렬해 top-1 항차 중앙시각의 ±6h 적중 여부
res = {}
detail = []
for f in FEATS:
    for sign, lab in ((-1, "max"), (1, "min")):
        hits_all, hits_t01 = [], []
        for _, r in pos.iterrows():
            vid, acc, tier = r["rfid_id"], int(r["acc_ts"]), int(r["tier"])
            g = V[V.rfid_id == vid].dropna(subset=[f])
            if len(g) < 2:
                continue
            top = g.iloc[int(np.argmin(sign * g[f].to_numpy() * -1)) if sign == -1
                         else int(np.argmin(g[f].to_numpy()))]
            hit = abs(int(top["t_mid"]) - acc) <= 6
            hits_all.append(hit)
            if tier <= 1:
                hits_t01.append(hit)
            detail.append(dict(feat=f, mode=lab, acc_id=int(r["acc_id"]), tier=tier, hit=bool(hit)))
        res[f"{f}|{lab}"] = dict(
            n_all=len(hits_all), hit_all=float(np.mean(hits_all)) if hits_all else None,
            n_t01=len(hits_t01), hit_t01=float(np.mean(hits_t01)) if hits_t01 else None,
        )

# 기준선: 선박 내 항차를 무작위 선택했을 때의 top-1 중앙시각 ±6h 적중 기대율
rng = np.random.default_rng(20261105)
base = []
for _, r in pos.iterrows():
    vid, acc = r["rfid_id"], int(r["acc_ts"])
    g = V[V.rfid_id == vid]
    if len(g) < 2:
        continue
    base.append(float((np.abs(g["t_mid"].to_numpy() - acc) <= 6).mean()))
res["_baseline_random_voyage_mid"] = dict(n_all=len(base), hit_all=float(np.mean(base)))
res["_meta"] = dict(thr=THR, n_events=int(len(pos)), n_vessels=int(pos.rfid_id.nunique()),
                    n_voyages_total=int(len(V)),
                    median_voyages_per_vessel=float(V.groupby("rfid_id")["n_voyages"].first().median()))

pd.DataFrame(detail).to_csv(f"{OUT}/g2_detail.csv", index=False, encoding="utf-8-sig")
with open(f"{OUT}/g2_summary.json", "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=2)

print(json.dumps(res["_meta"], ensure_ascii=False))
print("baseline(무작위 항차 중앙시각):", round(res["_baseline_random_voyage_mid"]["hit_all"], 4))
tab = [(k, v["hit_all"], v["hit_t01"], v["n_t01"]) for k, v in res.items() if not k.startswith("_")]
tab.sort(key=lambda x: -(x[1] or 0))
print(f"{'feature|mode':28s} {'hit_ALL':>8s} {'hit_T01':>8s} {'n_T01':>6s}")
for k, a, b, n in tab:
    print(f"{k:28s} {a:8.4f} {(b if b is not None else float('nan')):8.4f} {n:6d}")
