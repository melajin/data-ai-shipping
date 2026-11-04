#!/usr/bin/env python3
"""Print one synthetic sample's path-to-probability trace without training a model."""
from pathlib import Path
import argparse
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fishing_demo.data import CLASS_NAMES, load_dataset
from fishing_demo.features import FEATURE_NAMES, feature_matrix
from fishing_demo.models import Classifier, Preprocessor, softmax
from fishing_demo.pipeline import load_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/guided_baseline_20261026")
    parser.add_argument("--sample-id", default="S0-test-000-straight-02")
    args = parser.parse_args()

    # 1. Read synthetic coordinates and the already-trained model.
    dataset = load_dataset(args.out / "sample_dataset.json")
    model = load_model(args.out / "model.json")
    matches = [r for r in dataset["records"] if r["sample_id"] == args.sample_id]
    if len(matches) != 1:
        parser.error("sample-id must identify exactly one synthetic record")
    record = matches[0]

    # 2. Summarize the separate path parts as eight geometry numbers.
    raw, detail = feature_matrix([record])
    if not detail[0]["valid"]:
        parser.error(f"sample cannot be classified: {detail[0]['reason']}")

    # 3. Use the stored TRAIN statistics; do not fit anything here.
    preprocessor = Preprocessor.from_dict(model["preprocessor"])
    inputs = preprocessor.transform(raw)

    # 4. Turn the sixteen inputs into three probabilities.
    classifier = Classifier.from_dict(model["classifier"])
    logits = classifier.predict_logits(inputs)
    probabilities = softmax(logits, model["temperature"])[0]
    predicted = int(np.argmax(probabilities))

    # 5. Only now compare the prediction with the generator's answer.
    result = {
        "source_type": "synthetic_not_real_fishing_codes",
        "sample_id": record["sample_id"],
        "observed_points": sum(len(part) for part in record["parts"]),
        "separate_parts": len(record["parts"]),
        "features_8": dict(zip(FEATURE_NAMES, detail[0]["values"])),
        "model_inputs_16": inputs[0].tolist(),
        "logits_3": logits[0].tolist(),
        "probabilities_3": dict(zip(CLASS_NAMES, probabilities.tolist())),
        "predicted": CLASS_NAMES[predicted],
        "generator_answer": CLASS_NAMES[record["label"]] if record["label"] is not None else None,
        "correct": predicted == record["label"] if record["label"] is not None else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
