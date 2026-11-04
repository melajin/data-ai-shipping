#!/usr/bin/env python3
"""Full-Train geometry extraction for the 2026-10-29 cycle 2 contract.

The 2026-10-28 cycle sampled four rows per vessel per monthly file: 129,142 of
3,887,069 Train rows (3.32%). That made "the sample was too small" an untested
hypothesis. This tool computes shape9 and scale8 for every Train row so the
sample-size axis can be compared directly instead of assumed.

Identifier and label hashing reproduce the 2026-10-28 salt exactly, so the
frozen final split stays reproducible. Source CSVs are opened read only; no
coordinate is written to disk. Per-file SHA-256 is verified against the
2026-10-28 inventory as a provenance check.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.real_geometry_20261028 import FEATURE_NAMES as SHAPE9_NAMES
from fishing_demo.real_geometry_20261028 import geometry_features
from fishing_demo.real_scale_features_20261029 import FEATURE_NAMES as SCALE8_NAMES
from fishing_demo.real_scale_features_20261029 import scale_features

SALT = b"fishing-evaluation-cycle-20261028-id-index-v1"
DEFAULT_OUT = ROOT / "outputs" / "cycle2_20261029" / "extract"

# Class index comes from the salted label hash, never from a label literal
# written here. Order is the 2026-10-28 protocol order; index 1 is the pot-trap
# class. Transcribing these labels by hand once silently dropped class 0, so
# the hash is the only identifier this file carries.
CLASS_LABEL_SHA256 = (
    "1edc2d96759a1df336ff96ec264b6d4cbdd6130a757aa2aae8d97b063241af4f",
    "6c451d18f84a5e1d774592d7d05d528b9338e784e541a8413383b5f2edb08f7b",
    "dc049b9b4ebb132462ecf76ac702690b1499775aa662488d5bee1bd0f1ec3159",
    "eedcc6605ecd1794c5a6626a5b40d0570c98e0e666308e51cd8273a48a121e91",
)
# Expected labeled rows per class, from full_scan.json, used as a load check.
EXPECTED_CLASS_ROWS = (180878, 601059, 1422675, 1682455)

# Carried forward from outputs/evaluation_cycle_20261028/full_scan.json.
EXPECTED_TRAIN_SHA256 = (
    "800afffb3f107d02ee132645c76f7efe902d3189aab83d60b031d4dc195f1176",
    "8eb284e7b9c374c2b679376652535eecf898e9241a668cae1d61c63a2b41b422",
    "2765008e34544590c4692c125f92ba611c548a55f7816a866fb8df1f658550c0",
    "013964713caf1cb9db2765e27f3205746748264236047f5a8cb14fc38fc9f3f1",
    "b4eafc1494e8dc4aa4f72c6bf6d40efa63f29b2599ceafb2ca2eeb14ad960709",
    "4976ed8540aa0a57c7b01a97369a36a9122923fa11e0e1654e5866502a7b3a0a",
)
EXPECTED_TRAIN_ROWS = (497942, 479290, 657292, 717294, 761846, 773405)
# The one structurally invalid row quarantined by the 2026-10-28 repair audit.
QUARANTINE = {(5, 127862)}

REASON_CODES = (
    "ok", "geom_unreadable", "empty", "invalid_part", "invalid_coordinate",
    "invalid_coordinate_shape", "nonfinite_coordinate", "coordinate_out_of_range",
    "longitude_out_of_range", "latitude_out_of_range", "part_too_short",
    "spatial_span_exceeds_20_degrees", "mean_latitude_exceeds_85_degrees",
    "no_positive_length", "nonfinite_geometry", "nonfinite_scale",
)
_REASON_INDEX = {name: index for index, name in enumerate(REASON_CODES)}


class _DigestReader(io.RawIOBase):
    """Hash exact source bytes while they stream into the CSV decoder.

    ``eof_reached`` is the guard the 2026-10-28 Test-June record lacked: a hash
    taken over a partial read looks like a hash of a different file.
    """

    def __init__(self, stream, digest):
        self.stream = stream
        self.digest = digest
        self.bytes_hashed = 0
        self.eof_reached = False

    def readable(self):
        return True

    def readinto(self, buffer):
        chunk = self.stream.read(len(buffer))
        if not chunk:
            self.eof_reached = True
            return 0
        self.digest.update(chunk)
        self.bytes_hashed += len(chunk)
        buffer[:len(chunk)] = chunk
        return len(chunk)

    def close(self):
        if not self.closed:
            self.stream.close()
        super().close()


def _salted(value: str) -> str:
    return hashlib.sha256(SALT + value.encode("utf-8", errors="surrogatepass")).hexdigest()


def _load_geometry_summary():
    """Reuse the frozen 2026-10-28 WKT parser without importing its CLI."""
    path = ROOT / "tools" / "run_evaluation_cycle_20261028.py"
    spec = importlib.util.spec_from_file_location("_inventory_20261028", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.geometry_summary


def discover_train_dir(root: Path | None = None) -> Path:
    """Locate the six monthly Train CSVs without relying on console encoding."""
    if root is None:
        candidates = [Path("F:/") / name for name in os.listdir("F:/")]
        roots = [path for path in candidates
                 if path.is_dir() and "1027" in path.name and not path.name.startswith("$")]
        if len(roots) != 1:
            raise SystemExit(f"expected one source root on F:, found {len(roots)}")
        root = roots[0]
    for dirpath, _dirnames, filenames in os.walk(root):
        csvs = [name for name in filenames if name.lower().endswith(".csv")]
        if len(csvs) == 6 and "vpass" in dirpath.lower():
            return Path(dirpath)
    raise SystemExit(f"no six-CSV vpass Train directory under {root}")


def extract_file(task: tuple[int, str, str], shard: int = 0, shards: int = 1) -> dict:
    """Extract one monthly Train CSV, or one residue class of its rows.

    Sharding exists because a whole monthly file can take over thirteen
    minutes and this environment kills long runs. Every shard still streams the
    file to EOF, so each one independently confirms the file SHA-256; only the
    geometry work is divided. Rows are assigned by ``record_ordinal % shards``,
    which needs no byte-offset bookkeeping to stay exact.
    """
    file_ordinal, path_text, out_text = task
    path, out_path = Path(path_text), Path(out_text)
    if shards > 1:
        out_path = out_path.with_name(f"{out_path.stem}.s{shard}of{shards}.npz")
    done_path = out_path.with_suffix(".done.json")
    if out_path.exists() and done_path.exists():
        # A previous run was killed partway; keep the files it finished.
        report = json.loads(done_path.read_text(encoding="utf-8"))
        report["reused_existing_output"] = True
        return report
    geometry_summary = _load_geometry_summary()
    class_hashes = {value: index for index, value in enumerate(CLASS_LABEL_SHA256)}

    digest = hashlib.sha256()
    vessel_index: dict[str, int] = {}
    vessel_order: list[str] = []
    label_text: dict[int, str] = {}
    unlabeled = skipped = other_shard = 0
    started = time.perf_counter()

    # Grown by doubling rather than kept as Python lists: 0.8 M rows of boxed
    # floats would cost roughly a gigabyte per worker.
    capacity, count = 1 << 16, 0
    vessel_ids = np.empty(capacity, dtype=np.int32)
    label_ids = np.empty(capacity, dtype=np.int8)
    ordinals = np.empty(capacity, dtype=np.int32)
    valid_flags = np.empty(capacity, dtype=bool)
    reason_ids = np.empty(capacity, dtype=np.int8)
    shape9 = np.empty((capacity, 9), dtype=np.float32)
    scale8 = np.empty((capacity, 8), dtype=np.float32)

    def grow():
        nonlocal capacity, vessel_ids, label_ids, ordinals, valid_flags
        nonlocal reason_ids, shape9, scale8
        capacity *= 2
        vessel_ids = np.resize(vessel_ids, capacity)
        label_ids = np.resize(label_ids, capacity)
        ordinals = np.resize(ordinals, capacity)
        valid_flags = np.resize(valid_flags, capacity)
        reason_ids = np.resize(reason_ids, capacity)
        shape9 = np.resize(shape9, (capacity, 9))
        scale8 = np.resize(scale8, (capacity, 8))

    # Stream: a 1.2 GB file decoded in full would cost several GB per worker.
    handle = open(path, "rb")
    hashed = _DigestReader(handle, digest)
    stream = io.TextIOWrapper(io.BufferedReader(hashed, 1 << 22),
                              encoding="utf-8-sig", errors="strict", newline="")
    csv.field_size_limit(max(csv.field_size_limit(), 128 * 1024 * 1024))
    reader = csv.reader(stream, strict=True)
    header = next(reader)

    # 1-based, matching enumerate(reader, 1) in run_evaluation_cycle_20261028.py,
    # so record_ordinal and the quarantine coordinate stay comparable across cycles.
    for record_ordinal, row in enumerate(reader, 1):
        if (file_ordinal, record_ordinal) in QUARANTINE:
            skipped += 1
            continue
        if len(row) < 5:
            skipped += 1
            continue
        if shards > 1 and record_ordinal % shards != shard:
            other_shard += 1
            continue
        label_hash = _salted(row[4])
        label_id = class_hashes.get(label_hash)
        if label_id is None:
            unlabeled += 1
            continue
        # Record the source spelling once per class so the split-reproducing
        # label strings come from the data, never from a literal in this file.
        label_text.setdefault(label_id, row[4])
        vessel_hash = _salted(row[1])
        slot = vessel_index.get(vessel_hash)
        if slot is None:
            slot = len(vessel_order)
            vessel_index[vessel_hash] = slot
            vessel_order.append(vessel_hash)

        summary = geometry_summary(row[3], include_parts=True)
        parts = summary.get("parsed_parts")
        if parts is None:
            shape = {"valid": False, "reason": "geom_unreadable", "values": [None] * 9}
            scale = {"valid": False, "reason": "geom_unreadable"}
        else:
            shape = geometry_features(parts, projection="local_tangent")
            scale = scale_features(parts)

        usable = bool(shape["valid"] and scale["valid"])
        reason = "ok" if usable else (shape["reason"] or scale["reason"] or "empty")
        if count == capacity:
            grow()
        vessel_ids[count] = slot
        label_ids[count] = label_id
        ordinals[count] = record_ordinal
        valid_flags[count] = usable
        reason_ids[count] = _REASON_INDEX.get(reason, 0)
        # A valid record can still carry a null feature (no turn angle exists
        # when every part has two points); the mask block covers that.
        shape9[count] = [np.nan if value is None else value for value in shape["values"]]
        scale8[count] = ([np.nan if value is None else value for value in scale["values"]]
                         if usable else [np.nan] * 8)
        count += 1

    stream.close()
    if not hashed.eof_reached:
        raise RuntimeError(f"{path.name}: stream closed before EOF; hash would be partial")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        vessel_id=vessel_ids[:count],
        label_id=label_ids[:count],
        record_ordinal=ordinals[:count],
        valid=valid_flags[:count],
        reason_id=reason_ids[:count],
        shape9=shape9[:count],
        scale8=scale8[:count],
        vessel_hashes=np.asarray(vessel_order, dtype="U64"),
        month=np.full(count, file_ordinal + 1, dtype=np.int8),
    )
    data_rows = count + unlabeled + skipped + other_shard
    report = {
        "file_ordinal": file_ordinal,
        "shard": shard,
        "shards": shards,
        "rows_in_other_shards": other_shard,
        "name_sha256": _salted(path.name),
        "bytes": path.stat().st_size,
        "bytes_hashed": hashed.bytes_hashed,
        "bytes_fully_read": hashed.bytes_hashed == path.stat().st_size,
        "sha256": digest.hexdigest(),
        "sha256_matches_20261028": digest.hexdigest() == EXPECTED_TRAIN_SHA256[file_ordinal],
        "data_rows": data_rows,
        "rows_matches_20261028": data_rows == EXPECTED_TRAIN_ROWS[file_ordinal],
        "labeled_rows": count,
        "unlabeled_rows": unlabeled,
        "skipped_rows": skipped,
        "valid_rows": int(np.count_nonzero(valid_flags[:count])),
        "distinct_vessels": len(vessel_order),
        "rows_per_class": np.bincount(label_ids[:count], minlength=4).tolist(),
        "label_text": {str(key): value for key, value in sorted(label_text.items())},
        "header": header,
        "seconds": round(time.perf_counter() - started, 1),
        "output": str(out_path),
        "reused_existing_output": False,
    }
    done_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=None,
                        help="override source root; default discovers it on F:")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    # Three workers hold roughly 450 MB; six exhausted a 13.8 GB machine that
    # had 1.1 GB free and the run was killed partway.
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--only-file", type=int, default=None, metavar="ORDINAL",
                        help="extract just this monthly file (0-5) and stop; the "
                             "per-file .done.json lets later runs skip it")
    parser.add_argument("--shard", type=int, default=0,
                        help="with --only-file and --shards, the residue class to do")
    parser.add_argument("--shards", type=int, default=1,
                        help="split one file into this many row-interleaved shards")
    args = parser.parse_args()

    train_dir = discover_train_dir(args.source_root)
    names = sorted(os.listdir(train_dir))
    if len(names) != 6:
        raise SystemExit(f"expected 6 Train CSVs, found {len(names)}")
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = [(index, str(train_dir / name), str(args.out / f"train_{index}.npz"))
             for index, name in enumerate(names)]

    started = time.perf_counter()
    if args.only_file is not None:
        if not 0 <= args.only_file < 6:
            raise SystemExit("--only-file must be 0-5")
        report = extract_file(tasks[args.only_file], args.shard, args.shards)
        print(json.dumps({key: report[key] for key in
                          ("file_ordinal", "shard", "shards", "data_rows",
                           "labeled_rows", "rows_in_other_shards", "valid_rows",
                           "rows_per_class", "rows_matches_20261028",
                           "sha256_matches_20261028", "bytes_fully_read",
                           "distinct_vessels", "seconds", "reused_existing_output")},
                         ensure_ascii=False, indent=2))
        outstanding = []
        for index in range(6):
            whole = args.out / f"train_{index}.done.json"
            if whole.exists():
                continue
            parts = sorted(args.out.glob(f"train_{index}.s*of*.done.json"))
            outstanding.append(f"{index}({len(parts)} shards done)" if parts else str(index))
        print(f"files still outstanding: {outstanding}")
        return 0 if (report["sha256_matches_20261028"]
                     and report["rows_matches_20261028"]) else 1

    if args.workers <= 1:
        # One process, one file at a time: the lowest commit footprint there is.
        # Each finished file leaves a .done.json, so a kill costs one file.
        reports = []
        for task in tasks:
            report = extract_file(task)
            reports.append(report)
            print(f"file {report['file_ordinal']}: rows={report['data_rows']} "
                  f"valid={report['valid_rows']} per_class={report['rows_per_class']} "
                  f"sha_ok={report['sha256_matches_20261028']} "
                  f"({report['seconds']}s)", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            reports = list(pool.map(extract_file, tasks))
    reports.sort(key=lambda item: item["file_ordinal"])
    rows_per_class = [sum(item["rows_per_class"][index] for item in reports)
                      for index in range(4)]

    merged: dict[int, str] = {}
    for item in reports:
        for key, value in item.pop("label_text").items():
            previous = merged.setdefault(int(key), value)
            if previous != value:
                raise SystemExit(f"class {key} spelled two ways across files")
    vocabulary = []
    for index, expected in enumerate(CLASS_LABEL_SHA256):
        label = merged.get(index)
        if label is None or _salted(label) != expected:
            raise SystemExit(f"class {index} label did not round-trip to its 2026-10-28 hash")
        vocabulary.append({"index": index, "label": label, "label_sha256": expected})
    vocabulary_path = args.out.parent / "label_vocabulary.json"
    vocabulary_path.write_text(json.dumps({
        "schema_version": "cycle2_label_vocabulary_v1",
        "salt_note": "label_sha256 = sha256(salt || utf8(label)); salt matches 2026-10-28",
        "source": "read from the Train CSVs during this extraction, not transcribed",
        "labels": vocabulary,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "schema_version": "cycle2_full_extract_v1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_root_sha256": _salted(str(train_dir)),
        "shape9_feature_names": list(SHAPE9_NAMES),
        "scale8_feature_names": list(SCALE8_NAMES),
        "reason_codes": list(REASON_CODES),
        "quarantined_rows": sorted(f"{a}:{b}" for a, b in QUARANTINE),
        "files": reports,
        "totals": {
            "data_rows": sum(item["data_rows"] for item in reports),
            "labeled_rows": sum(item["labeled_rows"] for item in reports),
            "valid_rows": sum(item["valid_rows"] for item in reports),
            "unlabeled_rows": sum(item["unlabeled_rows"] for item in reports),
            "skipped_rows": sum(item["skipped_rows"] for item in reports),
        },
        "rows_per_class": rows_per_class,
        "expected_rows_per_class": list(EXPECTED_CLASS_ROWS),
        "rows_per_class_match": rows_per_class == list(EXPECTED_CLASS_ROWS),
        "all_sha256_match": all(item["sha256_matches_20261028"] for item in reports),
        "all_rows_match": all(item["rows_matches_20261028"] for item in reports),
        "wall_seconds": round(time.perf_counter() - started, 1),
        "limitations": [
            "Lengths are local-tangent polyline geometry in km, not distance per unit time.",
            "No per-point timestamp exists, so no speed or acceleration is derived.",
            "Separate MultiLineString parts are never joined.",
            "Source CSVs were opened read only and were not modified.",
        ],
    }
    report_path = args.out / "extract_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("totals", "rows_per_class", "rows_per_class_match",
                       "all_sha256_match", "all_rows_match", "wall_seconds")},
                     ensure_ascii=False, indent=2))
    print(f"report -> {report_path}")
    print(f"labels -> {vocabulary_path}")
    return 0 if (summary["all_sha256_match"] and summary["all_rows_match"]
                 and summary["rows_per_class_match"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
