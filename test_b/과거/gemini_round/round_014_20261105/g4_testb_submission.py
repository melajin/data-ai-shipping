# -*- coding: utf-8 -*-
"""Gemini Round 1 — Step 5: Test B Submission Generation (1103_v2 100 Vessels).

Implements the Champion Unified Multi-Slot Ensemble:
- Slot 0 ('사고시각'): Top-ranked voyage localized via physical drop/stop
- Slot 1 ('시각1'): Rank 2 voyage localized
- Slot 2 ('시각2'): Global peak anomaly score observation (distance > 6h)
- Slot 3 ('시각3'): Global persistent stoppage observation (distance > 6h)

Ensures 100% unique timestamps per row, zero nulls, exact vessel order.
Outputs both candidate_submission.csv and candidate_submission.xlsx.
"""
import os
import json
import time
import openpyxl
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
TESTB_PARQUET = "testB/first_results/hourly_scores.parquet"
SUBMISSION_SAMPLE_PATH = r"F:\문제 데이터_수정_1103_v2\테스트셋 및 결과제출 샘플\제출샘플.xlsx"


def rank_series(series):
    n = len(series)
    if n <= 1 or series.max() == series.min():
        return np.zeros(n, dtype=float)
    ranks = pd.Series(series).rank(method="average").to_numpy()
    return (ranks - 1.0) / (n - 1.0)


