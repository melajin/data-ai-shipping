import unittest
import pandas as pd
from linkage import candidates, choose_event


def rows(items):
    return pd.DataFrame([{"rfid_id": v, "dt_h": dt, "dist_km": dist,
                          "row_ts": 100 + dt, "source_month": 1,
                          "source_row_index": i, "gear_match": gear}
                         for i, (v, dt, dist, gear) in enumerate(items)])


class LinkageRegression(unittest.TestCase):
    def test_hidden_same_hour_candidate(self):
        d = rows([(1, 0, 1.8, True), (1, 4, 1.2, True)])
        self.assertEqual(set(candidates(d, 0, 2).rfid_id), {1})

    def test_spurious_single_becomes_two(self):
        d = rows([(1, 6, .1, True), (1, 0, 1, True), (2, 0, 1.5, True)])
        old = d.sort_values(["rfid_id", "dist_km", "dt_h"]).drop_duplicates("rfid_id")
        self.assertEqual(set(candidates(old, 0, 2).rfid_id), {2})
        self.assertEqual(set(candidates(d, 0, 2).rfid_id), {1, 2})

    def test_duplicates_do_not_inflate_vessels(self):
        self.assertEqual(len(candidates(rows([(1, 0, 1, True)] * 3), 0, 2)), 1)

    def test_witness_inside_chosen_tier(self):
        picked = choose_event(rows([(1, 0, 1.8, True), (1, 4, 1.2, True)]))
        self.assertEqual((picked["dt_h"], picked["dist_km"], picked["tier"]), (0, 1.8, 0))

    def test_non_nested_conflict_preserved(self):
        picked = choose_event(rows([(1, 0, 4, True), (2, 1, 1, True)]))
        self.assertEqual(picked["rfid_id"], 1)
        self.assertTrue(picked["conflict"])

    def test_gear_filter(self):
        d = rows([(1, 0, 1, False), (2, 0, 1, True)])
        self.assertEqual(set(candidates(d, 0, 2).rfid_id), {2})
        self.assertEqual(set(candidates(d, 0, 2, gear=False).rfid_id), {1, 2})

    def test_inclusive_boundaries(self):
        self.assertEqual(len(candidates(rows([(1, 6, 20, True)]), 6, 20)), 1)

    def test_empty_and_no_match(self):
        d = rows([(1, 6, 20, True)])
        self.assertIsNone(choose_event(d))
        self.assertIsNone(choose_event(d.iloc[:0]))

    def test_tied_witness_stable_under_permutation(self):
        d = rows([(1, 0, 1, True), (1, 0, 1, True)])
        a, b = choose_event(d), choose_event(d.iloc[::-1])
        self.assertEqual(a["source_row_index"], b["source_row_index"])


if __name__ == "__main__":
    unittest.main()
