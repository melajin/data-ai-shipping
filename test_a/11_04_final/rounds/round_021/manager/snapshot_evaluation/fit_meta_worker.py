from __future__ import annotations

"""One isolated fold-local sklearn fit; parent process enforces a hard timeout."""
import argparse
import json
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--select-output", type=Path, required=True)
    parser.add_argument("--features", type=int, choices=(12, 20), required=True)
    args = parser.parse_args()
    with np.load(args.input, allow_pickle=False) as z:
        x = np.asarray(z["x"], dtype=np.float64)
        y = np.asarray(z["y"], dtype=np.int64)
    if x.ndim != 2 or x.shape[1] != args.features or len(x) != len(y) or not np.isfinite(y).all():
        raise ValueError(f"Invalid training matrix: X={x.shape}, y={y.shape}")
    steps = []
    if args.features == 20:
        steps.append(("imputer", SimpleImputer(strategy="constant", fill_value=0.0, add_indicator=False)))
    steps.extend((
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(C=1.0, solver="lbfgs", multi_class="multinomial",
                                         max_iter=1000, class_weight=None, random_state=42)),
    ))
    model = Pipeline(steps)
    start = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        with threadpool_limits(limits=3):
            model.fit(x, y)
    seconds = time.perf_counter() - start
    with threadpool_limits(limits=3):
        select_p = model.predict_proba(x)
    args.select_output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.select_output, probabilities=select_p)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output, compress=3)
    print(json.dumps({"fit_seconds": seconds, "features": args.features,
                      "classes": model.named_steps["logistic"].classes_.astype(int).tolist()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
