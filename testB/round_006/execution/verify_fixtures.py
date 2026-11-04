"""Round006 executor fixtures for the two Round005 open gates.

Gate 1 (empty-schema provenance): an arbitrary caller template must no longer
reach publication; the canonical empty frame must come from the real Arrow
source schema and must strictly equal the canonical AST result.

Gate 2 (bounded metadata): per-part metadata retained in RAM must not grow with
batch count, while the complete per-part list must still exist on disk and be
sufficient to reconstruct the canonical frame.

Usage:
  python -B verify_fixtures.py --fixtures
  python -B verify_fixtures.py --sample
"""
from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.testing import assert_frame_equal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import isolated_stage as stg  # noqa: E402
from bounded_loader import UnsupportedDomain  # noqa: E402

DATA_ROOT = Path("D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/"
                 "29-30일 모델 심층 분석/분석 결과")
CANONICAL = DATA_ROOT / "tools" / "run_remeasure_20261031.py"
CANONICAL_SHA = "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c"
TRAIN1 = DATA_ROOT / "outputs" / "remeasure_20261031" / "rows_train_1.parquet"
TRAIN1_SHA = "7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140"

COLUMNS = ["row_index", "rfid_id", "part_dt", "rfid_time", "key_valid",
           "wkt_valid", "len_m", "bbox_m", "cen_lon", "cen_lat"]
STRICT = dict(check_exact=True, check_index_type=True, check_column_type=True,
              check_frame_type=True, check_names=True, check_dtype=True)

RESULTS: list[dict] = []


def record(name: str, detail=None) -> None:
    RESULTS.append({"case": name, "passed": True, "detail": detail})
    print(f"PASS {name}" + (f" :: {detail}" if detail else ""))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pin_inputs() -> dict:
    pinned = {}
    for label, path, expected in (("canonical", CANONICAL, CANONICAL_SHA),
                                  ("train_month1", TRAIN1, TRAIN1_SHA)):
        actual = sha256_file(path)
        if actual != expected:
            raise SystemExit(f"pinned input {label} sha mismatch: {actual} != {expected}")
        pinned[label] = actual
    for label in ("bounded_loader.py", "isolated_stage.py"):
        pinned[label] = sha256_file(HERE / label)
    return pinned


# --------------------------------------------------------------------------
# canonical load_rows, extracted by AST and driven with injected fake parquet
# --------------------------------------------------------------------------
def canonical_load_rows(tables_by_month: dict[int, pa.Table]):
    """Return the pinned canonical `load_rows`, reading from in-memory tables."""
    source = CANONICAL.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CANONICAL))
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "load_rows")

    class FakeParquet:
        def read_table(self, path, columns=None):
            month = int(str(path).rsplit("/", 1)[-1])
            table = tables_by_month[month]
            return table.select(list(columns)) if columns is not None else table

    namespace = {"pd": pd, "np": np, "pq": FakeParquet(), "gc": gc,
                 "log": lambda *a, **k: None,
                 "parquet_path": lambda dataset, month: f"{dataset}/{month}",
                 "MONTHS": tuple(sorted(tables_by_month))}
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(CANONICAL), "exec"), namespace)
    return namespace["load_rows"]


SOURCE_SCHEMA = pq.ParquetFile(TRAIN1).schema_arrow


def batch(rows: list[dict]) -> pa.RecordBatch:
    """Build a RecordBatch in the real train schema from python rows."""
    names = [f.name for f in SOURCE_SCHEMA]
    data = {name: pa.array([r.get(name) for r in rows], type=SOURCE_SCHEMA.field(name).type)
            for name in names}
    return pa.RecordBatch.from_pydict(data, schema=SOURCE_SCHEMA)


def table_of(rows: list[dict]) -> pa.Table:
    return pa.Table.from_batches([batch(rows)], schema=SOURCE_SCHEMA)


