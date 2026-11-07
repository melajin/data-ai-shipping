"""Round 009 검증·비판 3부 — 민감도 2026-11-05
V11 lin_mean(Tier0-1) 유일 생존 신호의 민감도: hour-of-day 창(±0/±1/±2/±3), n_rows 매칭 유무, 월 통제
V12 영(0) 과다 지표(sea_frac/maxgap)의 백분위 p-값이 동률(tie) 인공물임을 확인
V13 r(rows, s_gap)=0.830 주장 선박 단위 재현 시도
"""
import json
import sys
import numpy as np
import pandas as pd
import scipy.stats as st
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify_round9_review import R8, R9, build_vessel, ctrl_mask, pct_rank, log

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUT = {}


def one_sample(x):
    x = np.asarray([v for v in x if np.isfinite(v)])
    if len(x) < 10:
        return None
    dev = x - 0.5
    try:
        wp = float(st.wilcoxon(dev).pvalue)
    except ValueError:
        wp = np.nan
    boot = np.random.default_rng(11).choice(x, size=(3000, len(x)), replace=True).mean(1)
    return {"n": int(len(x)), "delta": round(float(x.mean() - 0.5), 4),
            "ci95": [round(float(np.percentile(boot, 2.5) - 0.5), 4),
                     round(float(np.percentile(boot, 97.5) - 0.5), 4)],
            "wilcoxon_p": round(wp, 5) if np.isfinite(wp) else None}


def main():
    pos = pd.read_csv(R8 / "devset_positives.csv")
    cols = ["rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "state", "s_gap", "score"]
    sc = pd.read_parquet(R8 / "dev_hourly_scores.parquet", columns=cols)
    pv = set(pos["rfid_id"].astype(int))
    scp = sc[sc["rfid_id_int"].isin(pv)].copy()
    min_ts = int(scp["ts"].min())
    span = int(scp["ts"].max()) - min_ts + 1
    vw = {int(r): build_vessel(g.sort_values("ts"), span, min_ts) for r, g in scp.groupby("rfid_id_int")}

    # ---------------- V11 민감도
    grid = {}
    for hw in [0, 1, 2, 3, 24]:            # 24 = hour-of-day 무통제
        for exact in [True, False]:
            key = f"hod+-{hw}h/nrows_{'matched' if exact else 'free'}"
            vals = {"lin_mean": [], "score_mean": [], "net_m": [], "len_mean": []}
            vals_t01 = {k: [] for k in vals}
            pool_sizes = []
            for acc in pos.itertuples():
                rfid, t_acc = int(acc.rfid_id), int(acc.acc_ts)
                W = vw[rfid]
                ai = t_acc - min_ts
                ci = np.where(W["center"] == ai)[0]
                if len(ci) == 0:
                    continue
                ci = int(ci[0])
                n_acc = int(W["n_rows"][ci])
                acc_centers = [int(a) - min_ts for a in pos.loc[pos.rfid_id == rfid, "acc_ts"].astype(int)]
                ok = ctrl_mask(W, span, acc_centers, 72, n_acc, exact=exact)
                if hw < 24:
                    hod = (W["center"] + min_ts) % 24
                    ah = (ai + min_ts) % 24
                    dh = np.minimum(np.abs(hod - ah), 24 - np.abs(hod - ah))
                    ok = ok & (dh <= hw)
                idx = np.where(ok)[0]
                pool_sizes.append(len(idx))
                if len(idx) < 15:
                    continue
                for m in vals:
                    p = pct_rank(W[m][ci], W[m][idx])
                    vals[m].append(p)
                    if int(acc.tier) <= 1:
                        vals_t01[m].append(p)
            grid[key] = {"median_pool": float(np.median(pool_sizes)),
                         "ALL": {m: one_sample(v) for m, v in vals.items()},
                         "Tier0_1": {m: one_sample(v) for m, v in vals_t01.items()}}
    OUT["V11_sensitivity"] = grid
    for k, v in grid.items():
        log(f"[V11] {k} pool_med={v['median_pool']:.0f}")
        for strat in ["ALL", "Tier0_1"]:
            for m, s in v[strat].items():
                if s:
                    log("   %-8s %-11s n=%3d d=%+.4f ci[%+.4f,%+.4f] p=%s"
                        % (strat, m, s["n"], s["delta"], s["ci95"][0], s["ci95"][1], s["wilcoxon_p"]))

    # ---------------- V12 동률 인공물
    ev = pd.read_csv(R9 / "review_v4_event_percentiles.csv")
    v12 = {}
    for m in ["sea_frac", "anch_frac", "maxgap", "stop_frac"]:
        acc_col, pct_col = "acc_" + m, f"pct_{m}_g72"
        if acc_col not in ev or pct_col not in ev:
            continue
        zero_acc = float((ev[acc_col] == 0).mean())
        p = ev[pct_col].dropna()
        v12[m] = {"frac_acc_value_zero": round(zero_acc, 4),
                  "frac_pct_below_0.5": round(float((p < 0.5).mean()), 4),
                  "frac_pct_exactly_0.5": round(float((p == 0.5).mean()), 4),
                  "unique_pct_values": int(p.nunique()),
                  "note": "값이 0에 몰린 지표는 중간순위(mid-rank) 백분위가 기계적으로 0.5 미만이 되어 Wilcoxon p가 인공적으로 작아진다"}
    OUT["V12_tie_artifact"] = v12
    log("[V12] " + json.dumps(v12, ensure_ascii=False, indent=1))

    # ---------------- V13 s_gap 상관
    vr = scp.groupby("rfid_id_int").agg(n=("ts", "size"), sgap=("s_gap", "mean"),
                                        sgap_max=("s_gap", "max"), score_max=("score", "max")).dropna()
    vr_all = sc.groupby("rfid_id_int").agg(n=("ts", "size"), sgap=("s_gap", "mean")).dropna()
    rowlvl = scp[["s_gap", "score"]].dropna()
    OUT["V13_sgap_correlation"] = {
        "report_claim_r_rows_vs_sgap": 0.830,
        "vessel_level_pos82_r_totalrows_vs_mean_sgap": round(float(np.corrcoef(vr.n, vr.sgap)[0, 1]), 4),
        "vessel_level_alldev_r_totalrows_vs_mean_sgap": round(float(np.corrcoef(vr_all.n, vr_all.sgap)[0, 1]), 4),
        "row_level_r_sgap_vs_score": round(float(np.corrcoef(rowlvl.s_gap, rowlvl.score)[0, 1]), 4),
    }
    log("[V13] " + json.dumps(OUT["V13_sgap_correlation"], ensure_ascii=False, indent=1))

    with open(R9 / "review_round9_metrics3.json", "w", encoding="utf-8") as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)
    log("saved review_round9_metrics3.json")


if __name__ == "__main__":
    main()
