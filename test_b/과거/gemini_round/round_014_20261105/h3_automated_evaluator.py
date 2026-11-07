# -*- coding: utf-8 -*-
"""Component 4: Automated Statistical Evaluator & Gate Verifier.

Evaluates predictions against devset_positives.csv, calculates:
- Voyage capture rate
- +-6h hit rate
- Binomial test p-values against random baselines
- Cluster bootstrap 95% CIs (B=4000, seed=11052026)
- Pre-registered gate status (Level 1: >=12%, Level 2: >=20%, Level 3: >=30%)
"""
import numpy as np
import pandas as pd
from scipy import stats

BOOTSTRAP_B = 4000
BOOTSTRAP_SEED = 11052026


def compute_cluster_bootstrap(df_events, hit_col, cluster_col="rfid_id", B=BOOTSTRAP_B, seed=BOOTSTRAP_SEED):
    rng = np.random.default_rng(seed)
    unique_clusters = df_events[cluster_col].unique()
    n_clusters = len(unique_clusters)
    cluster_indices = {c: df_events[df_events[cluster_col] == c].index.to_numpy() for c in unique_clusters}
    
    boot_rates = np.empty(B, dtype=float)
    for b in range(B):
        sampled_c = rng.choice(unique_clusters, size=n_clusters, replace=True)
        sampled_rows = np.concatenate([cluster_indices[c] for c in sampled_c])
        boot_rates[b] = df_events.loc[sampled_rows, hit_col].mean()
        
    ci_lower = float(np.percentile(boot_rates, 2.5))
    ci_upper = float(np.percentile(boot_rates, 97.5))
    return {
        "ci_lower_95": round(ci_lower, 4),
        "ci_upper_95": round(ci_upper, 4),
        "boot_se": round(float(np.std(boot_rates)), 4),
    }


def evaluate_hypothesis(df_selections, pos_df, voy_df):
    """Merges selections with positives and computes all statistical metrics."""
    # Ensure string types
    pos_df["rfid_id"] = pos_df["rfid_id"].astype(str)
    df_selections["rfid_id"] = df_selections["rfid_id"].astype(str)
    voy_df["rfid_id"] = voy_df["rfid_id"].astype(str)
    
    vessel_voyages = {vid: g for vid, g in voy_df.groupby("rfid_id")}
    vessel_n_voy = {vid: len(g) for vid, g in voy_df.groupby("rfid_id")}
    
    events = pos_df.merge(df_selections, on="rfid_id", how="left")
    
    eval_rows = []
    for _, r in events.iterrows():
        vid = r["rfid_id"]
        acc_id = int(r["acc_id"])
        acc_ts = int(r["acc_ts"])
        tier = int(r["tier"])
        is_t01 = (tier <= 1)
        
        n_voy = vessel_n_voy.get(vid, 0)
        eligible = (n_voy >= 11)
        
        t_pred = r["t_pred"]
        if pd.isna(t_pred):
            hit = False
        else:
            hit = bool(abs(int(t_pred) - acc_ts) <= 6)
            
        top_v_idx = r.get("top_voy")
        v_all = vessel_voyages.get(vid)
        if v_all is not None and pd.notna(top_v_idx):
            sel_voy = v_all[v_all["voy"] == int(top_v_idx)]
            if len(sel_voy) > 0:
                t_s = sel_voy.iloc[0]["t_start"]
                t_e = sel_voy.iloc[0]["t_end"]
                is_acc_voy = bool(t_s - 6 <= acc_ts <= t_e + 6)
            else:
                is_acc_voy = False
        else:
            is_acc_voy = False
        p_rand_voy = float((np.abs(v_all["t_mid"].to_numpy() - acc_ts) <= 6).mean()) if v_all is not None else 0.0
        
        eval_rows.append({
            "acc_id": acc_id,
            "rfid_id": vid,
            "tier": tier,
            "is_tier01": is_t01,
            "eligible_rem_ge_10": eligible,
            "acc_ts": acc_ts,
            "acc_type": r["발생유형"],
            "t_pred": t_pred,
            "pred_method": r["pred_method"],
            "hit": hit,
            "is_acc_voy": is_acc_voy,
            "base_rand_voy": p_rand_voy,
        })
        
    res_df = pd.DataFrame(eval_rows)
    
    def evaluate_cohort(sub_df, name):
        n = len(sub_df)
        hits = int(sub_df["hit"].sum())
        rate = hits / n if n > 0 else 0.0
        voy_caps = int(sub_df["is_acc_voy"].sum())
        voy_cap_rate = voy_caps / n if n > 0 else 0.0
        
        base_voy = float(sub_df["base_rand_voy"].mean()) if n > 0 else 0.0
        p_binom = float(stats.binomtest(hits, n, base_voy, alternative="greater").pvalue) if n > 0 else 1.0
        
        boot = compute_cluster_bootstrap(sub_df, "hit") if n > 0 and hits > 0 else {"ci_lower_95": 0.0, "ci_upper_95": 0.0, "boot_se": 0.0}
        
        return {
            "cohort": name,
            "n_events": n,
            "voyage_capture_count": voy_caps,
            "voyage_capture_rate": round(voy_cap_rate, 4),
            "hits": hits,
            "hit_rate": round(rate, 4),
            "baseline_random_voyage": round(base_voy, 4),
            "p_binom_vs_baseline": p_binom,
            "ci_95": [boot["ci_lower_95"], boot["ci_upper_95"]],
            "passed_level_1_12pct": bool(rate >= 0.12 and p_binom < 0.05),
            "passed_level_2_20pct": bool(rate >= 0.20),
            "passed_level_3_30pct": bool(rate >= 0.30),
        }
        
    t01_elig = evaluate_cohort(res_df[(res_df["is_tier01"] == True) & (res_df["eligible_rem_ge_10"] == True)], "PRIMARY_Tier0-1_Eligible (N=49)")
    t01_all = evaluate_cohort(res_df[res_df["is_tier01"] == True], "SECONDARY_Tier0-1_ALL (N=60)")
    all_elig = evaluate_cohort(res_df[res_df["eligible_rem_ge_10"] == True], "SECONDARY_ALL_Eligible (N=80)")
    all_100 = evaluate_cohort(res_df, "SECONDARY_ALL_100 (N=100)")
    
    return {
        "primary_t01_eligible": t01_elig,
        "secondary_t01_all": t01_all,
        "secondary_all_eligible": all_elig,
        "secondary_all_100": all_100,
        "detail_df": res_df,
    }
