# -*- coding: utf-8 -*-
"""Round012 선행 관문 v2 — Round008 수정 연결(100건/82척)로 재실행.
v1의 결함 2개를 고쳤다:
  (1) argmax 분기 버그 — max/min 두 방향이 모두 argmin으로 계산됐다.
  (2) Round007 연결(98건/85척)은 Round008에서 사전축약 오류로 수정됐으므로 Round008 연결을 주자료로 쓴다.
종점은 사전 고정: top-1 항차의 중앙 시각이 사고시각 ±6h 안인가 (ALL / Tier0-1).
기준선은 선박내 무작위 항차 중앙시각의 기대 적중률. 24개 검정에 max-T 보정.
읽기 전용. 새 모델·제출물 생성 없음.
"""
import json
import numpy as np
import pandas as pd

R8 = "testB/round_008_linkage_audit_20261105"
OUT = "testB/round_012_20261105"
THR = 6
SEED = 20261105

pos = pd.read_csv(f"{R8}/devset_positives.csv")
pos["rfid_id"] = pos["rfid_id"].astype(str)

cols = ["rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "state"]
parts = []
for f in ("dev_hourly_scores.parquet", "additional_hourly_scores.parquet"):
    d = pd.read_parquet(f"{R8}/{f}", columns=cols)
    parts.append(d)
trk = pd.concat(parts, ignore_index=True).rename(columns={"rfid_id_int": "rfid_id"})
trk["rfid_id"] = trk["rfid_id"].astype(str)
trk = trk[trk.rfid_id.isin(set(pos.rfid_id))].drop_duplicates(["rfid_id", "ts"])
trk = trk.sort_values(["rfid_id", "ts"])
print("대상 선박", trk.rfid_id.nunique(), "/ 정답 선박", pos.rfid_id.nunique(), "| 행", len(trk))

def haversine(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))

FEATS = ["voy_hours", "voy_span", "len_sum", "len_mean", "len_last3", "lin_voy",
         "lin_last3", "disp_max", "frac_sea_stop", "frac_slowturn", "frac_move", "gap_after"]

