#!/usr/bin/env python3
"""Independent checks on the 2026-10-29 full extraction.

Three claims are checked against the frozen 2026-10-28 artefacts rather than
asserted:

1. Roster identity. The full extract must carry the same 7,372 vessels with the
   same labels and the same per-class row counts.
2. s4 reproduction. Re-running the 2026-10-28 reservoir rule over the full
   extract must select exactly the rows the old cache holds. Without this the
   "sample" factor would confound selection changes with sample-size changes.
3. Feature identity. shape9 on those rows must match the cached values to
   float32 precision, so the "features" factor is the only thing that moved.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_EXTRACT = ROOT / "outputs" / "cycle2_20261029" / "extract"
DEFAULT_CACHE = ROOT / "outputs" / "evaluation_cycle_20261028" / "vessel_features_v2.json"
DEFAULT_OUT = ROOT / "outputs" / "cycle2_20261029" / "extract_verification.json"
SAMPLES_PER_VESSEL_PER_FILE = 4
EXPECTED_VESSELS = 7372
EXPECTED_CLASS_ROWS = (180878, 601059, 1422675, 1682455)
FLOAT32_TOLERANCE = 1e-5


def _selection_score(vessel_hash: str, file_ordinal: int, record_ordinal: int) -> str:
    return hashlib.sha256(
        f"{vessel_hash}\0{file_ordinal}\0{record_ordinal}".encode("ascii")).hexdigest()


def _negated(score: str) -> int:
    """Max-heap key: heapq is a min-heap, so the largest kept score sits on top."""
    return -int(score, 16)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, default=DEFAULT_EXTRACT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    # Keeping all 3.9 M rows would cost several GB. Only the rows the s4 rule
    # can still select are retained: a bounded four-entry heap per vessel per
    # monthly file, at most 24 rows per vessel.
    heaps: dict[tuple[str, int], list] = defaultdict(list)
    label_by_vessel: dict[str, int] = {}
    class_rows = [0, 0, 0, 0]
    for file_ordinal in range(6):
        # A monthly file may have been extracted whole or in row-interleaved
        # shards; both spellings carry the same per-row content.
        parts = (sorted(args.extract.glob(f"train_{file_ordinal}.npz"))
                 + sorted(args.extract.glob(f"train_{file_ordinal}.s*of*.npz")))
        if not parts:
            raise SystemExit(f"no extract found for monthly file {file_ordinal}")
        for part in parts:
            data = np.load(part, allow_pickle=False)
            hashes = data["vessel_hashes"]
            vessel_id = data["vessel_id"]
            label_id = data["label_id"]
            ordinals = data["record_ordinal"]
            valid = data["valid"]
            shape9 = data["shape9"]
            names = [str(value) for value in hashes]
            for index in range(len(vessel_id)):
                vessel_hash = names[vessel_id[index]]
                label = int(label_id[index])
                label_by_vessel[vessel_hash] = label
                class_rows[label] += 1
                record_ordinal = int(ordinals[index])
                key = (vessel_hash, file_ordinal)
                heap = heaps[key]
                score = _selection_score(vessel_hash, file_ordinal, record_ordinal)
                entry = (score, record_ordinal, bool(valid[index]), shape9[index].copy())
                item = (_negated(score), record_ordinal, entry)
                if len(heap) < SAMPLES_PER_VESSEL_PER_FILE:
                    heapq.heappush(heap, item)
                elif score < heap[0][2][0]:
                    heapq.heapreplace(heap, item)
            del data, hashes, vessel_id, label_id, ordinals, valid, shape9

    rows_by_vessel: dict[str, list[tuple[int, int, bool, np.ndarray]]] = defaultdict(list)
    for (vessel_hash, file_ordinal), heap in heaps.items():
        for _rank, _tie, (_score, record_ordinal, is_valid, values) in heap:
            rows_by_vessel[vessel_hash].append(
                (file_ordinal, record_ordinal, is_valid, values))
    heaps.clear()

    cache = json.loads(args.cache.read_text(encoding="utf-8"))
    cached = {entry["vessel_hash"]: entry for entry in cache["vessels"]}

    roster = {
        "extract_vessels": len(label_by_vessel),
        "cache_vessels": len(cached),
        "vessel_sets_identical": set(label_by_vessel) == set(cached),
        "rows_per_class": class_rows,
        "rows_per_class_match": class_rows == list(EXPECTED_CLASS_ROWS),
        "vessel_count_match": len(label_by_vessel) == EXPECTED_VESSELS,
    }

    selection = {"vessels_compared": 0, "identical": 0, "differing": 0,
                 "examples": []}
    features = {"rows_compared": 0, "agree": 0, "valid_flag_mismatch": 0,
                "value_mismatch": 0, "worst_abs_delta": 0.0}

    for vessel_hash, entry in cached.items():
        rows = rows_by_vessel.get(vessel_hash)
        if rows is None:
            continue
        per_file: dict[int, list[tuple[int, int, bool, np.ndarray]]] = defaultdict(list)
        for row in rows:
            per_file[row[0]].append(row)
        reselected = set()
        mine = {}
        for file_ordinal, group in per_file.items():
            group = sorted(group, key=lambda row: (
                _selection_score(vessel_hash, file_ordinal, row[1]), row[1]))
            for row in group[:SAMPLES_PER_VESSEL_PER_FILE]:
                reselected.add((file_ordinal, row[1]))
                mine[(file_ordinal, row[1])] = row

        cached_rows = {(row["file_ordinal"], row["record_ordinal"]): row
                       for row in entry["rows"]}
        selection["vessels_compared"] += 1
        if reselected == set(cached_rows):
            selection["identical"] += 1
        else:
            selection["differing"] += 1
            if len(selection["examples"]) < 5:
                selection["examples"].append({
                    "vessel_prefix": vessel_hash[:12],
                    "only_in_reselection": sorted(reselected - set(cached_rows))[:4],
                    "only_in_cache": sorted(set(cached_rows) - reselected)[:4],
                })

        for key in reselected & set(cached_rows):
            old, new = cached_rows[key], mine[key]
            features["rows_compared"] += 1
            if bool(old["valid"]) != bool(new[2]):
                features["valid_flag_mismatch"] += 1
                continue
            if not old["valid"]:
                features["agree"] += 1
                continue
            theirs = np.asarray([np.nan if v is None else v for v in old["values"]],
                                dtype=np.float64)
            ours = new[3].astype(np.float64)
            if not np.array_equal(np.isnan(theirs), np.isnan(ours)):
                features["value_mismatch"] += 1
                continue
            both = ~np.isnan(theirs)
            delta = float(np.max(np.abs(theirs[both] - ours[both]))) if both.any() else 0.0
            features["worst_abs_delta"] = max(features["worst_abs_delta"], delta)
            if delta <= FLOAT32_TOLERANCE:
                features["agree"] += 1
            else:
                features["value_mismatch"] += 1

    report = {
        "schema_version": "cycle2_extract_verification_v1",
        "roster": roster,
        "s4_selection": selection,
        "shape9_identity": features,
        "float32_tolerance": FLOAT32_TOLERANCE,
        "passed": bool(
            roster["vessel_sets_identical"] and roster["rows_per_class_match"]
            and roster["vessel_count_match"] and selection["differing"] == 0
            and features["valid_flag_mismatch"] == 0 and features["value_mismatch"] == 0),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nreport -> {args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
