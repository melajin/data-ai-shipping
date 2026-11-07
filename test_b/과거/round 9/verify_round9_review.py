"""Round 009 검증·비판 (Review) — 2026-11-05
Round 009의 Task1/Task2 결론을 실측으로 재검정한다.
V1 Task1 '충돌 0%'의 탐지가능성(detectability) 감사 + 식별 마진
V2 n_rows / missing_hours 완전 공선성 확인
V3 대조창 근접 편향 및 사고 여파 오염 측정
V4 분포 기반(백분위) 재검정 — 1회 추출 대조창을 전수 대조창 분포로 교체
V5 R009 설계의 검정력/최소검출효과(MDE)
V6 이진 상태지표에 Wilcoxon 대신 McNemar
V7 점수 역전 사례 재현
"""
import json
import sys
import numpy as np
import pandas as pd
import scipy.stats as st
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\testB")
R8 = BASE / "round_008_linkage_audit_20261105"
R9 = BASE / "round 9"

ST_FISH, ST_MOVE = "\uc800\uc18d\uad74\uace1", "\uc774\ub3d9"
ST_ANCH, ST_SEA, ST_COAST = "\uc815\ubc15\uc815\uc9c0", "\ud574\uc0c1\uc815\uc9c0", "\uc5f0\uc548\uc815\uc9c0"
ACTIVE = {ST_FISH, ST_MOVE}
STOPPED = {ST_ANCH, ST_SEA, ST_COAST}

CASCADE = [(0, 2.0), (0, 5.0), (1, 2.0), (1, 5.0), (2, 5.0), (0, 10.0), (1, 10.0), (3, 5.0), (2, 10.0)]
OUT = {}


def log(m):
    print(m, flush=True)