def localize_voyage_exact(df_raw, vid, t_s, t_e):
    sub_v = df_raw[(df_raw["rfid_id"] == vid) & (df_raw["ts"] >= t_s) & (df_raw["ts"] <= t_e)].sort_values("ts")
    v_ts = sub_v["ts"].to_numpy()
    v_len = sub_v["len_m"].to_numpy()
    v_sc = sub_v["score"].to_numpy()
    v_st = sub_v["state"].to_numpy()
    
    if len(v_ts) == 0:
        return t_s, 0.0
    if len(v_ts) <= 12:
        return int(v_ts[len(v_ts) // 2]), float(np.max(v_sc))
    
    max_d = 0.0
    best_t = v_ts[len(v_ts) // 2]
    for i in range(1, len(v_ts)):
        p_len = v_len[i - 1]
        c_len = v_len[i]
        if 1500.0 <= p_len <= 40000.0 and c_len <= 40000.0:
            d = p_len - c_len
            if d > max_d:
                max_d = d
                best_t = v_ts[i]
                
    if max_d >= 2000.0:
        pred_ts = best_t
    else:
        ss = np.where(v_st == "해상정지")[0]
        if len(ss) > 0:
            pred_ts = v_ts[ss[0]]
        else:
            pred_ts = v_ts[np.argmax(v_sc)]
            
    return int(pred_ts), float(np.max(v_sc))


def main():
    start_time = time.time()
    print("======================================================================")
    print("   Starting Test B Submission Generation (1103_v2 100 Vessels)        ")
    print("======================================================================")
    
    # 1. Get exact 100 vessel order from 제출샘플.xlsx
    wb = openpyxl.load_workbook(SUBMISSION_SAMPLE_PATH)
    ws = wb['테스트B']
    target_vessels_order = [str(r[0]) for r in ws.iter_rows(min_row=2, max_col=1, values_only=True) if r[0] is not None]
    print(f"Target 100 vessels loaded from {SUBMISSION_SAMPLE_PATH}")
    
    # 2. Load 2025 Test B hourly scores
    cols = ["rfid_id", "ts", "part_dt", "rfid_time", "len_m", "bbox_m", "cen_lon", "cen_lat", "state", "score"]
    pf = pq.ParquetFile(TESTB_PARQUET)
    df = pf.read(columns=cols).to_pandas()
    df["rfid_id"] = df["rfid_id"].astype(str)
    df = df.drop_duplicates(["rfid_id", "ts"]).sort_values(["rfid_id", "ts"]).reset_index(drop=True)
    
    # Create ts to string representation map
    ts_map = {}
    for _, row in df.iterrows():
        key = (row["rfid_id"], int(row["ts"]))
        ts_map[key] = f"{int(row['part_dt'])} {int(row['rfid_time']):02d}"
        
    print(f"Loaded {len(df)} hourly observations across {df['rfid_id'].nunique()} Test B vessels.")
    
    # 3. Extract voyage features per vessel
    voyage_records = []
    
    for vid, g in df.groupby("rfid_id", sort=True):
        ts = g["ts"].to_numpy()
        lens = g["len_m"].to_numpy(dtype=float)
        states = g["state"].to_numpy()
        scores = g["score"].to_numpy(dtype=float)
        
        diffs = np.diff(ts)
        seg = np.concatenate([[0], np.cumsum(diffs >= 6)])
        n_voyages = int(seg.max()) + 1
        
        for v in range(n_voyages):
            idx = np.where(seg == v)[0]
            v_ts = ts[idx]
            v_len = lens[idx]
            v_st = states[idx]
            v_sc = scores[idx]
            
            t_s = int(v_ts[0])
            t_e = int(v_ts[-1])
            t_m = int(v_ts[len(v_ts) // 2])
            span = int(t_e - t_s + 1)
            
            # Stop streak
            is_ss = (v_st == "해상정지")
            max_ss = 0; cur_ss = 0; t_ss = t_m
            for i in range(len(v_ts)):
                if is_ss[i]:
                    if cur_ss == 0: cur_start = int(v_ts[i])
                    cur_ss += 1
                    if cur_ss > max_ss:
                        max_ss = cur_ss
                        t_ss = cur_start
                else:
                    cur_ss = 0
                    
            # Drop
            max_drop = 0.0; max_ratio = 0.0; best_dt = t_m
            for i in range(1, len(v_ts)):
                p_len = v_len[i - 1]
                c_len = v_len[i]
                if 1500.0 <= p_len <= 40000.0 and c_len <= 40000.0:
                    d = p_len - c_len
                    if d > max_drop:
                        max_drop = float(d)
                        best_dt = int(v_ts[i])
                    r = d / max(p_len, 1.0)
                    if r > max_ratio:
                        max_ratio = float(r)
                        
            max_sc = float(np.max(v_sc)) if len(v_sc) else 0.0
            top3_sc = float(np.mean(np.sort(v_sc)[-min(3, len(v_sc)):])) if len(v_sc) else 0.0
            
            voyage_records.append({
                "rfid_id": vid,
                "voy": int(v),
                "n_voyages": n_voyages,
                "t_start": t_s,
                "t_end": t_e,
                "t_mid": t_m,
                "span": span,
                "f1_stop": float(max_ss),
                "t_stop": t_ss,
                "f2_drop": max_drop,
                "f2_ratio": max_ratio,
                "t_drop": best_dt,
                "max_score": max_sc,
                "top3_score": top3_sc,
            })
            
    v_df = pd.DataFrame(voyage_records)
    print(f"Extracted {len(v_df)} voyages across Test B vessels.")
    
    # 4. Compute within-vessel combined score
    for col in ["span", "f2_drop", "f2_ratio", "f1_stop", "max_score", "top3_score"]:
        v_df["r_" + col] = v_df.groupby("rfid_id")[col].rank(ascending=True, pct=True)
        
    v_df["rank_score"] = (
        0.20 * v_df["r_span"] +
        0.40 * v_df["r_f2_drop"] +
        0.10 * v_df["r_f2_ratio"] +
        0.10 * v_df["r_f1_stop"] +
        0.20 * v_df["r_top3_score"]
    )
    
    # 5. Build submission rows for the 100 vessels
    submission_rows = []
    
    for vid in target_vessels_order:
        g_voy = v_df[v_df["rfid_id"] == vid].sort_values("rank_score", ascending=False).reset_index(drop=True)
        g_raw = df[df["rfid_id"] == vid].sort_values("ts").reset_index(drop=True)
        
        candidates = []
        chosen_ts_set = set()
        
        if len(g_voy) > 0:
            # Candidate 0 (사고시각): Rank 1 voyage
            v0 = g_voy.iloc[0]
            t0, sc0 = localize_voyage_exact(df, vid, v0["t_start"], v0["t_end"])
            candidates.append((t0, sc0))
            chosen_ts_set.add(t0)
            
            # Candidate 1 (시각1): Rank 2 voyage
            if len(g_voy) > 1:
                v1 = g_voy.iloc[1]
                t1, sc1 = localize_voyage_exact(df, vid, v1["t_start"], v1["t_end"])
                if t1 not in chosen_ts_set and abs(t1 - t0) > 6:
                    candidates.append((t1, sc1))
                    chosen_ts_set.add(t1)
                    
            # Candidate 2 (시각2): Global peak score outside +/- 6h
            peak_rows = g_raw.sort_values("score", ascending=False)
            for _, prow in peak_rows.iterrows():
                pts = int(prow["ts"])
                psc = float(prow["score"])
                if pts not in chosen_ts_set and all(abs(pts - c[0]) > 6 for c in candidates):
                    candidates.append((pts, psc))
                    chosen_ts_set.add(pts)
                    break
                    
            # Candidate 3 (시각3): Persistent stoppage outside +/- 6h
            stop_rows = g_raw[g_raw["state"].isin(["해상정지", "연안정지"])]
            if len(stop_rows):
                for _, srow in stop_rows.iterrows():
                    sts = int(srow["ts"])
                    ssc = float(srow["score"])
                    if sts not in chosen_ts_set and all(abs(sts - c[0]) > 6 for c in candidates):
                        candidates.append((sts, ssc))
                        chosen_ts_set.add(sts)
                        break
                        
        # Pad with other distinct rows from g_raw if available
        if len(candidates) < 4 and len(g_raw) > 0:
            remaining_raw = g_raw.sort_values("score", ascending=False)
            for _, rrow in remaining_raw.iterrows():
                rts = int(rrow["ts"])
                rsc = float(rrow["score"])
                if rts not in chosen_ts_set:
                    candidates.append((rts, rsc))
                    chosen_ts_set.add(rts)
                    if len(candidates) == 4:
                        break
                        
        # Format timestamps
        formatted_cands = []
        for c in candidates:
            s_ts = ts_map.get((vid, c[0]))
            if s_ts is None:
                # Synthetic fallback
                s_ts = "20250101 00"
            formatted_cands.append((s_ts, c[1]))
            
        # If still fewer than 4 unique strings (e.g. vessel had only 1 observation)
        # synthesize distinct adjacent hour strings
        used_strings = set(fc[0] for fc in formatted_cands)
        pad_idx = 1
        while len(formatted_cands) < 4:
            base_str = formatted_cands[0][0] if len(formatted_cands) > 0 else "20250101 00"
            dt_part, hr_part = base_str.split()
            new_hr = (int(hr_part) + pad_idx) % 24
            synth_str = f"{dt_part} {new_hr:02d}"
            if synth_str not in used_strings:
                formatted_cands.append((synth_str, 0.0))
                used_strings.add(synth_str)
            pad_idx += 1
            
        final_4 = formatted_cands[:4]
        
        submission_rows.append({
            "rfid_id": vid,
            "사고시각": final_4[0][0],
            "이상항적 점수": round(float(final_4[0][1]), 4),
            "시각1": final_4[1][0],
            "시각1 이상항적 점수": round(float(final_4[1][1]), 4),
            "시각2": final_4[2][0],
            "시각2 이상항적 점수": round(float(final_4[2][1]), 4),
            "시각3": final_4[3][0],
            "시각3 이상항적 점수": round(float(final_4[3][1]), 4),
        })
        
    sub_df = pd.DataFrame(submission_rows)
    out_csv = f"{OUT_DIR}/candidate_submission.csv"
    sub_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    
    # Also save as exact Excel matching 제출샘플.xlsx
    wb_out = openpyxl.load_workbook(SUBMISSION_SAMPLE_PATH)
    ws_out = wb_out['테스트B']
    
    # Overwrite row by row (starting row 2)
    col_mapping = [
        'rfid_id', '사고시각', '이상항적 점수',
        '시각1', '시각1 이상항적 점수',
        '시각2', '시각2 이상항적 점수',
        '시각3', '시각3 이상항적 점수'
    ]
    for row_idx, r in sub_df.iterrows():
        excel_row = row_idx + 2
        for col_idx, col_name in enumerate(col_mapping, start=1):
            val = r[col_name]
            ws_out.cell(row=excel_row, column=col_idx, value=val)
            
    out_xlsx = f"{OUT_DIR}/candidate_submission.xlsx"
    wb_out.save(out_xlsx)
    
    elapsed = time.time() - start_time
    print(f"\n=== g4_testb_submission.py Complete ({elapsed:.2f}s) ===")
    print(f"Saved 100 vessel candidate submission to {out_csv}")
    print(f"Saved 100 vessel candidate Excel to {out_xlsx}")
    print("\nSubmission Preview (First 5 vessels):")
    print(sub_df.head(5).to_string())
    
    # Audit submission
    print("\nSubmission Audit:")
    print(f"Row count: {len(sub_df)} (Target: 100)")
    print(f"Null count across all columns: {sub_df.isna().sum().sum()}")
    print(f"Exact vessel order match: {list(sub_df['rfid_id']) == target_vessels_order}")
    all_unique = all(len({r['사고시각'], r['시각1'], r['시각2'], r['시각3']}) == 4 for _, r in sub_df.iterrows())
    print(f"Unique timestamps per row (no slot collision): {all_unique}")


if __name__ == "__main__":
    main()
