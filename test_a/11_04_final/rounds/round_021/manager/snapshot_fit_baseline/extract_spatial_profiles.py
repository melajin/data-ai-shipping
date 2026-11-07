from __future__ import annotations

"""Predicate-first, projected extraction of current 2026 development profiles.

Run only with the existing system Python that has pyarrow 24.0.0. This script
does not import the profile builder and does not read labels, predictions, 2025,
or holdout records. It writes only matching development id/res/cell/weight rows.
"""
import argparse
import csv
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--feature-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    parquet = args.parquet.resolve()
    feature_root = args.feature_root.resolve()
    output = args.output.resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Output must remain inside Round021 workspace: {output}") from exc
    started = time.perf_counter()
    before_sha = sha256_file(parquet)
    if before_sha.lower() != args.expected_sha256.lower():
        raise ValueError(f"Spatial parquet SHA mismatch: {before_sha}")

    # Read only development IDs from the already-cached metadata archive.
    with np.load(feature_root / "fold_0_features.npz", allow_pickle=False) as z:
        ids = z["rfid_ids"].astype(str).tolist()
    if len(ids) != 5897 or len(set(ids)) != 5897:
        raise ValueError("Round002 development ID list must contain 5,897 unique vessels")
    try:
        dev_int_ids = [int(v) for v in ids]
    except ValueError as exc:
        raise ValueError("Spatial parquet id:int64 cannot be safely joined to non-integer development IDs") from exc
    if len(set(dev_int_ids)) != 5897:
        raise ValueError("Integer conversion collapses development vessel IDs")
    dev_id_set = {str(v) for v in dev_int_ids}

    import pyarrow as pa
    import pyarrow.dataset as ds

    dataset = ds.dataset(str(parquet), format="parquet")
    required = {"id", "year", "block", "res", "cell", "weight"}
    if not required.issubset(set(dataset.schema.names)):
        raise ValueError(f"Unexpected spatial parquet schema: {dataset.schema}")
    # Predicate and column projection are attached to the scanner before any table is materialized.
    predicate = ((ds.field("year") == 2026) & (ds.field("block") == "full")
                 & ds.field("res").isin([0.01, 0.05]) & ds.field("id").isin(dev_int_ids))
    scanner = dataset.scanner(columns=["id", "year", "block", "res", "cell", "weight"],
                              filter=predicate, use_threads=False)
    table = scanner.to_table()
    rows = table.to_pylist()
    sums: dict[tuple[str, float], float] = defaultdict(float)
    cells: set[tuple[str, float, str]] = set()
    normalized = []
    for row in rows:
        vessel = str(int(row["id"]))
        resolution = float(row["res"])
        cell = str(row["cell"])
        weight = float(row["weight"])
        if vessel not in dev_id_set:
            raise ValueError("Predicate returned a non-development ID")
        if row["year"] != 2026 or row["block"] != "full" or resolution not in (0.01, 0.05):
            raise ValueError("Predicate returned a row outside the frozen 2026/full/.01/.05 contract")
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"Invalid spatial weight for {vessel}/{resolution}/{cell}")
        key = (vessel, resolution, cell)
        if key in cells:
            raise ValueError(f"Duplicate spatial profile cell: {key}")
        cells.add(key)
        sums[(vessel, resolution)] += weight
        normalized.append((vessel, resolution, cell, weight))
    totals = dict(sums)
    if not normalized or any(not math.isfinite(total) or total <= 0 for total in totals.values()):
        raise ValueError("Filtered spatial profiles are empty or contain zero-mass vessel profiles")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("id", "res", "cell", "weight"))
        for vessel, resolution, cell, weight in normalized:
            writer.writerow((vessel, format(resolution, ".2f"), cell,
                             format(weight / totals[(vessel, resolution)], ".17g")))
    after_sha = sha256_file(parquet)
    if before_sha != after_sha:
        raise ValueError("Spatial parquet changed during extraction")
    meta = {
        "status": "filtered_development_profiles_written",
        "source_sha256": before_sha,
        "source_bytes": parquet.stat().st_size,
        "source_schema": str(dataset.schema),
        "pyarrow_version": pa.__version__,
        "predicate": "year==2026 AND block=='full' AND res in {0.01,0.05} AND id in round002 fold0 development IDs",
        "projected_columns": ["id", "year", "block", "res", "cell", "weight"],
        "development_ids": len(ids),
        "filtered_rows": len(rows),
        "profiles_by_resolution": {str(res): sum(1 for key in totals if key[1] == res) for res in (0.01, 0.05)},
        "output_sha256": sha256_file(output),
        "output_bytes": output.stat().st_size,
        "elapsed_seconds": time.perf_counter() - started,
        "outer_probabilities_read": False,
        "labels_read": False,
        "2025_or_holdout_rows_materialized": False,
    }
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