# ---------------------------------------------------------------- V1
def v1_task1_conflict_detectability():
    obs = pd.read_csv(R8 / "links_observations.csv")
    audit = pd.read_csv(R9 / "task1_linkage_audit_167.csv")
    linked = audit[audit["status"].isin(["LINKED_CLEAN", "LINKED_CONFLICT"])].copy()

    recs = []
    for aid, g in obs.groupby("acc_id"):
        gm = g[g["gear_match"]]
        singles = {}
        for i, (w, r) in enumerate(CASCADE):
            sel = (gm.loc[(gm["dt_h"] <= w) & (gm["dist_km"] <= r)]
                     .sort_values(["rfid_id", "dist_km", "dt_h", "row_ts"], kind="stable")
                     .drop_duplicates("rfid_id"))
            vids = sorted(sel["rfid_id"].astype(int).unique())
            singles[i] = vids[0] if len(vids) == 1 else None
        chosen_tier = next((i for i in range(9) if singles[i] is not None), None)
        if chosen_tier is None:
            continue
        chosen = singles[chosen_tier]
        later = [i for i in range(chosen_tier + 1, 9) if singles[i] is not None]
        conflict = any(singles[i] != chosen for i in later)
        wide = (gm.loc[(gm["dt_h"] <= 6) & (gm["dist_km"] <= 20.0)]
                  .sort_values(["rfid_id", "dist_km"], kind="stable")
                  .drop_duplicates("rfid_id").sort_values("dist_km"))
        n_wide = len(wide)
        d_chosen = float(wide.loc[wide["rfid_id"] == chosen, "dist_km"].min()) if (wide["rfid_id"] == chosen).any() else np.nan
        others = wide.loc[wide["rfid_id"] != chosen, "dist_km"]
        d_next = float(others.min()) if len(others) else np.nan
        margin = (d_next - d_chosen) if (np.isfinite(d_next) and np.isfinite(d_chosen)) else np.nan
        recs.append(dict(acc_id=int(aid), chosen=chosen, chosen_tier=chosen_tier,
                         n_single_later=len(later), conflict_opportunity=len(later) > 0,
                         conflict=conflict, n_wide_cand=n_wide,
                         d_chosen_km=d_chosen, d_next_km=d_next, margin_km=margin))
    df = pd.DataFrame(recs).merge(linked[["acc_id", "status", "tier"]], on="acc_id", how="inner")
    df["stratum"] = np.where(df.chosen_tier <= 1, "Narrow(T0-1)",
                             np.where(df.chosen_tier <= 4, "Medium(T2-4)", "Broad(T5-8)"))
    df.to_csv(R9 / "review_v1_conflict_detectability.csv", index=False, encoding="utf-8-sig")

    res = {"n_linked_recomputed": int(len(df)),
           "tier_agrees_with_r009": int((df["chosen_tier"] == df["tier"]).sum()),
           "conflict_agrees_with_r009": int(((df["status"] == "LINKED_CONFLICT") == df["conflict"]).sum()),
           "strata": {}}
    for s, gg in df.groupby("stratum"):
        opp = gg["conflict_opportunity"]
        res["strata"][s] = {
            "n_events": int(len(gg)),
            "conflict_opportunity_n": int(opp.sum()),
            "conflict_opportunity_rate": round(float(opp.mean()), 4),
            "mean_n_single_later_tiers": round(float(gg["n_single_later"].mean()), 3),
            "conflicts": int(gg["conflict"].sum()),
            "conflict_rate_unconditional": round(float(gg["conflict"].mean()), 4),
            "conflict_rate_given_opportunity": (round(float(gg.loc[opp, "conflict"].mean()), 4) if opp.sum() else None),
            "mean_n_wide_cand": round(float(gg["n_wide_cand"].mean()), 2),
            "median_margin_km": round(float(gg["margin_km"].median()), 3),
            "pct_margin_lt_1km": round(float((gg["margin_km"] < 1.0).mean()), 4),
            "pct_margin_lt_2km": round(float((gg["margin_km"] < 2.0).mean()), 4),
        }
    opp_all = df["conflict_opportunity"]
    nar, med = df[df.stratum == "Narrow(T0-1)"], df[df.stratum == "Medium(T2-4)"]
    tbl = [[int(nar.conflict.sum()), int(len(nar) - nar.conflict.sum())],
           [int(med.conflict.sum()), int(len(med) - med.conflict.sum())]]
    res["overall"] = {
        "conflict_opportunity_rate": round(float(opp_all.mean()), 4),
        "conflict_rate_unconditional": round(float(df["conflict"].mean()), 4),
        "conflict_rate_given_opportunity": round(float(df.loc[opp_all, "conflict"].mean()), 4),
        "narrow_n": int(len(nar)),
        "narrow_with_opportunity": int(nar["conflict_opportunity"].sum()),
        "fisher_p_narrow_vs_medium": round(float(st.fisher_exact(tbl)[1]), 4),
    }
    OUT["V1_task1_conflict_detectability"] = res
    log("[V1] " + json.dumps(res, ensure_ascii=False, indent=1))


# ------------------------------------------------- shared window machinery
PATTERN_MAXGAP = np.zeros(128, dtype=np.int32)
PATTERN_FIRST = np.full(128, -1, dtype=np.int32)
PATTERN_LAST = np.full(128, -1, dtype=np.int32)
for _p in range(128):
    _bits = [k for k in range(7) if (_p >> k) & 1]
    if _bits:
        PATTERN_FIRST[_p], PATTERN_LAST[_p] = _bits[0], _bits[-1]
        PATTERN_MAXGAP[_p] = max([b - a - 1 for a, b in zip(_bits[:-1], _bits[1:])], default=0)
    else:
        PATTERN_MAXGAP[_p] = 7


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


METRICS = ["len_mean", "bbox_mean", "lin_mean", "score_mean", "score_max", "sgap_mean",
           "stop_frac", "sea_frac", "anch_frac", "maxgap", "cen_span_m", "net_m", "net_over_path"]


