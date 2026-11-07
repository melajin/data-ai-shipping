# -*- coding: utf-8 -*-
"""Round013 Synthetic Tests — §4/§5 Core Logic Validation.

Covers all 8 synthetic verification conditions specified in SUPERVISOR_TASK_01.md:
1. Time window vs row window (시간 공백/시간창 대 행창)
2. 6h split boundary (6h 분할 경계)
3. Voyage boundary backreference prevention (항차 경계 역참조 차단)
4. Quality conditions boundary for w=3 and w=7 (품질 조건 각 경계)
5. NaN and len < 1 handling (NaN/len<1)
6. Tie-breaking to earliest h (동률 최소값)
7. 10 vs 11 voyages: remaining >= 10 (10 대 11 항차)
8. Day/night boundary [06, 18) vs remainder (주야간 경계)
Plus sample direct calculation cross-check.
"""
import unittest
import numpy as np
import pandas as pd


def compute_lin_window(rows_ts, rows_len, rows_bbox, h, w):
    """Compute lin_w(h) for a trailing time window [h-w+1, h].
    rows_ts, rows_len, rows_bbox: observations in the voyage.
    """
    t_start_win = h - w + 1
    t_end_win = h
    
    # Filter observation rows strictly within the time window
    in_win = (rows_ts >= t_start_win) & (rows_ts <= t_end_win)
    if not np.any(in_win):
        return np.nan
    
    lens = rows_len[in_win]
    bboxes = rows_bbox[in_win]
    
    # Finite check
    finite_mask = np.isfinite(lens) & np.isfinite(bboxes)
    n_finite = int(np.sum(finite_mask))
    
    # Valid check: finite and len >= 1.0
    valid_mask = finite_mask & (lens >= 1.0)
    n_valid = int(np.sum(valid_mask))
    
    # Quality conditions
    if w == 7:
        if n_finite < 4 or n_valid < 3:
            return np.nan
    elif w == 3:
        if n_finite < 2 or n_valid < 2:
            return np.nan
    else:
        raise ValueError(f"Unsupported window size w={w}")
    
    # lin = sum(bbox_valid) / sum(len_valid)
    sum_bbox = np.sum(bboxes[valid_mask])
    sum_len = np.sum(lens[valid_mask])
    if sum_len <= 0:
        return np.nan
    return float(sum_bbox / sum_len)


