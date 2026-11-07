# -*- coding: utf-8 -*-
"""Round012 선행 관문 G1 — 항차(voyage) 단위 국소화의 천장 측정.
목적: 기존 라운드가 전부 "선박 전체 관측행 중 1시각"을 고르는 문제로 풀었다.
      관측이 항차 단위로 뭉쳐 있다면 문제는 "어느 항차인가"로 축소된다.
      이 스크립트는 그 축소가 실제로 얼마나 문제를 쉽게 만드는지를 dev 정답으로 실측한다.
읽기 전용. 새 모델·제출물 생성 없음.
"""
import json, sys
import numpy as np
import pandas as pd

ROOT = "testB/round_007_20261105"
OUT = "testB/round_012_20261105"

pos = pd.read_csv(f"{ROOT}/devset_positives.csv")
trk = pd.read_parquet(f"{ROOT}/dev_hourly_scores.parquet", columns=["rfid_id_int", "ts"])
trk = trk.rename(columns={"rfid_id_int": "rfid_id"}); trk["rfid_id"] = trk["rfid_id"].astype(str)
pos["rfid_id"] = pos["rfid_id"].astype(str)
trk = trk.sort_values(["rfid_id", "ts"])
by = {k: v["ts"].to_numpy() for k, v in trk.groupby("rfid_id")}

def segment(ts, thr):
    """gap >= thr 시간을 경계로 항차 분할. 반환: 각 행의 항차 index."""
    d = np.diff(ts)
    return np.concatenate([[0], np.cumsum(d >= thr)])

rows = []
for thr in (6, 12, 24, 48):
    for _, r in pos.iterrows():
        vid, acc = r["rfid_id"], int(r["acc_ts"])
        ts = by.get(vid)
        if ts is None or len(ts) == 0:
            continue
        seg = segment(ts, thr)
        nvoy = int(seg.max()) + 1
        near = np.abs(ts - acc) <= 6
        n_near = int(near.sum())
        # 사고 ±6h 안의 행이 속한 항차 (여러 개면 가장 가까운 행 기준)
        if n_near:
            j = int(np.argmin(np.abs(ts - acc)))
            v = int(seg[j])
            mask = seg == v
            vts = ts[mask]
            v_start, v_end = int(vts[0]), int(vts[-1])
            v_hours = int(len(vts))
            v_span = v_end - v_start + 1
            # 그 항차만 알고 있을 때 고를 수 있는 세 가지 보고 시각
            hit_start = abs(v_start - acc) <= 6
            hit_end = abs(v_end - acc) <= 6
            hit_mid = abs(int(vts[len(vts) // 2]) - acc) <= 6
            # 항차 내 무작위 행의 적중 기대율
            p_in_voy = float(np.abs(vts - acc).__le__(6).mean())
            is_last = (v == nvoy - 1)
            # 사고 항차 직후 공백 길이 vs 선박의 공백 중앙값
            gaps = np.diff(ts)
            gaps_big = gaps[gaps >= thr]
            after = np.nan
            if not is_last:
                nxt = ts[seg == v + 1]
                after = int(nxt[0] - v_end)
        else:
            v = v_start = v_end = v_hours = v_span = -1
            hit_start = hit_end = hit_mid = False
            p_in_voy = np.nan
            is_last = False
            after = np.nan
            gaps = np.diff(ts)
            gaps_big = gaps[gaps >= thr]
        rows.append(dict(
            thr=thr, acc_id=int(r["acc_id"]), rfid_id=vid, tier=int(r["tier"]),
            acc_type=r["발생유형"], n_rows=len(ts), n_voyages=nvoy,
            n_near6=n_near, base_hit_row=n_near / len(ts),
            base_hit_voyage=1.0 / nvoy,
            voy_hours=v_hours, voy_span=v_span,
            hit_voy_start=bool(hit_start), hit_voy_end=bool(hit_end), hit_voy_mid=bool(hit_mid),
            p_hit_in_voyage=p_in_voy, acc_voy_is_last=bool(is_last),
            gap_after_acc_voy=after,
            median_big_gap=float(np.median(gaps_big)) if len(gaps_big) else np.nan,
        ))

df = pd.DataFrame(rows)
df.to_csv(f"{OUT}/g1_voyage_events.csv", index=False, encoding="utf-8-sig")

summ = {}
for thr, g in df.groupby("thr"):
    ok = g[g.n_near6 > 0]
    t01 = ok[ok.tier <= 1]
    summ[str(thr)] = dict(
        n_events=int(len(g)), n_events_with_row_in_6h=int(len(ok)),
        median_n_rows=float(g.n_rows.median()),
        median_n_voyages=float(g.n_voyages.median()),
        median_voy_hours=float(ok.voy_hours.median()),
        baseline_random_row_hit=float(g.base_hit_row.mean()),
        baseline_random_voyage_hit=float(g.base_hit_voyage.mean()),
        # 천장: 사고 항차를 100% 맞혔다고 가정할 때의 ±6h 적중률
        ceiling_voy_end=float(ok.hit_voy_end.mean()),
        ceiling_voy_mid=float(ok.hit_voy_mid.mean()),
        ceiling_voy_start=float(ok.hit_voy_start.mean()),
        ceiling_random_row_in_voy=float(ok.p_hit_in_voyage.mean()),
        tier01_n=int(len(t01)),
        tier01_ceiling_voy_end=float(t01.hit_voy_end.mean()) if len(t01) else None,
        tier01_ceiling_voy_mid=float(t01.hit_voy_mid.mean()) if len(t01) else None,
        tier01_ceiling_random_row_in_voy=float(t01.p_hit_in_voyage.mean()) if len(t01) else None,
        acc_voy_is_last_frac=float(ok.acc_voy_is_last.mean()),
        median_gap_after_acc_voy=float(ok.gap_after_acc_voy.median()),
        median_vessel_big_gap=float(ok.median_big_gap.median()),
    )
with open(f"{OUT}/g1_summary.json", "w", encoding="utf-8") as f:
    json.dump(summ, f, ensure_ascii=False, indent=2)
print(json.dumps(summ, ensure_ascii=False, indent=2))
