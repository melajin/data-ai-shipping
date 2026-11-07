"""Task 2: Accident Window vs Control Window Within-Vessel Comparison & Hypothesis Testing
Author: Within-Vessel Comparator
Date: 2026-11-05
Working Directory: D:\\obsidian\\claude\\obsidian_export\\DATA AI SHIPPING\\testB\\round 9
Rules Compliance: AGENTS.md (psutil memory preflight, single-modifier rule, raw data preservation)
"""

import sys
import os
import json
import time
import datetime
import psutil
import numpy as np
import pandas as pd
import scipy.stats as stats
import scipy.ndimage as ndimage
from pathlib import Path

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Paths
BASE_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\testB")
ROUND008_DIR = BASE_DIR / "round_008_linkage_audit_20261105"
OUTPUT_DIR = BASE_DIR / "round 9"

PARQUET_PATH = ROUND008_DIR / "dev_hourly_scores.parquet"
POSITIVES_PATH = ROUND008_DIR / "devset_positives.csv"
NEGATIVES_PATH = ROUND008_DIR / "devset_negative_sample.csv"
EVENT_CHANGES_PATH = ROUND008_DIR / "event_changes.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def check_ram(stage: str, estimated_mb: float = 100.0):
    vm = psutil.virtual_memory()
    avail_mb = vm.available / (1024 ** 2)
    avail_gb = vm.available / (1024 ** 3)
    used_pct = vm.percent
    log(f"RAM Check [{stage}]: Available = {avail_gb:.2f} GB ({avail_mb:.1f} MiB), Used = {used_pct}%. "
        f"Estimated required = {estimated_mb:.1f} MiB.")
    if avail_mb < estimated_mb:
        raise MemoryError(f"Insufficient RAM for {stage}: {avail_mb:.1f} MiB available, {estimated_mb:.1f} MiB required.")
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "stage": stage,
        "available_mb": round(avail_mb, 2),
        "used_percent": used_pct,
        "estimated_mb": estimated_mb,
    }


def compute_paired_stats(x_acc: np.ndarray, x_ctrl: np.ndarray, name: str = ""):
    """Compute comprehensive paired comparison statistics."""
    valid_mask = np.isfinite(x_acc) & np.isfinite(x_ctrl)
    a = x_acc[valid_mask]
    c = x_ctrl[valid_mask]
    n = len(a)
    if n == 0:
        return {
            "name": name, "n": 0, "acc_mean": None, "ctrl_mean": None,
            "diff_mean": None, "diff_std": None, "cohen_d": None,
            "cliffs_delta": None, "wilcoxon_stat": None, "wilcoxon_p": None,
            "ttest_stat": None, "ttest_p": None, "n_pos": 0, "n_neg": 0, "n_tie": 0
        }

    diff = a - c
    mean_a = float(np.mean(a))
    mean_c = float(np.mean(c))
    diff_mean = float(np.mean(diff))
    diff_std = float(np.std(diff, ddof=1)) if n > 1 else 0.0

    # Cohen's d for paired differences
    cohen_d = float(diff_mean / diff_std) if diff_std > 1e-12 else 0.0

    # Paired Cliff's delta / Sign delta: proportion of positive diffs minus negative diffs
    n_pos = int(np.sum(diff > 1e-9))
    n_neg = int(np.sum(diff < -1e-9))
    n_tie = int(np.sum(np.abs(diff) <= 1e-9))
    cliffs_delta = float((n_pos - n_neg) / n) if n > 0 else 0.0

    # Paired t-test
    if n > 1 and diff_std > 1e-12:
        ttest_res = stats.ttest_rel(a, c)
        t_stat, t_p = float(ttest_res.statistic), float(ttest_res.pvalue)
    else:
        t_stat, t_p = 0.0, 1.0

    # Wilcoxon signed-rank test
    if n_pos + n_neg > 0:
        try:
            w_res = stats.wilcoxon(a, c)
            w_stat, w_p = float(w_res.statistic), float(w_res.pvalue)
        except Exception:
            w_stat, w_p = None, None
    else:
        w_stat, w_p = 0.0, 1.0

    return {
        "name": name,
        "n": n,
        "acc_mean": round(mean_a, 6),
        "ctrl_mean": round(mean_c, 6),
        "diff_mean": round(diff_mean, 6),
        "diff_std": round(diff_std, 6),
        "cohen_d": round(cohen_d, 4),
        "cliffs_delta": round(cliffs_delta, 4),
        "wilcoxon_stat": round(w_stat, 4) if w_stat is not None else None,
        "wilcoxon_p": float(w_p) if w_p is not None else None,
        "ttest_stat": round(t_stat, 4),
        "ttest_p": float(t_p),
        "n_pos": n_pos,
        "n_neg": n_neg,
        "n_tie": n_tie
    }


