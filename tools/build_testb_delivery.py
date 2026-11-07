"""Create portable frozen inputs/references from trusted local saved Test B assets.

This builder is a workspace preparation tool, not required by the shipped runtime.
It reads the explicitly authorized local density pickle once and exports plain
JSON. No source module is imported and no AST or source text is executed.
"""
from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
from pathlib import Path
import pickle
import shutil
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
PACKAGE = WORKSPACE / "deliverables/testb_system_20261106"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorer-source", required=True, type=Path)
    parser.add_argument("--distance-source", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(PACKAGE / "src"))
    from run_analysis import INPUT_COLUMNS, memory_preflight, sha256
    preflight = memory_preflight()
    import pyarrow.parquet as pq

    source = next((WORKSPACE / "testB").glob("*/first_results"))
    originals = [source / name for name in
                 ("hourly_scores.parquet", "candidate_A.csv", "harbors.json", "density.pkl",
                  "gap_reference.npy", "jump_reference.npy", "run.py")]
    originals.extend((args.scorer_source, args.distance_source))
    original_hashes = {str(path): sha256(path) for path in originals}
    inputs, references = PACKAGE / "inputs", PACKAGE / "references"
    if inputs.exists() or references.exists():
        raise FileExistsError("New package inputs/references directories required")
    inputs.mkdir(parents=True)
    references.mkdir()
    table = pq.read_table(source / "hourly_scores.parquet", columns=list(INPUT_COLUMNS))
    expected = pq.read_table(source / "hourly_scores.parquet", columns=["rfid_id", "ts", "source_ordinal",
                                                                      "state", "s_zone", "s_change", "s_gap", "score"])
    if table.num_rows != 46705 or expected.num_rows != 46705:
        raise ValueError("Expected frozen 46705-row baseline")
    pq.write_table(table, inputs / "observations.parquet")
    pq.write_table(expected, inputs / "stored_expected.parquet")
    shutil.copyfile(source / "candidate_A.csv", inputs / "stored_candidates.csv")
    with (source / "candidate_A.csv").open(encoding="utf-8-sig", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    roster = [row["rfid_id"] for row in candidates]
    if len(roster) != 100 or len(set(roster)) != 100:
        raise ValueError("Expected frozen 100-vessel roster")
    with (inputs / "roster.csv").open("x", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["rfid_id"])
        writer.writerows((rfid,) for rfid in roster)
    for name in ("harbors.json", "gap_reference.npy", "jump_reference.npy"):
        shutil.copyfile(source / name, references / name)
    # Trusted local artifact explicitly authorized for this packaging operation.
    with (source / "density.pkl").open("rb") as handle:
        fine, coarse = pickle.load(handle)
    density = {"fine": [[int(x), int(y), float(count)] for (x, y), count in fine.items()],
               "coarse": [[int(x), int(y), float(count)] for (x, y), count in coarse.items()]}
    with (references / "density.json").open("x", encoding="utf-8") as target:
        json.dump(density, target, separators=(",", ":"), allow_nan=False)
    if any(sha256(path) != original_hashes[str(path)] for path in originals):
        raise ValueError("Original artifact changed during packaging")
    provenance = {
        "purpose": "Frozen original unsupervised baseline reproduction; no training or new model",
        "scorer": {"original_filename": args.scorer_source.name,
                   "sha256": original_hashes[str(args.scorer_source)],
                   "line_ranges_inclusive": {"grid_constants": [44, 50], "state_constants": [178, 185],
                                             "haversine_vec": [188, 194], "quantile_normalizer": [350, 359],
                                             "density_lookup": [389, 398], "robust_z_squash": [420, 433],
                                             "score_vessel": [436, 530]}},
        "scalar_distance": {"original_filename": args.distance_source.name,
                            "sha256": original_hashes[str(args.distance_source)],
                            "line_ranges_inclusive": {"earth_radius": [41, 41], "haversine_m": [123, 129]}},
        "execution_wrapper": {"original_filename": "first_results/run.py",
                              "sha256": original_hashes[str(source / "run.py")],
                              "semantics": "Timestamp/rfid_time/source_ordinal stable order; peak maximum score then source_ordinal"},
        "adaptations": ["Source aliases remeasure.haversine_m and remeasure.EARTH_R replaced by explicit local identical helpers",
                        "Original first_results nearest-harbor cKDTree wrapper retained",
                        "Trusted local density pickle converted to portable JSON; no runtime pickle/source imports",
                        "Old cached output columns separated from projected score inputs; never used by scorer"],
        "frozen_original_assets": {path.name: {"sha256": original_hashes[str(path)], "bytes": path.stat().st_size}
                                  for path in originals if path.parent == source},
        "density_conversion": {"fine_cells": len(fine), "coarse_cells": len(coarse),
                               "format": "lists of integer grid x,y and float count; lookup semantics unchanged"},
        "preparation_memory_preflight": preflight,
        "originals_unchanged": True,
    }
    (references / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts = {}
    for folder in (inputs, references, PACKAGE / "src"):
        for path in sorted(folder.glob("*")):
            if path.is_file() and (folder != PACKAGE / "src" or path.suffix == ".py"):
                artifacts[path.relative_to(PACKAGE).as_posix()] = sha256(path)
    config = {"schema_version": "testb_frozen_package_v1", "mode": "frozen_baseline_reproduction",
              "training_enabled": False, "threshold": None, "external_delivery_enabled": False,
              "output_kind": "review_evidence_only", "memory": {"expected_peak_mib": 512, "reserve_mib": 640},
              "selection": "maximum score then minimum original source_ordinal", "artifacts": artifacts}
    (PACKAGE / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    requirements = "\n".join(f"{name}=={importlib.metadata.version(name)}" for name in ("numpy", "pandas", "pyarrow", "scipy"))
    (PACKAGE / "requirements.txt").write_text(requirements + "\n", encoding="ascii")
    print(json.dumps({"status": "portable_inputs_prepared", "rows": table.num_rows, "vessels": len(roster),
                      "originals_unchanged": True, "artifact_count": len(artifacts),
                      "data_bytes": sum(path.stat().st_size for folder in (inputs, references) for path in folder.iterdir())}))


if __name__ == "__main__":
    main()