def build_vessel(v_s, span, min_ts):
    idx = v_s["ts"].values - min_ts
    obs = np.zeros(span, np.int8)
    obs[idx] = 1

    def nanarr(col):
        a = np.full(span, np.nan)
        a[idx] = v_s[col].values
        return a

    lenm, bbox = nanarr("len_m"), nanarr("bbox_m")
    lat, lon = nanarr("cen_lat"), nanarr("cen_lon")
    score, sgap = nanarr("score"), nanarr("s_gap")
    stt = np.empty(span, dtype=object)
    stt[idx] = v_s["state"].values
    is_stop = np.where(obs == 1, np.isin(stt, list(STOPPED)).astype(float), np.nan)
    is_sea = np.where(obs == 1, (stt == ST_SEA).astype(float), np.nan)
    is_anch = np.where(obs == 1, (stt == ST_ANCH).astype(float), np.nan)
    lin = bbox / np.maximum(lenm, 1.0)

    sw = np.lib.stride_tricks.sliding_window_view
    W = {}
    obsw = sw(obs.astype(np.int32), 7)
    pat = (obsw * (1 << np.arange(7))).sum(1)
    W["n_rows"] = obsw.sum(1)
    W["maxgap"] = PATTERN_MAXGAP[pat].astype(float)
    starts = np.arange(span - 6)
    ok = PATTERN_FIRST[pat] >= 0
    fi = np.where(ok, starts + np.maximum(PATTERN_FIRST[pat], 0), 0)
    li = np.where(ok, starts + np.maximum(PATTERN_LAST[pat], 0), 0)
    net = np.where(ok, haversine_m(lat[fi], lon[fi], lat[li], lon[li]), np.nan)

    with np.errstate(invalid="ignore"):
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        for nm, arr in [("len_mean", lenm), ("bbox_mean", bbox), ("lin_mean", lin),
                        ("score_mean", score), ("sgap_mean", sgap),
                        ("stop_frac", is_stop), ("sea_frac", is_sea), ("anch_frac", is_anch)]:
            W[nm] = np.nanmean(sw(arr, 7), axis=1)
        W["score_max"] = np.nanmax(sw(score, 7), axis=1)
        len_sum = np.nansum(sw(lenm, 7), axis=1)
        latw, lonw = sw(lat, 7), sw(lon, 7)
        W["cen_span_m"] = haversine_m(np.nanmin(latw, 1), np.nanmin(lonw, 1),
                                      np.nanmax(latw, 1), np.nanmax(lonw, 1))
    W["net_m"] = net
    W["net_over_path"] = net / np.maximum(len_sum, 1.0)
    W["center"] = starts + 3
    return W


def load_windows():
    pos = pd.read_csv(R8 / "devset_positives.csv")
    cols = ["rfid_id_int", "ts", "len_m", "bbox_m", "cen_lon", "cen_lat", "state", "s_gap", "score"]
    sc = pd.read_parquet(R8 / "dev_hourly_scores.parquet", columns=cols)
    pv = set(pos["rfid_id"].astype(int))
    sc = sc[sc["rfid_id_int"].isin(pv)].copy()
    min_ts, max_ts = int(sc["ts"].min()), int(sc["ts"].max())
    span = max_ts - min_ts + 1
    log(f"[load] rows={len(sc)} vessels={sc.rfid_id_int.nunique()} span={span}h")
    vw = {}
    for rfid, g in sc.groupby("rfid_id_int"):
        vw[int(rfid)] = build_vessel(g.sort_values("ts"), span, min_ts)
    return pos, vw, span, min_ts


def ctrl_mask(W, span, acc_centers_idx, guard_h, n_target, exact=True):
    """eligible control window centers: outside guard of every accident, n_rows matched"""
    c = W["center"]
    ok = (W["n_rows"] > 0)
    for ai in acc_centers_idx:
        ok &= (np.abs(c - ai) >= guard_h + 4)   # window [c-3,c+3] vs guard [a-g,a+g]
    if exact:
        ok &= (W["n_rows"] == n_target)
    return ok


def pct_rank(value, pool):
    """mid-rank percentile of value within pool (NaN-safe)"""
    pool = pool[np.isfinite(pool)]
    if len(pool) == 0 or not np.isfinite(value):
        return np.nan
    less = np.sum(pool < value)
    eq = np.sum(pool == value)
    return float((less + 0.5 * eq) / len(pool))