def main():
    start_time = time.time()
    log("Starting Task 2: Within-Vessel Comparison & Behavioral Hypothesis Testing...")

    # 1. RAM Preflight
    ram_log = []
    ram_log.append(check_ram("Preflight", estimated_mb=80.0))

    # 2. Load Positives, Negatives, Event Changes
    log(f"Loading {POSITIVES_PATH}...")
    df_pos = pd.read_csv(POSITIVES_PATH)
    log(f"Positives loaded: {len(df_pos)} rows, {df_pos['rfid_id'].nunique()} unique vessels.")

    retained_ids = set()
    if EVENT_CHANGES_PATH.exists():
        df_ec = pd.read_csv(EVENT_CHANGES_PATH)
        retained_ids = set(df_ec[df_ec['status'] == 'retained_identity']['new_rfid_id'].dropna().astype(int))
        log(f"Retained identity vessels from event_changes: {len(retained_ids)} vessels.")

    # 3. Read dev_hourly_scores.parquet with selective columns
    ram_log.append(check_ram("Pre-parquet Load", estimated_mb=120.0))
    cols_to_load = [
        'rfid_id_int', 'ts', 'part_dt', 'rfid_time',
        'len_m', 'bbox_m', 'state', 's_zone', 's_change', 's_gap', 'score'
    ]
    log(f"Loading selective columns from {PARQUET_PATH}...")
    scores_df = pd.read_parquet(PARQUET_PATH, columns=cols_to_load)
    log(f"Parquet loaded: {len(scores_df)} rows, memory usage = {scores_df.memory_usage().sum() / (1024**2):.1f} MiB.")

    # Filter to positive vessels only
    pos_vessels = set(df_pos['rfid_id'].astype(int).unique())
    pos_scores = scores_df[scores_df['rfid_id_int'].isin(pos_vessels)].copy()
    log(f"Filtered positive scores: {len(pos_scores)} rows across {pos_scores['rfid_id_int'].nunique()} vessels.")
    del scores_df  # Free unneeded rows
    ram_log.append(check_ram("Post-filter Parquet", estimated_mb=50.0))

    # Calculate linearity: bbox_m / np.maximum(len_m, 1.0)
    pos_scores['linearity'] = pos_scores['bbox_m'] / np.maximum(pos_scores['len_m'], 1.0)

    min_ts = int(pos_scores['ts'].min())
    max_ts = int(pos_scores['ts'].max())
    span = max_ts - min_ts + 1
    log(f"Time span: min_ts={min_ts}, max_ts={max_ts}, span={span} hours.")

    # Operational state classification
    # Active states: 저속굴곡 (fishing/trawling), 이동 (transit)
    # Stopped states: 정박정지 (anchored/moored), 해상정지 (drifting at sea), 연안정지 (coastal stop)
    active_states = {'저속굴곡', '이동'}
    stopped_states = {'정박정지', '해상정지', '연안정지'}

    # 4. Process Each Vessel and Each Accident Window
    # For every vessel:
    #   - Acc Window: t_acc ± 3h (span 7 hours)
    #   - Guard Band: t_acc ± 12h (excluded from control pool)
    #   - Control Windows: any 7h window [tc - 3, tc + 3] that does not overlap any guard band and has >= 1 obs
    #   - Match: 1:1 matching to control window with closest n_rows (tie-break: closest in time)
    #   - Extract metrics for:
    #       * Experiment 1: observation effect (n_rows, valid buckets, gaps)
    #       * Experiment 2: behavioral hypotheses (H1 len/bbox, H2 linearity, H3 asymmetry & state)
    #       * Existing score components (s_zone, s_change, s_gap, score)

    log("Beginning window extraction and matching for all 82 vessels...")
    event_records = []
    vessel_records = []

    for rfid, g in df_pos.groupby('rfid_id'):
        rfid = int(rfid)
        v_s = pos_scores[pos_scores['rfid_id_int'] == rfid].sort_values('ts')
        all_acc_ts = g['acc_ts'].values
        acc_ids = g['acc_id'].tolist()
        min_tier = int(g['tier'].min())
        has_conflict = bool(g['conflict'].any())
        is_multi = bool(len(g) > 1)
        is_retained = bool(rfid in retained_ids)

        # Dense arrays over the 4344 hour timeline for fast vectorized convolution
        obs = np.zeros(span, dtype=np.int32)
        len_m = np.zeros(span, dtype=np.float64)
        bbox_m = np.zeros(span, dtype=np.float64)
        lin = np.zeros(span, dtype=np.float64)
        sc = np.full(span, np.nan, dtype=np.float64)
        s_gap = np.full(span, np.nan, dtype=np.float64)
        s_zone = np.full(span, np.nan, dtype=np.float64)
        s_change = np.full(span, np.nan, dtype=np.float64)
        state_arr = np.empty(span, dtype=object)

        ts_idx = v_s['ts'].values - min_ts
        obs[ts_idx] = 1
        len_m[ts_idx] = v_s['len_m'].values
        bbox_m[ts_idx] = v_s['bbox_m'].values
        lin[ts_idx] = v_s['linearity'].values
        sc[ts_idx] = v_s['score'].values
        s_gap[ts_idx] = v_s['s_gap'].values
        s_zone[ts_idx] = v_s['s_zone'].values
        s_change[ts_idx] = v_s['s_change'].values
        state_arr[ts_idx] = v_s['state'].values

        # 7-hour sliding row count: window centered at i is [i-3, i+3]
        counts = np.convolve(obs, np.ones(7, dtype=np.int32), mode='same')

        # Construct Guard Band: for all accidents of this vessel, [a - 12, a + 12]
        # Any control window [tc - 3, tc + 3] must have NO hour within [a - 12, a + 12].
        # That means |tc - a| >= 16.
        guard_mask = np.zeros(span, dtype=bool)
        for a in all_acc_ts:
            ai = a - min_ts
            guard_mask[max(0, ai - 15):min(span, ai + 16)] = True

        valid_ctrl = (counts > 0) & (~guard_mask)
        valid_ctrl[:3] = False
        valid_ctrl[-3:] = False

        ctrl_indices = np.where(valid_ctrl)[0]
        ctrl_counts = counts[ctrl_indices]

        # Process each accident for this vessel
        v_event_acc_stats = []
        v_event_ctrl_stats = []

        for acc in g.itertuples():
            t_acc = int(acc.acc_ts)
            ai = t_acc - min_ts

            # Slices
            a_slice = slice(max(0, ai - 3), min(span, ai + 4))
            a_pre_slice = slice(max(0, ai - 3), ai)
            a_post_slice = slice(ai + 1, min(span, ai + 4))

            n_acc = int(counts[ai])
            n_acc_pre = int(obs[a_pre_slice].sum())
            n_acc_post = int(obs[a_post_slice].sum())
            acc_obs_mask = (obs[a_slice] == 1)

            # Accident window metrics
            acc_len_mean = float(np.mean(len_m[a_slice][acc_obs_mask])) if n_acc > 0 else 0.0
            acc_len_sum = float(np.sum(len_m[a_slice][acc_obs_mask]))
            acc_bbox_mean = float(np.mean(bbox_m[a_slice][acc_obs_mask])) if n_acc > 0 else 0.0
            acc_bbox_sum = float(np.sum(bbox_m[a_slice][acc_obs_mask]))
            acc_lin_mean = float(np.mean(lin[a_slice][acc_obs_mask])) if n_acc > 0 else 0.0
            acc_lin_agg = float(acc_bbox_sum / max(acc_len_sum, 1.0))

            acc_score_mean = float(np.nanmean(sc[a_slice])) if n_acc > 0 else 0.0
            acc_score_max = float(np.nanmax(sc[a_slice])) if n_acc > 0 else 0.0
            acc_gap_mean = float(np.nanmean(s_gap[a_slice])) if n_acc > 0 else 0.0
            acc_gap_max = float(np.nanmax(s_gap[a_slice])) if n_acc > 0 else 0.0
            acc_zone_mean = float(np.nanmean(s_zone[a_slice])) if n_acc > 0 else 0.0
            acc_zone_max = float(np.nanmax(s_zone[a_slice])) if n_acc > 0 else 0.0
            acc_change_mean = float(np.nanmean(s_change[a_slice])) if n_acc > 0 else 0.0
            acc_change_max = float(np.nanmax(s_change[a_slice])) if n_acc > 0 else 0.0

            # Pre vs Post Asymmetry
            acc_len_pre = float(np.sum(len_m[a_pre_slice]))
            acc_len_post = float(np.sum(len_m[a_post_slice]))
            acc_asym_len = float((acc_len_post - acc_len_pre) / max(acc_len_post + acc_len_pre, 1.0))
            acc_asym_rows = float((n_acc_post - n_acc_pre) / max(n_acc_post + n_acc_pre, 1))

            # Max gap between observations in 7h window
            acc_pattern = obs[a_slice]
            obs_positions = np.where(acc_pattern == 1)[0]
            if len(obs_positions) >= 2:
                acc_max_internal_gap = int(np.max(np.diff(obs_positions) - 1))
            else:
                acc_max_internal_gap = 7 - len(obs_positions)

            # State transition pre -> post
            pre_states = [s for s in state_arr[a_pre_slice] if s is not None]
            post_states = [s for s in state_arr[a_post_slice] if s is not None]
            st_pre = max(set(pre_states), key=pre_states.count) if pre_states else "MISSING"
            st_post = max(set(post_states), key=post_states.count) if post_states else "MISSING"

            acc_state_changed = bool(st_pre != st_post)
            acc_active_to_stop = bool((st_pre in active_states) and (st_post in stopped_states or st_post == "MISSING"))
            acc_drifting = bool(st_post == "해상정지")

            # 1:1 Control Matching
            diffs = np.abs(ctrl_counts - n_acc)
            min_diff = np.min(diffs)
            best_candidates = ctrl_indices[diffs == min_diff]
            # Tie-break: temporal proximity to ai
            best_ci = int(best_candidates[np.argmin(np.abs(best_candidates - ai))])
            best_tc = best_ci + min_ts

            # Control window metrics
            c_slice = slice(best_ci - 3, best_ci + 4)
            c_pre_slice = slice(best_ci - 3, best_ci)
            c_post_slice = slice(best_ci + 1, best_ci + 4)

            n_ctrl = int(counts[best_ci])
            n_ctrl_pre = int(obs[c_pre_slice].sum())
            n_ctrl_post = int(obs[c_post_slice].sum())
            c_obs_mask = (obs[c_slice] == 1)

            ctrl_len_mean = float(np.mean(len_m[c_slice][c_obs_mask])) if n_ctrl > 0 else 0.0
            ctrl_len_sum = float(np.sum(len_m[c_slice][c_obs_mask]))
            ctrl_bbox_mean = float(np.mean(bbox_m[c_slice][c_obs_mask])) if n_ctrl > 0 else 0.0
            ctrl_bbox_sum = float(np.sum(bbox_m[c_slice][c_obs_mask]))
            ctrl_lin_mean = float(np.mean(lin[c_slice][c_obs_mask])) if n_ctrl > 0 else 0.0
            ctrl_lin_agg = float(ctrl_bbox_sum / max(ctrl_len_sum, 1.0))

            ctrl_score_mean = float(np.nanmean(sc[c_slice])) if n_ctrl > 0 else 0.0
            ctrl_score_max = float(np.nanmax(sc[c_slice])) if n_ctrl > 0 else 0.0
            ctrl_gap_mean = float(np.nanmean(s_gap[c_slice])) if n_ctrl > 0 else 0.0
            ctrl_gap_max = float(np.nanmax(s_gap[c_slice])) if n_ctrl > 0 else 0.0
            ctrl_zone_mean = float(np.nanmean(s_zone[c_slice])) if n_ctrl > 0 else 0.0
            ctrl_zone_max = float(np.nanmax(s_zone[c_slice])) if n_ctrl > 0 else 0.0
            ctrl_change_mean = float(np.nanmean(s_change[c_slice])) if n_ctrl > 0 else 0.0
            ctrl_change_max = float(np.nanmax(s_change[c_slice])) if n_ctrl > 0 else 0.0

            ctrl_len_pre = float(np.sum(len_m[c_pre_slice]))
            ctrl_len_post = float(np.sum(len_m[c_post_slice]))
            ctrl_asym_len = float((ctrl_len_post - ctrl_len_pre) / max(ctrl_len_post + ctrl_len_pre, 1.0))
            ctrl_asym_rows = float((n_ctrl_post - n_ctrl_pre) / max(n_ctrl_post + n_ctrl_pre, 1))

            c_pattern = obs[c_slice]
            c_obs_positions = np.where(c_pattern == 1)[0]
            if len(c_obs_positions) >= 2:
                ctrl_max_internal_gap = int(np.max(np.diff(c_obs_positions) - 1))
            else:
                ctrl_max_internal_gap = 7 - len(c_obs_positions)

            c_pre_states = [s for s in state_arr[c_pre_slice] if s is not None]
            c_post_states = [s for s in state_arr[c_post_slice] if s is not None]
            c_st_pre = max(set(c_pre_states), key=c_pre_states.count) if c_pre_states else "MISSING"
            c_st_post = max(set(c_post_states), key=c_post_states.count) if c_post_states else "MISSING"

            ctrl_state_changed = bool(c_st_pre != c_st_post)
            ctrl_active_to_stop = bool((c_st_pre in active_states) and (c_st_post in stopped_states or c_st_post == "MISSING"))
            ctrl_drifting = bool(c_st_post == "해상정지")

            # Stratum mean of all exact/closest matching control windows
            stratum_indices = best_candidates
            stratum_score_means = [np.nanmean(sc[idx - 3: idx + 4]) for idx in stratum_indices]
            stratum_len_means = [np.mean(len_m[idx - 3: idx + 4][obs[idx - 3: idx + 4] == 1]) for idx in stratum_indices]
            matched_stratum_score_mean = float(np.nanmean(stratum_score_means))
            matched_stratum_len_mean = float(np.nanmean(stratum_len_means))

            # Unconstrained baseline (all valid control windows for vessel)
            unconstrained_n_rows_mean = float(np.mean(ctrl_counts))
            unconstrained_score_mean = float(np.nanmean(sc[ctrl_indices]))

            event_dict = {
                "acc_id": int(acc.acc_id),
                "rfid_id": rfid,
                "tier": int(acc.tier),
                "conflict": bool(acc.conflict),
                "vessel_multi_accident": is_multi,
                "is_retained": is_retained,
                "acc_ts": t_acc,
                "ctrl_tc": best_tc,
                "match_row_diff": int(min_diff),
                # Exp 1: Observation
                "acc_n_rows": n_acc,
                "ctrl_n_rows": n_ctrl,
                "ctrl_unconstrained_n_rows_mean": round(unconstrained_n_rows_mean, 4),
                "acc_max_internal_gap": acc_max_internal_gap,
                "ctrl_max_internal_gap": ctrl_max_internal_gap,
                # Exp 2: H1 Activity
                "acc_len_mean": round(acc_len_mean, 2),
                "ctrl_len_mean": round(ctrl_len_mean, 2),
                "acc_len_sum": round(acc_len_sum, 2),
                "ctrl_len_sum": round(ctrl_len_sum, 2),
                "acc_bbox_mean": round(acc_bbox_mean, 2),
                "ctrl_bbox_mean": round(ctrl_bbox_mean, 2),
                # Exp 2: H2 Linearity
                "acc_lin_mean": round(acc_lin_mean, 4),
                "ctrl_lin_mean": round(ctrl_lin_mean, 4),
                "acc_lin_agg": round(acc_lin_agg, 4),
                "ctrl_lin_agg": round(ctrl_lin_agg, 4),
                # Exp 2: H3 Asymmetry & State
                "acc_n_pre": n_acc_pre,
                "acc_n_post": n_acc_post,
                "ctrl_n_pre": n_ctrl_pre,
                "ctrl_n_post": n_ctrl_post,
                "acc_len_pre": round(acc_len_pre, 2),
                "acc_len_post": round(acc_len_post, 2),
                "ctrl_len_pre": round(ctrl_len_pre, 2),
                "ctrl_len_post": round(ctrl_len_post, 2),
                "acc_asym_rows": round(acc_asym_rows, 4),
                "ctrl_asym_rows": round(ctrl_asym_rows, 4),
                "acc_asym_len": round(acc_asym_len, 4),
                "ctrl_asym_len": round(ctrl_asym_len, 4),
                "acc_st_pre": st_pre,
                "acc_st_post": st_post,
                "ctrl_st_pre": c_st_pre,
                "ctrl_st_post": c_st_post,
                "acc_state_changed": acc_state_changed,
                "ctrl_state_changed": ctrl_state_changed,
                "acc_active_to_stop": acc_active_to_stop,
                "ctrl_active_to_stop": ctrl_active_to_stop,
                "acc_drifting": acc_drifting,
                "ctrl_drifting": ctrl_drifting,
                "acc_state_changed_rate": float(acc_state_changed),
                "ctrl_state_changed_rate": float(ctrl_state_changed),
                "acc_active_to_stop_rate": float(acc_active_to_stop),
                "ctrl_active_to_stop_rate": float(ctrl_active_to_stop),
                "acc_drifting_rate": float(acc_drifting),
                "ctrl_drifting_rate": float(ctrl_drifting),
                # Score components
                "acc_score_mean": round(acc_score_mean, 6),
                "ctrl_score_mean": round(ctrl_score_mean, 6),
                "acc_score_max": round(acc_score_max, 6),
                "ctrl_score_max": round(ctrl_score_max, 6),
                "acc_gap_mean": round(acc_gap_mean, 6),
                "ctrl_gap_mean": round(ctrl_gap_mean, 6),
                "acc_zone_mean": round(acc_zone_mean, 6),
                "ctrl_zone_mean": round(ctrl_zone_mean, 6),
                "acc_change_mean": round(acc_change_mean, 6),
                "ctrl_change_mean": round(ctrl_change_mean, 6),
                "matched_stratum_score_mean": round(matched_stratum_score_mean, 6),
                "matched_stratum_len_mean": round(matched_stratum_len_mean, 2),
                "unconstrained_score_mean": round(unconstrained_score_mean, 6)
            }
            event_records.append(event_dict)
            v_event_acc_stats.append(event_dict)

        # Aggregate across accidents to vessel level (N=82)
        df_va = pd.DataFrame(v_event_acc_stats)
        vessel_dict = {
            "rfid_id": rfid,
            "n_accidents": len(g),
            "acc_ids": ";".join(map(str, acc_ids)),
            "tier_min": min_tier,
            "has_conflict": has_conflict,
            "is_multi_accident": is_multi,
            "is_retained": is_retained,
            "acc_ts_list": ";".join(map(str, all_acc_ts)),
            "ctrl_candidates_count": len(ctrl_indices),
            # Exp 1: Observation
            "acc_n_rows": round(float(df_va["acc_n_rows"].mean()), 2),
            "ctrl_n_rows": round(float(df_va["ctrl_n_rows"].mean()), 2),
            "ctrl_unconstrained_n_rows_mean": round(float(df_va["ctrl_unconstrained_n_rows_mean"].mean()), 2),
            "diff_n_rows": round(float(df_va["acc_n_rows"].mean() - df_va["ctrl_n_rows"].mean()), 4),
            "obs_elev_raw": round(float(df_va["acc_n_rows"].mean() - df_va["ctrl_unconstrained_n_rows_mean"].mean()), 4),
            "acc_max_internal_gap": round(float(df_va["acc_max_internal_gap"].mean()), 2),
            "ctrl_max_internal_gap": round(float(df_va["ctrl_max_internal_gap"].mean()), 2),
            # Exp 2: H1 Activity
            "acc_len_mean": round(float(df_va["acc_len_mean"].mean()), 2),
            "ctrl_len_mean": round(float(df_va["ctrl_len_mean"].mean()), 2),
            "diff_len_mean": round(float(df_va["acc_len_mean"].mean() - df_va["ctrl_len_mean"].mean()), 2),
            "acc_len_sum": round(float(df_va["acc_len_sum"].mean()), 2),
            "ctrl_len_sum": round(float(df_va["ctrl_len_sum"].mean()), 2),
            "acc_bbox_mean": round(float(df_va["acc_bbox_mean"].mean()), 2),
            "ctrl_bbox_mean": round(float(df_va["ctrl_bbox_mean"].mean()), 2),
            "diff_bbox_mean": round(float(df_va["acc_bbox_mean"].mean() - df_va["ctrl_bbox_mean"].mean()), 2),
            # Exp 2: H2 Linearity
            "acc_lin_mean": round(float(df_va["acc_lin_mean"].mean()), 4),
            "ctrl_lin_mean": round(float(df_va["ctrl_lin_mean"].mean()), 4),
            "diff_lin_mean": round(float(df_va["acc_lin_mean"].mean() - df_va["ctrl_lin_mean"].mean()), 4),
            "acc_lin_agg": round(float(df_va["acc_lin_agg"].mean()), 4),
            "ctrl_lin_agg": round(float(df_va["ctrl_lin_agg"].mean()), 4),
            # Exp 2: H3 Asymmetry & State
            "acc_n_pre": round(float(df_va["acc_n_pre"].mean()), 2),
            "acc_n_post": round(float(df_va["acc_n_post"].mean()), 2),
            "ctrl_n_pre": round(float(df_va["ctrl_n_pre"].mean()), 2),
            "ctrl_n_post": round(float(df_va["ctrl_n_post"].mean()), 2),
            "acc_len_pre": round(float(df_va["acc_len_pre"].mean()), 2),
            "acc_len_post": round(float(df_va["acc_len_post"].mean()), 2),
            "ctrl_len_pre": round(float(df_va["ctrl_len_pre"].mean()), 2),
            "ctrl_len_post": round(float(df_va["ctrl_len_post"].mean()), 2),
            "acc_asym_rows": round(float(df_va["acc_asym_rows"].mean()), 4),
            "ctrl_asym_rows": round(float(df_va["ctrl_asym_rows"].mean()), 4),
            "acc_asym_len": round(float(df_va["acc_asym_len"].mean()), 4),
            "ctrl_asym_len": round(float(df_va["ctrl_asym_len"].mean()), 4),
            "acc_state_changed_rate": round(float(df_va["acc_state_changed"].astype(float).mean()), 4),
            "ctrl_state_changed_rate": round(float(df_va["ctrl_state_changed"].astype(float).mean()), 4),
            "acc_active_to_stop_rate": round(float(df_va["acc_active_to_stop"].astype(float).mean()), 4),
            "ctrl_active_to_stop_rate": round(float(df_va["ctrl_active_to_stop"].astype(float).mean()), 4),
            "acc_drifting_rate": round(float(df_va["acc_drifting"].astype(float).mean()), 4),
            "ctrl_drifting_rate": round(float(df_va["ctrl_drifting"].astype(float).mean()), 4),
            # Score Components
            "acc_score_mean": round(float(df_va["acc_score_mean"].mean()), 6),
            "ctrl_score_mean": round(float(df_va["ctrl_score_mean"].mean()), 6),
            "diff_score_mean": round(float(df_va["acc_score_mean"].mean() - df_va["ctrl_score_mean"].mean()), 6),
            "acc_score_max": round(float(df_va["acc_score_max"].mean()), 6),
            "ctrl_score_max": round(float(df_va["ctrl_score_max"].mean()), 6),
            "diff_score_max": round(float(df_va["acc_score_max"].mean() - df_va["ctrl_score_max"].mean()), 6),
            "acc_gap_mean": round(float(df_va["acc_gap_mean"].mean()), 6),
            "ctrl_gap_mean": round(float(df_va["ctrl_gap_mean"].mean()), 6),
            "diff_gap_mean": round(float(df_va["acc_gap_mean"].mean() - df_va["ctrl_gap_mean"].mean()), 6),
            "acc_zone_mean": round(float(df_va["acc_zone_mean"].mean()), 6),
            "ctrl_zone_mean": round(float(df_va["ctrl_zone_mean"].mean()), 6),
            "diff_zone_mean": round(float(df_va["acc_zone_mean"].mean() - df_va["ctrl_zone_mean"].mean()), 6),
            "acc_change_mean": round(float(df_va["acc_change_mean"].mean()), 6),
            "ctrl_change_mean": round(float(df_va["ctrl_change_mean"].mean()), 6),
            "diff_change_mean": round(float(df_va["acc_change_mean"].mean() - df_va["ctrl_change_mean"].mean()), 6),
            "ctrl_unconstrained_score_mean": round(float(df_va["unconstrained_score_mean"].mean()), 6),
            "raw_score_diff": round(float(df_va["acc_score_mean"].mean() - df_va["unconstrained_score_mean"].mean()), 6),
        }
        vessel_records.append(vessel_dict)

    df_vessels = pd.DataFrame(vessel_records)
    df_events = pd.DataFrame(event_records)
    log(f"Processed comparison tables: {len(df_vessels)} vessels, {len(df_events)} events.")

    # Save CSV outputs
    comparison_csv_path = OUTPUT_DIR / "task2_within_vessel_comparison.csv"
    df_vessels.to_csv(comparison_csv_path, index=False, encoding="utf-8-sig")
    log(f"Saved {comparison_csv_path} ({len(df_vessels)} rows).")

    event_csv_path = OUTPUT_DIR / "task2_event_comparison.csv"
    df_events.to_csv(event_csv_path, index=False, encoding="utf-8-sig")
    log(f"Saved {event_csv_path} ({len(df_events)} rows).")

    # 5. Experiment 3: Integrated Statistical Testing Across Hierarchical Subsets
    # Define Subsets:
    subsets = {
        "all_vessels": df_vessels,
        "non_conflict_vessels": df_vessels[~df_vessels["has_conflict"]],
        "tier_0_1_vessels": df_vessels[df_vessels["tier_min"] <= 1],
        "retained_identity_vessels": df_vessels[df_vessels["is_retained"]],
        "single_accident_vessels": df_vessels[~df_vessels["is_multi_accident"]],
    }

    metrics_to_test = [
        # Exp 1
        ("n_rows", "acc_n_rows", "ctrl_n_rows"),
        ("max_internal_gap", "acc_max_internal_gap", "ctrl_max_internal_gap"),
        # Exp 2: H1
        ("len_mean", "acc_len_mean", "ctrl_len_mean"),
        ("len_sum", "acc_len_sum", "ctrl_len_sum"),
        ("bbox_mean", "acc_bbox_mean", "ctrl_bbox_mean"),
        # Exp 2: H2
        ("linearity_mean", "acc_lin_mean", "ctrl_lin_mean"),
        ("linearity_agg", "acc_lin_agg", "ctrl_lin_agg"),
        # Exp 2: H3
        ("asym_rows", "acc_asym_rows", "ctrl_asym_rows"),
        ("asym_len", "acc_asym_len", "ctrl_asym_len"),
        ("state_changed_rate", "acc_state_changed_rate", "ctrl_state_changed_rate"),
        ("active_to_stop_rate", "acc_active_to_stop_rate", "ctrl_active_to_stop_rate"),
        ("drifting_rate", "acc_drifting_rate", "ctrl_drifting_rate"),
        # Components
        ("score_mean", "acc_score_mean", "ctrl_score_mean"),
        ("score_max", "acc_score_max", "ctrl_score_max"),
        ("gap_mean", "acc_gap_mean", "ctrl_gap_mean"),
        ("zone_mean", "acc_zone_mean", "ctrl_zone_mean"),
        ("change_mean", "acc_change_mean", "ctrl_change_mean"),
    ]

    hypothesis_results = {
        "metadata": {
            "created_at": datetime.datetime.now().isoformat(),
            "script": "run_task2_comparison.py",
            "vessels_total": len(df_vessels),
            "events_total": len(df_events),
            "ram_preflight": ram_log
        },
        "subsets_counts": {k: len(v) for k, v in subsets.items()},
        "tests": {}
    }

    log("Running paired statistical tests across subsets...")
    for sub_name, sub_df in subsets.items():
        sub_results = {}
        for metric_name, col_acc, col_ctrl in metrics_to_test:
            st = compute_paired_stats(sub_df[col_acc].values, sub_df[col_ctrl].values, name=metric_name)
            sub_results[metric_name] = st
        hypothesis_results["tests"][sub_name] = sub_results

    # Also run on event-level (N=100)
    event_sub_results = {}
    for metric_name, col_acc, col_ctrl in metrics_to_test:
        if col_acc in df_events.columns and col_ctrl in df_events.columns:
            st = compute_paired_stats(df_events[col_acc].values, df_events[col_ctrl].values, name=metric_name)
            event_sub_results[metric_name] = st
    hypothesis_results["tests"]["all_events_n100"] = event_sub_results

    # 6. Oaxaca-Blinder / Kitagawa Decomposition of Observation vs Behavioral Effects
    # Raw unconstrained diff = Y_acc - Y_ctrl_unconstrained
    # Conditioned behavior diff = Y_acc - Y_ctrl_matched
    # Observation confounding = Y_ctrl_matched - Y_ctrl_unconstrained
    # Total = Behavior + Observation Confounding
    log("Computing Oaxaca-Blinder / Kitagawa decomposition...")
    decomposition_results = {
        "metadata": {
            "created_at": datetime.datetime.now().isoformat(),
            "description": "Decomposition of Raw Difference into Behavioral Effect (row-matched) and Observation Confounding (row count elevation)."
        },
        "subsets": {}
    }

    for sub_name, sub_df in subsets.items():
        decomp_sub = {}
        # 1. Observation row count elevation
        obs_raw_diff = float(np.mean(sub_df["acc_n_rows"] - sub_df["ctrl_unconstrained_n_rows_mean"]))
        obs_matched_diff = float(np.mean(sub_df["acc_n_rows"] - sub_df["ctrl_n_rows"]))

        # 2. Score decomposition
        y_acc = sub_df["acc_score_mean"].values
        y_ctrl_matched = sub_df["ctrl_score_mean"].values
        y_ctrl_unconstrained = sub_df["ctrl_unconstrained_score_mean"].values

        delta_raw = float(np.mean(y_acc - y_ctrl_unconstrained))
        delta_behavior = float(np.mean(y_acc - y_ctrl_matched))
        delta_observation = float(np.mean(y_ctrl_matched - y_ctrl_unconstrained))

        pct_obs = float((delta_observation / delta_raw) * 100) if abs(delta_raw) > 1e-6 else 0.0
        pct_behavior = float((delta_behavior / delta_raw) * 100) if abs(delta_raw) > 1e-6 else 0.0

        decomp_sub["row_count"] = {
            "acc_n_rows_mean": round(float(np.mean(sub_df["acc_n_rows"])), 3),
            "ctrl_unconstrained_n_rows_mean": round(float(np.mean(sub_df["ctrl_unconstrained_n_rows_mean"])), 3),
            "ctrl_matched_n_rows_mean": round(float(np.mean(sub_df["ctrl_n_rows"])), 3),
            "row_count_elevation_raw": round(obs_raw_diff, 3),
            "row_count_matching_residual": round(obs_matched_diff, 4)
        }
        decomp_sub["score_mean"] = {
            "delta_raw": round(delta_raw, 6),
            "delta_behavior": round(delta_behavior, 6),
            "delta_observation": round(delta_observation, 6),
            "pct_observation_confounding": round(pct_obs, 2),
            "pct_behavioral_effect": round(pct_behavior, 2)
        }

        decomposition_results["subsets"][sub_name] = decomp_sub

    # Save JSON files
    hypo_path = OUTPUT_DIR / "task2_hypothesis_results.json"
    with open(hypo_path, "w", encoding="utf-8") as f:
        json.dump(hypothesis_results, f, indent=2, ensure_ascii=False)
    log(f"Saved {hypo_path}.")

    decomp_path = OUTPUT_DIR / "task2_decomposition.json"
    with open(decomp_path, "w", encoding="utf-8") as f:
        json.dump(decomposition_results, f, indent=2, ensure_ascii=False)
    log(f"Saved {decomp_path}.")

    # 7. Identify Top Hits and Inversions
    df_vessels["score_diff"] = df_vessels["acc_score_mean"] - df_vessels["ctrl_score_mean"]
    df_vessels["len_diff"] = df_vessels["acc_len_mean"] - df_vessels["ctrl_len_mean"]

    top_hits = df_vessels.sort_values("score_diff", ascending=False).head(5)
    top_inversions = df_vessels.sort_values("score_diff", ascending=True).head(5)

    log("Execution complete in {:.2f}s.".format(time.time() - start_time))
    return hypothesis_results, decomposition_results, df_vessels


if __name__ == "__main__":
    main()