def compute_voyage_collapse(rows_ts, rows_len, rows_bbox, w):
    """Compute lin_min_w and t_collapse_w for a voyage.
    h ranges from t_start + w - 1 to t_end (all integer hours).
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


class TestSyntheticLogic(unittest.TestCase):
    
    def test_01_time_window_vs_row_window(self):
        """1. Time window vs row window.
        Observations at t=[0, 1, 5].
        For w=3, at h=5, time window is [3, 5], containing only t=5 (1 row).
        A row window of 3 would wrongly pick [0, 1, 5] (3 rows).
        Must evaluate to NaN because n_finite=1 < 2.
        """
        ts = np.array([0, 1, 5])
        ln = np.array([10.0, 10.0, 10.0])
        bb = np.array([5.0, 5.0, 5.0])
        
        # h=5, w=3 -> [3, 5] -> only row at t=5
        val = compute_lin_window(ts, ln, bb, h=5, w=3)
        self.assertTrue(np.isnan(val), "h=5 should be NaN because time window [3,5] only has 1 observation")
        
        # h=2, w=3 -> [0, 2] -> rows at t=0, 1 (2 rows, len>=1) -> Valid!
        val_h2 = compute_lin_window(ts, ln, bb, h=2, w=3)
        self.assertAlmostEqual(val_h2, 10.0 / 20.0, places=6)

    def test_02_six_hour_split_boundary(self):
        """2. 6h split boundary.
        diff < 6 stays in same voyage, diff >= 6 splits.
        """
        ts = np.array([10, 15, 21, 26])
        diffs = np.diff(ts)
        self.assertEqual(diffs[0], 5)  # same voyage
        self.assertEqual(diffs[1], 6)  # new voyage!
        self.assertEqual(diffs[2], 5)  # same voyage
        
        seg = np.concatenate([[0], np.cumsum(diffs >= 6)])
        self.assertEqual(list(seg), [0, 0, 1, 1])

    def test_03_voyage_boundary_backreference_prevention(self):
        """3. Voyage boundary backreference prevention.
        Voyage 1 starts at t=21. h candidate starts at 21 + w - 1.
        Trailing window never looks back at voyage 0 (which ended at 15).
        """
        # Voyage 1 data: t=21, 22, 23
        ts1 = np.array([21, 22, 23])
        ln1 = np.array([10.0, 10.0, 10.0])
        bb1 = np.array([2.0, 3.0, 4.0])
        
        # for w=3, candidate h starts at 21 + 3 - 1 = 23
        valid, lin_min, t_col, count = compute_voyage_collapse(ts1, ln1, bb1, w=3)
        self.assertTrue(valid)
        self.assertEqual(t_col, 23)
        self.assertAlmostEqual(lin_min, (2.0 + 3.0 + 4.0) / 30.0, places=6)

    def test_04_quality_conditions_boundary(self):
        """4. Quality conditions boundary for w=7 and w=3."""
        # For w=7: n_finite >= 4 and n_valid >= 3
        # Subcase 4A: 3 finite rows, all len>=1 -> n_finite=3, n_valid=3 -> Fail
        ts = np.array([0, 1, 2])
        ln = np.array([10.0, 10.0, 10.0])
        bb = np.array([1.0, 1.0, 1.0])
        self.assertTrue(np.isnan(compute_lin_window(ts, ln, bb, h=6, w=7)))
        
        # Subcase 4B: 4 finite rows, but only 2 len>=1 -> n_finite=4, n_valid=2 -> Fail
        ts = np.array([0, 1, 2, 3])
        ln = np.array([10.0, 10.0, 0.5, 0.8])
        bb = np.array([1.0, 1.0, 1.0, 1.0])
        self.assertTrue(np.isnan(compute_lin_window(ts, ln, bb, h=6, w=7)))
        
        # Subcase 4C: 4 finite rows, 3 len>=1 -> n_finite=4, n_valid=3 -> Pass!
        ts = np.array([0, 1, 2, 3])
        ln = np.array([10.0, 10.0, 10.0, 0.5])
        bb = np.array([1.0, 1.0, 1.0, 1.0])
        # Only the 3 rows with len>=1 are in valid_mask: sum(bb)=3, sum(ln)=30 -> 0.1
        val_4c = compute_lin_window(ts, ln, bb, h=6, w=7)
        self.assertAlmostEqual(val_4c, 3.0 / 30.0, places=6)
        
        # For w=3: n_finite >= 2 and n_valid >= 2
        # Subcase 4D: 1 finite row -> Fail
        ts3 = np.array([0])
        ln3 = np.array([10.0])
        bb3 = np.array([1.0])
        self.assertTrue(np.isnan(compute_lin_window(ts3, ln3, bb3, h=2, w=3)))
        
        # Subcase 4E: 2 finite rows, 1 len>=1, 1 len<1 -> Fail
        ts3 = np.array([0, 1])
        ln3 = np.array([10.0, 0.5])
        bb3 = np.array([1.0, 1.0])
        self.assertTrue(np.isnan(compute_lin_window(ts3, ln3, bb3, h=2, w=3)))
        
        # Subcase 4F: 2 finite rows, 2 len>=1 -> Pass!
        ts3 = np.array([0, 1])
        ln3 = np.array([10.0, 10.0])
        bb3 = np.array([2.0, 4.0])
        self.assertAlmostEqual(compute_lin_window(ts3, ln3, bb3, h=2, w=3), 6.0 / 20.0, places=6)

    def test_05_nan_and_len_less_than_1(self):
        """5. NaN and len < 1 handling."""
        ts = np.array([0, 1, 2, 3])
        ln = np.array([np.nan, 10.0, 10.0, 0.5])
        bb = np.array([5.0, 2.0, 2.0, np.nan])
        # row 0: ln is nan -> not finite
        # row 1: ln=10, bb=2 -> finite, valid
        # row 2: ln=10, bb=2 -> finite, valid
        # row 3: bb is nan -> not finite
        # n_finite = 2, n_valid = 2
        # For w=3, h=2: window [0, 2] -> rows 0, 1, 2 -> finite: rows 1, 2 (2) -> valid: 2 -> Pass!
        val = compute_lin_window(ts, ln, bb, h=2, w=3)
        self.assertAlmostEqual(val, 4.0 / 20.0, places=6)

    def test_06_tie_breaking(self):
        """6. Tie-breaking to earliest h.
        If lin_min is equal at h=10 and h=14, t_collapse must be 10.
        """
        ts = np.array([8, 9, 10, 12, 13, 14])
        # At h=10 (window [8, 10]): rows 8, 9, 10. Say lin = 0.10
        # At h=14 (window [12, 14]): rows 12, 13, 14. Say lin = 0.10
        ln = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
        bb = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        
        valid, lin_min, t_col, count = compute_voyage_collapse(ts, ln, bb, w=3)
        self.assertTrue(valid)
        self.assertAlmostEqual(lin_min, 3.0 / 30.0, places=6)
        self.assertEqual(t_col, 10, "Earliest h must be chosen among identical minimum lin values")

    def test_07_ten_vs_eleven_voyages(self):
        """7. 10 vs 11 voyages: remaining >= 10."""
        # Vessel A: 10 voyages -> hold out 1 -> 9 remaining (< 10) -> Ineligible
        n_voy_A = 10
        rem_ge_10_A = (n_voy_A - 1) >= 10
        self.assertFalse(rem_ge_10_A)
        self.assertEqual(n_voy_A >= 11, rem_ge_10_A)
        
        # Vessel B: 11 voyages -> hold out 1 -> 10 remaining (>= 10) -> Eligible
        n_voy_B = 11
        rem_ge_10_B = (n_voy_B - 1) >= 10
        self.assertTrue(rem_ge_10_B)
        self.assertEqual(n_voy_B >= 11, rem_ge_10_B)

    def test_08_day_night_boundary(self):
        """8. Day/night boundary: [06, 18) vs remainder."""
        def is_daytime(ts):
            h = ts % 24
            return 6 <= h < 18
            
        self.assertFalse(is_daytime(5))    # 05:00 -> Night
        self.assertTrue(is_daytime(6))     # 06:00 -> Day
        self.assertTrue(is_daytime(12))    # 12:00 -> Day
        self.assertTrue(is_daytime(17))    # 17:00 -> Day
        self.assertFalse(is_daytime(18))   # 18:00 -> Night
        self.assertFalse(is_daytime(23))   # 23:00 -> Night
        self.assertFalse(is_daytime(0))    # 00:00 -> Night
        self.assertFalse(is_daytime(24 + 5)) # 05:00 next day -> Night
        self.assertTrue(is_daytime(24 + 6))  # 06:00 next day -> Day

    def test_09_independent_direct_summation_cross_check(self):
        """9. Independent direct summation cross check on sample multi-row voyage."""
        # Simulated voyage with gaps and varying len/bbox
        ts = np.array([100, 101, 102, 103, 105, 106, 107, 108])  # gap at 104
        ln = np.array([12.0, 15.0,  0.5, 20.0, 30.0, 25.0, 18.0, 22.0])  # ts=102 has len < 1.0
        bb = np.array([ 3.0,  5.0,  0.2,  4.0,  8.0,  2.0,  3.0,  4.0])
        
        # Test both w=3 and w=7
        for w in (3, 7):
            valid, lin_min, t_col, count = compute_voyage_collapse(ts, ln, bb, w=w)
            self.assertTrue(valid)
            
            # Independent naive direct calculation
            naive_records = []
            for h in range(100 + w - 1, 108 + 1):
                # explicitly collect all rows with ts in [h-w+1, h]
                collected_bb = []
                collected_ln = []
                n_fin = 0
                for t_i, l_i, b_i in zip(ts, ln, bb):
                    if h - w + 1 <= t_i <= h:
                        if np.isfinite(l_i) and np.isfinite(b_i):
                            n_fin += 1
                            if l_i >= 1.0:
                                collected_bb.append(b_i)
                                collected_ln.append(l_i)
                n_val = len(collected_ln)
                is_qual = (n_fin >= 4 and n_val >= 3) if w == 7 else (n_fin >= 2 and n_val >= 2)
                if is_qual:
                    val = sum(collected_bb) / sum(collected_ln)
                    naive_records.append((val, h))
            
            # Find min with earliest h tie-breaking
            min_val = min(r[0] for r in naive_records)
            earliest_h = min(r[1] for r in naive_records if r[0] == min_val)
            
            self.assertAlmostEqual(lin_min, min_val, places=7)
            self.assertEqual(t_col, earliest_h)
            self.assertEqual(count, len(naive_records))



if __name__ == '__main__':
    unittest.main()
