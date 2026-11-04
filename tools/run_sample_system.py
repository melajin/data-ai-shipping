#!/usr/bin/env python3
"""Run the explicit synthetic sample experiment; real CSV is not accepted here."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_OUTPUT_NAMES = {
    "demo": ("sample_dataset.json", "model.json", "report.json", "predictions.json", "dashboard.html"),
    "generate": ("sample_dataset.json",),
    "train": ("model.json", "report.json", "predictions.json", "dashboard.html"),
    "predict": ("predictions.json",),
}


def _check_output_paths(parser, args):
    """Reject protected destinations and input aliases before any output write."""
    try:
        out = args.out.resolve()
        workspace = Path(__file__).resolve().parents[1]
        protected_dirs = tuple(path.resolve() for path in (
            workspace / "data" / "raw", workspace / "tools", workspace / "fishing_demo",
            workspace / "docs", workspace / "tests"))

        def protected(path):
            return path == workspace or any(path == directory or directory in path.parents
                                            for directory in protected_dirs)

        if protected(out):
            parser.error("choose a separate output directory, such as outputs/sample_system")
        # Only files written by this command are targets. In particular, train
        # can read out/sample_dataset.json because it does not emit that file.
        targets = tuple(out / name for name in _OUTPUT_NAMES[args.command])
        inputs = tuple(path for path in (args.data, args.model) if path is not None)
        for target in targets:
            resolved_target = target.resolve()
            if protected(resolved_target):
                parser.error("output target resolves into a protected directory; select a different --out directory")
            for input_path in inputs:
                same_input = resolved_target == input_path.resolve()
                if not same_input:
                    try:
                        # Resolving path strings does not detect hard links.
                        same_input = target.samefile(input_path)
                    except FileNotFoundError:
                        same_input = False
                if same_input:
                    parser.error("output would overwrite an input; select a different --out directory")
        return out
    except (OSError, RuntimeError) as exc:
        parser.error(f"cannot inspect output destinations: {exc}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="demo", choices=("demo", "generate", "train", "predict"))
    parser.add_argument("--out", type=Path, default=Path("outputs/sample_system"), help="output directory")
    parser.add_argument("--data", type=Path, help="fishing_sample_v1 JSON")
    parser.add_argument("--model", type=Path, help="frozen model JSON for predict")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=400, help="maximum training epochs (1..400)")
    args = parser.parse_args(argv)
    if args.seed < 0 or not 1 <= args.epochs <= 400:
        parser.error("seed must be nonnegative; epochs must be between 1 and 400")
    if args.command in ("train", "predict") and args.data is None:
        parser.error("--data is required")
    if args.command == "predict" and args.model is None:
        parser.error("--model is required")
    out = _check_output_paths(parser, args)
    try:
        from fishing_demo.data import generate_dataset, load_dataset, write_dataset
        from fishing_demo.pipeline import load_model, predict_records, run_demo, save_json, train_experiment
        if args.command == "generate":
            dataset = generate_dataset(seed=args.seed)
            write_dataset(dataset, out / "sample_dataset.json")
            print(f"Synthetic records: {len(dataset['records'])}; {out / 'sample_dataset.json'}")
        elif args.command == "predict":
            prediction = predict_records(load_dataset(args.data), load_model(args.model))
            save_json(out / "predictions.json", prediction)
            print(f"Frozen synthetic inference: {len(prediction)} records; {out / 'predictions.json'}")
        else:
            report = (run_demo(out, seed=args.seed, epochs=args.epochs) if args.command == "demo"
                      else train_experiment(load_dataset(args.data), out, seed=args.seed, epochs=args.epochs))
            print(f"Synthetic-only selected model: {report['selected_model']}")
            for split in ("test", "stress"):
                m = report["metrics"][split]
                print(f"{split}: accuracy={m['accuracy']:.4f}, macro_f1={m['macro_f1']:.4f}, nll={m['nll']:.4f}")
            print(f"Dashboard: {out / 'dashboard.html'}")
            print("These are synthetic geometry classes, not real fishing codes or accident detection results.")
        return 0
    except (ValueError, OSError, KeyError, ImportError) as exc:
        print(f"Sample experiment failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
