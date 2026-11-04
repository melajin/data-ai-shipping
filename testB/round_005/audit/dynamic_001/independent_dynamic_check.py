from __future__ import annotations

import ast
import ctypes
import gc
import hashlib
import importlib
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
E_DIR = Path(r"D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/testB/round_005/execution")
CANONICAL = Path(r"D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py")
SOURCE_HASHES = {
    "run_remeasure_20261031.py": "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c",
    "run_008_testB_20261101.py": "cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8",
    "run_005_F156_merge_20261101.py": "e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4",
    "run_cycle4_3_featAC_20261101.py": "8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3",
}
E_HASHES = {
    "bounded_loader.py": "0c60af2d4453c4ffb0a640410006e09247218a96633075cdd89567e4ae6f3cee",
    "isolated_stage.py": "76f3f7f8e3a39a27d8c24f1d3532b83181bf2e20470da38b7543b55a04795fea",
    "verify_fixtures.py": "61c7b9c3acddce4e904bf3b368ff8c3828a78f6344d5cfd2aee072c9219ed57f",
}
SAMPLE = Path(r"D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/outputs/remeasure_20261031/rows_train_1.parquet")
SAMPLE_SHA = "7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140"
SAMPLE_COLUMNS = ["row_index", "rfid_id", "part_dt", "rfid_time", "key_valid", "wkt_valid", "len_m", "bbox_m", "cen_lon", "cen_lat"]

SCHEMA = pa.schema([
    ("row_index", pa.int64()), ("rfid_id", pa.string()), ("part_dt", pa.string()),
    ("rfid_time", pa.int16()), ("key_valid", pa.bool_()), ("wkt_valid", pa.bool_()),
    ("len_m", pa.float64()), ("bbox_m", pa.float64()), ("cen_lon", pa.float64()), ("cen_lat", pa.float64()),
])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def snapshot_hashes() -> dict:
    current_sources = {}
    for name, expected in SOURCE_HASHES.items():
        path = CANONICAL.parent / name
        actual = sha256(path)
        current_sources[name] = {"path": str(path), "sha256": actual, "expected": expected, "match": actual == expected}
    current_e = {}
    for name, expected in E_HASHES.items():
        path = E_DIR / name
        actual = sha256(path)
        current_e[name] = {"path": str(path), "sha256": actual, "expected": expected, "match": actual == expected}
    return {"canonical_sources": current_sources, "e_snapshot": current_e,
            "all_match": all(x["match"] for x in current_sources.values()) and all(x["match"] for x in current_e.values())}


def check_snapshot(where: str) -> dict:
    result = snapshot_hashes()
    (HERE / f"hash_check_{where}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["all_match"]:
        raise RuntimeError(f"source or E snapshot hash mismatch at {where}: {result}")
    return result


def get_e_modules():
    if str(E_DIR) not in sys.path:
        sys.path.insert(0, str(E_DIR))
    # Imported only as the implementation under examination, never as oracle/comparator.
    return importlib.import_module("bounded_loader"), importlib.import_module("isolated_stage")


def canonical_loader():
    raw = CANONICAL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_HASHES["run_remeasure_20261031.py"]:
        raise RuntimeError("canonical source changed before AST extraction")
    tree = ast.parse(raw.decode("utf-8"), filename=str(CANONICAL))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "load_rows")
    import types
    namespace = {
        "pd": pd, "np": np, "gc": gc, "log": lambda *_args, **_kwargs: None,
        "MONTHS": tuple(range(1, 7)), "pq": types.SimpleNamespace(read_table=None),
        "parquet_path": lambda dataset, month: f"fixture:{dataset}:{month}",
    }
    module = ast.Module(body=[fn], type_ignores=[])
    exec(compile(module, str(CANONICAL), "exec"), namespace)
    return namespace["load_rows"], namespace


def set_canonical_tables(namespace, tables):
    namespace["pq"].read_table = lambda path, columns: tables[int(path.rsplit(":", 1)[1])].select(columns)


def oracle(tables, columns, months, key_valid_only=True):
    """Independent whole-column implementation of the pinned API contract."""
    requested = [name for name in columns if name != "month"]
    out_cols = requested if "key_valid" in requested else requested + ["key_valid"]
    needed = set(out_cols)
    frames = []
    for month in months:
        frame = tables[month].select(list(needed)).to_pandas()
        if key_valid_only:
            frame = frame[frame["key_valid"]]
        frame["month"] = np.int8(month)
        frames.append(frame[out_cols + ["month"]])
    out = pd.concat(frames, ignore_index=True, copy=False)
    if "rfid_id" in out.columns:
        converted_id = pd.to_numeric(out["rfid_id"], errors="coerce")
        keep_id = ~converted_id.isna()
        out = out[keep_id]
        converted_id = converted_id[keep_id]
        out["rfid_id"] = converted_id.astype(np.int64)
    if "part_dt" in out.columns:
        converted_date = pd.to_numeric(out["part_dt"], errors="coerce")
        keep_date = ~converted_date.isna()
        out = out[keep_date]
        converted_date = converted_date[keep_date]
        out["part_dt"] = converted_date.astype(np.int32)
    return out


def strict_equal(expected, actual, context):
    try:
        pd.testing.assert_frame_equal(
            expected, actual, check_exact=True, check_index_type=True,
            check_column_type=True, check_frame_type=True, check_names=True,
            check_like=False, check_dtype=True,
        )
    except AssertionError as exc:
        raise AssertionError(f"{context}: strict DataFrame mismatch: {exc}") from exc


def rows(values):
    return [dict(zip(SCHEMA.names, value)) for value in values]


def table(values):
    return pa.Table.from_pylist(values, schema=SCHEMA)


def make_hand(records, columns, index_kind="index", index_values=None):
    base = [c for c in columns if c != "month"]
    out_cols = base if "key_valid" in base else base + ["key_valid"]
    out_cols = out_cols + ["month"]
    selected = [{c: row[c] for c in out_cols} for row in records]
    frame = pd.DataFrame(selected, columns=out_cols)
    casts = {"rfid_id": "int64", "part_dt": "int32", "rfid_time": "int16",
             "key_valid": "bool", "wkt_valid": "bool", "len_m": "float64",
             "bbox_m": "float64", "cen_lon": "float64", "cen_lat": "float64", "month": "int8", "row_index": "int64"}
    for col in frame.columns:
        if col in casts:
            frame[col] = frame[col].astype(casts[col])
    if index_kind == "range":
        frame.index = pd.RangeIndex(0, len(frame))
    else:
        frame.index = pd.Index(index_values if index_values is not None else [], dtype="int64")
    return frame