def row(**kw) -> dict:
    base = {"row_index": 0, "part_dt": "20260101", "rfid_id": "1001",
            "rfid_time": np.int16(1), "fishing_code": "A", "key_valid": True,
            "wkt_valid": True, "n_coords": np.int32(2), "len_m": 1.0,
            "bbox_m": 2.0, "cen_lon": 3.0, "cen_lat": 4.0}
    base.update(kw)
    return base


def reconstruct(final: Path) -> pd.DataFrame:
    """Rebuild the frame using only the published contract: parts.jsonl order."""
    manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    lines = [json.loads(l) for l in
             (final / manifest["parts_file"]).read_text(encoding="utf-8").splitlines() if l]
    if len(lines) != manifest["parts_file_lines"]:
        raise AssertionError("parts.jsonl line count disagrees with manifest")
    digest = hashlib.sha256()
    for part in lines:
        digest.update((json.dumps(part, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    if digest.hexdigest() != manifest["parts_file_sha256"]:
        raise AssertionError("parts.jsonl digest disagrees with manifest")
    pieces = []
    for part in lines:
        path = final / part["name"]
        if sha256_file(path) != part["sha256"]:
            raise AssertionError(f"part sha mismatch: {part['name']}")
        frame = pq.read_table(path).to_pandas()
        labels = frame.pop("__canonical_index__").to_numpy()
        frame.index = pd.Index(labels)
        pieces.append(frame)
    out = pd.concat(pieces) if len(pieces) > 1 else pieces[0]
    if manifest["index_range_reconstructable"]:
        out.index = pd.RangeIndex(0, len(out))
    return out


class Workspace:
    """A private allowed root under this round's execution directory."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix=".fixture-", dir=HERE))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.root, ignore_errors=True)

    def final(self, name: str = "out") -> Path:
        return self.root / name


def run(ws: Workspace, name="out", **kw) -> dict:
    return stg.run_testfit(columns=COLUMNS, allowed_root=ws.root, final=None,
                           final_path=ws.final(name), stage="testfit", **kw) \
        if False else stg.run_testfit(columns=COLUMNS, allowed_root=ws.root,
                                      final_path=ws.final(name), stage="testfit", **kw)


def denied(fn, *types) -> Exception:
    try:
        fn()
    except types as exc:  # noqa: B902
        return exc
    raise AssertionError(f"expected one of {types} but call succeeded")


# --------------------------------------------------------------------------
# Gate 1 : empty-schema provenance
# --------------------------------------------------------------------------
def canonical_empty_expected() -> pd.DataFrame:
    """The canonical AST result when every month is present but has no rows."""
    load_rows = canonical_load_rows({1: table_of([]), 2: table_of([])})
    return load_rows("train", COLUMNS, months=[1, 2], key_valid_only=True)


def gate1_empty_schema() -> None:
    expected = canonical_empty_expected()
    record("g1.canonical_empty_reference",
           {"columns": list(expected.columns),
            "dtypes": {c: str(t) for c, t in expected.dtypes.items()},
            "index_type": type(expected.index).__name__, "rows": len(expected)})

    # 1a. no batches and no source schema -> fail closed, nothing published
    with Workspace() as ws:
        exc = denied(lambda: run(ws, batches=[], month=1), stg.EmptySchemaUnavailable)
        assert not ws.final().exists(), "nothing may be published without a schema"
        assert (ws.root / "quarantine").exists(), "failure must be quarantined"
        record("g1a.no_schema_fails_closed", str(exc)[:80])

    # 1b. real source schema only -> module builds the canonical empty frame
    with Workspace() as ws:
        receipt = run(ws, batches=[], month=1, empty_source_schema=SOURCE_SCHEMA)
        assert receipt["published"] is True
        got = reconstruct(ws.final())
        assert_frame_equal(got, expected, **STRICT)
        record("g1b.schema_only_matches_canonical",
               {"provenance": receipt["empty_schema_provenance"][:60], "rows": len(got)})

    # 1c. exact canonical template supplied -> accepted as a cross-check
    with Workspace() as ws:
        receipt = run(ws, batches=[], month=1, empty_source_schema=SOURCE_SCHEMA,
                      empty_template=expected.copy())
        assert_frame_equal(reconstruct(ws.final()), expected, **STRICT)
        assert "cross-checked equal" in receipt["empty_schema_provenance"]
        record("g1c.exact_template_cross_checked")

    # 1d. the Round005 hole: wrong feature dtype must now be refused
    with Workspace() as ws:
        bad = expected.copy()
        bad["wkt_valid"] = bad["wkt_valid"].astype(object)
        exc = denied(lambda: run(ws, batches=[], month=1,
                                 empty_source_schema=SOURCE_SCHEMA, empty_template=bad),
                     ValueError)
        assert "dtypes differ" in str(exc), str(exc)
        assert not ws.final().exists(), "wrong-dtype template must not be published"
        record("g1d.wrong_dtype_template_refused", str(exc)[:90])

    # 1e. the Round005 hole: wrong index class must now be refused
    with Workspace() as ws:
        bad = expected.copy()
        bad.index = pd.Index([], dtype="int64")
        exc = denied(lambda: run(ws, batches=[], month=1,
                                 empty_source_schema=SOURCE_SCHEMA, empty_template=bad),
                     ValueError)
        assert "index class" in str(exc), str(exc)
        assert not ws.final().exists(), "wrong-index template must not be published"
        record("g1e.wrong_index_class_template_refused", str(exc)[:90])

    # 1f. wrong column order / nonempty template still refused
    for label, bad in (("reordered", expected[list(expected.columns)[::-1]].copy()),
                       ("nonempty", pd.DataFrame({c: [v] for c, v in
                                                  zip(expected.columns, range(len(expected.columns)))}))):
        with Workspace() as ws:
            denied(lambda bad=bad: run(ws, batches=[], month=1,
                                       empty_source_schema=SOURCE_SCHEMA, empty_template=bad),
                   ValueError)
            assert not ws.final().exists()
        record(f"g1f.{label}_template_refused")

    # 1g. a template without the real schema is not a schema source
    with Workspace() as ws:
        exc = denied(lambda: run(ws, batches=[], month=1, empty_template=expected.copy()),
                     stg.StageDenied)
        assert "cross-check" in str(exc)
        record("g1g.template_without_schema_denied", str(exc)[:90])

    # 1h. a non-Arrow object cannot impersonate a source schema
    with Workspace() as ws:
        denied(lambda: run(ws, batches=[], month=1,
                           empty_source_schema={"rfid_id": "int64"}), stg.StageDenied)
        record("g1h.fake_schema_object_denied")

    # 1i. a schema missing a projected column fails closed
    with Workspace() as ws:
        thin = pa.schema([SOURCE_SCHEMA.field("row_index")])
        exc = denied(lambda: run(ws, batches=[], month=1, empty_source_schema=thin),
                     stg.StageDenied)
        assert "lacks required columns" in str(exc)
        record("g1i.incomplete_schema_denied", str(exc)[:90])

    # 1j. months=[] keeps the canonical pd.concat([]) ValueError
    with Workspace() as ws:
        denied(lambda: run(ws, months=[], batches_for_month=lambda m: [],
                           empty_source_schema=SOURCE_SCHEMA), ValueError)
        record("g1j.empty_month_list_preserves_canonical_error")

    # 1k. a real zero-row batch still carries its own schema (no template path)
    with Workspace() as ws:
        receipt = run(ws, batches=[batch([])], month=1)
        assert "empty_schema_provenance" not in receipt
        assert_frame_equal(reconstruct(ws.final()),
                           canonical_load_rows({1: table_of([])})("train", COLUMNS, months=[1]),
                           **STRICT)
        record("g1k.zero_row_batch_keeps_own_schema")


# --------------------------------------------------------------------------
# Gate 2 : bounded per-part metadata
# --------------------------------------------------------------------------
def deep_size(obj, seen=None) -> int:
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return 0
    seen.add(id(obj))
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            size += deep_size(k, seen) + deep_size(v, seen)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            size += deep_size(v, seen)
    return size


METADATA_KEYS = ("files_head", "files_last", "files_total", "files_retention",
                 "parts_file", "parts_file_sha256", "parts_file_lines",
                 "metadata_retain_limit")


def gate2_bounded_metadata() -> None:
    sizes = {}
    for count in (1, 8, 32, 128):
        rows = [row(row_index=i, rfid_id=str(1000 + i)) for i in range(4)]
        with Workspace() as ws:
            receipt = run(ws, batches=[batch(rows) for _ in range(count)], month=1)
            assert receipt["batches"] == count
            assert receipt["rows"] == 4 * count
            retained = len(receipt["files_head"]) + (1 if receipt["files_last"] else 0)
            assert len(receipt["files_head"]) <= stg.DEFAULT_METADATA_RETAIN
            sizes[count] = {"metadata_bytes": sum(deep_size(receipt[k]) for k in METADATA_KEYS),
                            "retained_entries": retained,
                            "parts_file_lines": receipt["parts_file_lines"]}
            # the complete per-part list is on disk and is still sufficient
            got = reconstruct(ws.final())
            expected = canonical_load_rows({1: table_of(rows * count)})("train", COLUMNS, months=[1])
            assert_frame_equal(got, expected, **STRICT)
    record("g2a.metadata_sizes", sizes)
    base = sizes[8]["metadata_bytes"]
    for count in (32, 128):
        growth = sizes[count]["metadata_bytes"] - base
        assert growth <= 128, f"metadata grew {growth} bytes from 8 to {count} batches"
    assert sizes[128]["metadata_bytes"] - sizes[32]["metadata_bytes"] <= 0 + 128
    assert sizes[128]["parts_file_lines"] == 128
    assert sizes[128]["retained_entries"] == stg.DEFAULT_METADATA_RETAIN + 1
    record("g2b.metadata_is_not_O_batches",
           {"bytes_8": base, "bytes_32": sizes[32]["metadata_bytes"],
            "bytes_128": sizes[128]["metadata_bytes"]})

    # explicit cap is honoured and validated
    with Workspace() as ws:
        receipt = run(ws, batches=[batch([row()]) for _ in range(10)], month=1,
                      metadata_retain=2)
        assert len(receipt["files_head"]) == 2 and receipt["files_total"] == 10
        assert "complete list in parts.jsonl" in receipt["files_retention"]
        record("g2c.explicit_retain_cap_honoured", receipt["files_retention"])
    for bad in (0, -1, True, 1.5):
        with Workspace() as ws:
            denied(lambda bad=bad: run(ws, batches=[batch([row()])], month=1,
                                       metadata_retain=bad), stg.StageDenied)
    record("g2d.invalid_retain_cap_denied")

    # schema drift across batches is still refused with the bounded manifest
    with Workspace() as ws:
        thin = pa.schema([SOURCE_SCHEMA.field(n) for n in
                          ["row_index", "rfid_id", "part_dt", "rfid_time", "key_valid", "wkt_valid",
                           "len_m", "bbox_m", "cen_lon", "cen_lat"]])

        class OddBatch:
            num_rows = 1

            def select(self, cols):
                data = {n: pa.array([1 if n == "row_index" else None],
                                    type=thin.field(n).type) for n in cols}
                data["key_valid"] = pa.array([True])
                data["rfid_id"] = pa.array(["7"])
                data["part_dt"] = pa.array(["20260101"])
                return pa.RecordBatch.from_pydict({n: data[n] for n in cols})

        exc = denied(lambda: run(ws, batches=[batch([row()]), OddBatch()], month=1),
                     stg.StageDenied, AssertionError, ValueError, TypeError)
        assert not ws.final().exists(), "drift must not publish"
        record("g2e.schema_drift_refused", type(exc).__name__)

    # late unsupported value: earlier parts stay quarantined, nothing published
    with Workspace() as ws:
        good = batch([row(rfid_id="1001")])
        bad = batch([row(rfid_id="1.5")])
        denied(lambda: run(ws, batches=[good, bad], month=1), UnsupportedDomain)
        assert not ws.final().exists()
        quarantined = list((ws.root / "quarantine").iterdir())
        assert quarantined, "late failure must leave a quarantine receipt"
        receipt = json.loads((quarantined[0] / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["published"] is False and receipt["quarantined"] is True
        assert receipt["files_total"] == 1 and len(receipt["files_head"]) == 1
        record("g2f.late_failure_quarantined_bounded_receipt",
               {"files_total": receipt["files_total"], "error_type": receipt["error_type"]})

    # commit failure keeps the manifest out of the final path
    with Workspace() as ws:
        def boom(src, dst):
            raise OSError("simulated commit failure")
        denied(lambda: run(ws, batches=[batch([row()])], month=1, commit=boom), OSError)
        assert not ws.final().exists()
        record("g2g.commit_failure_not_published")

    # index holes from numeric drops are preserved through the disk round-trip
    with Workspace() as ws:
        rows = [row(row_index=0, rfid_id="1001"), row(row_index=1, rfid_id="abc"),
                row(row_index=2, rfid_id="1003"), row(row_index=3, key_valid=False),
                row(row_index=4, rfid_id="1005")]
        receipt = run(ws, batches=[batch(rows[:3]), batch(rows[3:])], month=1)
        got = reconstruct(ws.final())
        expected = canonical_load_rows({1: table_of(rows)})("train", COLUMNS, months=[1])
        assert_frame_equal(got, expected, **STRICT)
        assert receipt["index_range_reconstructable"] is False
        assert list(got.index) == list(expected.index)
        record("g2h.index_holes_preserved", {"labels": [int(i) for i in got.index]})


# --------------------------------------------------------------------------
# fixed real sample, re-run through the changed caller
# --------------------------------------------------------------------------
def sample() -> dict:
    pinned = pin_inputs()
    pf = pq.ParquetFile(TRAIN1)
    batches, taken = [], 0
    for rb in pf.iter_batches(batch_size=4096, columns=COLUMNS):
        batches.append(rb)
        taken += rb.num_rows
        if taken >= 16384:
            break
    assert taken == 16384 and [b.num_rows for b in batches] == [4096] * 4, [b.num_rows for b in batches]
    combined = pa.Table.from_batches(batches)
    expected = canonical_load_rows({1: combined})("train", COLUMNS, months=[1])
    with Workspace() as ws:
        receipt = run(ws, batches=batches, month=1, empty_source_schema=SOURCE_SCHEMA)
        got = reconstruct(ws.final())
        assert_frame_equal(got, expected, **STRICT)
        detail = {"rows": int(receipt["rows"]), "batches": int(receipt["batches"]),
                  "metadata_bytes": sum(deep_size(receipt[k]) for k in METADATA_KEYS),
                  "index_range_reconstructable": receipt["index_range_reconstructable"],
                  "dtypes": receipt["dtypes"],
                  "parts_file_sha256": receipt["parts_file_sha256"]}
    record("s1.fixed_sample_strict_equal", detail)
    post = pin_inputs()
    assert post == pinned, "pinned inputs changed during the run"
    record("s2.pinned_inputs_unchanged", pinned)
    return detail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    started = time.strftime("%Y-%m-%d %H:%M:%S %z")
    pinned = pin_inputs()
    if args.fixtures:
        gate1_empty_schema()
        gate2_bounded_metadata()
    if args.sample:
        sample()
    payload = {"started": started, "finished": time.strftime("%Y-%m-%d %H:%M:%S %z"),
               "mode": {"fixtures": args.fixtures, "sample": args.sample},
               "pinned_inputs": pinned,
               "environment": {"python": platform.python_version(), "pandas": pd.__version__,
                               "numpy": np.__version__, "pyarrow": pa.__version__,
                               "platform": platform.platform()},
               "cases": len(RESULTS), "results": RESULTS,
               "all_assertions_passed": True}
    name = "fixture_result.json" if args.fixtures and not args.sample else \
           ("sample_result.json" if args.sample and not args.fixtures else "combined_result.json")
    (HERE / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")
    print(f"cases={len(RESULTS)} all_assertions_passed=true written={name}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.exit(main())
