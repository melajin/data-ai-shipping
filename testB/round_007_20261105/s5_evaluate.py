#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 007 / S5 — 시각 선택 규칙과 사고 판정 임계값을 dev(2026)에서 실측 비교한다.

측정 설계상 중요한 점:
  1. **천장(oracle)을 먼저 센다.** 사고시각 ±6시간 안에 관측행이 아예 없는 선박은 어떤 규칙도
     맞힐 수 없다. 이 분모를 빼놓고 적중률을 말하면 규칙 비교가 왜곡된다.
  2. **무작위 기준선을 센다.** 선박의 관측행 중 ±6시간 안에 드는 비율이 곧 '아무 행이나
     찍었을 때'의 기대 적중률이다. 규칙은 이 값을 넘어야 의미가 있다.
  3. **공백 뒤 관측(reappearance)과 공백 앞 관측(disappearance)을 따로 둔다.** 현재 s_gap은
     공백 '뒤' 행에 점수를 붙이지만, 사고 발생시각은 송신이 끊기기 직전에 더 가깝다.
  4. 임계값은 식별된 양성 85척과 사고 목록과 무관한 음성 표본으로만 재고, 사고 인접하지만
     신원 미확정인 1,245척 풀은 보정에서 제외하고 따로 보고한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TOL = 6  # 공식 규칙: 6시간 초과는 0점


# --------------------------------------------------------------------------- 규칙들
def rule_times(g: pd.DataFrame) -> dict[str, float]:
    """한 선박의 시간순 점수표에서 규칙별 예측 시각(ts, 정수시간)을 만든다."""
    ts = g["ts"].to_numpy()
    sc = g["score"].to_numpy()
    out: dict[str, float] = {}
    fin = np.isfinite(sc)
    if not fin.any():
        return out
    # 1) 전체기간 평균점수 최고점 (현재 A)
    out["A_peak"] = ts[fin][np.argmax(sc[fin])]
    # 2) 성분별 최고점
    for c, name in (("s_zone", "A_zone"), ("s_change", "A_change"), ("s_gap", "A_gap")):
        v = g[c].to_numpy()
        m = np.isfinite(v)
        if m.any():
            out[name] = ts[m][np.argmax(v[m])]
    # 3) 공백 앞 행 — s_gap 최고점 행의 '직전 관측' 시각 (사라진 시점)
    v = g["s_gap"].to_numpy()
    m = np.isfinite(v)
    if m.any():
        i = int(np.flatnonzero(m)[np.argmax(v[m])])
        out["A_gap_prev"] = ts[i - 1] if i > 0 else ts[i]
    # 4) 가장 긴 관측 공백의 앞/뒤
    if len(ts) > 1:
        d = np.diff(ts)
        j = int(np.argmax(d))
        out["maxgap_prev"] = ts[j]
        out["maxgap_next"] = ts[j + 1]
    # 5) 이상 구간 시작 — A_peak가 속한 '임계 초과 연속 구간'의 첫 시각
    for q in (0.90, 0.95, 0.99):
        thr = np.nanquantile(sc[fin], q)
        above = fin & (sc >= thr)
        pk = int(np.flatnonzero(fin)[np.argmax(sc[fin])])
        i = pk
        while i - 1 >= 0 and above[i - 1] and (ts[i] - ts[i - 1]) <= 3:
            i -= 1
        out[f"onset_q{int(q*100)}"] = ts[i]
    # 6) 점수 급상승 지점 — 직전 12행 중앙값 대비 증가량 최대
    if fin.sum() >= 13:
        sf, tf = sc[fin], ts[fin]
        rise = np.full(len(sf), -np.inf)
        for i in range(12, len(sf)):
            rise[i] = sf[i] - np.median(sf[i - 12:i])
        out["rise12"] = tf[int(np.argmax(rise))]
    # 7) 해상정지(항구·정박지에서 먼 정지) 첫 발생 / 최장 연속 구간 시작
    st = g["state"].to_numpy().astype(str)
    sea = st == "해상정지"
    if sea.any():
        out["sea_stop_first"] = ts[np.flatnonzero(sea)[0]]
        # 최장 연속 해상정지 런의 시작
        best_len, best_start, cur_len, cur_start = 0, None, 0, None
        for i in range(len(sea)):
            if sea[i]:
                if cur_len == 0:
                    cur_start = i
                cur_len += 1
                if cur_len > best_len:
                    best_len, best_start = cur_len, cur_start
            else:
                cur_len = 0
        out["sea_stop_longest"] = ts[best_start]
    # 8) 항적 마지막 관측 (침몰·송신중단 가정)
    out["track_end"] = ts[-1]
    return out