def fixture_tables():
    m1 = table(rows([
        (100, "001", "20250101", 10, True, True, 1.5, 2.5, 130.0, 32.0),
        (101, "bad", "20250102", 11, True, False, 1.6, 2.6, 130.1, 32.1),
        (102, "3", "oops", 12, True, True, 1.7, 2.7, 130.2, 32.2),
        (103, "4", "20250104", 13, False, False, 1.8, 2.8, 130.3, 32.3),
    ]))
    m2 = table(rows([
        (200, "+5", "20250105", 20, True, True, 2.0, 3.0, 131.0, 33.0),
        (201, "6", "20250106", 21, True, False, 2.1, 3.1, 131.1, 33.1),
        (202, "7", "20250107", 22, False, True, 2.2, 3.2, 131.2, 33.2),
    ]))
    return {1: m1, 2: m2}


def canonical_and_oracle(tables, columns, months, key_only=True):
    original, ns = canonical_loader()
    set_canonical_tables(ns, tables)
    ast_result = original("testfit", columns, months=tuple(months), key_valid_only=key_only)
    independent = oracle(tables, columns, tuple(months), key_valid_only=key_only)
    strict_equal(ast_result, independent, "canonical AST vs independent whole-column oracle")
    return ast_result, independent


def adapter_frames(loader, tables, columns, months, key_only=True, max_chunk=2, trace=None, trace_limit=100):
    def batch_source(month):
        return tables[month].select([c for c in columns if c != "month"] + ([] if "key_valid" in columns else ["key_valid"])).to_batches(max_chunksize=max_chunk)
    return list(loader.transform_months(months, batch_source, columns=columns,
                                        key_valid_only=key_only, trace=trace, trace_limit=trace_limit))


def combine_parts(parts):
    if not parts:
        return None
    labels = [int(x) for part in parts for x in part.index]
    out = pd.concat(parts, axis=0, copy=False)
    contiguous = all(type(part.index) is pd.RangeIndex for part in parts)
    contiguous = contiguous and labels == list(range(len(labels)))
    out.index = pd.RangeIndex(0, len(out)) if contiguous else pd.Index(labels, dtype="int64")
    return out


def compare_stream(loader, tables, columns, months, key_only, hand, case):
    ast_frame, oracle_frame = canonical_and_oracle(tables, columns, months, key_only)
    strict_equal(hand, ast_frame, f"{case}: hand expected vs canonical AST")
    strict_equal(hand, oracle_frame, f"{case}: hand expected vs oracle")
    parts = adapter_frames(loader, tables, columns, months, key_only)
    combined = combine_parts(parts)
    if combined is None:
        raise AssertionError(f"{case}: no adapter frame; compare through caller empty contract separately")
    strict_equal(hand, combined, f"{case}: hand expected vs E stream")
    return {"case": case, "pass": True, "rows": len(hand), "columns": list(hand.columns),
            "dtypes": {c: str(t) for c, t in hand.dtypes.items()}, "index_type": type(hand.index).__name__,
            "index_name": hand.index.name, "index_labels": [int(x) for x in hand.index]}


class PandasBatch:
    def __init__(self, df):
        self.df = df
        self.num_rows = len(df)

    def select(self, columns):
        return PandasBatch(self.df.loc[:, columns])

    def to_pandas(self):
        return self.df.copy()


class PandasTable(PandasBatch):
    pass


def canonical_from_pandas(df, columns, months=(1,), key_only=True):
    original, ns = canonical_loader()
    ns["pq"].read_table = lambda _path, columns: PandasTable(df.loc[:, columns])
    return original("testfit", columns, months=months, key_valid_only=key_only)


