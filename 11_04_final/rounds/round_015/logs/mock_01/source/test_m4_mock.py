"""Pure standard-library contract mock for the round015 M4 helpers."""

from __future__ import annotations

import sys
import unittest

from m4_synthetic import (
    CALL_LIMITS,
    REQUIRED_CALLS,
    CallBudget,
    MergeGuard,
    canonicalize_member_logits,
    capture_target_only,
    member_target_labels,
)


class Round015M4MockTests(unittest.TestCase):
    def test_stdlib_only_import_and_explicit_permutation_direction(self) -> None:
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("numpy", sys.modules)
        permutation = [2, 0, 3, 1]
        self.assertEqual(member_target_labels([0, 1, 2, 3], permutation), [2, 0, 3, 1])
        # Canonical class k is found at member output index p[k].
        member_logits = [[10.0, 20.0, 30.0, 40.0]]
        self.assertEqual(canonicalize_member_logits(member_logits, permutation), [[30.0, 10.0, 40.0, 20.0]])
        self.assertEqual(sorted(permutation), [0, 1, 2, 3])

    def test_context_rows_are_removed_before_a_detached_target_copy(self) -> None:
        hidden = [[[float(row), float(row + 100)] for row in range(20)]]
        logits = [[[float(row), float(row + 1), float(row + 2), float(row + 3)] for row in range(20)]]
        target_hidden, target_logits = capture_target_only(hidden, logits, train_size=16, expected_total_rows=20)
        self.assertEqual(target_hidden, [[[16.0, 116.0], [17.0, 117.0], [18.0, 118.0], [19.0, 119.0]]])
        self.assertEqual(target_logits[0][0], [16.0, 17.0, 18.0, 19.0])
        hidden[0][16][0] = -999.0
        logits[0][16][0] = -999.0
        self.assertEqual(target_hidden[0][0][0], 16.0)
        self.assertEqual(target_logits[0][0][0], 16.0)
        with self.assertRaises(ValueError):
            capture_target_only(hidden, logits, train_size=16, expected_total_rows=19)

    def test_call_budget_accepts_contract_and_rejects_overrun(self) -> None:
        budget = CallBudget()
        for name, count in REQUIRED_CALLS.items():
            budget.record(name, count)
        budget.record("head_evaluation", CALL_LIMITS["head_evaluation"])
        budget.verify_required()
        with self.assertRaises(RuntimeError):
            budget.record("head_evaluation")
        with self.assertRaises(RuntimeError):
            budget.record("full_forward")

    def test_low_rank_merge_is_permitted_once(self) -> None:
        guard = MergeGuard()
        self.assertEqual(guard.merge_once(3, 4), 7)
        self.assertTrue(guard.merged)
        with self.assertRaises(RuntimeError):
            guard.merge_once(7, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
