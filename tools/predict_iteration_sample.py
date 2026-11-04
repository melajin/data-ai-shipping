#!/usr/bin/env python3
"""Use the predeclared example of the improved synthetic model, without training."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fishing_demo.data import CLASS_NAMES, generate_dataset
from fishing_demo.iteration_features import feature_matrix
from fishing_demo.models import Preprocessor
from fishing_demo.pipeline import dataset_digest
from tools.run_iterative_models import load_iteration_model, predict_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/iterative_models_20261026")
    parser.add_argument("--sample-id", default="S0-stress-000-straight-01")
    args = parser.parse_args()

    # 1. Read the selected model from the predeclared final example.
    results = json.loads((args.out / "results.json").read_text(encoding="utf-8"))
    if not results.get("final", {}).get("executed"):
        parser.error("the frozen final evaluation must be completed first")
    fixture = next(r for r in results["final"]["candidate_records"]
                   if r["data_seed"] == 9101 and r["init_seed"] == 42)
    bundle = load_iteration_model(args.out / fixture["model_path"])

    # 2. Recreate the exact synthetic data, then find one trajectory.
    dataset = generate_dataset(bundle["data_seed"])
    if dataset_digest(dataset) != bundle["dataset_sha256"]:
        parser.error("the generator no longer reproduces the model's recorded data")
    matches = [r for r in dataset["records"] if r["sample_id"] == args.sample_id]
    if len(matches) != 1:
        parser.error("sample-id must identify one trajectory in generator seed 9101")
    record = matches[0]

    # 3. Geometry numbers become standardized numbers plus missing indicators.
    raw = feature_matrix([record], bundle["config"]["family"])
    inputs = Preprocessor.from_dict(bundle["preprocessor"]).transform(raw)

    # 4. Keep all learned numbers fixed and calculate three probabilities.
    probabilities, valid = predict_bundle(bundle, [record])
    if not valid[0]:
        parser.error("this trajectory has no valid geometric input")
    guess = int(np.argmax(probabilities[0]))

    # 5. Compare with the generator's label only after inference.
    truth = record["label"]
    result = {
        "source_type": "synthetic_not_real_fishing_codes",
        "generator_seed": bundle["data_seed"], "initialization_seed": bundle["init_seed"],
        "sample_id": record["sample_id"], "model": bundle["config"]["name"],
        "features_9": dict(zip(bundle["feature_names"], raw[0].tolist())),
        "model_inputs_18": inputs[0].tolist(),
        "probabilities": dict(zip(CLASS_NAMES, probabilities[0].tolist())),
        "prediction": CLASS_NAMES[guess], "generator_answer": CLASS_NAMES[truth],
        "correct": guess == truth, "training_performed": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