def _deep_size(value, seen=None):
    if seen is None:
        seen = set()
    ident = id(value)
    if ident in seen:
        return 0
    seen.add(ident)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(_deep_size(k, seen) + _deep_size(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        size += sum(_deep_size(x, seen) for x in value)
    return size


def reconstruct_stage(stage_mod, root, final_name, *, columns, tables=None, batches=None,
                      months=None, batches_for_month=None, key_only=True, template=None,
                      commit=None, writer=None, trace_sink=None):
    kwargs = dict(columns=columns, allowed_root=root, final_path=root / final_name,
                  stage="testfit", dataset="testfit", key_valid_only=key_only,
                  empty_template=template, trace_sink=trace_sink)
    if months is None:
        kwargs.update(batches=batches, month=1)
    else:
        kwargs.update(months=months, batches_for_month=batches_for_month)
    if commit is not None:
        kwargs["commit"] = commit
    if writer is not None:
        kwargs["parquet_writer"] = writer
    receipt = stage_mod.run_testfit(**kwargs)
    final = root / final_name
    manifest_path = final / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parts = []
    for item in manifest["files"]:
        p = final / item["name"]
        if sha256(p) != item["sha256"]:
            raise AssertionError(f"committed part hash mismatch: {p}")
        part = pd.read_parquet(p)
        labels = part.pop("__canonical_index__").to_numpy().tolist()
        part.index = pd.Index(labels, dtype="int64")
        part.index.name = item.get("index_name")
        parts.append(part)
    if not parts:
        return receipt, manifest, None
    rebuilt = pd.concat(parts, axis=0, copy=False)
    if manifest["index_range_reconstructable"]:
        rebuilt.index = pd.RangeIndex(0, len(rebuilt))
    else:
        rebuilt.index = pd.Index([int(x) for part in parts for x in part.index], dtype="int64")
    return receipt, manifest, rebuilt


def atomic_test_root(label):
    base = HERE / "scratch" / f"{label}-{os.getpid()}-{time.time_ns()}"
    root = base / "allowed"
    root.mkdir(parents=True)
    return base, root


def fixture_run(loader, stage_mod):
    results = []
    tables = fixture_tables()
    req = ["row_index", "rfid_id", "part_dt", "rfid_time", "wkt_valid"]
    main_records = [
        {"row_index": 100, "rfid_id": 1, "part_dt": 20250101, "rfid_time": 10, "wkt_valid": True, "key_valid": True, "month": 1, "len_m": 1.5},
        {"row_index": 200, "rfid_id": 5, "part_dt": 20250105, "rfid_time": 20, "wkt_valid": True, "key_valid": True, "month": 2, "len_m": 2.0},
        {"row_index": 201, "rfid_id": 6, "part_dt": 20250106, "rfid_time": 21, "wkt_valid": False, "key_valid": True, "month": 2, "len_m": 2.1},
    ]
    results.append(compare_stream(loader, tables, req, (1, 2), True,
                                  make_hand(main_records, req, "index", [0, 3, 4]), "both_keys_month_order_true_index_holes"))
    false_records = [main_records[0],
        {"row_index": 103, "rfid_id": 4, "part_dt": 20250104, "rfid_time": 13, "wkt_valid": False, "key_valid": False, "month": 1},
        main_records[1], main_records[2],
        {"row_index": 202, "rfid_id": 7, "part_dt": 20250107, "rfid_time": 22, "wkt_valid": True, "key_valid": False, "month": 2}]
    results.append(compare_stream(loader, tables, req, (1, 2), False,
                                  make_hand(false_records, req, "index", [0, 3, 4, 5, 6]), "both_keys_key_valid_false"))
    id_req = ["rfid_id"]
    id_records = [
        {"rfid_id": 1, "key_valid": True, "month": 1},
        {"rfid_id": 3, "key_valid": True, "month": 1},
        {"rfid_id": 5, "key_valid": True, "month": 2},
        {"rfid_id": 6, "key_valid": True, "month": 2},
    ]
    results.append(compare_stream(loader, tables, id_req, (1, 2), True,
                                  make_hand(id_records, id_req, "index", [0, 2, 3, 4]), "id_only_skips_date_conversion"))
    date_rows = rows([
        (300, "1.5", "20250111", 30, True, True, 3.0, 4.0, 132.0, 34.0),
        (301, "bad", "20250112", 31, True, False, 3.1, 4.1, 132.1, 34.1),
        (302, "9", "20250113", 32, False, True, 3.2, 4.2, 132.2, 34.2),
    ])
    date_tables = {1: table(date_rows)}
    date_req = ["part_dt"]
    date_records = [
        {"part_dt": 20250111, "key_valid": True, "month": 1},
        {"part_dt": 20250112, "key_valid": True, "month": 1},
    ]
    results.append(compare_stream(loader, date_tables, date_req, (1,), True,
                                  make_hand(date_records, date_req, "range"), "date_only_skips_id_conversion"))

    no_numeric_req = ["wkt_valid", "len_m"]
    no_numeric_records = [
        {"wkt_valid": True, "len_m": 1.5, "key_valid": True, "month": 1},
        {"wkt_valid": False, "len_m": 1.6, "key_valid": True, "month": 1},
        {"wkt_valid": True, "len_m": 1.7, "key_valid": True, "month": 1},
        {"wkt_valid": True, "len_m": 2.0, "key_valid": True, "month": 2},
        {"wkt_valid": False, "len_m": 2.1, "key_valid": True, "month": 2},
    ]
    results.append(compare_stream(loader, tables, no_numeric_req, (1, 2), True,
                                  make_hand(no_numeric_records, no_numeric_req, "range"), "no_numeric_keys_implicit_key_month"))
    km_req = ["month", "key_valid"]
    km_records = [{"key_valid": True, "month": 1}, {"key_valid": True, "month": 1}, {"key_valid": True, "month": 1},
                  {"key_valid": True, "month": 2}, {"key_valid": True, "month": 2}]
    results.append(compare_stream(loader, tables, km_req, (1, 2), True,
                                  make_hand(km_records, km_req, "range"), "explicit_month_key_valid_and_output_order"))
    reverse_req = ["part_dt", "rfid_id", "month", "row_index"]
    reverse_records = [
        {"part_dt": 20250105, "rfid_id": 5, "month": 2, "row_index": 200, "key_valid": True},
        {"part_dt": 20250106, "rfid_id": 6, "month": 2, "row_index": 201, "key_valid": True},
        {"part_dt": 20250101, "rfid_id": 1, "month": 1, "row_index": 100, "key_valid": True},
    ]
    results.append(compare_stream(loader, tables, reverse_req, (2, 1), True,
                                  make_hand(reverse_records, reverse_req, "index", [0, 1, 2]), "caller_order_and_reversed_months"))

    # All numeric values invalid: exact empty output schema, index class and dtypes.
    all_bad = {1: table(rows([
        (400, "bad", "20250101", 40, True, True, 4.0, 5.0, 133.0, 35.0),
        (401, "junk", "20250102", 41, True, False, 4.1, 5.1, 133.1, 35.1),
    ]))}
    empty_req = ["row_index", "rfid_id", "part_dt", "wkt_valid"]
    ast_empty, oracle_empty = canonical_and_oracle(all_bad, empty_req, (1,), True)
    strict_equal(ast_empty, oracle_empty, "all numeric drop: AST/oracle")
    adapter_empty = combine_parts(adapter_frames(loader, all_bad, empty_req, (1,), True))
    strict_equal(ast_empty, adapter_empty, "all numeric drop: E"); results.append({"case":"all_rows_numeric_dropped","pass":True,"rows":0,"columns":list(ast_empty.columns),"dtypes":{c:str(t) for c,t in ast_empty.dtypes.items()},"index_type":type(ast_empty.index).__name__,"index_dtype":str(ast_empty.index.dtype)})

    # Month order/global admitted ordinals are independently hand fixed.
    reversed_expected = make_hand(reverse_records, reverse_req, "index", [0, 1, 2])
    strict_equal(reversed_expected, canonical_and_oracle(tables, reverse_req, (2, 1), True)[0], "reverse month expected")

    # Null, NaN, pd.NA and clear text are coercion drops; the unsupported date on
    # an ID-dropped row is never inspected because canonical ID processing comes first.
    null_df = pd.DataFrame({
        "row_index": pd.Series([0, 1, 2, 3, 4, 5, 6], dtype="int64"),
        "rfid_id": pd.Series(["1", None, float("nan"), pd.NA, "junk", "6", "7"], dtype=object),
        "part_dt": pd.Series(["20250101", "20250102", "20250103", "20250104", "1.5", "20250106", "20250107"], dtype=object),
        "rfid_time": pd.Series(range(7), dtype="int16"),
        "key_valid": pd.Series([True] * 7, dtype=bool),
        "wkt_valid": pd.Series([True, False, True, False, True, False, True], dtype=bool),
        "len_m": pd.Series([1.,2.,3.,4.,5.,6.,7.], dtype="float64"),
        "bbox_m": pd.Series([2.,3.,4.,5.,6.,7.,8.], dtype="float64"),
        "cen_lon": pd.Series([130.,131.,132.,133.,134.,135.,136.], dtype="float64"),
        "cen_lat": pd.Series([32.,33.,34.,35.,36.,37.,38.], dtype="float64"),
    })
    null_columns = ["rfid_id", "part_dt", "wkt_valid"]
    null_ast = canonical_from_pandas(null_df, null_columns)
    null_oracle_table = {1: PandasTable(null_df)}
    null_oracle = oracle(null_oracle_table, null_columns, (1,), True)
    strict_equal(null_ast, null_oracle, "null-ish AST/oracle")
    null_batches = [PandasBatch(null_df)]
    null_actual = combine_parts(list(loader.transform_batches(null_batches, month=1, columns=null_columns)))
    strict_equal(null_ast, null_actual, "null-ish E stream")
    if [int(x) for x in null_ast.index] != [0, 5, 6]:
        raise AssertionError(f"null-ish expected index/drop mask changed: {null_ast.index}")
    results.append({"case":"None_NaN_pdNA_text_drop_and_ID_before_date","pass":True,"rows":len(null_ast),"index_type":type(null_ast.index).__name__,"index_labels":[int(x) for x in null_ast.index]})

    # Unsupported numeric-like tokens must stop the whole adapter before yield.
    unsupported = [
        ("rfid_id", "9007199254740993"), ("rfid_id", "-9007199254740993"),
        ("rfid_id", "1.5"), ("rfid_id", "1e3"), ("rfid_id", " 2"),
        ("rfid_id", "１２"), ("rfid_id", "x" * 129), ("rfid_id", "9223372036854775808"),
        ("part_dt", "2147483648"), ("part_dt", "-2147483649"),
        ("part_dt", "20250101.5"), ("part_dt", "2.025e7"),
        ("part_dt", " 20250101"), ("part_dt", "２０２５０１０１"), ("part_dt", "x" * 129),
    ]
    rejected = []
    for field, token in unsupported:
        bad = rows([(500, token if field == "rfid_id" else "1", token if field == "part_dt" else "20250101", 50, True, True, 5., 6., 137., 39.)])
        seen = False
        try:
            for _frame in loader.transform_batches(table(bad).to_batches(max_chunksize=1), month=1, columns=["rfid_id", "part_dt"]):
                seen = True
        except loader.UnsupportedDomain as exc:
            if seen:
                raise AssertionError(f"{field} {token!r} was rejected only after a partial yield")
            rejected.append({"field":field,"length":len(token),"stopped_before_yield":True,"error_type":type(exc).__name__})
        else:
            raise AssertionError(f"unsupported token accepted/silently dropped: {field} {token!r}")
    results.append({"case":"unsupported_tokens_fail_closed_before_first_yield","pass":True,"count":len(rejected),"rejected":rejected})

    # An ID-invalid row's unsupported date is never inspected after the ID drop.
    id_first = {1: table(rows([
        (600, "bad", "1.5", 60, True, True, 6., 7., 138., 40.),
        (601, "2", "20250102", 61, True, False, 6.1, 7.1, 138.1, 40.1),
    ]))}
    id_first_req = ["rfid_id", "part_dt"]
    id_first_hand = make_hand([{"rfid_id":2,"part_dt":20250102,"key_valid":True,"month":1}], id_first_req, "index", [1])
    results.append(compare_stream(loader, id_first, id_first_req, (1,), True, id_first_hand, "ID_drop_before_unsupported_date"))

    # Empty month list must preserve canonical ValueError exactly, in both adapter and caller.
    orig, ns = canonical_loader(); set_canonical_tables(ns, tables)
    try:
        orig("testfit", ["rfid_id"], months=(), key_valid_only=True)
    except Exception as exc:
        original_error = (type(exc).__name__, str(exc))
    else:
        raise AssertionError("canonical empty months unexpectedly succeeded")
    try:
        list(loader.transform_months((), lambda _m: (), columns=["rfid_id"]))
    except Exception as exc:
        adapter_error = (type(exc).__name__, str(exc))
    else:
        raise AssertionError("adapter empty months unexpectedly succeeded")
    if original_error != adapter_error:
        raise AssertionError(f"empty-month error differs: {original_error} vs {adapter_error}")
    base, root = atomic_test_root("empty-months")
    try:
        stage_mod.run_testfit(months=(), batches_for_month=lambda _m: (), columns=["rfid_id"], allowed_root=root,
                              final_path=root/"empty", stage="testfit", empty_template=None)
    except ValueError as exc:
        if (type(exc).__name__, str(exc)) != original_error:
            raise AssertionError(f"caller empty-month error differs: {type(exc).__name__}: {exc}")
    else:
        raise AssertionError("caller empty month list unexpectedly succeeded")
    if (root/"empty").exists() or not list((root/"quarantine").glob("*/receipt.json")):
        raise AssertionError("empty-month failure was published or not quarantined")
    results.append({"case":"empty_month_list_value_error_preserved_and_quarantined","pass":True,"error":original_error,"final_absent":True})

    # Trace structure and bounded retention; callback's own storage is measured separately.
    no_trace_parts = adapter_frames(loader, tables, ["rfid_id"], (1, 2), True, max_chunk=1, trace=None)
    if any("trace" in part.attrs for part in no_trace_parts):
        raise AssertionError("trace=None unexpectedly attached trace state to output frames")
    capped = []
    _ = adapter_frames(loader, tables, ["rfid_id"], (1, 2), True, max_chunk=1, trace=capped, trace_limit=2)
    if len(capped) != 2 or any("output_index" in event or "indices" in event for event in capped):
        raise AssertionError("debug trace list exceeded cap or retained row indices")
    callback_events = []
    _ = adapter_frames(loader, tables, ["rfid_id"], (1, 2), True, max_chunk=1, trace=lambda event: callback_events.append(event), trace_limit=1)
    if len(callback_events) != 7:
        raise AssertionError(f"stream sink was not invoked per non-None physical batch: {len(callback_events)}")
    source_text = (E_DIR/"bounded_loader.py").read_text(encoding="utf-8")
    if "local_trace" in source_text or "output_index" in source_text:
        raise AssertionError("bounded loader source still contains row-index trace storage")
    results.append({"case":"bounded_debug_and_no_trace","pass":True,"trace_none_parts":len(no_trace_parts),"capped_records":len(capped),"cap":2,"sink_events":len(callback_events),"sink_retention_owned_by_test_callback":len(callback_events)})

    atomic_results = atomic_cases(loader, stage_mod, tables)
    memory_results = metadata_scaling(loader, stage_mod)
    return {"fixture_cases":results,"atomic_cases":atomic_results,"metadata_scaling":memory_results,
            "frame_case_count":len(results),"atomic_case_count":len(atomic_results),
            "all_fixture_assertions_passed":all(x.get("pass") is True for x in results+atomic_results),
            "production_gate":"CONDITIONAL_FAIL if bad empty-template provenance accepted; see limitations"}


def atomic_cases(loader, stage_mod, tables):
    out = []
    good_table = table(rows([
        (700,"1","20250101",70,True,True,7.,8.,139.,41.),
        (701,"2","20250102",71,True,False,7.1,8.1,139.1,41.1),
    ]))
    good_batches = good_table.to_batches(max_chunksize=1)
    hand = make_hand([
        {"rfid_id":1,"part_dt":20250101,"key_valid":True,"month":1},
        {"rfid_id":2,"part_dt":20250102,"key_valid":True,"month":1},
    ], ["rfid_id","part_dt"], "range")
    base, root = atomic_test_root("normal-commit")
    receipt, manifest, rebuilt = reconstruct_stage(stage_mod, root, "final", columns=["rfid_id","part_dt"], batches=good_batches)
    strict_equal(hand, rebuilt, "normal caller committed parts reconstruction")
    if not receipt["published"] or "published" in manifest or "publication_semantics" not in manifest:
        raise AssertionError("public manifest success semantics are incorrect")
    for item in manifest["files"]:
        if item["rows"] != 1 or item["index_type"] != "RangeIndex":
            raise AssertionError(f"manifest part metadata incorrect: {item}")
    out.append({"case":"normal_commit_and_strict_reconstruction","pass":True,"files":len(manifest["files"]),"published_receipt":receipt["published"],"manifest_has_publication_semantics":True,"reconstructed_rows":len(rebuilt)})

    def verify_quarantine(name, expected_type, producer, **kwargs):
        base, root = atomic_test_root(name)
        final = root/"final"
        try:
            stage_mod.run_testfit(columns=["rfid_id","part_dt"], allowed_root=root, final_path=final,
                                  stage="testfit", dataset="testfit", batches=producer(), month=1, **kwargs)
        except expected_type as exc:
            error = type(exc).__name__
        else:
            raise AssertionError(f"{name}: expected {expected_type.__name__}")
        if final.exists():
            raise AssertionError(f"{name}: incomplete final was published")
        receipts = list((root/"quarantine").glob("*/receipt.json"))
        if not receipts:
            raise AssertionError(f"{name}: quarantine receipt missing")
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        if not receipt.get("quarantined") or receipt.get("published") is not False:
            raise AssertionError(f"{name}: quarantine state incorrect: {receipt}")
        out.append({"case":name,"pass":True,"exception":error,"final_absent":True,"quarantine_receipt":str(receipts[0]),"committed_batches_before_failure":receipt.get("batches")})

    def late_unsupported():
        yield from good_table.slice(0,1).to_batches(max_chunksize=1)
        yield from table(rows([(702,"1.5","20250103",72,True,True,7.2,8.2,139.2,41.2)])).to_batches(max_chunksize=1)
    verify_quarantine("late_unsupported_after_one_yield", loader.UnsupportedDomain, late_unsupported)

    def late_error():
        yield from good_table.slice(0,1).to_batches(max_chunksize=1)
        raise RuntimeError("independent injected midstream exception")
    verify_quarantine("late_general_exception_after_one_yield", RuntimeError, late_error)

    def good_again():
        yield from good_batches
    def fail_writer(*_args, **_kwargs):
        raise OSError("independent injected parquet write failure")
    verify_quarantine("scratch_write_failure", OSError, good_again, parquet_writer=fail_writer)

    base, root = atomic_test_root("stage-create-failure")
    def fail_mkdir(_path):
        raise OSError("independent injected stage creation failure")
    final = root/"final"
    try:
        stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=final, stage="testfit",
                              batches=good_batches, month=1, stage_create=fail_mkdir)
    except OSError:
        pass
    else:
        raise AssertionError("stage creation failure not surfaced")
    if final.exists() or not list((root/"quarantine").glob("*/receipt.json")):
        raise AssertionError("stage creation failure did not quarantine/no-final")
    out.append({"case":"stage_creation_failure","pass":True,"final_absent":True,"quarantine_receipt":True})

    base, root = atomic_test_root("commit-failure")
    final = root/"final"
    def fail_commit(_src, _dst):
        raise OSError("independent injected commit failure")
    try:
        stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=final, stage="testfit",
                              batches=good_batches, month=1, commit=fail_commit)
    except OSError:
        pass
    else:
        raise AssertionError("commit failure not surfaced")
    qreceipt = list((root/"quarantine").glob("*/receipt.json"))
    if final.exists() or not qreceipt or json.loads(qreceipt[0].read_text(encoding="utf-8")).get("error_type") != "OSError":
        raise AssertionError("commit failure final/quarantine state incorrect")
    out.append({"case":"commit_failure","pass":True,"final_absent":True,"quarantine_receipt":True})

    base, root = atomic_test_root("commit-race")
    final = root/"final"
    def race_commit(src, dst):
        dst.mkdir()
        (dst/"sentinel.bin").write_bytes(b"preexisting-target")
        stage_mod._atomic_noreplace(src, dst)
    try:
        stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=final, stage="testfit",
                              batches=good_batches, month=1, commit=race_commit)
    except OSError:
        pass
    else:
        raise AssertionError("commit race replaced or accepted existing target")
    sentinel = final/"sentinel.bin"
    sentinel_hash = sha256(sentinel)
    if sentinel.read_bytes() != b"preexisting-target" or final.exists() is False:
        raise AssertionError("commit race sentinel changed")
    if list((root/"quarantine").glob("*/receipt.json")) == []:
        raise AssertionError("commit race quarantine receipt missing")
    out.append({"case":"commit_time_target_creation_race_no_clobber","pass":True,"sentinel_sha256":sentinel_hash,"sentinel_unchanged":True,"final_contains_only_sentinel":[p.name for p in final.iterdir()]})

    base, root = atomic_test_root("existing-final")
    final = root/"final"; final.mkdir(); sentinel=final/"sentinel.txt"; sentinel.write_bytes(b"existing final sentinel")
    before=sha256(sentinel)
    try:
        stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=final, stage="testfit", batches=good_batches, month=1)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing final accepted")
    if sha256(sentinel) != before or sentinel.read_bytes() != b"existing final sentinel":
        raise AssertionError("existing final changed")
    out.append({"case":"preexisting_final_preserved","pass":True,"sentinel_sha256":before})

    # Empty DataFrame schema/index exactness and trust boundary.
    empty_table = table([])
    empty_columns = ["row_index","rfid_id","part_dt","wkt_valid"]
    empty_tables = {1:empty_table,2:empty_table}
    empty_ast, empty_oracle = canonical_and_oracle(empty_tables, empty_columns, (1,2), True)
    strict_equal(empty_ast, empty_oracle, "canonical empty template base")
    empty_parts = adapter_frames(loader, empty_tables, empty_columns, (1,2), True)
    if empty_parts:
        raise AssertionError("empty Arrow tables unexpectedly yielded parts; expected no-batch stream")
    base, root = atomic_test_root("all-empty-canonical-template")
    receipt, manifest, rebuilt = reconstruct_stage(stage_mod, root, "final", columns=empty_columns, months=(1,2),
        batches_for_month=lambda m: empty_tables[m].to_batches(), template=empty_ast)
    strict_equal(empty_ast, rebuilt, "all-empty caller with exact canonical template")
    out.append({"case":"all_empty_with_exact_canonical_template","pass":True,"rows":0,"columns":list(rebuilt.columns),"dtypes":{c:str(t) for c,t in rebuilt.dtypes.items()},"index_type":type(rebuilt.index).__name__})

    base, root = atomic_test_root("all-empty-no-template")
    try:
        stage_mod.run_testfit(columns=empty_columns, allowed_root=root, final_path=root/"final", stage="testfit",
            months=(1,2), batches_for_month=lambda _m: [], empty_template=None)
    except stage_mod.EmptySchemaUnavailable:
        pass
    else:
        raise AssertionError("schema-less all-empty stream published")
    if (root/"final").exists() or not list((root/"quarantine").glob("*/receipt.json")):
        raise AssertionError("schema-less empty stream failure not quarantined")
    out.append({"case":"all_empty_without_template_fail_closed","pass":True,"final_absent":True,"quarantine_receipt":True})

    # A zero-row RecordBatch is different from a stream with no batches.
    zero_batch = pa.RecordBatch.from_arrays([pa.array([], type=field.type) for field in SCHEMA], schema=SCHEMA)
    mixed_table = {1: table(rows([(800,"8","20250108",80,True,True,8.,9.,140.,42.)]))}
    mixed_parts = list(loader.transform_batches([zero_batch, *mixed_table[1].to_batches(max_chunksize=1)], month=1,
                                                 columns=["row_index","rfid_id","part_dt","wkt_valid"]))
    if len(mixed_parts) != 2 or len(mixed_parts[0]) != 0:
        raise AssertionError("zero-row physical batch was conflated with no-batch stream")
    base, root = atomic_test_root("zero-row-physical-batch")
    receipt, manifest, rebuilt = reconstruct_stage(stage_mod, root, "final", columns=["row_index","rfid_id","part_dt","wkt_valid"],
        batches=[zero_batch, *mixed_table[1].to_batches(max_chunksize=1)])
    expected_record={"row_index":800,"rfid_id":8,"part_dt":20250108,"wkt_valid":True,"key_valid":True,"month":1}
    expected=make_hand([expected_record],["row_index","rfid_id","part_dt","wkt_valid"],"range")
    strict_equal(expected, rebuilt, "zero-row batch + data caller reconstruction")
    out.append({"case":"zero_row_batch_distinct_from_no_batch","pass":True,"files":len(manifest["files"]),"first_part_rows":manifest["files"][0]["rows"]})

    # Bad empty templates are accepted by current API unless caller independently
    # establishes provenance. Measure both dtype and index mismatch, do not relabel PASS.
    wrong_dtype = empty_ast.copy()
    if "len_m" not in wrong_dtype.columns:
        wrong_dtype["len_m"] = pd.Series([], dtype="object")
        wanted_cols = [c for c in empty_ast.columns]
        wrong_dtype = wrong_dtype.reindex(columns=wanted_cols + ["len_m"] if "len_m" not in wanted_cols else wanted_cols)
    # Use an existing feature column with a deliberately false dtype while keeping column order.
    wrong_dtype = empty_ast.copy()
    wrong_dtype["wkt_valid"] = wrong_dtype["wkt_valid"].astype("object")
    wrong_index = empty_ast.copy()
    wrong_index.index = pd.Index([], dtype="int64")
    bad_template_observations=[]
    for case, bad_template in [("wrong_feature_dtype_template", wrong_dtype), ("wrong_index_class_template", wrong_index)]:
        base, root = atomic_test_root(case)
        _, manifest, rebuilt = reconstruct_stage(stage_mod, root, "final", columns=empty_columns, months=(1,2),
            batches_for_month=lambda m: empty_tables[m].to_batches(), template=bad_template)
        try:
            strict_equal(empty_ast, rebuilt, case)
            equal=True
        except AssertionError as exc:
            equal=False
            detail=str(exc).splitlines()[0:3]
        bad_template_observations.append({"case":case,"accepted_and_published":True,"strictly_equal_to_canonical":equal,
            "expected_dtypes":{c:str(t) for c,t in empty_ast.dtypes.items()},"actual_dtypes":{c:str(t) for c,t in rebuilt.dtypes.items()},
            "expected_index_type":type(empty_ast.index).__name__,"actual_index_type":type(rebuilt.index).__name__,"mismatch_excerpt":detail if not equal else []})
    out.append({"case":"empty_template_dtype_and_index_provenance_limit","pass":True,"observations":bad_template_observations,
                "gate_effect":"accepted wrong template is a caller precondition/production limitation, not canonical equivalence"})

    # Empty list of None chunks is distinct from a genuine zero-row batch.
    base, root = atomic_test_root("all-none")
    try:
        stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=root/"final", stage="testfit",
            batches=[None,None], month=1, empty_template=None)
    except stage_mod.EmptySchemaUnavailable:
        pass
    else:
        raise AssertionError("all-None stream was published without schema")
    if (root/"final").exists() or not list((root/"quarantine").glob("*/receipt.json")):
        raise AssertionError("all-None stream not quarantined")
    out.append({"case":"all_none_stream_no_template_fail_closed","pass":True,"final_absent":True,"quarantine_receipt":True})

    # Caller preflight denials.
    denial_cases=[]
    for name, stage, dataset, columns, final_path in [
        ("non_testfit_stage","train","testfit",["rfid_id"],None),
        ("non_testfit_dataset","testfit","train",["rfid_id"],None),
        ("duplicate_requested_columns","testfit","testfit",["rfid_id","rfid_id"],None),
        ("reserved_index_column","testfit","testfit",["__canonical_index__"],None),
        ("root_as_final","testfit","testfit",["rfid_id"],"ROOT"),
        ("path_traversal_outside_root","testfit","testfit",["rfid_id"],"OUTSIDE"),
    ]:
        base, root = atomic_test_root("deny-"+name)
        if final_path == "ROOT": target=root
        elif final_path == "OUTSIDE": target=base/"outside"
        else: target=root/"denied"
        try:
            stage_mod.run_testfit(columns=columns, allowed_root=root, final_path=target, stage=stage,
                                  dataset=dataset, batches=good_batches, month=1)
        except (stage_mod.StageDenied, FileExistsError):
            denial_cases.append({"case":name,"denied":True})
        else:
            raise AssertionError(f"unsafe caller input accepted: {name}")
    out.append({"case":"stage_dataset_columns_root_and_path_preflight_denials","pass":True,"denials":denial_cases})

    # Link/junction path tests are rooted entirely inside audit scratch.
    link_results=[]
    def junction(target: Path, link: Path):
        import subprocess
        proc = subprocess.run(["cmd.exe","/c","mklink","/J",str(link),str(target)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise OSError(f"mklink /J exit={proc.returncode}: {proc.stderr}")
    base, root = atomic_test_root("final-link")
    outside = base/"outside"; outside.mkdir()
    link = root/"link_out"
    link_kind = "symlink"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:
        link_kind = "junction_fallback"
        try:
            junction(outside, link)
        except Exception as je:
            link_results.append({"case":"final_link_escape","verified":False,"symlink_error":str(exc),"junction_error":str(je)})
        else:
            try:
                stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=link/"escaped", stage="testfit", batches=good_batches, month=1)
            except stage_mod.StageDenied:
                link_results.append({"case":"final_link_escape","verified":True,"link_kind":link_kind,"symlink_error":str(exc)})
            else:
                raise AssertionError("junction final path escape accepted")
    else:
        try:
            stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=link/"escaped", stage="testfit", batches=good_batches, month=1)
        except stage_mod.StageDenied:
            link_results.append({"case":"final_link_escape","verified":True,"link_kind":link_kind})
        else:
            raise AssertionError("symlink final path escape accepted")

    base, root = atomic_test_root("quarantine-link")
    outside = base/"outside"; outside.mkdir()
    qlink = root/"quarantine"
    q_kind="symlink"
    try:
        os.symlink(outside, qlink, target_is_directory=True)
    except OSError as exc:
        q_kind="junction_fallback"
        try:
            junction(outside, qlink)
        except Exception as je:
            link_results.append({"case":"quarantine_root_link","verified":False,"symlink_error":str(exc),"junction_error":str(je)})
        else:
            try:
                stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=root/"final", stage="testfit", batches=good_batches, month=1)
            except stage_mod.StageDenied:
                link_results.append({"case":"quarantine_root_link","verified":True,"link_kind":q_kind,"outside_writes":list(outside.iterdir())})
            else:
                raise AssertionError("quarantine junction accepted")
    else:
        try:
            stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=root/"final", stage="testfit", batches=good_batches, month=1)
        except stage_mod.StageDenied:
            link_results.append({"case":"quarantine_root_link","verified":True,"link_kind":q_kind,"outside_writes":list(outside.iterdir())})
        else:
            raise AssertionError("quarantine symlink accepted")
    if any(not r.get("verified") for r in link_results):
        # Missing link permissions are recorded as an unavailable dynamic check,
        # not falsely presented as a verified pass.
        out.append({"case":"link_and_junction_checks","pass":True,"checks":link_results,"scope_note":"unavailable direct link check is explicitly not verified"})
    else:
        out.append({"case":"link_and_junction_checks","pass":True,"checks":link_results,"scope_note":"junction fallback is distinct from symbolic link coverage"})

    return out


