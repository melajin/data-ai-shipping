# -*- coding: utf-8 -*-
"""Round012 G3 — 현행 "이상항적 점수"가 실제로 무엇을 재고 있는가.
제출 9열은 rfid_id / 사고시각 / 이상항적 점수 / 시각1~3 + 각 시각의 이상항적 점수다.
즉 제출물의 본체는 이상항적 점수이고, 그중 사고시각 한 칸만 정량채점된다.
그래서 이상항적 점수 자체가 무엇에 반응하는지를 먼저 확인한다.
가설: s_gap이 재는 "관측 공백"은 이상이 아니라 입항이고,
      따라서 선박별 최고점(A)이 "출항 시각"에 몰려 있을 것이다.
읽기 전용. 새 모델·제출물 생성 없음.
"""
import json
import numpy as np
import pandas as pd

df = pd.read_parquet("testB/first_results/hourly_scores.parquet").sort_values(["rfid_id", "ts"])
df["gap"] = df.groupby("rfid_id")["ts"].diff()
df["voy_first"] = df["gap"].isna() | (df["gap"] >= 6)

out = {"n_rows": int(len(df)), "n_vessels": int(df.rfid_id.nunique()),
       "voy_first_frac": float(df.voy_first.mean()), "components": {}}
for c in ("s_zone", "s_change", "s_gap", "score"):
    out["components"][c] = dict(
        mean_voy_first=float(df.loc[df.voy_first, c].mean()),
        mean_other=float(df.loc[~df.voy_first, c].mean()),
        delta=float(df.loc[df.voy_first, c].mean() - df.loc[~df.voy_first, c].mean()))

A = df.loc[df.groupby("rfid_id")["score"].idxmax()]
out["A_peak"] = dict(
    n=int(len(A)),
    voy_first_count=int(A.voy_first.sum()), voy_first_frac=float(A.voy_first.mean()),
    enrichment_vs_random=float(A.voy_first.mean() / df.voy_first.mean()),
    mean_s_gap_at_A=float(A.s_gap.mean()),
    A_is_vessel_first_row=int(A.gap.isna().sum()))
thr = float(df.score.quantile(0.99))
top = df[df.score >= thr]
out["global_top1pct"] = dict(threshold=thr, n=int(len(top)), voy_first_frac=float(top.voy_first.mean()))

with open("testB/round_012_20261105/g3_summary.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
