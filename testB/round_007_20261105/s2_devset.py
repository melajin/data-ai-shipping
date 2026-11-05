#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 007 / S2 — 연결 결과를 평가 가능한 dev 라벨셋으로 확정한다.

판단:
  - '전 격자에서 단일'(S1의 grid_stable_single=4건)은 느슨한 조건에서 후보가 폭발하므로
    쓸모없는 기준이다. 대신 **중첩 캐스케이드**를 쓴다: 가장 좁은 조건부터 올라가며
    처음으로 단일 후보가 되는 지점의 선박을 그 사건의 후보 신원으로 삼고,
    더 좁은 조건에서 다른 선박이 단일로 지목됐는지(모순)를 따로 센다.
  - 티어를 나누어 같은 측정을 각 티어에서 반복할 수 있게 한다. 티어별 결과가 비슷하면
    신원 잡음이 결과를 만든 것이 아니다.
  - 음성(미사고) 후보는 느슨한 조건(w6/r20, 어구무시)에서도 어떤 사고의 후보가 아닌 선박으로 둔다.
    사고 목록은 신고된 사건만이므로 이것은 '확정 정상'이 아니라 '사고 근거 없음'이다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
CACHE = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과\outputs\remeasure_20261031")
ACC_XLSX = HERE.parent / "intake/1103_v2/inspection_001/reference_01_26년 1~6월 어선 사고현황(테스트 데이터).xlsx"

# 좁은 -> 넓은 캐스케이드 (어구 제약 항상 적용)
CASCADE = [(0, 2.0), (0, 5.0), (1, 2.0), (1, 5.0), (2, 5.0), (0, 10.0), (1, 10.0), (3, 5.0), (2, 10.0)]
NEG_W, NEG_R = 6, 20.0


def main():
    links = pd.read_csv(HERE / "links_candidates.csv")
    acc = pd.read_excel(ACC_XLSX).reset_index().rename(columns={"index": "acc_id"})
    acc["acc_ts"] = acc["발생일시"].values.astype("datetime64[h]").astype(np.int64)

    recs = []
    for aid, grp in links.groupby("acc_id"):
        g = grp[grp.gear_match]
        chosen, tier, conflict = None, None, False
        for i, (w, r) in enumerate(CASCADE):
            s = g[(g.dt_h <= w) & (g.dist_km <= r)]
            vs = sorted(set(s.rfid_id))
            if len(vs) == 1:
                if chosen is None:
                    chosen, tier = vs[0], i
                elif vs[0] != chosen:
                    conflict = True
        if chosen is None:
            continue
        row = g[g.rfid_id == chosen].iloc[0]
        recs.append({"acc_id": int(aid), "rfid_id": int(chosen), "tier": int(tier),
                     "cascade_cond": str(CASCADE[tier]), "conflict": bool(conflict),
                     "dt_h": float(row.dt_h), "dist_km": float(row.dist_km),
                     "n_cand_base_gear": int(g[(g.dt_h <= 1) & (g.dist_km <= 5)].rfid_id.nunique())})
    dev = pd.DataFrame(recs)
    dev = dev.merge(acc[["acc_id", "acc_ts", "발생일시", "발생유형", "어업면허", "톤수",
                         "사고선박수", "위도(변환)", "경도(변환)"]], on="acc_id", how="left")

    # 한 선박이 여러 사건에 연결되는 경우 확인 (제출은 선박당 시각 1개)
    multi = dev.groupby("rfid_id")["acc_id"].nunique()
    dev["vessel_multi_accident"] = dev["rfid_id"].map(multi) > 1

    # 음성 후보 모집단: 느슨한 조건에서도 어떤 사고의 후보가 아닌 선박
    cand_loose = set(links[(links.dt_h <= NEG_W) & (links.dist_km <= NEG_R)].rfid_id.astype(int))
    vessels = set()
    for m in range(1, 7):
        d = pq.read_table(CACHE / f"rows_train_{m}.parquet", columns=["rfid_id", "key_valid"]).to_pandas()
        d = d[d.key_valid]
        vessels |= set(pd.to_numeric(d.rfid_id, errors="coerce").dropna().astype(np.int64))
    negatives = sorted(vessels - cand_loose)

    dev.to_csv(HERE / "devset_positives.csv", index=False, encoding="utf-8-sig")
    rng = np.random.default_rng(20261105)
    neg_sample = sorted(rng.choice(np.array(negatives), size=min(1500, len(negatives)), replace=False).tolist())
    pd.DataFrame({"rfid_id": neg_sample}).to_csv(HERE / "devset_negative_sample.csv", index=False)

    summary = {
        "vessels_total_train": len(vessels),
        "accidents_total": int(len(acc)),
        "events_with_identified_vessel": int(len(dev)),
        "events_by_tier": {str(CASCADE[t]): int(c) for t, c in dev.tier.value_counts().sort_index().items()},
        "events_with_conflict": int(dev.conflict.sum()),
        "distinct_vessels": int(dev.rfid_id.nunique()),
        "vessels_with_multiple_events": int((multi > 1).sum()),
        "accident_adjacent_vessels_loose": len(cand_loose),
        "negative_pool": len(negatives),
        "negative_sample": len(neg_sample),
        "neg_condition": {"window_h": NEG_W, "radius_km": NEG_R, "gear_filter": False},
        "caveat": ("음성은 '사고 목록 근거 없음'이며 확정 정상이 아니다. "
                   "양성 신원은 시각·좌표·어구만으로 정했고 이상점수를 쓰지 않았다."),
    }
    (HERE / "devset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(dev.groupby("발생유형").size().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    main()