def metadata_scaling(loader, stage_mod):
    records=[]
    source = table(rows([(900,"9","20250109",90,True,True,9.,10.,141.,43.)]))
    for count in (1, 8, 32):
        base, root = atomic_test_root(f"metadata-{count}")
        def repeated():
            for _ in range(count):
                yield from source.to_batches(max_chunksize=1)
        receipt = stage_mod.run_testfit(columns=["rfid_id"], allowed_root=root, final_path=root/"final",
                                        stage="testfit", batches=repeated(), month=1)
        manifest = json.loads((root/"final"/"manifest.json").read_text(encoding="utf-8"))
        if len(receipt["files"]) != count or len(manifest["files"]) != count:
            raise AssertionError("manifest per-part metadata count differs from input batches")
        records.append({"batches":count,"receipt_files":len(receipt["files"]),"manifest_files":len(manifest["files"]),
                        "receipt_recursive_bytes":_deep_size(receipt),"manifest_file_entries_recursive_bytes":_deep_size(manifest["files"])})
    slopes=[]
    for left,right in zip(records,records[1:]):
        slopes.append((right["batches"],right["receipt_recursive_bytes"]-left["receipt_recursive_bytes"],
                       right["manifest_file_entries_recursive_bytes"]-left["manifest_file_entries_recursive_bytes"]))
    if any(r["receipt_files"] != r["batches"] for r in records):
        raise AssertionError("stage receipt did not report every part")
    return {"pass":True,"records":records,"incremental_bytes":slopes,
            "interpretation":"trace retention is bounded separately; caller receipt/files metadata is O(batch_count), has no configured cap, and remains a scale limitation"}


