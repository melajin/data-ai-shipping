# -*- coding: utf-8 -*-
"""Round013 Utility Module — RAM monitoring, hashing, logging, and core calculations.
"""
import os
import hashlib
import datetime
import psutil
import numpy as np


RAM_THRESHOLD_MIB = 768.0
KST = datetime.timezone(datetime.timedelta(hours=9))


def get_now_kst_iso():
    return datetime.datetime.now(KST).isoformat()


def get_ram_status():
    vm = psutil.virtual_memory()
    proc = psutil.Process()
    avail_mib = vm.available / (1024 * 1024)
    total_mib = vm.total / (1024 * 1024)
    rss_mib = proc.memory_info().rss / (1024 * 1024)
    return {
        "timestamp_kst": get_now_kst_iso(),
        "available_mib": round(avail_mib, 2),
        "total_mib": round(total_mib, 2),
        "process_rss_mib": round(rss_mib, 2),
        "threshold_mib": RAM_THRESHOLD_MIB,
        "is_sufficient": avail_mib >= RAM_THRESHOLD_MIB,
    }


def assert_ram_sufficient(phase_name="operation", estimated_peak_mib=512.0):
    status = get_ram_status()
    log_msg = (
        f"[RAM CHECK] [{phase_name}] Available: {status['available_mib']} MiB "
        f"(Total: {status['total_mib']} MiB, Process RSS: {status['process_rss_mib']} MiB). "
        f"Est. peak: {estimated_peak_mib} MiB. Sufficient: {status['is_sufficient']}"
    )
    print(log_msg)
    append_log(log_msg)
    if not status["is_sufficient"]:
        raise MemoryError(
            f"Available RAM ({status['available_mib']} MiB) is below threshold ({RAM_THRESHOLD_MIB} MiB). "
            f"Operation '{phase_name}' postponed."
        )
    return status


def append_log(message, log_file="testB/round_013_20261105/execution.log"):
    timestamp = get_now_kst_iso()
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def compute_file_sha256(filepath):
    if not os.path.exists(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_lin_window(rows_ts, rows_len, rows_bbox, h, w):
    """Compute lin_w(h) = sum(bbox) / sum(len) over valid rows in trailing window [h-w+1, h].
    rows_ts: 1D array of sorted observation ts for this voyage.
    rows_len: 1D array of len_m.
    rows_bbox: 1D array of bbox_m.
    h: integer epoch-hour window end.
    w: window size (7 or 3).
    """
    t_start_win = h - w + 1
    t_end_win = h
    
    in_win = (rows_ts >= t_start_win) & (rows_ts <= t_end_win)
    if not np.any(in_win):
        return np.nan
        
    lens = rows_len[in_win]
    bboxes = rows_bbox[in_win]
    
    finite_mask = np.isfinite(lens) & np.isfinite(bboxes)
    n_finite = int(np.sum(finite_mask))
    
    valid_mask = finite_mask & (lens >= 1.0)
    n_valid = int(np.sum(valid_mask))
    
    if w == 7:
        if n_finite < 4 or n_valid < 3:
            return np.nan
    elif w == 3:
        if n_finite < 2 or n_valid < 2:
            return np.nan
    else:
        raise ValueError(f"Unsupported w={w}")
        
    sum_bbox = np.sum(bboxes[valid_mask])
    sum_len = np.sum(lens[valid_mask])
    if sum_len <= 0:
        return np.nan
    return float(sum_bbox / sum_len)


def compute_voyage_collapse(rows_ts, rows_len, rows_bbox, w):
    """Compute lin_min_w and t_collapse_w across all candidate integer hours h.
    h ranges from t_start + w - 1 to t_end.
    Tie-breaking: earliest h with strictly minimal lin.
    Returns: (valid_bool, lin_min_w, t_collapse_w, n_valid_h)
    """
    if len(rows_ts) == 0:
        return False, np.nan, np.nan, 0
        
    t_start = int(rows_ts[0])
    t_end = int(rows_ts[-1])
    
    if t_start + w - 1 > t_end:
        return False, np.nan, np.nan, 0
        
    best_lin = None
    best_h = None
    valid_count = 0
    
    for h in range(t_start + w - 1, t_end + 1):
        val = compute_lin_window(rows_ts, rows_len, rows_bbox, h, w)
        if not np.isnan(val):
            valid_count += 1
            if best_lin is None or val < best_lin:
                best_lin = val
                best_h = h
                
    if best_lin is None:
        return False, np.nan, np.nan, 0
    return True, best_lin, best_h, valid_count
