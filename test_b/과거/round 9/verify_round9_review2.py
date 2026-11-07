"""Round 009 검증·비판 2부 — 2026-11-05
V8  관측행수-점수 상관(r=0.514 주장) 재현 시도: 창 단위 / 선박 단위
V9  n_rows 미매칭 백분위 — 1:1 매칭이 무엇을 제거했는지 정량화
V10 시각(hour-of-day)·월 교란 통제 후 백분위 재검정
"""
import json
import sys
import numpy as np
import pandas as pd
import scipy.stats as st
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_round9_review import (BASE, R8, R9, METRICS, build_vessel, ctrl_mask, pct_rank, log)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUT = {}
CONT = ["len_mean", "bbox_mean", "lin_mean", "score_mean", "score_max",
        "cen_span_m", "net_m", "net_over_path"]


def main():
    pos = pd.read_csv(R8 / "devset_positives.csv")
    cols = ["rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "state", "s_gap", "score"]
    sc = pd.read_parquet(R8 / "dev_hourly_scores.parquet", columns=cols)
    pv = set(pos["rfid_id"].astype(int))
    scp = sc[sc["rfid_id_int"].isin(pv)].copy()
    min_ts, max_ts = int(scp["ts"].min()), int(scp["ts"].max())
    span = max_ts - min_ts + 1
    vw = {int(r): build_vessel(g.sort_values("ts"), span, min_ts) for r, g in scp.groupby("rfid_id_int")}

    # ---------------- V8 상관 재현
    nr, smean, sgap = [], [], []
    for rfid, W in vw.items():
        m = W["n_rows"] > 0
        nr.append(W["n_rows"][m]); smean.append(W["score_mean"][m]); sgap.append(W["sgap_mean"][m])
    nr, smean, sgap = np.concatenate(nr), np.concatenate(smean), np.concatenate(sgap)
    ok = np.isfinite(smean)
    okg = np.isfinite(sgap)
    # 선박 단위: 총 관측행수 vs 선박 최고/평균 점수
    vrow = scp.groupby("rfid_id_int").agg(n_rows_total=("ts", "size"),
                                          score_max=("score", "max"),
                                          score_mean=("score", "mean"),
                                          sgap_mean=("s_gap", "mean")).reset_index()
    # 전체 dev 선박(양성+음성)
    vrow_all = sc.groupby("rfid_id_int").agg(n_rows_total=("ts", "size"),
                                             score_max=("score", "max"),
                                             score_mean=("score", "mean")).reset_index()
    v8 = {
        "report_claim": {"r_rows_vs_score": 0.514, "r_rows_vs_s_gap": 0.830,
                         "source": "task2_report.md 1.3절 — 산출 코드/출력 파일에 없음(run_task2_comparison.py 에 상관계수 계산 코드 전무)"},
        "window_level_positive_vessels": {
            "n_windows": int(ok.sum()),
            "pearson_r_nrows_vs_score_mean": round(float(np.corrcoef(nr[ok], smean[ok])[0, 1]), 4),
            "spearman_r_nrows_vs_score_mean": round(float(st.spearmanr(nr[ok], smean[ok]).statistic), 4),
            "pearson_r_nrows_vs_sgap_mean": round(float(np.corrcoef(nr[okg], sgap[okg])[0, 1]), 4),
        },
        "vessel_level_positive_82": {
            "n": int(len(vrow)),
            "pearson_r_totalrows_vs_score_max": round(float(np.corrcoef(vrow.n_rows_total, vrow.score_max)[0, 1]), 4),
            "pearson_r_totalrows_vs_score_mean": round(float(np.corrcoef(vrow.n_rows_total, vrow.score_mean)[0, 1]), 4),
        },
        "vessel_level_all_dev": {
            "n": int(len(vrow_all)),
            "pearson_r_totalrows_vs_score_max": round(float(np.corrcoef(vrow_all.n_rows_total, vrow_all.score_max)[0, 1]), 4),
            "pearson_r_totalrows_vs_score_mean": round(float(np.corrcoef(vrow_all.n_rows_total, vrow_all.score_mean)[0, 1]), 4),
        },
    }
    OUT["V8_rowcount_score_correlation"] = v8
    log("[V8] " + json.dumps(v8, ensure_ascii=False, indent=1))

    # ---------------- V9 / V10
    rows = []
    for acc in pos.itertuples():
        rfid, t_acc = int(acc.rfid_id), int(acc.acc_ts)
        W = vw[rfid]
        ai = t_acc - min_ts
        pos_ci = np.where(W["center"] == ai)[0]
        if len(pos_ci) == 0:
            continue
        ci = int(pos_ci[0])
        n_acc = int(W["n_rows"][ci])
        acc_centers = [int(a) - min_ts for a in pos.loc[pos.rfid_id == rfid, "acc_ts"].astype(int)]
        rec = dict(acc_id=int(acc.acc_id), rfid_id=rfid, tier=int(acc.tier), n_acc_rows=n_acc,
                   acc_hod=int((t_acc) % 24))

        # V9: n_rows 미매칭 (guard 72h)
        ok_free = ctrl_mask(W, span, acc_centers, 72, n_acc, exact=False)
        idx = np.where(ok_free)[0]
        rec["n_ctrl_free"] = int(len(idx))
        if len(idx):
            for m in ["n_rows", "maxgap", "sgap_mean"] + CONT:
                rec["pctfree_" + m] = pct_rank(W[m][ci], W[m][idx])

        # V10: 동일 hour-of-day ±1h + 동일 n_rows + guard 72h
        hod = (W["center"] + min_ts) % 24
        acc_hod = (ai + min_ts) % 24
        dh = np.minimum(np.abs(hod - acc_hod), 24 - np.abs(hod - acc_hod))
        ok_hod = ctrl_mask(W, span, acc_centers, 72, n_acc, exact=True) & (dh <= 1)
        idx2 = np.where(ok_hod)[0]
        rec["n_ctrl_hod"] = int(len(idx2))
        if len(idx2) >= 15:
            for m in CONT + ["maxgap", "sgap_mean"]:
                rec["pcthod_" + m] = pct_rank(W[m][ci], W[m][idx2])
        rows.append(rec)

    ev = pd.DataFrame(rows)
    ev.to_csv(R9 / "review_v9v10_percentiles.csv", index=False, encoding="utf-8-sig")

    def summarize(prefix, metrics, label, subset=None):
        sub = ev if subset is None else ev.loc[subset]
        d = {"n_events": int(len(sub)), "metrics": {}}
        for m in metrics:
            col = prefix + m
            if col not in sub:
                continue
            x = sub[col].dropna().values
            if len(x) < 10:
                continue
            dev = x - 0.5
            try:
                wp = float(st.wilcoxon(dev).pvalue)
            except ValueError:
                wp = np.nan
            boot = np.random.default_rng(7).choice(x, size=(2000, len(x)), replace=True).mean(1)
            d["metrics"][m] = {"n": int(len(x)), "mean_pct": round(float(x.mean()), 4),
                               "delta": round(float(x.mean() - 0.5), 4),
                               "ci95": [round(float(np.percentile(boot, 2.5) - 0.5), 4),
                                        round(float(np.percentile(boot, 97.5) - 0.5), 4)],
                               "wilcoxon_p": round(wp, 5) if np.isfinite(wp) else None}
        OUT[label] = d
        log(f"[{label}] n={d['n_events']}")
        for m, s in d["metrics"].items():
            log("  %-14s n=%3d d=%+.4f ci[%+.4f,%+.4f] p=%s" % (m, s["n"], s["delta"], s["ci95"][0], s["ci95"][1], s["wilcoxon_p"]))

    summarize("pctfree_", ["n_rows", "maxgap", "sgap_mean"] + CONT, "V9_unmatched_percentile")
    summarize("pcthod_", CONT + ["maxgap", "sgap_mean"], "V10_hourofday_matched_percentile")
    summarize("pcthod_", CONT, "V10_hourofday_matched_Tier01", subset=(ev.tier <= 1))
    OUT["V10_pool_sizes"] = {"median_n_ctrl_hod": float(np.nanmedian(ev.n_ctrl_hod)),
                             "events_with_ge15": int((ev.n_ctrl_hod >= 15).sum()),
                             "acc_hod_distribution": {str(k): int(v) for k, v in ev.acc_hod.value_counts().sort_index().items()}}

    with open(R9 / "review_round9_metrics2.json", "w", encoding="utf-8") as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)
    log("saved review_round9_metrics2.json")


if __name__ == "__main__":
    main()