def sample_run(loader, stage_mod):
    if sha256(SAMPLE) != SAMPLE_SHA:
        raise RuntimeError("fixed sample source SHA mismatch")
    parquet_file = pq.ParquetFile(SAMPLE)
    schema_names = parquet_file.schema_arrow.names
    missing = [c for c in SAMPLE_COLUMNS if c not in schema_names]
    if missing:
        raise RuntimeError(f"fixed sample projection columns missing: {missing}")
    batches=[]
    physical_count=0
    for batch in parquet_file.iter_batches(batch_size=4096, columns=SAMPLE_COLUMNS):
        if physical_count >= 16384:
            break
        remaining=16384-physical_count
        if batch.num_rows > remaining:
            batch=batch.slice(0,remaining)
        batches.append(batch)
        physical_count += batch.num_rows
    if physical_count != 16384 or len(batches) != 4 or any(b.num_rows != 4096 for b in batches):
        raise RuntimeError(f"fixed physical sample selection mismatch: rows={physical_count}, batches={[b.num_rows for b in batches]}")
    # Verify the projected sample itself is in the declared limited domain.
    first_idx = batches[0].column(batches[0].schema.get_field_index("row_index")).to_pylist()
    last_idx = batches[-1].column(batches[-1].schema.get_field_index("row_index")).to_pylist()
    if first_idx[0] != 0 or last_idx[-1] != 16383:
        raise RuntimeError(f"row_index endpoints do not match physical selection: {first_idx[0]}, {last_idx[-1]}")

    # Hold only four Arrow record batches; independently construct the whole-column
    # canonical/oracle result from their 16,384-row projected union.
    sample_table = pa.Table.from_batches(batches)
    original, ns = canonical_loader()
    ns["pq"].read_table = lambda _path, columns: sample_table.select(columns)
    columns = SAMPLE_COLUMNS.copy()
    ast_frame = original("train", columns, months=(1,), key_valid_only=True)
    oracle_frame = oracle({1:sample_table}, columns, (1,), True)
    strict_equal(ast_frame, oracle_frame, "fixed sample canonical AST vs whole-column oracle")

    # The actual E caller consumes the four original physical batches one by one,
    # writes a private staged directory, commits, then reconstructs from saved parts.
    base, root = atomic_test_root("actual-month1-first-16384")
    receipt, manifest, rebuilt = reconstruct_stage(stage_mod, root, "committed", columns=columns,
        batches=iter(batches), tables=None, key_only=True)
    strict_equal(ast_frame, rebuilt, "fixed sample actual caller reconstruction vs canonical AST")
    output_oracle = oracle_frame
    strict_equal(output_oracle, rebuilt, "fixed sample actual caller reconstruction vs independent oracle")
    if receipt["batches"] != 4 or [x["rows"] for x in manifest["files"]] != [4096]*4:
        raise AssertionError("sample was not processed in four independent 4096-row parts")
    if [x["concat_offset_start"] for x in manifest["files"]] != [0,4096,8192,12288]:
        raise AssertionError("sample batch global concat offsets differ")
    rss = process_metrics()
    return {"source_path":str(SAMPLE),"source_sha256":sha256(SAMPLE),"selected_rows":physical_count,
            "selection":"month 1, physical rows 0..16383, 10 columns, 4 batches of 4096",
            "columns":SAMPLE_COLUMNS,"row_index_endpoints":[int(first_idx[0]),int(last_idx[-1])],
            "canonical_rows_after_key_valid_and_numeric_transforms":len(ast_frame),
            "key_valid_admitted_rows":sum(int(x["admitted_rows"]) for x in manifest["files"]),
            "output_rows":len(rebuilt),"strict_ast_oracle_caller_equal":True,
            "parts":[{"rows":x["rows"],"admitted_rows":x["admitted_rows"],"offset_start":x["concat_offset_start"],"offset_end":x["concat_offset_end"],"index_type":x["index_type"],"index_dtype":x["index_dtype"]} for x in manifest["files"]],
            "output_sha256":[x["sha256"] for x in manifest["files"]],"manifest_sha256":sha256(root/"committed"/"manifest.json"),
            "process_metrics_after_sample":rss,"limitations":"one fixed 16,384-row sample only; not full-domain or production approval"}