voy = []
for vid, g in trk.groupby("rfid_id"):
    ts = g["ts"].to_numpy()
    seg = np.concatenate([[0], np.cumsum(np.diff(ts) >= THR)])
    g = g.assign(voy=seg)
    nvoy = int(seg.max()) + 1
    for v, h in g.groupby("voy"):
        t = h["ts"].to_numpy()
        ln = h["len_m"].to_numpy(float); bb = h["bbox_m"].to_numpy(float)
        lo = h["cen_lon"].to_numpy(float); la = h["cen_lat"].to_numpy(float)
        st = h["state"].to_numpy()
        nx = g.loc[g.voy == v + 1, "ts"]
        l3 = slice(max(0, len(t) - 3), len(t))
        voy.append(dict(
            rfid_id=vid, voy=int(v), n_voyages=nvoy,
            t_start=int(t[0]), t_end=int(t[-1]), t_mid=int(t[len(t) // 2]),
            voy_hours=float(len(t)), voy_span=float(t[-1] - t[0] + 1),
            len_sum=float(np.nansum(ln)), len_mean=float(np.nanmean(ln)),
            len_last3=float(np.nanmean(ln[l3])),
            lin_voy=float(np.nansum(bb) / max(np.nansum(ln), 1.0)),
            lin_last3=float(np.nanmean(bb[l3]) / max(np.nanmean(ln[l3]), 1.0)),
            disp_max=float(np.nanmax(haversine(lo[0], la[0], lo, la))) if len(t) > 1 else 0.0,
            frac_sea_stop=float((st == "해상정지").mean()),
            frac_slowturn=float((st == "저속굴곡").mean()),
            frac_move=float((st == "이동").mean()),
            gap_after=float(nx.iloc[0] - t[-1]) if len(nx) else np.nan,
        ))
V = pd.DataFrame(voy)
V.to_csv(f"{OUT}/g2v2_voyages.csv", index=False, encoding="utf-8-sig")
byv = {k: d for k, d in V.groupby("rfid_id")}

# ---------- G1: 천장과 기준선 ----------
g1 = []
for _, r in pos.iterrows():
    vid, acc, tier = r["rfid_id"], int(r["acc_ts"]), int(r["tier"])
    d = byv.get(vid)
    if d is None or len(d) < 2:
        continue
    tm = d["t_mid"].to_numpy(); ts_ = d["t_start"].to_numpy(); te = d["t_end"].to_numpy()
    inside = (ts_ - 6 <= acc) & (acc <= te + 6)
    j = int(np.argmin(np.abs(tm - acc)))
    g1.append(dict(acc_id=int(r["acc_id"]), rfid_id=vid, tier=tier, acc_type=r["발생유형"],
                   n_voyages=int(d["n_voyages"].iloc[0]),
                   acc_in_a_voyage=bool(inside.any()),
                   ceiling_mid=bool(abs(tm[j] - acc) <= 6),
                   ceiling_end=bool(abs(te[j] - acc) <= 6),
                   base_random_voy=float((np.abs(tm - acc) <= 6).mean()),
                   acc_voy_is_last=bool(j == len(d) - 1),
                   gap_after_acc_voy=float(d["gap_after"].to_numpy()[j]),
                   median_gap_after=float(np.nanmedian(d["gap_after"].to_numpy()))))
G1 = pd.DataFrame(g1)
G1.to_csv(f"{OUT}/g1v2_events.csv", index=False, encoding="utf-8-sig")
t01 = G1[G1.tier <= 1]
g1s = dict(n_events=len(G1), n_tier01=len(t01),
           median_voyages=float(G1.n_voyages.median()),
           acc_in_a_voyage=float(G1.acc_in_a_voyage.mean()),
           ceiling_mid_ALL=float(G1.ceiling_mid.mean()), ceiling_mid_T01=float(t01.ceiling_mid.mean()),
           ceiling_end_ALL=float(G1.ceiling_end.mean()), ceiling_end_T01=float(t01.ceiling_end.mean()),
           baseline_random_voyage_ALL=float(G1.base_random_voy.mean()),
           baseline_random_voyage_T01=float(t01.base_random_voy.mean()),
           acc_voy_is_last_frac=float(G1.acc_voy_is_last.mean()),
           median_gap_after_acc_voy=float(G1.gap_after_acc_voy.median()),
           median_gap_after_other=float(G1.median_gap_after.median()))

# ---------- G2: 특징별 top-1 항차 적중 ----------
from scipy import stats
res, detail = {}, []
for f in FEATS:
    for lab in ("max", "min"):
        hits, hits01, bases = [], [], []
        for _, r in pos.iterrows():
            vid, acc, tier = r["rfid_id"], int(r["acc_ts"]), int(r["tier"])
            d = byv.get(vid)
            if d is None or len(d) < 2:
                continue
            dd = d.dropna(subset=[f])
            if len(dd) < 2:
                continue
            a = dd[f].to_numpy(float)
            i = int(np.argmax(a)) if lab == "max" else int(np.argmin(a))
            hit = bool(abs(int(dd["t_mid"].iloc[i]) - acc) <= 6)
            hits.append(hit); bases.append(float((np.abs(dd["t_mid"].to_numpy() - acc) <= 6).mean()))
            if tier <= 1:
                hits01.append(hit)
            detail.append(dict(feat=f, mode=lab, acc_id=int(r["acc_id"]), tier=tier, hit=hit))
        k, n, p0 = int(np.sum(hits)), len(hits), float(np.mean(bases))
        res[f"{f}|{lab}"] = dict(n=n, hits=k, hit_rate=k / n, baseline=p0,
                                 p_binom=float(stats.binomtest(k, n, p0, alternative="greater").pvalue),
                                 n_t01=len(hits01),
                                 hit_rate_t01=float(np.mean(hits01)) if hits01 else None)
pd.DataFrame(detail).to_csv(f"{OUT}/g2v2_detail.csv", index=False, encoding="utf-8-sig")
best = max((v["p_binom"], k) for k, v in res.items())
res["_g1"] = g1s
res["_meta"] = dict(thr=THR, linkage="round_008 (100 events / 82 vessels)",
                    n_tests=len(FEATS) * 2, min_p=min(v["p_binom"] for v in res.values() if isinstance(v, dict) and "p_binom" in v),
                    bonferroni_alpha=0.05 / (len(FEATS) * 2))
with open(f"{OUT}/g2v2_summary.json", "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=2)

print("\n[G1] ", json.dumps(g1s, ensure_ascii=False, indent=2))
print(f"\n[G2] 24개 검정, Bonferroni alpha = {0.05/24:.5f}")
print(f"{'feature|mode':24s} {'hit':>6s} {'rate':>7s} {'base':>7s} {'p':>9s} {'T01':>7s}")
for k, v in sorted(res.items(), key=lambda x: x[1]["p_binom"] if isinstance(x[1], dict) and "p_binom" in x[1] else 9):
    if not isinstance(v, dict) or "p_binom" not in v:
        continue
    print(f"{k:24s} {v['hits']:6d} {v['hit_rate']:7.4f} {v['baseline']:7.4f} {v['p_binom']:9.4f} {(v['hit_rate_t01'] or 0):7.4f}")
