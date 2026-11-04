"""Final-stage guards use fixtures only; no synthetic final dataset is generated."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import critique_final_comparison_20261027 as final


def paired_records(deltas, *, normal_delta=0.0):
    baseline, candidate = [], []
    for index, seed in enumerate(final.FINAL_SEEDS):
        for init_index, init in enumerate(final.INIT_SEEDS):
            metrics = {}
            for role in ("normal", "shift"):
                metrics[role] = {
                    "accuracy": .5, "macro_f1": .4 + .05 * init_index, "nll": 1.0, "brier": .6,
                    "total": 8, "valid": 7, "abstained": 1, "evaluated_labeled": 6,
                    "support": [2, 2, 2], "evaluation_row_sha256": f"{role}_{seed}",
                    "confusion": [[1, 1, 0], [0, 1, 1], [1, 0, 1]],
                }
            row = {"data_seed": seed, "init_seed": init, "metrics": metrics}
            baseline.append(row)
            changed = copy.deepcopy(row)
            # The opposite initialization effects disappear within each seed.
            noise = .15 if init_index == 0 else -.15
            changed["metrics"]["shift"]["macro_f1"] += deltas[index] + noise
            changed["metrics"]["normal"]["macro_f1"] += normal_delta + noise
            candidate.append(changed)
    return baseline, candidate


class FinalComparisonTests(unittest.TestCase):
    def _sealed_fixture(self, directory):
        directory = Path(directory)
        dev_dir, out = directory / "development", directory / "final"
        dev_dir.mkdir()
        out.mkdir()
        source_bytes = b"fixed fixture source\n"
        source_path = directory / "fixture.py"
        source_path.write_bytes(source_bytes)
        sources = {"fixture.py": final.development.sha256(source_path)}
        for path in (dev_dir / "source_snapshot/fixture.py", out / "source_snapshot/fixture.py"):
            path.parent.mkdir(parents=True)
            path.write_bytes(source_bytes)
        for name in ("results.json", "protocol.json", "run_evidence.json"):
            (dev_dir / name).write_text("{}\n", encoding="utf-8")
        evidence = {"path": str(dev_dir), "results_sha256": final.development.sha256(dev_dir / "results.json"),
                    "protocol_sha256": final.development.sha256(dev_dir / "protocol.json"),
                    "run_evidence_sha256": final.development.sha256(dev_dir / "run_evidence.json"),
                    "source_snapshot_sha256": sources, "selected_development_candidate": None,
                    "completed_model_count": 9, "records_per_model": 6,
                    "development_selection_recomputed_matches_recorded": True}
        protocol = final.final_protocol_payload(sources, evidence, started_at="2026-10-27T00:00:00+00:00")
        protocol_path = out / "protocol.json"
        final.save_json(protocol_path, protocol)
        protocol_hash = final.development.sha256(protocol_path)
        protocol_path.with_suffix(".sha256").write_text(protocol_hash + "\n", encoding="ascii")
        freeze_path = out / "freeze.json"
        frozen = final.freeze_payload(protocol, protocol_hash, frozen_at="2026-10-27T00:00:01+00:00")
        final.save_json(freeze_path, frozen)
        freeze_path.with_suffix(".sha256").write_text(final.development.sha256(freeze_path) + "\n", encoding="ascii")
        return sources, evidence, protocol_path, freeze_path

    def test_pre_freeze_and_out_of_schedule_requests_make_zero_generator_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(final, "generate_dataset") as generate:
            gate = final.FinalSeedGate({}, {}, Path(directory) / "missing_protocol.json")
            with self.assertRaisesRegex(ValueError, "before a verified freeze"):
                gate.get(final.FINAL_SEEDS[0])
            for seed in (9101, 2101, True, 12101.0):
                with self.assertRaisesRegex(ValueError, "ten fixed"):
                    gate.get(seed)
            generate.assert_not_called()

    def test_valid_freeze_unlocks_once_per_seed_and_tamper_blocks_next_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, evidence, protocol_path, freeze_path = self._sealed_fixture(directory)
            fixture = {"metadata": {"source_type": "synthetic"}, "records": []}
            prepared = {"dataset": fixture, "metadata": {"dataset_sha256": final.development.digest(fixture)}}
            with patch.object(final.development, "source_hashes", return_value=sources), \
                    patch.object(final, "generate_dataset", return_value=fixture) as generate, \
                    patch.object(final.development, "prepare_dataset", return_value=prepared) as prepare:
                gate = final.FinalSeedGate(sources, evidence, protocol_path)
                gate.unlock_final(freeze_path)
                first = gate.get(final.FINAL_SEEDS[0])
                self.assertIs(first, gate.get(final.FINAL_SEEDS[0]))
                generate.assert_called_once_with(seed=12101)
                prepare.assert_called_once_with(fixture, 12101)
                self.assertEqual(gate.calls[0]["freeze_sha256"], final.development.sha256(freeze_path))
                self.assertTrue((protocol_path.parent / "datasets/seed_12101.json").is_file())
                freeze_path.write_text("{}\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    gate.get(final.FINAL_SEEDS[1])
                self.assertEqual(generate.call_count, 1)

    def test_changed_freeze_semantics_fail_even_when_file_hash_sidecar_is_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, evidence, protocol_path, freeze_path = self._sealed_fixture(directory)
            frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
            frozen["final_data_seeds"] = list(range(9101, 9111))
            final.save_json(freeze_path, frozen)
            freeze_path.with_suffix(".sha256").write_text(final.development.sha256(freeze_path), encoding="ascii")
            with patch.object(final.development, "source_hashes", return_value=sources), \
                    patch.object(final, "generate_dataset") as generate:
                gate = final.FinalSeedGate(sources, evidence, protocol_path)
                with self.assertRaisesRegex(ValueError, "prespecified comparison"):
                    gate.unlock_final(freeze_path)
                with self.assertRaisesRegex(ValueError, "before a verified freeze"):
                    gate.get(12101)
                generate.assert_not_called()

    def test_source_or_development_results_changed_after_freeze_block_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            sources, evidence, protocol_path, freeze_path = self._sealed_fixture(directory)
            with patch.object(final.development, "source_hashes", return_value=sources) as source_hashes, \
                    patch.object(final, "generate_dataset") as generate:
                gate = final.FinalSeedGate(sources, evidence, protocol_path)
                gate.unlock_final(freeze_path)
                source_hashes.return_value = {"fixture.py": "changed"}
                with self.assertRaisesRegex(ValueError, "source changed"):
                    gate.get(12101)
                source_hashes.return_value = sources
                (Path(evidence["path"]) / "results.json").write_text('{"changed": true}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    gate.get(12101)
                generate.assert_not_called()

    def test_bootstrap_uses_ten_seed_means_after_two_initializations(self):
        deltas = np.linspace(.03, .12, 10)
        baseline, candidate = paired_records(deltas)
        summary = final.final_summary(baseline, candidate, is_primary=True)
        actual = [row["shift"]["delta"] for row in summary["per_seed"]]
        np.testing.assert_allclose(actual, deltas, rtol=0, atol=1e-15)
        self.assertEqual(summary["seed_count"], 10)
        self.assertAlmostEqual(summary["shift_mean_delta"], deltas.mean())
        rng = np.random.default_rng(20261027)
        sampled = np.asarray(actual)[rng.integers(0, 10, size=(2000, 10))].mean(axis=1)
        expected = np.quantile(sampled, [.025, .975])
        interval = summary["shift_paired_bootstrap95"]
        self.assertEqual((interval["low"], interval["high"]), tuple(expected))
        self.assertEqual(interval["seed"], 20261027)
        self.assertEqual(interval["repetitions"], 2000)
        with self.assertRaisesRegex(ValueError, "exactly ten"):
            final.paired_bootstrap(np.repeat(deltas, 2))
        with self.assertRaisesRegex(ValueError, "every prespecified"):
            final.final_summary(baseline[:-1], candidate)

    def test_no_primary_keeps_all_nine_fixed_models_and_never_promotes_auxiliary_winner(self):
        baseline, candidate = paired_records([.1] * 10)
        summary = final.final_summary(baseline, candidate, is_primary=False)
        stages = [{"candidate": final.development.CANDIDATES[0], "summary": summary}]
        self.assertTrue(all(summary["conditions"].values()))
        self.assertIsNone(summary["primary_success"])
        self.assertEqual(final.primary_result(stages, None)["candidate"], None)
        protocol = final.final_protocol_payload({}, {"selected_development_candidate": None}, started_at="fixture")
        self.assertEqual(1 + len(protocol["candidates"]), 9)
        self.assertIsNone(protocol["primary_candidate"])
        self.assertTrue(protocol["all_nine_models_run_when_primary_is_none"])
        self.assertFalse(protocol["candidate_selection_from_final_scores"])
        self.assertEqual(protocol["intervals"]["multiplicity_adjustment"], "none")

    def test_primary_criteria_require_both_seed_direction_and_unchanged_denominators(self):
        baseline, candidate = paired_records([.1] * 8 + [-.001] * 2)
        summary = final.final_summary(baseline, candidate, is_primary=True)
        self.assertEqual(summary["positive_shift_seeds"], 8)
        self.assertTrue(summary["primary_success"])
        candidate[0]["metrics"]["shift"]["evaluation_row_sha256"] = "different_rows"
        failed = final.final_summary(baseline, candidate, is_primary=True)
        self.assertFalse(failed["conditions"]["same_denominators"])
        self.assertFalse(failed["primary_success"])

    def test_source_change_since_development_rejects_before_reading_or_generating_final_data(self):
        sources = {name: "fixed" for name in final.development.SOURCE_FILES}
        changed = {**sources, "fishing_demo/models.py": "changed"}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(final.development, "source_hashes", return_value=changed), \
                patch.object(final, "generate_dataset") as generate:
            with self.assertRaisesRegex(ValueError, "current sources differ"):
                final.validate_development(directory, expected_sources=sources)
            generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