def process_metrics():
    if platform.system() == "Windows":
        from ctypes import wintypes
        class PMC(ctypes.Structure):
            _fields_=[("cb",ctypes.c_ulong),("PageFaultCount",ctypes.c_ulong),("PeakWorkingSetSize",ctypes.c_size_t),
                      ("WorkingSetSize",ctypes.c_size_t),("QuotaPeakPagedPoolUsage",ctypes.c_size_t),
                      ("QuotaPagedPoolUsage",ctypes.c_size_t),("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),
                      ("QuotaNonPagedPoolUsage",ctypes.c_size_t),("PagefileUsage",ctypes.c_size_t),
                      ("PeakPagefileUsage",ctypes.c_size_t)]
        pmc=PMC(); pmc.cb=ctypes.sizeof(PMC)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        handle = kernel32.GetCurrentProcess()
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(pmc),pmc.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return {"working_set_rss_mib":round(pmc.WorkingSetSize/(1024*1024),2),
                "peak_working_set_rss_mib":round(pmc.PeakWorkingSetSize/(1024*1024),2),
                "commit_pagefile_mib":round(pmc.PagefileUsage/(1024*1024),2),
                "peak_commit_pagefile_mib":round(pmc.PeakPagefileUsage/(1024*1024),2)}
    return {"unavailable":"Windows process metrics only"}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--fixtures"
    if mode not in ("--fixtures", "--sample"):
        raise ValueError("mode must be --fixtures or --sample")
    started=time.time()
    hashes_before=check_snapshot("before_"+mode[2:])
    loader, stage_mod = get_e_modules()
    if mode == "--fixtures":
        payload={"mode":"independent small fixtures and caller transaction checks","started_unix":started,
                 "python":sys.version,"pandas":pd.__version__,"numpy":np.__version__,"pyarrow":pa.__version__,
                 "snapshot_before":hashes_before,"process_metrics_before":process_metrics()}
        payload.update(fixture_run(loader,stage_mod))
    else:
        payload={"mode":"fixed actual month1 physical sample","started_unix":started,
                 "python":sys.version,"pandas":pd.__version__,"numpy":np.__version__,"pyarrow":pa.__version__,
                 "snapshot_before":hashes_before,"process_metrics_before":process_metrics()}
        payload["sample"] = sample_run(loader,stage_mod)
        payload["all_sample_checks_passed"] = payload["sample"]["strict_ast_oracle_caller_equal"]
    payload["finished_unix"]=time.time()
    payload["process_metrics_after"]=process_metrics()
    payload["snapshot_after"]=check_snapshot("after_"+mode[2:])
    if not payload["snapshot_after"]["all_match"]:
        raise RuntimeError("source/E snapshot changed during verification")
    result_path=HERE/("fixture_result.json" if mode=="--fixtures" else "actual_sample_result.json")
    result_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    summary={"mode":mode,"fixture_cases":payload.get("frame_case_count"),"atomic_cases":payload.get("atomic_case_count"),
             "all_fixture_assertions_passed":payload.get("all_fixture_assertions_passed"),
             "all_sample_checks_passed":payload.get("all_sample_checks_passed"),
             "sample_output_rows":payload.get("sample",{}).get("output_rows"),
             "snapshot_hashes_match":payload["snapshot_after"]["all_match"],"production_gate":"FAIL/CONDITIONAL"}
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
