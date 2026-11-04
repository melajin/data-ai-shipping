"""CLI boundaries that prevent invalid training and destructive output aliases."""

import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import run_sample_system as cli


class SampleCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        for directory in ("tools", "docs", "tests", "fishing_demo", "data/raw"):
            (self.workspace / directory).mkdir(parents=True)
        # Redirect the guard's workspace to isolated files; never mutate real sources.
        patcher = patch.object(cli, "__file__", str(self.workspace / "tools" / "run_sample_system.py"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = self.root / "output"
        self.out.mkdir()
        self.data = self.root / "input.json"
        self.model = self.root / "frozen.json"
        self.data.write_bytes(b"input dataset must remain unchanged")
        self.model.write_bytes(b"input model must remain unchanged")
        self.report = {"selected_model": "test-model", "metrics": {
            split: {"accuracy": 0.5, "macro_f1": 0.4, "nll": 0.8}
            for split in ("test", "stress")}}

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = cli.main(list(map(str, args)))
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def predict_args(self):
        return ["predict", "--data", self.data, "--model", self.model, "--out", self.out]

    def test_epochs_above_model_limit_are_rejected_before_outputs(self):
        for epochs in (0, 401, 5000):
            with self.subTest(epochs=epochs):
                code, _, stderr = self.invoke(["demo", "--out", self.out, "--epochs", epochs])
                self.assertEqual(code, 2)
                self.assertIn("epochs must be between 1 and 400", stderr)
                self.assertEqual(list(self.out.iterdir()), [])

    def test_epoch_bounds_reach_training_unchanged(self):
        with patch("fishing_demo.pipeline.run_demo", return_value=self.report) as run:
            for epochs in (1, 400):
                with self.subTest(epochs=epochs):
                    code, _, stderr = self.invoke(["demo", "--out", self.out, "--epochs", epochs])
                    self.assertEqual(code, 0, stderr)
                    run.assert_called_with(self.out.resolve(), seed=42, epochs=epochs)

    def test_existing_output_hardlink_cannot_overwrite_either_input(self):
        target = self.out / "predictions.json"
        for input_path in (self.data, self.model):
            with self.subTest(input=input_path.name):
                try:
                    os.link(input_path, target)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"hard links unavailable in temporary directory: {exc}")
                before = input_path.read_bytes()
                self.assertTrue(target.samefile(input_path))
                code, _, stderr = self.invoke(self.predict_args())
                self.assertEqual(code, 2)
                self.assertIn("output would overwrite an input", stderr)
                self.assertEqual(input_path.read_bytes(), before)
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(sorted(path.name for path in self.out.iterdir()), ["predictions.json"])
                target.unlink()

    def test_existing_output_symlink_into_each_protected_subtree_is_rejected(self):
        target = self.out / "predictions.json"
        try:
            target.symlink_to(self.data)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symbolic links unavailable (OS error {getattr(exc, 'winerror', None)})")
        target.unlink()
        for directory in ("data/raw", "tools", "docs", "tests", "fishing_demo"):
            with self.subTest(directory=directory):
                protected_file = self.workspace / directory / "keep.json"
                protected_file.write_bytes(b"protected original")
                target.symlink_to(protected_file)
                code, _, stderr = self.invoke(self.predict_args())
                self.assertEqual(code, 2)
                self.assertIn("output target resolves into a protected directory", stderr)
                self.assertEqual(protected_file.read_bytes(), b"protected original")
                target.unlink()

    def test_resolved_file_target_is_checked_even_when_output_directory_is_safe(self):
        # Emulate the resolved file destination independently of whether the OS
        # grants permission to create a real file symlink in the preceding test.
        target = self.out / "predictions.json"
        original_resolve = Path.resolve
        for directory in ("data/raw", "tools", "docs", "tests", "fishing_demo"):
            with self.subTest(directory=directory):
                protected_file = self.workspace / directory / "keep.json"
                protected_file.write_bytes(b"protected destination")

                def resolve_file_alias(path, *args, **kwargs):
                    if path == target:
                        return protected_file
                    return original_resolve(path, *args, **kwargs)

                with patch.object(Path, "resolve", new=resolve_file_alias):
                    code, _, stderr = self.invoke(self.predict_args())
                self.assertEqual(code, 2)
                self.assertIn("output target resolves into a protected directory", stderr)
                self.assertEqual(protected_file.read_bytes(), b"protected destination")
                self.assertFalse(target.exists())

    def test_workspace_and_protected_output_directories_remain_blocked(self):
        destinations = [self.workspace] + [self.workspace / name / "nested-output"
            for name in ("data/raw", "tools", "docs", "tests", "fishing_demo")]
        for destination in destinations:
            with self.subTest(destination=destination):
                code, _, stderr = self.invoke(["generate", "--out", destination])
                self.assertEqual(code, 2)
                self.assertIn("choose a separate output directory", stderr)
                self.assertFalse((destination / "sample_dataset.json").exists())

    def test_train_can_read_generated_dataset_from_same_output_directory(self):
        dataset_path = self.out / "sample_dataset.json"
        dataset_path.write_bytes(b"generated dataset remains unchanged")
        dataset = {"records": []}
        with patch("fishing_demo.data.load_dataset", return_value=dataset) as load, \
             patch("fishing_demo.pipeline.train_experiment", return_value=self.report) as train:
            code, _, stderr = self.invoke(["train", "--data", dataset_path, "--out", self.out, "--epochs", 1])
        self.assertEqual(code, 0, stderr)
        load.assert_called_once_with(dataset_path)
        train.assert_called_once_with(dataset, self.out.resolve(), seed=42, epochs=1)
        self.assertEqual(dataset_path.read_bytes(), b"generated dataset remains unchanged")

    def test_predict_can_read_adjacent_dataset_and_model_without_overwriting_them(self):
        dataset_path = self.out / "sample_dataset.json"
        model_path = self.out / "model.json"
        dataset_path.write_bytes(b"adjacent dataset")
        model_path.write_bytes(b"adjacent model")
        with patch("fishing_demo.data.load_dataset", return_value={}), \
             patch("fishing_demo.pipeline.load_model", return_value={}), \
             patch("fishing_demo.pipeline.predict_records", return_value=[{"status": "ok"}]), \
             patch("fishing_demo.pipeline.save_json") as save:
            code, _, stderr = self.invoke(["predict", "--data", dataset_path, "--model", model_path,
                                           "--out", self.out])
        self.assertEqual(code, 0, stderr)
        save.assert_called_once_with(self.out.resolve() / "predictions.json", [{"status": "ok"}])
        self.assertEqual(dataset_path.read_bytes(), b"adjacent dataset")
        self.assertEqual(model_path.read_bytes(), b"adjacent model")

    def test_direct_input_output_collision_remains_blocked(self):
        dataset_path = self.out / "report.json"
        dataset_path.write_bytes(b"direct input")
        code, _, stderr = self.invoke(["train", "--data", dataset_path, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("output would overwrite an input", stderr)
        self.assertEqual(dataset_path.read_bytes(), b"direct input")


if __name__ == "__main__":
    unittest.main()
