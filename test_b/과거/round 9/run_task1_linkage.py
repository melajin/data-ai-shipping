"""Task 1: Full Linkage Audit Script for 167 Maritime Accidents.
Complies with AGENTS.md rules: memory preflight check, raw data preservation,
single file modifier, and strictly non-invasive to Task 2.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

# Ensure standard output encoding is utf-8
sys.stdout.reconfigure(encoding='utf-8')

ROUND9_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\testB\round 9")
ROUND8_DIR = Path(r"D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\testB\round_008_linkage_audit_20261105")
EXCEL_PATH = next((ROUND8_DIR.parent / "intake" / "1103_v2" / "inspection_001").glob("reference_01*.xlsx"))

CASCADE = [
    (0, 2.0),   # Tier 0
    (0, 5.0),   # Tier 1
    (1, 2.0),   # Tier 2
    (1, 5.0),   # Tier 3
    (2, 5.0),   # Tier 4
    (0, 10.0),  # Tier 5
    (1, 10.0),  # Tier 6
    (3, 5.0),   # Tier 7
    (2, 10.0),  # Tier 8
]

# Unicode escaped mapping for fishing gear
GEAR_MAP = {
    "\uc790\ub9dd": "\uc790\ub9dd",
    "\uc5f0\uc548\ubcf5\ud569": "\uc5f0\uc548\ubcf5\ud569",
    "\ud1b5\ubc1c": "\ud1b5\ubc1c",
    "\uc5f0\uc2b9": "\ucc44\ub09a\uae30\uc5f0\uc2b9\ub09a\uc2dc"
}


def preflight_memory_check():
    """Verify available RAM and log preflight receipt in compliance with AGENTS.md."""
    vm = psutil.virtual_memory()
    active_py = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            if 'python' in (p.info['name'] or '').lower():
                active_py.append({
                    'pid': p.pid,
                    'name': p.info['name'],
                    'rss_mib': round(p.info['memory_info'].rss / (1024 * 1024), 2)
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    avail_mib = round(vm.available / (1024 * 1024), 2)
    est_peak_mib = 300.0  # Processing small table of 25.6k rows
    allowed = avail_mib >= 1024.0  # At least 1GB reserve

    receipt = {
        "checked_at": datetime.now().astimezone().isoformat(),
        "total_ram_mib": round(vm.total / (1024 * 1024), 2),
        "available_ram_mib": avail_mib,
        "estimated_peak_mib": est_peak_mib,
        "reserve_threshold_mib": 1024.0,
        "allowed": allowed,
        "estimate_basis": "Pandas DataFrame operations on 25,600 observation rows and 167 accidents; minimal memory footprint.",
        "active_python_processes": active_py
    }
    
    if not allowed:
        raise SystemExit(f"Preflight check failed: Available RAM ({avail_mib} MiB) is below required safety threshold.")
    
    print(f"[Memory Preflight OK] Available RAM: {avail_mib} MiB | Estimated Peak: {est_peak_mib} MiB")
    return receipt


def candidates(rows, window_h, radius_km, gear=True):
    """One representative row per vessel inside this condition only."""
    mask = (rows['dt_h'] <= window_h) & (rows['dist_km'] <= radius_km)
    if gear:
        mask = mask & rows['gear_match']
    order = ["rfid_id", "dist_km", "dt_h", "row_ts"]
    order += [c for c in ("source_month", "source_row_index") if c in rows.columns]
    return (rows.loc[mask].sort_values(order, kind="stable")
            .drop_duplicates("rfid_id"))


def choose_event_detailed(rows):
    """Evaluate all 9 cascade conditions and capture full tier candidate details."""
    tier_details = {}
    chosen, chosen_tier, conflict, witness = None, None, False, None
    conflicting_tiers = []

    for i, (w, r) in enumerate(CASCADE):
        selected = candidates(rows, w, r, gear=True)
        vids = [int(v) for v in selected['rfid_id'].unique()]
        tier_details[i] = {
            "tier": i,
            "window_h": w,
            "radius_km": r,
            "n_candidates": len(vids),
            "candidates": vids,
            "is_single": (len(vids) == 1)
        }
        if len(selected) == 1:
            row = selected.iloc[0]
            vid = int(row['rfid_id'])
            if chosen is None:
                chosen = vid
                chosen_tier = i
                witness = row
            elif vid != chosen:
                conflict = True
                conflicting_tiers.append({
                    "tier": i,
                    "cond": str(CASCADE[i]),
                    "vid": vid
                })

    return {
        "chosen": chosen,
        "tier": chosen_tier,
        "witness": witness,
        "conflict": conflict,
        "conflicting_tiers": conflicting_tiers,
        "tier_details": tier_details
    }


def main():
    start_time = time.monotonic()
    mem_receipt = preflight_memory_check()

    print("Loading datasets...")
    obs_path = ROUND8_DIR / "links_observations.csv"
    pos_path = ROUND8_DIR / "devset_positives.csv"
    
    obs = pd.read_csv(obs_path)
    pos = pd.read_csv(pos_path)
    acc = pd.read_excel(EXCEL_PATH).reset_index().rename(columns={"index": "acc_id"})
    
    col_time = "\ubc1c\uc0dd\uc77c\uc2dc"
    col_station = "\uad00\ud560\ud574\uacbd\uc11c"
    col_sea = "\ubc1c\uc0dd\ud574\uc5ed"
    col_lat = "\uc704\ub3c4(\ubcc0\ud658)"
    col_lon = "\uacbd\ub3c4(\ubcc0\ud658)"
    col_type = "\ubc1c\uc0dd\uc720\ud615"
    col_n_ships = "\uc0ac\uace0\uc120\ubc15\uc218"
    col_gear = "\uc5b4\uc5c5\uba74\ud5c8"
    col_ton = "\ud1a4\uc218"

    acc["acc_ts"] = acc[col_time].to_numpy().astype("datetime64[h]").astype(np.int64)
    acc["gear_code"] = acc[col_gear].map(GEAR_MAP)

    print(f"Total accidents: {len(acc)} (acc_id 0 to {len(acc)-1})")
    print(f"Total observation rows: {len(obs)}")

    # ==========================================
    # 1. 167 Accidents Full Linkage Audit
    # ==========================================
    audit_records = []
    conflict_cases_dict = {}
    unlinked_breakdown = {
        "UNLINKED_NO_OBS": [],
        "UNLINKED_GEAR_MISMATCH": [],
        "UNLINKED_COMPETITION": [],
        "UNLINKED_OUT_OF_CASCADE": []
    }

    status_counts = {
        "LINKED_CLEAN": 0,
        "LINKED_CONFLICT": 0,
        "UNLINKED_NO_OBS": 0,
        "UNLINKED_GEAR_MISMATCH": 0,
        "UNLINKED_COMPETITION": 0,
        "UNLINKED_OUT_OF_CASCADE": 0
    }

    for aid in range(len(acc)):
        a_info = acc.iloc[aid]
        sub = obs[obs['acc_id'] == aid]

        n_obs_total = len(sub)
        n_vessels_total = sub['rfid_id'].nunique() if n_obs_total > 0 else 0
        min_dist_km = float(sub['dist_km'].min()) if n_obs_total > 0 else None
        min_dt_h = int(sub['dt_h'].min()) if n_obs_total > 0 else None

        gear_sub = sub[sub['gear_match']] if n_obs_total > 0 else pd.DataFrame()
        n_obs_gear = len(gear_sub)
        n_vessels_gear = gear_sub['rfid_id'].nunique() if n_obs_gear > 0 else 0
        min_dist_gear_km = float(gear_sub['dist_km'].min()) if n_obs_gear > 0 else None
        min_dt_gear_h = int(gear_sub['dt_h'].min()) if n_obs_gear > 0 else None

        link_eval = choose_event_detailed(sub) if n_obs_total > 0 else None
        
        status = None
        chosen_vid = None
        tier = None
        cascade_cond = None
        conflict = False
        rep_dt_h = None
        rep_dist_km = None
        rep_row_ts = None
        rep_month = None
        rep_row_index = None
        n_cand_base_gear = 0

        if n_obs_total == 0:
            status = "UNLINKED_NO_OBS"
            unlinked_breakdown["UNLINKED_NO_OBS"].append({
                "acc_id": aid,
                "accident_time": str(a_info[col_time]),
                "station": str(a_info[col_station]),
                "sea_area": str(a_info[col_sea]),
                "lat": float(a_info[col_lat]),
                "lon": float(a_info[col_lon]),
                "accident_type": str(a_info[col_type]),
                "gear": str(a_info[col_gear]),
                "tonnage": float(a_info[col_ton]),
                "reason": "\u00b16h \ubc0f 20km \ubc18\uacbd \ub0b4\uc5d0 AIS/RFID \uad00\uce21 \ud589\uc774 \uc804\ud600 \uc5c6\uc74c (0\ud589)"
            })
        elif n_obs_gear == 0:
            status = "UNLINKED_GEAR_MISMATCH"
            unlinked_breakdown["UNLINKED_GEAR_MISMATCH"].append({
                "acc_id": aid,
                "accident_time": str(a_info[col_time]),
                "station": str(a_info[col_station]),
                "sea_area": str(a_info[col_sea]),
                "accident_type": str(a_info[col_type]),
                "gear": str(a_info[col_gear]),
                "tonnage": float(a_info[col_ton]),
                "n_obs_total": n_obs_total,
                "n_vessels_total": n_vessels_total,
                "min_dist_km": min_dist_km,
                "min_dt_h": min_dt_h,
                "reason": f"\uc778\uadfc\uc5d0 {n_vessels_total}\ucc99({n_obs_total}\ud589)\uc758 \uad00\uce21\uc774 \uc788\uc73c\ub098 \uc5b4\uc5c5\uba74\ud5c8('{a_info[col_gear]}')\uc640 \uc77c\uce58\ud558\ub294 \uc120\ubc15\uc774 \uc804\ubb34\ud558\uc5ec \uc804\uc6d0 \ud0c8\ub77d"
            })
        else:
            base_selected = candidates(sub, 1, 5.0, gear=True)
            n_cand_base_gear = len(base_selected)

            if link_eval["chosen"] is not None:
                chosen_vid = link_eval["chosen"]
                tier = link_eval["tier"]
                cascade_cond = str(CASCADE[tier])
                conflict = link_eval["conflict"]
                witness = link_eval["witness"]
                rep_dt_h = float(witness["dt_h"])
                rep_dist_km = float(witness["dist_km"])
                rep_row_ts = int(witness["row_ts"])
                rep_month = int(witness["source_month"])
                rep_row_index = int(witness["source_row_index"])

                if conflict:
                    status = "LINKED_CONFLICT"
                    conflict_cases_dict[aid] = {
                        "acc_id": aid,
                        "accident_time": str(a_info[col_time]),
                        "station": str(a_info[col_station]),
                        "sea_area": str(a_info[col_sea]),
                        "lat": float(a_info[col_lat]),
                        "lon": float(a_info[col_lon]),
                        "accident_type": str(a_info[col_type]),
                        "gear": str(a_info[col_gear]),
                        "tonnage": float(a_info[col_ton]),
                        "selected_vessel": chosen_vid,
                        "selected_tier": tier,
                        "selected_cond": cascade_cond,
                        "rep_dt_h": rep_dt_h,
                        "rep_dist_km": rep_dist_km,
                        "conflicting_tiers": link_eval["conflicting_tiers"],
                        "all_tier_details": link_eval["tier_details"],
                        "diagnosis": ""
                    }
                else:
                    status = "LINKED_CLEAN"
            else:
                any_in_cascade = any(link_eval["tier_details"][t]["n_candidates"] > 0 for t in range(len(CASCADE)))
                if not any_in_cascade:
                    status = "UNLINKED_OUT_OF_CASCADE"
                    unlinked_breakdown["UNLINKED_OUT_OF_CASCADE"].append({
                        "acc_id": aid,
                        "accident_time": str(a_info[col_time]),
                        "station": str(a_info[col_station]),
                        "accident_type": str(a_info[col_type]),
                        "gear": str(a_info[col_gear]),
                        "tonnage": float(a_info[col_ton]),
                        "n_obs_gear": n_obs_gear,
                        "n_vessels_gear": n_vessels_gear,
                        "min_dist_gear_km": min_dist_gear_km,
                        "min_dt_gear_h": min_dt_gear_h,
                        "reason": f"\uc5b4\uad6c \uc77c\uce58 \uc120\ubc15({n_vessels_gear}\ucc99, {n_obs_gear}\ud589)\uc774 \uc874\uc7ac\ud558\ub098, \ubaa8\ub450 9\uac1c CASCADE \uc870\uac74 \ubc16(\uac70\ub9ac>10km \ub610\ub294 \uc2dc\uac04\ucc28>3h \ub4f1)\uc5d0 \uc704\uce58\ud558\uc5ec \ud0c8\ub77d"
                    })
                else:
                    status = "UNLINKED_COMPETITION"
                    max_c = max(link_eval["tier_details"][t]["n_candidates"] for t in range(len(CASCADE)))
                    unlinked_breakdown["UNLINKED_COMPETITION"].append({
                        "acc_id": aid,
                        "accident_time": str(a_info[col_time]),
                        "station": str(a_info[col_station]),
                        "accident_type": str(a_info[col_type]),
                        "gear": str(a_info[col_gear]),
                        "tonnage": float(a_info[col_ton]),
                        "n_obs_gear": n_obs_gear,
                        "n_vessels_gear": n_vessels_gear,
                        "min_dist_gear_km": min_dist_gear_km,
                        "min_dt_gear_h": min_dt_gear_h,
                        "max_cands_cascade": max_c,
                        "reason": f"CASCADE \uc870\uac74 \ub0b4 \uc5b4\uad6c \uc77c\uce58 \uc120\ubc15\uc774 \uc874\uc7ac\ud558\ub098, \ud6c4\ubcf4\uac00 \ub098\ud0c0\ub098\ub294 \ubaa8\ub4e0 \ud2f0\uc5b4\uc5d0\uc11c \ud56d\uc0c1 2\ucc99 \uc774\uc0c1(\ucd5c\ub300 {max_c}\ucc99) \uacbd\ud569\ud558\uc5ec \ub2e8\uc77c \ud6c4\ubcf4 \uc120\uc815 \ubd88\uac00"
                    })

        status_counts[status] += 1

        primary_analysis_set = (status == "LINKED_CLEAN")
        high_confidence_narrow_set = (status in ["LINKED_CLEAN", "LINKED_CONFLICT"]) and (tier in [0, 1])

        audit_records.append({
            "acc_id": aid,
            "status": status,
            "rfid_id": chosen_vid,
            "tier": tier,
            "cascade_cond": cascade_cond,
            "conflict": conflict,
            "primary_analysis_set": primary_analysis_set,
            "high_confidence_narrow_set": high_confidence_narrow_set,
            "dt_h": rep_dt_h,
            "dist_km": rep_dist_km,
            "row_ts": rep_row_ts,
            "source_month": rep_month,
            "source_row_index": rep_row_index,
            "n_cand_base_gear": n_cand_base_gear,
            "min_dist_km": min_dist_km,
            "min_dt_h": min_dt_h,
            "n_obs_total": n_obs_total,
            "n_vessels_total": n_vessels_total,
            "min_dist_gear_km": min_dist_gear_km,
            "min_dt_gear_h": min_dt_gear_h,
            "n_obs_gear": n_obs_gear,
            "n_vessels_gear": n_vessels_gear,
            col_time: str(a_info[col_time]),
            col_station: str(a_info[col_station]),
            col_sea: str(a_info[col_sea]),
            col_lat: float(a_info[col_lat]),
            col_lon: float(a_info[col_lon]),
            col_type: str(a_info[col_type]),
            col_n_ships: int(a_info[col_n_ships]),
            col_gear: str(a_info[col_gear]),
            col_ton: float(a_info[col_ton])
        })

    audit_df = pd.DataFrame(audit_records)
    print("\n=== Audit Status Summary ===")
    for k, v in status_counts.items():
        print(f"  {k}: {v}\uac74")
    print(f"  Total: {sum(status_counts.values())}\uac74")

    assert status_counts["LINKED_CLEAN"] == 95
    assert status_counts["LINKED_CONFLICT"] == 5
    assert status_counts["UNLINKED_NO_OBS"] == 2
    assert status_counts["UNLINKED_GEAR_MISMATCH"] == 7
    assert status_counts["UNLINKED_COMPETITION"] == 27
    assert status_counts["UNLINKED_OUT_OF_CASCADE"] == 31
    assert len(audit_df) == 167

    audit_csv_path = ROUND9_DIR / "task1_linkage_audit_167.csv"
    audit_df.to_csv(audit_csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {audit_csv_path}")

    # ==========================================
    # 2. Detailed Diagnosis of 5 Conflict Cases
    # ==========================================
    for aid, conf in conflict_cases_dict.items():
        sub = obs[obs['acc_id'] == aid]
        chosen = conf["selected_vessel"]
        chosen_tier = conf["selected_tier"]
        conf_tiers = conf["conflicting_tiers"]
        
        diag_parts = []
        for ct in conf_tiers:
            t_idx = ct["tier"]
            alt_vid = ct["vid"]
            t_cond = ct["cond"]
            chosen_obs = sub[(sub['rfid_id'] == chosen) & sub['gear_match']]
            alt_obs = sub[(sub['rfid_id'] == alt_vid) & sub['gear_match']]
            diag_parts.append(
                f"Tier {t_idx} {t_cond}\uc5d0\uc11c \uc120\ubc15 {alt_vid}(\ucd5c\uadfc\uc811 dt={alt_obs['dt_h'].min()}h, dist={alt_obs['dist_km'].min():.2f}km)\uac00 "
                f"\ub2e8\uc77c \ud6c4\ubcf4\ub85c \ucd9c\ud604\ud558\uc5ec, Tier {chosen_tier} {CASCADE[chosen_tier]}\uc5d0\uc11c \uc6b0\uc120 \uc120\uc815\ub41c \uc120\ubc15 {chosen}(dt={chosen_obs['dt_h'].min()}h, dist={chosen_obs['dist_km'].min():.2f}km)\uacfc \uc2e0\uc6d0 \ucda9\ub3cc \ubc1c\uc0dd"
            )
        conf["diagnosis"] = " / ".join(diag_parts)

    conflict_json_path = ROUND9_DIR / "task1_conflict_audit.json"
    with open(conflict_json_path, "w", encoding="utf-8") as f:
        json.dump(conflict_cases_dict, f, ensure_ascii=False, indent=2)
    print(f"Saved: {conflict_json_path}")

    # ==========================================
    # 3. Stability Metrics Computation (3 Types)
    # ==========================================
    linked_df = audit_df[audit_df['status'].isin(['LINKED_CLEAN', 'LINKED_CONFLICT'])].copy()
    
    def assign_tier_group(t):
        if t in [0, 1]:
            return "Narrow (Tier 0-1, w0/r<=5km)"
        elif t in [2, 3, 4]:
            return "Medium (Tier 2-4)"
        elif t in [5, 6, 7, 8]:
            return "Broad (Tier 5-8)"
        return "Unknown"

    linked_df['group'] = linked_df['tier'].apply(assign_tier_group)

    stability_records = []
    for _, r in linked_df.iterrows():
        aid = int(r['acc_id'])
        chosen_vid = int(r['rfid_id'])
        tier = int(r['tier'])
        sub = obs[obs['acc_id'] == aid]

        tier_cands = {}
        for i, (w, rad) in enumerate(CASCADE):
            tier_cands[i] = list(candidates(sub, w, rad, gear=True)['rfid_id'].unique())

        subsequent_tiers = list(range(tier + 1, len(CASCADE)))
        subsequent_with_cands = [i for i in subsequent_tiers if len(tier_cands[i]) > 0]
        
        retention_subsequent = [chosen_vid in tier_cands[i] for i in subsequent_with_cands]
        unique_subsequent = [tier_cands[i] == [chosen_vid] for i in subsequent_with_cands]
        
        single_subsequent = [i for i in subsequent_tiers if len(tier_cands[i]) == 1]
        id_match_subsequent = [tier_cands[i][0] == chosen_vid for i in single_subsequent]

        base_cands = list(candidates(sub, 1, 5.0, gear=True)['rfid_id'].unique())
        widest_cands = list(candidates(sub, 6, 20.0, gear=True)['rfid_id'].unique())

        stability_records.append({
            "acc_id": aid,
            "group": r['group'],
            "tier": tier,
            "rfid_id": chosen_vid,
            "conflict": r['conflict'],
            "no_conflict": not r['conflict'],
            "retention_subsequent_mean": float(np.mean(retention_subsequent)) if retention_subsequent else 1.0,
            "retention_base": (chosen_vid in base_cands),
            "retention_widest": (chosen_vid in widest_cands),
            "unique_subsequent_mean": float(np.mean(unique_subsequent)) if unique_subsequent else 1.0,
            "unique_base": (base_cands == [chosen_vid]),
            "unique_widest": (widest_cands == [chosen_vid]),
            "n_cands_base": len(base_cands),
            "n_cands_widest": len(widest_cands),
            "id_match_subsequent_mean": float(np.mean(id_match_subsequent)) if single_subsequent else 1.0,
            "has_single_subsequent": len(single_subsequent) > 0,
            "n_single_subsequent": len(single_subsequent)
        })

    stab_df = pd.DataFrame(stability_records)

    stability_summary = {
        "metric_definitions": {
            "\ud6c4\ubcf4 \uc720\uc9c0\uc728 (Candidate Retention Rate)": {
                "\uc124\uba85": "\uc870\uac74 \ud655\uc7a5 \uc2dc \uc120\ud0dd\ub41c \ud6c4\ubcf4 \uc120\ubc15\uc774 \ud6c4\ubcf4\uad70\uc5d0 \uacc4\uc18d \uc794\uc874\ud558\ub294 \ube44\uc728",
                "\uc138\ubd80\uc9c0\ud45c": {
                    "retention_subsequent_mean": "\uc120\uc815 \ud2f0\uc5b4 \uc774\ud6c4 \ud6c4\uc18d CASCADE \uc870\uac74 \uc911 \ud6c4\ubcf4\uac00 \uc874\uc7ac\ud558\ub294 \uc870\uac74\ub4e4\uc5d0\uc11c \uc120\uc815 \uc120\ubc15\uc774 \ud6c4\ubcf4\uad70\uc5d0 \ud3ec\ud568\ub41c \ube44\uc728",
                    "retention_base_rate": "\uae30\uc900 \uc870\uac74 (w=1h, r=5km) \ud6c4\ubcf4\uad70\uc5d0 \uc120\uc815 \uc120\ubc15\uc774 \ud3ec\ud568\ub41c \ube44\uc728",
                    "retention_widest_rate": "\ucd5c\ub300 \uad00\uce21\ucc3d (w=6h, r=20km) \ud6c4\ubcf4\uad70\uc5d0 \uc120\uc815 \uc120\ubc15\uc774 \ud3ec\ud568\ub41c \ube44\uc728 (\ub2e8\uc870 \ud655\uc7a5 \uc2dc \uc774\ub860\uc0c1 100%)"
                }
            },
            "\ub2e8\uc77c\uc131 \uc720\uc9c0\uc728 (Uniqueness Retention Rate)": {
                "\uc124\uba85": "\uc881\uc740 \uc870\uac74\uc5d0\uc11c \ub2e8\uc77c \ud6c4\ubcf4\uc600\ub358 \ubc30\uac00 \uc870\uac74 \ud655\uc7a5 \ud6c4\uc5d0\ub3c4 \uc5ec\ud0c0 \uacbd\ud569 \uc120\ubc15\uc758 \uc9c4\uc785 \uc5c6\uc774 \uc720\uc77c\ud55c \ud6c4\ubcf4\ub85c \ub0a8\ub294 \ube44\uc728",
                "\uc138\ubd80\uc9c0\ud45c": {
                    "unique_subsequent_mean": "\ud6c4\uc18d CASCADE \uc870\uac74\ub4e4\uc5d0\uc11c \ucd94\uac00 \uacbd\ud569 \uc120\ubc15 \uc5c6\uc774 \ub2e8\uc77c \ud6c4\ubcf4 \uc0c1\ud0dc\ub97c \uc720\uc9c0\ud55c \ube44\uc728",
                    "unique_base_rate": "\uae30\uc900 \uc870\uac74 (w=1h, r=5km)\uc5d0\uc11c \uc720\uc77c\ud55c \ub2e8\uc77c \ud6c4\ubcf4\ub85c \uc720\uc9c0\ub41c \ube44\uc728",
                    "unique_widest_rate": "\ucd5c\ub300 \uad00\uce21\ucc3d (w=6h, r=20km)\uc5d0\uc11c \uc720\uc77c\ud55c \ub2e8\uc77c \ud6c4\ubcf4\ub85c \uc720\uc9c0\ub41c \ube44\uc728"
                }
            },
            "\ub300\ud45c \uc2e0\uc6d0 \uc548\uc815\uc131 (Representative Identity Stability)": {
                "\uc124\uba85": "\uc870\uac74 \ubcc0\uacbd \uc2dc \uc120\ud0dd\ub418\ub294 \uc120\ubc15 \uc2e0\uc6d0\uc758 \uc77c\uad00\uc131 \ubc0f \ucda9\ub3cc \ubd80\uc7ac \ube44\uc728",
                "\uc138\ubd80\uc9c0\ud45c": {
                    "conflict_free_rate": "\ubaa8\ub4e0 9\uac1c CASCADE \uc870\uac74\uc5d0 \uac78\uccd0 \uc2e0\uc6d0 \ubd88\uc77c\uce58\uac00 \uc804\ud600 \ubc1c\uc0dd\ud558\uc9c0 \uc54a\uc740 \uc0ac\uac74 \ube44\uc728 (1 - conflict)",
                    "id_match_single_subsequent_mean": "\ud6c4\uc18d \uc870\uac74\uc5d0\uc11c \ub2e8\uc77c \ud6c4\ubcf4\uac00 \ub2e4\uc2dc \ucd9c\ud604\ud588\uc744 \ub54c, \ucd5c\ucd08 \uc120\uc815 \uc120\ubc15\uacfc \ub3d9\uc77c \uc120\ubc15\uc77c \ud655\ub960"
                }
            }
        },
        "overall": {},
        "by_stratum": {}
    }

    def summarize_stab_group(df_group):
        n = len(df_group)
        unique_vessels = df_group['rfid_id'].nunique()
        multi_acc_vessels = (df_group['rfid_id'].value_counts() > 1).sum()
        return {
            "n_events": n,
            "distinct_vessels": unique_vessels,
            "multi_accident_vessels": int(multi_acc_vessels),
            "\ud6c4\ubcf4_\uc720\uc9c0\uc728": {
                "\ud6c4\uc18d_\ud2f0\uc5b4_\ud3c9\uade0_\uc794\uc874\uc728": round(float(df_group['retention_subsequent_mean'].mean()), 4),
                "\uae30\uc900\uc870\uac74(1h_5km)_\uc794\uc874\uc728": round(float(df_group['retention_base'].mean()), 4),
                "\ucd5c\ub300\ucc3d(6h_20km)_\uc794\uc874\uc728": round(float(df_group['retention_widest'].mean()), 4)
            },
            "\ub2e8\uc77c\uc131_\uc720\uc9c0\uc728": {
                "\ud6c4\uc18d_\ud2f0\uc5b4_\ud3c9\uade0_\ub2e8\uc77c\uc720\uc9c0\uc728": round(float(df_group['unique_subsequent_mean'].mean()), 4),
                "\uae30\uc900\uc870\uac74(1h_5km)_\ub2e8\uc77c\uc720\uc9c0\uc728": round(float(df_group['unique_base'].mean()), 4),
                "\ucd5c\ub300\ucc3d(6h_20km)_\ub2e8\uc77c\uc720\uc9c0\uc728": round(float(df_group['unique_widest'].mean()), 4),
                "\uae30\uc900\uc870\uac74_\ud3c9\uade0_\ud6c4\ubcf4\uc218": round(float(df_group['n_cands_base'].mean()), 2),
                "\ucd5c\ub300\ucc3d_\ud3c9\uade0_\ud6c4\ubcf4\uc218": round(float(df_group['n_cands_widest'].mean()), 2)
            },
            "\ub300\ud45c_\uc2e0\uc6d0_\uc548\uc815\uc131": {
                "\ucda9\ub3cc_\ubd80\uc7ac\uc728(\uc2e0\uc6d0\uc77c\uce58\uc728)": round(float(df_group['no_conflict'].mean()), 4),
                "\ucda9\ub3cc_\ubc1c\uc0dd\uac74\uc218": int(df_group['conflict'].sum()),
                "\ub2e8\uc77c\ucd9c\ud604_\ud6c4\uc18d\uc870\uac74_\uc2e0\uc6d0\uc77c\uce58\uc728": round(float(df_group['id_match_subsequent_mean'].mean()), 4)
            }
        }

    stability_summary["overall"] = summarize_stab_group(stab_df)

    strata_order = [
        "Narrow (Tier 0-1, w0/r<=5km)",
        "Medium (Tier 2-4)",
        "Broad (Tier 5-8)"
    ]
    for st in strata_order:
        sub_grp = stab_df[stab_df['group'] == st]
        stability_summary["by_stratum"][st] = summarize_stab_group(sub_grp)

    stability_json_path = ROUND9_DIR / "task1_linkage_stability_metrics.json"
    with open(stability_json_path, "w", encoding="utf-8") as f:
        json.dump(stability_summary, f, ensure_ascii=False, indent=2)
    print(f"Saved: {stability_json_path}")

    # ==========================================
    # 4. Unlinked Breakdown Analysis (67 cases)
    # ==========================================
    unlinked_summary = {
        "total_unlinked_cases": 67,
        "category_counts": {k: len(v) for k, v in unlinked_breakdown.items()},
        "category_percentages": {k: round(len(v) / 67 * 100, 2) for k, v in unlinked_breakdown.items()},
        "categories": {
            "UNLINKED_NO_OBS": {
                "count": len(unlinked_breakdown["UNLINKED_NO_OBS"]),
                "description": "\uc0ac\uace0 \ubc1c\uc0dd \uc2dc\uac01 \u00b16h \ubc0f \ubc18\uacbd 20km \uc774\ub0b4\uc5d0 \ud574\uc591 \uad00\uce21 \ud589(AIS/RFID)\uc774 0\uac74\uc73c\ub85c \uc644\uc804\ud788 \ubd80\uc7ac",
                "cases": unlinked_breakdown["UNLINKED_NO_OBS"]
            },
            "UNLINKED_GEAR_MISMATCH": {
                "count": len(unlinked_breakdown["UNLINKED_GEAR_MISMATCH"]),
                "description": "\uc2dc\uacf5\uac04 \uad00\uce21\uc740 \ub2e4\uc218 \uc874\uc7ac\ud558\ub098, \uc0ac\uace0 \uc120\ubc15\uc758 \uc5b4\uc5c5\uba74\ud5c8\uc640 \uc77c\uce58\ud558\ub294 \uc120\ubc15\uc774 \uc804\ubb34\ud558\uc5ec \uc804\uc6d0 \uc81c\uc678",
                "cases": unlinked_breakdown["UNLINKED_GEAR_MISMATCH"]
            },
            "UNLINKED_COMPETITION": {
                "count": len(unlinked_breakdown["UNLINKED_COMPETITION"]),
                "description": "CASCADE \uc870\uac74 \ub0b4 \uc5b4\uc5c5\uba74\ud5c8 \uc77c\uce58 \uc120\ubc15\uc774 \uc874\uc7ac\ud558\ub098, \ud6c4\ubcf4\uac00 \ub098\ud0c0\ub098\ub294 \ubaa8\ub4e0 \uc870\uac74\uc5d0\uc11c 2\ucc99 \uc774\uc0c1 \ud56d\uc0c1 \uacbd\ud569\ud558\uc5ec \ub2e8\uc77c \ud6c4\ubcf4 \ud2b9\uc815 \ubd88\uac00",
                "distance_stats_km": {
                    "min": round(float(np.min([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_COMPETITION"]])), 2),
                    "mean": round(float(np.mean([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_COMPETITION"]])), 2),
                    "median": round(float(np.median([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_COMPETITION"]])), 2),
                    "max": round(float(np.max([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_COMPETITION"]])), 2),
                },
                "cases": unlinked_breakdown["UNLINKED_COMPETITION"]
            },
            "UNLINKED_OUT_OF_CASCADE": {
                "count": len(unlinked_breakdown["UNLINKED_OUT_OF_CASCADE"]),
                "description": "\uc5b4\uc5c5\uba74\ud5c8 \uc77c\uce58 \uc120\ubc15\uc774 \uad00\uce21\ucc3d(\u00b16h/20km) \ub0b4\uc5d0 \uc874\uc7ac\ud558\ub098, 9\uac1c CASCADE \uc870\uac74(\uac70\ub9ac<=10km, \uc2dc\uac04<=3h \ub4f1) \uc678\uacfd\uc5d0\ub9cc \uc704\uce58",
                "distance_stats_km": {
                    "min": round(float(np.min([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_OUT_OF_CASCADE"]])), 2),
                    "mean": round(float(np.mean([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_OUT_OF_CASCADE"]])), 2),
                    "median": round(float(np.median([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_OUT_OF_CASCADE"]])), 2),
                    "max": round(float(np.max([c["min_dist_gear_km"] for c in unlinked_breakdown["UNLINKED_OUT_OF_CASCADE"]])), 2),
                },
                "cases": unlinked_breakdown["UNLINKED_OUT_OF_CASCADE"]
            }
        }
    }

    unlinked_json_path = ROUND9_DIR / "task1_unlinked_breakdown.json"
    with open(unlinked_json_path, "w", encoding="utf-8") as f:
        json.dump(unlinked_summary, f, ensure_ascii=False, indent=2)
    print(f"Saved: {unlinked_json_path}")

    # ==========================================
    # 5. Definitions of Analysis Sets
    # ==========================================
    clean_vessels = linked_df.loc[~linked_df['conflict'], 'rfid_id'].unique()
    narrow_vessels = linked_df.loc[linked_df['tier'].isin([0, 1]), 'rfid_id'].unique()

    print("\n=== Dataset Definitions ===")
    print(f"Primary Analysis Set (LINKED_CLEAN): {len(linked_df[~linked_df['conflict']])}\uac74 / {len(clean_vessels)}\ucc99")
    print(f"High-Confidence Narrow Set (Tier 0-1): {len(linked_df[linked_df['tier'].isin([0, 1])])}\uac74 / {len(narrow_vessels)}\ucc99")

    elapsed = round(time.monotonic() - start_time, 2)
    print(f"\n[Task 1 Execution Completed in {elapsed}s]")


if __name__ == "__main__":
    main()