# ---------------------------------------------------------------- V3/V4
def v3_v4_control_design(pos, vw, span, min_ts, guards=(12, 24, 72, 168)):
    rows = []
    prox_rows = []
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

        rec = dict(acc_id=int(acc.acc_id), rfid_id=rfid, tier=int(acc.tier),
                   conflict=bool(acc.conflict), acc_ts=t_acc, n_acc_rows=n_acc)
        for m in METRICS:
            rec["acc_" + m] = float(W[m][ci])

        for guard in guards:
            ok = ctrl_mask(W, span, acc_centers, guard, n_acc, exact=True)
            idx = np.where(ok)[0]
            rec[f"n_ctrl_g{guard}"] = int(len(idx))
            if len(idx) == 0:
                continue
            for m in METRICS:
                pool = W[m][idx]
                rec[f"pct_{m}_g{guard}"] = pct_rank(W[m][ci], pool)
                rec[f"ctrlmean_{m}_g{guard}"] = float(np.nanmean(pool)) if np.isfinite(pool).any() else np.nan
            if guard == 72:
                # 대조창 간 변동성: 1회 추출 설계의 분산 기여
                for m in ["score_mean", "len_mean"]:
                    rec[f"ctrlsd_{m}"] = float(np.nanstd(W[m][idx], ddof=1)) if len(idx) > 1 else np.nan
        # V3: 근접 vs 원거리 대조창 (guard 12h 기준 풀에서 거리별)
        ok12 = ctrl_mask(W, span, acc_centers, 12, n_acc, exact=True)
        idx12 = np.where(ok12)[0]
        if len(idx12):
            dist_h = np.abs(W["center"][idx12] - ai)
            for lab, sel in [("near16_24", (dist_h <= 24)),
                             ("mid24_72", (dist_h > 24) & (dist_h <= 72)),
                             ("far_gt168", (dist_h > 168))]:
                s = idx12[sel]
                if len(s) == 0:
                    continue
                prox_rows.append(dict(acc_id=int(acc.acc_id), rfid_id=rfid, bin=lab, n=len(s),
                                      score_mean=float(np.nanmean(W["score_mean"][s])),
                                      len_mean=float(np.nanmean(W["len_mean"][s])),
                                      stop_frac=float(np.nanmean(W["stop_frac"][s])),
                                      sea_frac=float(np.nanmean(W["sea_frac"][s])),
                                      maxgap=float(np.nanmean(W["maxgap"][s]))))
        rows.append(rec)

    ev = pd.DataFrame(rows)
    ev.to_csv(R9 / "review_v4_event_percentiles.csv", index=False, encoding="utf-8-sig")
    px = pd.DataFrame(prox_rows)
    px.to_csv(R9 / "review_v3_control_proximity.csv", index=False, encoding="utf-8-sig")

    # ---- V3 결과: 근접 대조창 vs 원거리 대조창 (사건 내 짝지음)
    v3 = {}
    piv = px.pivot_table(index="acc_id", columns="bin",
                         values=["score_mean", "len_mean", "stop_frac", "sea_frac", "maxgap"])
    for m in ["score_mean", "len_mean", "stop_frac", "sea_frac", "maxgap"]:
        try:
            a = piv[(m, "near16_24")]
            b = piv[(m, "far_gt168")]
            both = a.notna() & b.notna()
            d = (a[both] - b[both]).values
            w = st.wilcoxon(a[both], b[both]) if len(d) > 5 else None
            v3[m] = {"n_pairs": int(both.sum()),
                     "near_mean": round(float(a[both].mean()), 5),
                     "far_mean": round(float(b[both].mean()), 5),
                     "diff_near_minus_far": round(float(np.mean(d)), 5),
                     "wilcoxon_p": (round(float(w.pvalue), 5) if w else None)}
        except KeyError:
            v3[m] = "bin missing"
    v3["n_events_with_near_bin"] = int((px["bin"] == "near16_24").sum())
    OUT["V3_control_proximity_contamination"] = v3
    log("[V3] " + json.dumps(v3, ensure_ascii=False, indent=1))

    # ---- V4 결과: 백분위 one-sample 검정 (0.5 대비)
    v4 = {}
    strata = {"ALL": ev.index, "Tier0_1": ev.index[ev.tier <= 1], "CLEAN": ev.index[~ev.conflict]}
    for guard in guards:
        for sname, sidx in strata.items():
            sub = ev.loc[sidx]
            key = f"guard{guard}h/{sname}"
            d = {"n_events": int(len(sub)),
                 "median_n_ctrl": float(np.nanmedian(sub[f"n_ctrl_g{guard}"])) if f"n_ctrl_g{guard}" in sub else None,
                 "metrics": {}}
            for m in METRICS:
                col = f"pct_{m}_g{guard}"
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
                nz = dev[dev != 0]
                sp = float(st.binomtest(int((nz > 0).sum()), len(nz), 0.5).pvalue) if len(nz) else np.nan
                boot = np.random.default_rng(42).choice(x, size=(2000, len(x)), replace=True).mean(1)
                d["metrics"][m] = {"n": int(len(x)),
                                   "mean_pct": round(float(x.mean()), 4),
                                   "delta_vs_0.5": round(float(x.mean() - 0.5), 4),
                                   "ci95": [round(float(np.percentile(boot, 2.5)) - 0.5, 4),
                                            round(float(np.percentile(boot, 97.5)) - 0.5, 4)],
                                   "wilcoxon_p": round(wp, 5) if np.isfinite(wp) else None,
                                   "sign_p": round(sp, 5) if np.isfinite(sp) else None}
            v4[key] = d
    OUT["V4_distribution_based_retest"] = v4
    for k in [f"guard72h/ALL", f"guard72h/Tier0_1", f"guard12h/ALL"]:
        if k in v4:
            log(f"[V4] {k} " + json.dumps(v4[k], ensure_ascii=False, indent=1))
    return ev