def main():
    sc = pd.read_parquet(HERE / "dev_hourly_scores.parquet")
    pos = pd.read_csv(HERE / "devset_positives.csv")
    neg = pd.read_csv(HERE / "devset_negative_sample.csv")

    pos_vessels = sorted(set(pos.rfid_id.astype(int)))
    truth = pos.groupby("rfid_id")["acc_ts"].apply(lambda s: sorted(int(x) for x in s)).to_dict()

    groups = {rid: g.sort_values(["ts", "source_ordinal"], kind="stable")
              for rid, g in sc.groupby("rfid_id_int", sort=False)}

    # ---------------- 천장과 무작위 기준선
    diag = []
    for rid in pos_vessels:
        g = groups.get(rid)
        if g is None:
            diag.append({"rfid_id": rid, "n_rows": 0, "has_row_within_tol": False,
                         "random_hit_prob": 0.0, "min_abs_err_any_row": None})
            continue
        ts = g["ts"].to_numpy()
        errs = np.min(np.abs(ts[:, None] - np.array(truth[rid])[None, :]), axis=1)
        diag.append({"rfid_id": rid, "n_rows": len(g),
                     "has_row_within_tol": bool((errs <= TOL).any()),
                     "random_hit_prob": float((errs <= TOL).mean()),
                     "min_abs_err_any_row": int(errs.min()),
                     "n_events": len(truth[rid])})
    diag = pd.DataFrame(diag)

    # ---------------- 규칙별 예측과 오차
    recs = []
    for rid in pos_vessels:
        g = groups.get(rid)
        if g is None:
            continue
        rt = rule_times(g)
        for rule, t in rt.items():
            err = min(abs(int(t) - a) for a in truth[rid])
            recs.append({"rfid_id": rid, "rule": rule, "pred_ts": int(t), "abs_err_h": int(err)})
    rules = pd.DataFrame(recs)

    oracle_ok = set(diag[diag.has_row_within_tol].rfid_id)
    tbl = []
    for rule, g in rules.groupby("rule"):
        g_all = g
        g_or = g[g.rfid_id.isin(oracle_ok)]
        tbl.append({
            "rule": rule,
            "n_vessels": int(len(g_all)),
            "hit<=1h": round(float((g_all.abs_err_h <= 1).mean()), 4),
            "hit<=3h": round(float((g_all.abs_err_h <= 3).mean()), 4),
            "hit<=6h": round(float((g_all.abs_err_h <= 6).mean()), 4),
            "hit<=24h": round(float((g_all.abs_err_h <= 24).mean()), 4),
            "median_abs_err_h": float(g_all.abs_err_h.median()),
            "n_oracle_vessels": int(len(g_or)),
            "hit<=6h_within_oracle": round(float((g_or.abs_err_h <= 6).mean()), 4) if len(g_or) else None,
        })
    tbl = pd.DataFrame(tbl).sort_values("hit<=6h", ascending=False)

    # 조합 규칙: 성분/물리 후보 중 '어느 하나라도' 6시간 안에 든 비율 (상한 진단)
    any_hit = rules.groupby("rfid_id").abs_err_h.min()
    combo = {
        "any_rule_hit<=6h": round(float((any_hit <= 6).mean()), 4),
        "oracle_has_row_within_6h": round(float(diag.has_row_within_tol.mean()), 4),
        "random_row_hit<=6h_expected": round(float(diag.random_hit_prob.mean()), 4),
        "median_rows_per_positive_vessel": float(diag.n_rows.median()),
    }

    # ---------------- 임계값: 양성 85척 vs 음성 표본
    def peak(rid):
        g = groups.get(rid)
        if g is None or not np.isfinite(g["score"].to_numpy()).any():
            return np.nan
        return float(np.nanmax(g["score"].to_numpy()))

    pk_pos = pd.Series({r: peak(r) for r in pos_vessels}).dropna()
    neg_vessels = sorted(set(neg.rfid_id.astype(int)) - set(pos_vessels))
    pk_neg = pd.Series({r: peak(r) for r in neg_vessels}).dropna()

    # AUC (Mann-Whitney)
    both = np.concatenate([pk_pos.to_numpy(), pk_neg.to_numpy()])
    lab = np.concatenate([np.ones(len(pk_pos)), np.zeros(len(pk_neg))])
    rank = pd.Series(both).rank().to_numpy()
    auc = float((rank[lab == 1].sum() - len(pk_pos) * (len(pk_pos) + 1) / 2) / (len(pk_pos) * len(pk_neg)))

    # 시간오차를 반영한 임계값 곡선 (A_peak 기준, 모집단 비율로 FP 환산)
    a_err = rules[rules.rule == "A_peak"].set_index("rfid_id").abs_err_h
    pool_neg, pool_pos_known = 6127, len(pk_pos)
    curve = []
    for thr in np.round(np.arange(0.30, 1.001, 0.02), 3):
        tp = int(sum(1 for r in pk_pos.index if pk_pos[r] >= thr and a_err.get(r, 999) <= TOL))
        pred_pos_true = int((pk_pos >= thr).sum())
        fp_timing = pred_pos_true - tp
        fp_neg_rate = float((pk_neg >= thr).mean())
        fp_neg_scaled = fp_neg_rate * pool_neg
        fn = pool_pos_known - tp
        prec_dev = tp / max(1, tp + fp_timing + (pk_neg >= thr).sum())
        rec_dev = tp / max(1, pool_pos_known)
        curve.append({"thr": float(thr), "tp_pos_within6h": tp,
                      "pos_predicted": pred_pos_true, "pos_pred_wrong_time": fp_timing,
                      "neg_fp_rate": round(fp_neg_rate, 4),
                      "neg_fp_scaled_to_pool6127": round(fp_neg_scaled, 1),
                      "precision_devmix": round(prec_dev, 4), "recall_known_pos": round(rec_dev, 4),
                      "f1_devmix": round(2 * prec_dev * rec_dev / max(1e-9, prec_dev + rec_dev), 4)})

    out = {
        "rule_comparison": tbl.to_dict("records"),
        "combo": combo,
        "threshold": {
            "n_pos": int(len(pk_pos)), "n_neg": int(len(pk_neg)),
            "peak_pos_describe": pk_pos.describe().round(4).to_dict(),
            "peak_neg_describe": pk_neg.describe().round(4).to_dict(),
            "auc_peak_score": round(auc, 4),
            "curve_note": ("precision_devmix는 dev 혼합비(양성85 vs 음성표본1500)에서 계산한 값이며 "
                           "Test B 100척의 실제 사고 비율이 다르면 그대로 옮길 수 없다."),
            "curve": curve,
        },
        "caveats": [
            "양성 신원은 시각·좌표·어구로 정한 단일 후보이며 확정 신원이 아니다.",
            "음성은 사고 목록에 근거가 없는 선박이며 확정 정상이 아니다.",
            "dev는 2026, 제출 대상은 2025다. 규칙과 임계값은 여기서 고정한 뒤 2025에 적용한다.",
        ],
    }
    (HERE / "evaluation_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    rules.to_csv(HERE / "rule_predictions.csv", index=False, encoding="utf-8-sig")
    diag.to_csv(HERE / "positive_diagnostics.csv", index=False, encoding="utf-8-sig")

    print(tbl.to_string(index=False))
    print()
    print(json.dumps(combo, ensure_ascii=False, indent=2))
    print()
    print("AUC(peak score, pos vs neg) =", round(auc, 4))
    print(pd.DataFrame(curve).to_string(index=False))


if __name__ == "__main__":
    main()
