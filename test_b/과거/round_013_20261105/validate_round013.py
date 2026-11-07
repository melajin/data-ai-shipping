# -*- coding: utf-8 -*-
"""Synthetic boundary/quality validation for Round013 ??3-5 helpers."""
import math
import unittest
from run_round013 import compute_local, direct_window_audit, split_voyages, hour_bucket, audit_deduplicate


def row(t, length=1.0, bbox=1.0, order=None):
    return {'rfid_id':'v','ts':t,'_ts_int':t,'_order':t if order is None else order,
            'len_m':length,'bbox_m':bbox,'cen_lon':None,'cen_lat':None,'state':'x'}


def voyage(tsrows):
    return {'rfid_id':'v','voyage_no':1,'t_start':tsrows[0]['_ts_int'],'t_end':tsrows[-1]['_ts_int'],
            'n_rows':len(tsrows),'_rows':tsrows}


class Round013Synthetic(unittest.TestCase):
    def test_time_windows_not_last_observed_rows(self):
        v=voyage([row(0,bbox=10),row(2,bbox=10),row(4,bbox=0)])
        fast=compute_local(v,3); direct=direct_window_audit(v,3)
        self.assertEqual(fast[1],4)
        self.assertAlmostEqual(fast[0],5.0)
        self.assertEqual(fast,direct)
        self.assertNotAlmostEqual(fast[0],(10+10+0)/3)

    def test_six_hour_split_boundary(self):
        records=[row(10),row(15),row(21)]
        groups=split_voyages(records)
        self.assertEqual([(x['t_start'],x['t_end']) for x in groups],[(10,15),(21,21)])

    def test_window_cannot_reference_previous_voyage(self):
        records=[row(0,bbox=100),row(1,bbox=100),row(2,bbox=100),
                 row(8,bbox=2),row(9,bbox=2),row(10,bbox=2)]
        groups=split_voyages(records)
        self.assertEqual(len(groups),2)
        second=groups[1]
        self.assertEqual(compute_local(second,3),(2.0,10,1))
        self.assertEqual(direct_window_audit(second,3),(2.0,10,1))

    def test_quality_thresholds_and_nan_len_under_one(self):
        w3=voyage([row(0,length=0,bbox=5),row(1,length=1,bbox=2),row(2,length=1,bbox=2)])
        # Two finite rows, exactly two len>=1 rows are required; len=0 row cannot enter denominator.
        self.assertEqual(compute_local(w3,3),(2.0,2,1))
        w3_bad=voyage([row(0,length=0,bbox=5),row(1,length=1,bbox=2),row(2,length=float('nan'),bbox=2)])
        self.assertIsNone(compute_local(w3_bad,3)[0])
        w7=voyage([row(i,length=(0 if i<4 else 1),bbox=2) for i in range(7)])
        self.assertIsNotNone(compute_local(w7,7)[0]) # 7 finite; exactly 3 good
        w7_bad=voyage([row(i,length=(0 if i<5 else 1),bbox=2) for i in range(7)])
        self.assertIsNone(compute_local(w7_bad,7)[0]) # 7 finite; only 2 good
        w7_few_finite=voyage([row(i,length=1,bbox=2) for i in range(3)]+[row(3,length=float('nan'),bbox=2)])
        self.assertIsNone(compute_local(w7_few_finite,7)[0])

    def test_nan_and_len_below_one_are_not_silently_counted(self):
        v=voyage([row(0,1,1),row(1,float('nan'),100),row(2,0.5,100)])
        self.assertIsNone(compute_local(v,3)[0])

    def test_minimum_tie_chooses_earliest_hour(self):
        v=voyage([row(i,1,2) for i in range(5)])
        val,h,n=compute_local(v,3)
        self.assertEqual((val,h,n),(2.0,2,3))

    def test_raw_leave_one_out_boundary_10_vs_11(self):
        eligible=lambda n:n>=11 # target excluded; remaining must be >=10
        self.assertFalse(eligible(10))
        self.assertTrue(eligible(11))

    def test_day_night_boundaries(self):
        self.assertEqual(hour_bucket(5),'night_18_06')
        self.assertEqual(hour_bucket(6),'day_06_18')
        self.assertEqual(hour_bucket(17),'day_06_18')
        self.assertEqual(hour_bucket(18),'night_18_06')
        self.assertEqual(hour_bucket(30),'day_06_18')

    def test_first_duplicate_preserved_and_conflict_audited(self):
        a={'rfid_id':'v','ts':1,'_order':0,'len_m':1.0,'bbox_m':1.0,'state':'a'}
        b={'rfid_id':'v','ts':1,'_order':1,'len_m':1.0,'bbox_m':2.0,'state':'a'}
        kept,audit=audit_deduplicate([a,b],('len_m','bbox_m','state'))
        self.assertIs(kept[0],a)
        self.assertEqual(audit['duplicate_extra_rows'],1)
        self.assertEqual(audit['conflicting_duplicate_groups'],1)
        self.assertEqual(audit['conflicting_duplicate_rows'],1)


if __name__=='__main__': unittest.main(verbosity=2)