# ---------------------------------------------------------------- V2/V5/V6/V7
def v2_v5_v6_v7(ev):
    e9 = pd.read_csv(R9 / "task2_event_comparison.csv")
    v9 = pd.read_csv(R9 / "task2_within_vessel_comparison.csv")

    # V2 공선성
    v2 = {"identity_missing_eq_7_minus_nrows": True,
          "acc_n_rows_mean": round(float(e9.acc_n_rows.mean()), 4),
          "implied_missing_hours": round(7 - float(e9.acc_n_rows.mean()), 4),
          "report_missing_hours_acc": 1.350,
          "exact_match_pairs": int((e9.match_row_diff == 0).sum()),
          "n_events": int(len(e9)),
          "note": "missing_hours = 7 - n_rows 는 산술 항등식. n_rows 를 1:1로 고정하면 H3(공백량) 및 s_gap 은 설계상 상수가 된다."}
    corr = float(np.corrcoef(e9.acc_n_rows, e9.acc_score_mean)[0, 1])
    v2["corr_acc_nrows_vs_score_mean"] = round(corr, 4)
    OUT["V2_collinearity"] = v2
    log("[V2] " + json.dumps(v2, ensure_ascii=False, indent=1))

    # V5 검정력
    v5 = {}
    for nm, (a, c) in {"score_mean": (v9.acc_score_mean, v9.ctrl_score_mean),
                       "len_mean": (v9.acc_len_mean, v9.ctrl_len_mean),
                       "bbox_mean": (v9.acc_bbox_mean, v9.ctrl_bbox_mean),
                       "lin_mean": (v9.acc_lin_mean, v9.ctrl_lin_mean)}.items():
        d = (a - c).dropna().values
        n = len(d)
        sd = float(np.std(d, ddof=1))
        se = sd / np.sqrt(n)
        mde = 2.8 * se  # 양측 alpha=.05, power=.80
        v5[nm] = {"n": n, "mean_diff": round(float(d.mean()), 5), "sd_diff": round(sd, 5),
                  "se": round(se, 5),
                  "ci95": [round(float(d.mean() - 1.96 * se), 5), round(float(d.mean() + 1.96 * se), 5)],
                  "MDE_80pct_power": round(float(mde), 5),
                  "observed_over_MDE": round(float(abs(d.mean()) / mde), 3)}
        # 1회 추출 대조창의 분산 기여
        if nm in ("score_mean", "len_mean") and f"ctrlsd_{nm}" in ev:
            v5[nm]["within_vessel_ctrl_sd_median"] = round(float(np.nanmedian(ev[f"ctrlsd_{nm}"])), 5)
            v5[nm]["ctrl_sd_over_paired_sd"] = round(float(np.nanmedian(ev[f"ctrlsd_{nm}"]) / sd), 3)
    tier = v9[v9.tier_min <= 1]
    d = (tier.acc_score_mean - tier.ctrl_score_mean).dropna().values
    v5["score_mean_Tier0_1"] = {"n": len(d), "mean_diff": round(float(d.mean()), 5),
                                "ci95": [round(float(d.mean() - 1.96 * np.std(d, ddof=1) / np.sqrt(len(d))), 5),
                                         round(float(d.mean() + 1.96 * np.std(d, ddof=1) / np.sqrt(len(d))), 5)],
                                "MDE_80pct_power": round(float(2.8 * np.std(d, ddof=1) / np.sqrt(len(d))), 5)}
    OUT["V5_power_and_MDE"] = v5
    log("[V5] " + json.dumps(v5, ensure_ascii=False, indent=1))

    # V6 McNemar
    v6 = {}
    for nm, (ca, cc) in {"state_changed": ("acc_state_changed", "ctrl_state_changed"),
                         "active_to_stop": ("acc_active_to_stop", "ctrl_active_to_stop"),
                         "drifting": ("acc_drifting", "ctrl_drifting")}.items():
        a = e9[ca].astype(bool).values
        c = e9[cc].astype(bool).values
        b01 = int(np.sum(a & ~c))
        b10 = int(np.sum(~a & c))
        n_disc = b01 + b10
        p = float(st.binomtest(b01, n_disc, 0.5).pvalue) if n_disc else np.nan
        v6[nm] = {"acc_rate": round(float(a.mean()), 4), "ctrl_rate": round(float(c.mean()), 4),
                  "discordant_acc_only": b01, "discordant_ctrl_only": b10,
                  "mcnemar_exact_p": round(p, 5) if np.isfinite(p) else None,
                  "n_discordant": n_disc}
    OUT["V6_mcnemar"] = v6
    log("[V6] " + json.dumps(v6, ensure_ascii=False, indent=1))

    # V7 역전 사례
    row = v9[v9.rfid_id == 36015383]
    if len(row):
        r = row.iloc[0]
        OUT["V7_inversion_case"] = {
            "rfid_id": 36015383,
            "acc_score_mean": round(float(r.acc_score_mean), 4),
            "ctrl_score_mean": round(float(r.ctrl_score_mean), 4),
            "diff": round(float(r.acc_score_mean - r.ctrl_score_mean), 4),
            "report_claims": {"acc": 0.3485, "ctrl": 0.5838, "diff": -0.2354},
        }
        sub = ev[ev.rfid_id == 36015383]
        if len(sub):
            OUT["V7_inversion_case"]["pct_score_mean_g72_all_controls"] = \
                [round(float(x), 4) for x in sub.get("pct_score_mean_g72", pd.Series(dtype=float)).dropna().tolist()]
        log("[V7] " + json.dumps(OUT["V7_inversion_case"], ensure_ascii=False, indent=1))


def main():
    v1_task1_conflict_detectability()
    pos, vw, span, min_ts = load_windows()
    ev = v3_v4_control_design(pos, vw, span, min_ts)
    v2_v5_v6_v7(ev)
    with open(R9 / "review_round9_metrics.json", "w", encoding="utf-8") as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)
    log("saved review_round9_metrics.json")


if __name__ == "__main__":
    main()
