# -*- coding: utf-8 -*-
"""Synthetic unit checks for the Round013 ??6-7 fixed procedures."""
import unittest
from g6_selection_and_confidence import eligibility_reason,select_minimum,rank_confidence,observed_midpoint
from g7_evaluate import baseline_probability,passes,exact_mde,cluster_bootstrap,upper_tail

class Round013PostSynthetic(unittest.TestCase):
    def test_10_vs_11_valid_and_raw_history_gate(self):
        self.assertEqual(eligibility_reason(10,10),'raw_history_insufficient')
        self.assertEqual(eligibility_reason(11,10),'valid_history_insufficient')
        self.assertEqual(eligibility_reason(11,0),'no_valid_voyage')
        self.assertEqual(eligibility_reason(11,11),'eligible')
        self.assertEqual(eligibility_reason(12,11),'eligible')

    def test_minimum_and_exact_ties_choose_earliest_start_then_number(self):
        rows=[{'_score':0.1,'t_start':20,'voyage_no':1},
              {'_score':0.1,'t_start':10,'voyage_no':2},
              {'_score':0.1,'t_start':10,'voyage_no':1},
              {'_score':0.2,'t_start':1,'voyage_no':1}]
        self.assertEqual(select_minimum(rows)['voyage_no'],1)
        self.assertEqual(select_minimum(rows)['t_start'],10)

    def test_midpoint_is_sorted_observed_row_at_floor_n_over_2(self):
        self.assertEqual(observed_midpoint([3,8]),8)
        self.assertEqual(observed_midpoint([2,4,6,8]),6)
        self.assertIsNone(observed_midpoint([]))

    def test_baseline_includes_both_voyage_endpoints_and_excludes_outside(self):
        self.assertAlmostEqual(baseline_probability(20,25,14),1/6) # acc+6 touches first hour
        self.assertAlmostEqual(baseline_probability(20,25,31),1/6) # acc-6 touches last hour
        self.assertEqual(baseline_probability(20,25,12),0.0)
        self.assertEqual(baseline_probability(20,25,33),0.0)
        self.assertEqual(baseline_probability(20,25,20),1.0) # all six hours overlap the 13-hour event window

    def test_midrank_confidence_tie_formula(self):
        r=rank_confidence(1.0,[1.0,1.0,2.0,3.0])
        self.assertEqual((r['less'],r['equal'],r['n_reference']),(0,2,4))
        self.assertEqual(r['rank_percentile'],0.25)
        self.assertEqual(r['confidence'],0.75)
        self.assertEqual(rank_confidence(1.0,[2.0,3.0])['confidence'],1.0)

    def test_cluster_bootstrap_resamples_vessel_with_all_its_events(self):
        groups={'multi':[{'collapse_hit':1},{'collapse_hit':1}],
                'single':[{'collapse_hit':0}]}
        b=cluster_bootstrap(groups,reps=500,seed=11)
        self.assertTrue(b['defined'])
        self.assertEqual(b['clusters'],2)
        self.assertEqual(b['lower'],0.0)
        self.assertEqual(b['upper'],1.0)
        self.assertEqual(b['unique_bootstrap_rates'],[0.0,2/3,1.0])

    def test_two_test_bonferroni_and_preregistered_boundary(self):
        self.assertTrue(passes(0.12,min(1,2*0.024)))
        self.assertFalse(passes(0.119,min(1,2*0.024)))
        self.assertFalse(passes(0.12,min(1,2*0.025))) # adjusted p equals .05, strict less-than fails
        self.assertFalse(passes(0.5,min(1,2*0.03)))

    def test_exact_binomial_mde_threshold_and_power(self):
        m=exact_mde(60,0.04,alpha=0.025,power=0.8)
        self.assertTrue(m['defined'])
        self.assertLessEqual(upper_tail(m['critical_k'],60,0.04),0.025)
        self.assertGreater(upper_tail(m['critical_k']-1,60,0.04),0.025)
        self.assertGreaterEqual(upper_tail(m['critical_k'],60,m['minimum_alternative_p']),0.8)
        self.assertLess(upper_tail(m['critical_k'],60,m['minimum_alternative_p']-1e-5),0.8)
        self.assertGreater(m['mde_absolute'],0)

    def test_mde_extreme_and_zero_denominator_cases(self):
        zero=exact_mde(0,None)
        self.assertFalse(zero['defined'])
        pzero=exact_mde(10,0.0,alpha=.025,power=.8)
        self.assertTrue(pzero['defined'])
        self.assertEqual(pzero['critical_k'],1)
        self.assertAlmostEqual(pzero['minimum_alternative_p'],1-0.2**0.1,places=10)
        p1=exact_mde(10,1.0)
        self.assertFalse(p1['defined'])

    def test_linear_percentile_interpolation(self):
        from g7_evaluate import linear_quantile
        self.assertAlmostEqual(linear_quantile([0,1,2,3],.5),1.5)

if __name__=='__main__': unittest.main(verbosity=2)
