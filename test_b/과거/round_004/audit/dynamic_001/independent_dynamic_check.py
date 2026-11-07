from __future__ import annotations
import ast, ctypes, gc, hashlib, importlib.util, json, math, os, sys, types
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

DYNAMIC = Path(__file__).resolve().parent
EXEC = DYNAMIC.parents[1] / "execution"
ROOT = DYNAMIC.parents[3]
SOURCE = Path(r"D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py")
PARQUET = Path(r"D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/outputs/remeasure_20261031/rows_train_1.parquet")
PARQUET_EXPECTED_SHA = "7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140"
SOURCE_PINS = {
    "run_remeasure_20261031.py": (Path(r"D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py"), "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c"),
    "run_008_testB_20261101.py": (Path(r"D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py"), "cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8"),
    "run_005_F156_merge_20261101.py": (Path(r"D:/repos/fishing-track-classification/code/tools/run_005_F156_merge_20261101.py"), "e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4"),
    "run_cycle4_3_featAC_20261101.py": (Path(r"D:/repos/fishing-track-classification/code/tools/run_cycle4_3_featAC_20261101.py"), "8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3"),
}
SOURCE_SHA = SOURCE_PINS["run_remeasure_20261031.py"][1]
sys.path.insert(0, str(EXEC))
SAMPLE_N, BATCH_MAX = 16384, 4096
SAMPLE_COLS = ["row_index", "rfid_id", "part_dt", "rfid_time", "key_valid", "wkt_valid", "len_m", "bbox_m", "cen_lon", "cen_lat"]
SCHEMA = pa.schema([
    ("row_index", pa.int64()), ("rfid_id", pa.string()), ("part_dt", pa.string()),
    ("rfid_time", pa.int16()), ("key_valid", pa.bool_()), ("wkt_valid", pa.bool_()),
    ("len_m", pa.float64()), ("bbox_m", pa.float64()), ("cen_lon", pa.float64()), ("cen_lat", pa.float64()),
])


def process_memory_snapshot():
    """Windows GetProcessMemoryInfo: working set is RSS, PagefileUsage is commit."""
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    info = Counters()
    info.cb = ctypes.sizeof(info)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.windll.psapi
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(info), info.cb):
        return {"error": "GetProcessMemoryInfo failed"}
    scale = 1024 * 1024
    return {"current_rss_mib": round(info.WorkingSetSize / scale, 2),
            "peak_rss_mib": round(info.PeakWorkingSetSize / scale, 2),
            "current_commit_mib": round(info.PagefileUsage / scale, 2),
            "peak_commit_mib": round(info.PeakPagefileUsage / scale, 2)}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_sha_snapshots() -> dict:
    return {name: {"path": str(path), "sha256": sha256(path), "pinned_sha256": pin}
            for name, (path, pin) in SOURCE_PINS.items()}


def load_canonical_ast(tables: dict[int, pa.Table]):
    source_bytes = SOURCE.read_bytes()
    actual = hashlib.sha256(source_bytes).hexdigest()
    if actual != SOURCE_SHA:
        raise RuntimeError(f"canonical source SHA mismatch: {actual}")
    tree = ast.parse(source_bytes, filename=str(SOURCE))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "load_rows")

    def fake_read(path, columns):
        month = int(str(path).rsplit(":", 1)[1])
        return tables[month].select(columns)

    ns = {
        "pd": pd, "np": np, "gc": gc, "log": lambda *_args, **_kwargs: None,
        "MONTHS": (1,), "pq": types.SimpleNamespace(read_table=fake_read),
        "parquet_path": lambda dataset, month: Path(f"injected:{dataset}:{month}"),
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns["load_rows"]


def independent_whole_column_oracle(tables: dict[int, pa.Table], columns: list[str], months, key_valid_only: bool):
    """Fresh contract implementation; shares no E helper/parser/comparator."""
    requested = [column for column in columns if column != "month"]
    output = requested if "key_valid" in requested else requested + ["key_valid"]
    frames = []
    for month in months:
        frame = tables[month].select(output).to_pandas()
        if key_valid_only:
            frame = frame.loc[frame["key_valid"]]
        frame["month"] = np.int8(month)
        frames.append(frame[output + ["month"]])
    result = pd.concat(frames, ignore_index=True, copy=False)
    for column, dtype in (("rfid_id", np.int64), ("part_dt", np.int32)):
        if column in result.columns:
            converted = pd.to_numeric(result[column], errors="coerce")
            admitted = converted.notna()
            # Keep the concatenated RangeIndex when no rows are dropped, as
            # the pinned source does; otherwise preserve the resulting holes.
            if not bool(admitted.all()):
                result = result.loc[admitted]
                converted = converted.loc[admitted]
            result[column] = converted.astype(dtype)
    return result


def frame_equal(a, b):
    try:
        pd.testing.assert_frame_equal(a, b, check_dtype=True, check_index_type=True, check_column_type=True)
        return {"equal": True}
    except AssertionError as exc:
        return {"equal": False, "difference": str(exc).splitlines()[:12]}


def frame_values_and_index_labels_equal(a, b):
    """Check values, dtypes, columns, NaN placement and index labels, not index container class."""
    try:
        pd.testing.assert_frame_equal(a, b, check_dtype=True, check_index_type=False, check_column_type=True)
        if not a.index.equals(b.index) or a.index.dtype != b.index.dtype or a.index.names != b.index.names:
            return {"equal": False, "difference": ["index labels, dtype, or names differ"]}
        return {"equal": True}
    except AssertionError as exc:
        return {"equal": False, "difference": str(exc).splitlines()[:12]}


def pyrow(row_index, rid, date, key=True, wkt=True):
    return {"row_index": row_index, "rfid_id": rid, "part_dt": date,
            "rfid_time": row_index % 24, "key_valid": key, "wkt_valid": wkt,
            "len_m": float(row_index), "bbox_m": float(row_index),
            "cen_lon": 120.0 + row_index / 100000.0, "cen_lat": 30.0 + row_index / 100000.0}


def table(rows, schema=SCHEMA):
    return pa.Table.from_pylist(rows, schema=schema)


def empty_batch(schema=SCHEMA):
    return pa.RecordBatch.from_arrays([pa.array([], type=f.type) for f in schema], schema=schema)


def divided_batches(source: pa.Table, max_rows=2, inject_empty=True):
    batches = list(source.to_batches(max_chunksize=max_rows))
    if inject_empty:
        batches.insert(min(1, len(batches)), empty_batch(source.schema))
    return batches


def main_fixture_tables():
    m1 = [
        pyrow(0, "001", "20250101", True, True),
        pyrow(1, "99", "20250102", False, False),
        pyrow(2, None, "20250103", True, True),
        pyrow(3, "3", "bad", True, True),
        pyrow(4, "-0004", "2147483647", True, False),
        pyrow(5, "9007199254740992", "-2147483648", True, True),
    ]
    m2 = [
        pyrow(0, "-9007199254740992", "20250201", True, False),
        pyrow(1, "abc", "1.5", True, True),  # ID drop means this unsupported date must not be examined.
        pyrow(2, "7", "20250202", False, False),
    ]
    return {1: table(m1), 2: table(m2)}


def hand_expected(key_only: bool):
    if key_only:
        idx = [0, 3, 4, 5]
        vals = [1, -4, 2**53, -(2**53)]
        dates = [20250101, 2147483647, -(2**31), 20250201]
        wkt = [True, False, True, False]
        keys = [True] * 4
        months = [1, 1, 1, 2]
    else:
        idx = [0, 1, 4, 5, 6, 8]
        vals = [1, 99, -4, 2**53, -(2**53), 7]
        dates = [20250101, 20250102, 2147483647, -(2**31), 20250201, 20250202]
        wkt = [True, False, False, True, False, False]
        keys = [True, False, True, True, True, False]
        months = [1, 1, 1, 1, 2, 2]
    return pd.DataFrame({
        "rfid_id": np.asarray(vals, dtype=np.int64),
        "part_dt": np.asarray(dates, dtype=np.int32),
        "wkt_valid": np.asarray(wkt, dtype=bool),
        "key_valid": np.asarray(keys, dtype=bool),
        "month": np.asarray(months, dtype=np.int8),
    }, index=pd.Index(idx, dtype="int64"))


def adapter_batch_months(tables, months, columns, key_only):
    from bounded_loader import transform_batches, transform_months
    batches = {month: divided_batches(tables[month]) for month in months}
    chunks = list(transform_months(months, lambda month: batches[month], columns=columns, key_valid_only=key_only))
    return (pd.concat(chunks) if chunks else None), batches


def fixture_core(loader, tables):
    from bounded_loader import transform_batches
    rows = {}
    expected_cols = ["rfid_id", "part_dt", "wkt_valid"]
    for key_only in (True, False):
        original = loader("train", expected_cols, months=(1, 2), key_valid_only=key_only)
        oracle = independent_whole_column_oracle(tables, expected_cols, (1, 2), key_only)
        first = frame_equal(original, oracle)
        hand = frame_equal(oracle, hand_expected(key_only))
        actual, batches = adapter_batch_months(tables, (1, 2), expected_cols, key_only)
        third = frame_equal(original, actual) if actual is not None else {"equal": False, "difference": ["adapter returned no frame"]}
        rows[str(key_only)] = {
            "canonical_ast_equals_independent_oracle": first,
            "oracle_equals_hand_expected": hand,
            "adapter_as_third_implementation_equals_ast": third,
            "canonical_index": original.index.tolist(),
            "hand_index": hand_expected(key_only).index.tolist(),
            "output_columns": list(original.columns),
            "dtypes": {name: str(dtype) for name, dtype in original.dtypes.items()},
            "adapter_batch_sizes_including_empty": {str(m): [b.num_rows for b in batches[m]] for m in batches},
            "excluded_index_holes_preserved": original.index.tolist() == hand_expected(key_only).index.tolist(),
        }
    return rows


def api_cases(loader, tables):
    cases = {}
    # ID-only: date tokens are numeric-like but omitted and must not be inspected.
    id_table = table([pyrow(0, "001", "1.5"), pyrow(1, "bad", "1e3"), pyrow(2, "+2", " 42 "), pyrow(3, "NaN", "junk")])
    # Date-only: ID tokens are numeric-like but omitted and must not be inspected.
    date_table = table([pyrow(0, "1.5", "20250101"), pyrow(1, "1e3", "bad"), pyrow(2, " 42 ", "20250102"), pyrow(3, "NaN", "NaN")])
    one = {1: id_table}
    local_loader = load_canonical_ast(one)
    expected = local_loader("train", ["rfid_id"], months=(1,), key_valid_only=True)
    oracle = independent_whole_column_oracle(one, ["rfid_id"], (1,), True)
    actual, _ = adapter_batch_months(one, (1,), ["rfid_id"], True)
    cases["id_only_ignores_unsupported_dates"] = {"ast_oracle": frame_equal(expected, oracle), "adapter": frame_equal(expected, actual), "columns": list(actual.columns), "index": actual.index.tolist()}
    one = {1: date_table}
    local_loader = load_canonical_ast(one)
    expected = local_loader("train", ["part_dt"], months=(1,), key_valid_only=True)
    oracle = independent_whole_column_oracle(one, ["part_dt"], (1,), True)
    actual, _ = adapter_batch_months(one, (1,), ["part_dt"], True)
    cases["date_only_ignores_unsupported_ids"] = {"ast_oracle": frame_equal(expected, oracle), "adapter": frame_equal(expected, actual), "columns": list(actual.columns), "index": actual.index.tolist()}
    for cols, name in ((["wkt_valid"], "both_numeric_keys_omitted"),
                       (["month", "wkt_valid", "part_dt", "key_valid", "rfid_id"], "explicit_month_keyvalid_order"),
                       (["wkt_valid", "rfid_id", "key_valid", "part_dt", "month"], "caller_order_permutation"),
                       (["key_valid", "month"], "keyvalid_month_only")):
        local_loader = load_canonical_ast(tables)
        expected = local_loader("train", cols, months=(1, 2), key_valid_only=True)
        oracle = independent_whole_column_oracle(tables, cols, (1, 2), True)
        actual, _ = adapter_batch_months(tables, (1, 2), cols, True)
        cases[name] = {"ast_oracle": frame_equal(expected, oracle), "adapter": frame_equal(expected, actual),
                       "columns_expected": list(expected.columns), "columns_adapter": list(actual.columns),
                       "index_equal": expected.index.tolist() == actual.index.tolist()}
    return cases


def empty_cases(loader):
    from bounded_loader import transform_months
    empty = table([])
    empty_tables = {1: empty, 2: empty}
    cols = ["rfid_id", "part_dt", "wkt_valid"]
    empty_loader = load_canonical_ast(empty_tables)
    one_original = empty_loader("train", cols, months=(1,), key_valid_only=True)
    one_oracle = independent_whole_column_oracle(empty_tables, cols, (1,), True)
    chunks_one, _ = adapter_batch_months(empty_tables, (1,), cols, True)
    two_original = empty_loader("train", cols, months=(1, 2), key_valid_only=True)
    two_oracle = independent_whole_column_oracle(empty_tables, cols, (1, 2), True)
    chunks_two, _ = adapter_batch_months(empty_tables, (1, 2), cols, True)
    empty_months = {}
    try:
        empty_loader("train", ["rfid_id"], months=(), key_valid_only=True)
        empty_months["canonical_error"] = None
    except Exception as exc:
        empty_months["canonical_error"] = {"type": type(exc).__name__, "message": str(exc)}
    try:
        list(transform_months((), lambda _m: (), columns=["rfid_id"]))
        empty_months["adapter_error"] = None
    except Exception as exc:
        empty_months["adapter_error"] = {"type": type(exc).__name__, "message": str(exc)}
    return {
        "empty_batch_in_nonempty_month": "covered in core fixture; output equal",
        "one_empty_month": {"canonical_rows": len(one_original), "oracle": frame_equal(one_original, one_oracle),
                             "adapter_yielded_chunks": 0 if chunks_one is None else len(chunks_one),
                             "adapter_can_materialize_empty_schema_frame": chunks_one is not None,
                             "classification": "UNKNOWN: stream has no zero-row frame/schema; caller contract needed"},
        "all_empty_months": {"canonical_rows": len(two_original), "oracle": frame_equal(two_original, two_oracle),
                             "adapter_yielded_chunks": 0 if chunks_two is None else len(chunks_two),
                             "adapter_can_materialize_empty_schema_frame": chunks_two is not None,
                             "classification": "UNKNOWN: stream has no zero-row frame/schema; caller contract needed"},
        "months_empty_list": {**empty_months, "same_type_and_message": empty_months.get("canonical_error") == empty_months.get("adapter_error")},
    }


def null_nan_cases(loader):
    from bounded_loader import transform_batches, transform_months
    id_nan_schema = SCHEMA.set(1, pa.field("rfid_id", pa.float64()))
    id_nan = table([pyrow(0, float("nan"), "20250101"), pyrow(1, None, "20250102")], id_nan_schema)
    dt_nan_schema = SCHEMA.set(2, pa.field("part_dt", pa.float64()))
    dt_nan = table([pyrow(0, "1", float("nan")), pyrow(1, "2", None)], dt_nan_schema)
    results = {}
    for name, t, cols in (("IEEE_NaN_and_null_ID", id_nan, ["rfid_id", "part_dt"]),
                          ("IEEE_NaN_and_null_date", dt_nan, ["rfid_id", "part_dt"])):
        tables = {1: t}
        local_loader = load_canonical_ast(tables)
        original = local_loader("train", cols, months=(1,), key_valid_only=True)
        oracle = independent_whole_column_oracle(tables, cols, (1,), True)
        chunks = list(transform_months((1,), lambda _m: t.to_batches(max_chunksize=1), columns=cols, key_valid_only=True))
        actual = pd.concat(chunks) if chunks else None
        results[name] = {"ast_oracle": frame_equal(original, oracle), "adapter": frame_equal(original, actual) if actual is not None else {"equal": False},
                         "canonical_rows": len(original), "adapter_rows": None if actual is None else len(actual)}
    return results


def unsupported_cases(loader):
    from bounded_loader import transform_batches, UnsupportedDomain
    cases = []
    specs = [
        ("9007199254740993", "rfid_id"), ("-9007199254740993", "rfid_id"),
        ("1.0", "rfid_id"), ("1.5", "rfid_id"), ("1e3", "rfid_id"),
        (" 12", "rfid_id"), ("12 ", "rfid_id"), ("١", "rfid_id"),
        ("１２", "rfid_id"), ("9" * 129, "rfid_id"),
        ("20250101.5", "part_dt"), ("2.025e7", "part_dt"),
        (" 20250101", "part_dt"), ("20250101 ", "part_dt"),
        ("２０２５０１０１", "part_dt"), ("9" * 129, "part_dt"),
        ("2147483648", "part_dt"), ("-2147483649", "part_dt"),
        ("9223372036854775808", "rfid_id"),
    ]
    for token, field in specs:
        row = pyrow(0, token if field == "rfid_id" else "1", token if field == "part_dt" else "20250101")
        t = table([row]); tables = {1: t}; cols = [field]
        ast_value = None
        try:
            local_loader = load_canonical_ast(tables)
            ast_df = local_loader("train", cols, months=(1,), key_valid_only=True)
            ast_value = {"rows": len(ast_df), "values": [repr(x) for x in ast_df[field].tolist()], "dtype": str(ast_df[field].dtype)}
            oracle_df = independent_whole_column_oracle(tables, cols, (1,), True)
            oracle_agreement = frame_equal(ast_df, oracle_df)
        except Exception as exc:
            ast_value = {"error": type(exc).__name__ + ": " + str(exc)}
            oracle_agreement = None
        stopped, error, yields = False, None, 0
        try:
            for _frame in transform_batches(t.to_batches(max_chunksize=1), month=1, columns=cols, key_valid_only=True):
                yields += 1
        except UnsupportedDomain as exc:
            stopped, error = True, str(exc)
        cases.append({"token": token, "field": field, "canonical": ast_value,
                      "oracle_agreement": oracle_agreement, "adapter_stopped_whole_call": stopped,
                      "adapter_yields_before_stop": yields, "adapter_error": error})
    bool_schema = SCHEMA.set(1, pa.field("rfid_id", pa.bool_()))
    bool_table = table([pyrow(0, True, "20250101")], bool_schema)
    try:
        list(transform_batches(bool_table.to_batches(), month=1, columns=["rfid_id"]))
        bool_stop = False
    except UnsupportedDomain:
        bool_stop = True
    cases.append({"token": "True", "field": "rfid_id", "adapter_stopped_whole_call": bool_stop,
                  "note": "source-compatible type outside string/integer domain; fail closed, not silently dropped"})
    excluded_bad = table([pyrow(0, "1.5", "2.025e7", False, False)])
    excluded_tables = {1: excluded_bad}
    local_loader = load_canonical_ast(excluded_tables)
    canonical = local_loader("train", ["rfid_id", "part_dt"], months=(1,), key_valid_only=True)
    error, chunks = None, []
    try:
        chunks = list(transform_batches(excluded_bad.to_batches(max_chunksize=1), month=1,
                                        columns=["rfid_id", "part_dt"], key_valid_only=True))
    except UnsupportedDomain as exc:
        error = str(exc)
    adapter = pd.concat(chunks) if chunks else None
    cases.append({"field": "rfid_id+part_dt", "token": "1.5+2.025e7 with key_valid=False",
                  "canonical_rows": len(canonical), "adapter_stopped_whole_call": error is not None,
                  "adapter_yielded_rows": 0 if adapter is None else len(adapter),
                  "adapter_error": error,
                  "classification": "excluded by key_valid before numeric validation"})
    return cases


def late_unsupported_and_streaming_trace():
    from bounded_loader import transform_batches, transform_months, UnsupportedDomain
    first = table([pyrow(0, "1", "20250101")]).to_batches()[0]
    late = table([pyrow(1, "1.5", "20250102")]).to_batches()[0]
    received = []
    iterator = transform_batches([first, late], month=1, columns=["rfid_id", "part_dt"])
    error = None
    try:
        while True:
            received.append(next(iterator))
    except StopIteration:
        pass
    except UnsupportedDomain as exc:
        error = str(exc)
    partial = {"yielded_frames_before_error": len(received), "yielded_rows_before_error": sum(len(f) for f in received),
               "later_error": error, "atomic_or_quarantine_in_adapter": False,
               "classification": "FAIL for standalone whole-stage fail-closed claim; caller needs temp/quarantine then commit"}

    rows = [pyrow(i, str(i + 1), "20250101") for i in range(3)]
    source = table(rows)
    batches = list(source.to_batches(max_chunksize=1))
    gen = transform_months((1,), lambda _m: batches, columns=["rfid_id"], trace=None)
    observations = []
    for expected_yield in range(1, 4):
        try:
            next(gen)
        except StopIteration:
            break
        loc = gen.gi_frame.f_locals
        local = loc.get("local_trace", [])
        observations.append({"frames_yielded": expected_yield, "local_trace_records_retained": len(local),
                            "retained_output_index_entries": sum(len(x.get("output_index", [])) for x in local),
                            "trace_argument_is_none": loc.get("trace") is None})
    trace = {"observations": observations, "classification": "FAIL bounded-memory/streaming claim; trace=None still accumulates all batch index lists until month finishes"}
    gen.close()
    return {"late_unsupported": partial, "trace_none_growth": trace}


def parquet_footer_metadata():
    files = sorted(PARQUET.parent.glob("rows_train_*.parquet"))
    if len(files) != 6:
        raise RuntimeError(f"expected 6 train parquet footers, found {len(files)}")
    rows = []
    for path in files:
        pf = pq.ParquetFile(path)
        rows.append({"name": path.name, "bytes": path.stat().st_size,
                     "footer_rows": int(pf.metadata.num_rows), "row_groups": int(pf.metadata.num_row_groups),
                     "schema": [{"name": field.name, "type": str(field.type)} for field in pf.schema_arrow]})
    return {"read_mode": "ParquetFile metadata/footer only; no rows read", "files": rows,
            "train_footer_total_rows": sum(x["footer_rows"] for x in rows),
            "pinned_train_expected_rows": 3887069,
            "pinned_history_test_total_rows": 4212389,
            "train_total_matches_pinned": sum(x["footer_rows"] for x in rows) == 3887069}


def actual_sample(loader):
    if not PARQUET.is_file():
        raise FileNotFoundError(str(PARQUET))
    selection_plan = json.loads((DYNAMIC / "selection_plan.json").read_text(encoding="utf-8-sig"))
    if selection_plan.get("sample_data_read") is not False or selection_plan.get("expected_rows") != SAMPLE_N:
        raise RuntimeError("selection plan missing or altered before read")
    actual_hash = sha256(PARQUET)
    if actual_hash != PARQUET_EXPECTED_SHA:
        raise RuntimeError(f"sample source SHA mismatch: {actual_hash}")
    pf = pq.ParquetFile(PARQUET)
    footer_rows = int(pf.metadata.num_rows)
    raw_batches, selected = [], 0
    physical_reads = 0
    for rb in pf.iter_batches(batch_size=BATCH_MAX, columns=SAMPLE_COLS):
        take = min(rb.num_rows, SAMPLE_N - selected)
        if take:
            raw_batches.append(rb.slice(0, take))
            selected += take
        physical_reads += 1
        if selected == SAMPLE_N:
            break
    if selected != SAMPLE_N:
        raise RuntimeError(f"selected {selected} rows, expected {SAMPLE_N}")
    combined = pa.Table.from_batches(raw_batches)
    source_row_index = combined.column("row_index").to_pylist()
    hand_selection = (len(source_row_index) == SAMPLE_N and source_row_index == list(range(SAMPLE_N)))
    tables = {1: combined}
    cols = ["rfid_id", "part_dt", "rfid_time", "wkt_valid", "len_m", "bbox_m", "cen_lon", "cen_lat"]
    local_loader = load_canonical_ast(tables)
    original = local_loader("train", cols, months=(1,), key_valid_only=True)
    oracle = independent_whole_column_oracle(tables, cols, (1,), True)
    base_checks = {"canonical_AST_equals_independent_oracle": frame_equal(original, oracle),
                   "canonical_AST_equals_independent_oracle_values_and_index_labels": frame_values_and_index_labels_equal(original, oracle),
                   "hand_selection_is_first_16384_source_rows": hand_selection,
                   "selected_rows": selected, "columns": list(original.columns),
                   "dtypes": {k: str(v) for k, v in original.dtypes.items()},
                   "canonical_index_first_last": [int(original.index[0]), int(original.index[-1])] if len(original) else None}

    from bounded_loader import transform_batches
    adapter_parts, batch_trace = [], []
    concat_offset, physical_offset = 0, 0
    original_indices = set(int(x) for x in original.index.tolist())
    for call_number, rb in enumerate(raw_batches):
        rows_in = rb.num_rows
        valid = [bool(x) for x in rb.column("key_valid").to_pylist()]
        admitted = sum(valid)
        source_ri = [int(x) for x in rb.column("row_index").to_pylist()]
        trace = []
        call_chunks = list(transform_batches([rb], month=1, columns=cols, key_valid_only=True,
                                             first_concat_ordinal=concat_offset, trace=trace))
        adapter_parts.extend(call_chunks)
        frame = pd.concat(call_chunks) if call_chunks else None
        local_global_indices = list(range(concat_offset, concat_offset + admitted))
        excluded = [idx for idx in local_global_indices if idx not in original_indices]
        batch_trace.append({
            "adapter_call_number": call_number, "adapter_invocation_count": 1,
            "physical_input_offset_start": physical_offset, "physical_input_offset_end_exclusive": physical_offset + rows_in,
            "input_rows": rows_in, "source_row_index_first_last": [source_ri[0], source_ri[-1]] if source_ri else [],
            "key_valid_admitted_rows": admitted, "global_concat_ordinal_start": concat_offset,
            "global_concat_ordinal_end_exclusive": concat_offset + admitted,
            "output_rows": 0 if frame is None else len(frame),
            "output_index": [] if frame is None else [int(x) for x in frame.index.tolist()],
            "excluded_concat_indices": excluded,
            "excluded_source_row_index": [source_ri[i] for i, key_ok in enumerate(valid) if not key_ok],
        })
        concat_offset += admitted
        physical_offset += rows_in
    actual = pd.concat(adapter_parts) if adapter_parts else None
    comparison = frame_equal(original, actual) if actual is not None else {"equal": False, "difference": ["adapter yielded no frames"]}
    semantic_comparison = frame_values_and_index_labels_equal(original, actual) if actual is not None else {"equal": False, "difference": ["adapter yielded no frames"]}
    return {"source_path": str(PARQUET), "source_bytes": PARQUET.stat().st_size,
            "source_sha256_checked_before_row_selection": actual_hash, "expected_source_sha256": PARQUET_EXPECTED_SHA,
            "source_sha_match": actual_hash == PARQUET_EXPECTED_SHA, "month": 1,
            "selection": "first 16,384 physical rows", "selection_hand_check": base_checks,
            "footer_total_rows_month1": footer_rows, "projected_columns": SAMPLE_COLS,
            "batch_size_max": BATCH_MAX, "parquet_iter_batches_calls": physical_reads,
            "actual_E_transform_batches_calls": len(raw_batches),
            "transform_calls_are_separate_batches": len(raw_batches) > 1,
            "whole_column_AST_oracle_checks_precede_adapter": base_checks["canonical_AST_equals_independent_oracle"],
            "adapter_equals_AST": comparison,
            "adapter_equals_AST_values_and_index_labels": semantic_comparison,
            "concat_admitted_total": concat_offset,
            "excluded_concat_indices": sorted(set(range(concat_offset)) - original_indices),
            "canonical_output_rows": len(original),
            "excluded_by_oracle": selected - len(original),
            "batch_trace": batch_trace,
            "original_output_sha256": hashlib.sha256(original.to_csv(index=True).encode()).hexdigest(),
            "adapter_output_sha256": None if actual is None else hashlib.sha256(actual.to_csv(index=True).encode()).hexdigest()}


def main():
    result = {"schema": "round004_v_independent_dynamic_review_v1", "started_at": None,
              "requested_model": "gpt-6-luna", "requested_effort": "xhigh", "provider_internal_model_effort": "unknown",
              "result_scope": "independent limited fixtures, footer metadata and one fixed Train sample; not full equivalence"}
    result["process_memory_before"] = process_memory_snapshot()
    result["E_code_snapshot"] = {
        "bounded_loader.py": {"sha256": sha256(EXEC / "bounded_loader.py"), "expected_from_E_manifest": "da1c5b35561ea4d7478dc169e0cf4edaa6416c0aabb87e34d418dea9a9ab11c8"},
        "compare_loader_adapter.py": {"sha256": sha256(EXEC / "compare_loader_adapter.py"), "expected_from_E_manifest": "f1205517b8f3995677e2e678d116fe4fa1e5a04defed6541e90a4f945f4645fe"},
    }
    result["canonical_source_snapshots"] = file_sha_snapshots()
    if any(item["sha256"] != item["expected_from_E_manifest"] for item in result["E_code_snapshot"].values()):
        result["fatal"] = "E code changed after frozen artifact manifest"
        (DYNAMIC / "dynamic_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 8
    if any(x["sha256"] != x["pinned_sha256"] for x in result["canonical_source_snapshots"].values()):
        result["fatal"] = "canonical source hash mismatch"
        (DYNAMIC / "dynamic_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 9
    from bounded_loader import transform_batches, transform_months
    tables = main_fixture_tables()
    ast_loader = load_canonical_ast(tables)
    result["core_fixtures"] = fixture_core(ast_loader, tables)
    result["requested_columns_API"] = api_cases(ast_loader, tables)
    result["empty_boundary_cases"] = empty_cases(ast_loader)
    result["null_nan_cases"] = null_nan_cases(ast_loader)
    result["unsupported_cases"] = unsupported_cases(ast_loader)
    result["streaming_and_late_failure"] = late_unsupported_and_streaming_trace()
    result["metadata_only_source_lineage"] = parquet_footer_metadata()
    if result["metadata_only_source_lineage"]["train_footer_total_rows"] != 3887069:
        result["metadata_only_source_lineage"]["finding"] = "Train footer total differs from pinned historical count"
    result["actual_sample"] = actual_sample(ast_loader)
# excluded row count is computed inside actual_sample from its own canonical AST fixture
    core_ok = all(v["canonical_ast_equals_independent_oracle"]["equal"] and
                  v["oracle_equals_hand_expected"]["equal"] and
                  v["adapter_as_third_implementation_equals_ast"]["equal"]
                  for v in result["core_fixtures"].values())
    api_ok = all(v.get("ast_oracle", {"equal": True}).get("equal", False) and v.get("adapter", {"equal": True}).get("equal", False)
                 for v in result["requested_columns_API"].values())
    null_ok = all(v["ast_oracle"]["equal"] and v["adapter"]["equal"] for v in result["null_nan_cases"].values())
    sample_ok = result["actual_sample"]["source_sha_match"] and result["actual_sample"]["selection_hand_check"]['hand_selection_is_first_16384_source_rows'] and result["actual_sample"]["whole_column_AST_oracle_checks_precede_adapter"]["equal"] and result["actual_sample"]["adapter_equals_AST_values_and_index_labels"]["equal"] and result["actual_sample"]["actual_E_transform_batches_calls"] > 1
    result["gates"] = {"core_AST_oracle_hand_and_adapter_equal": core_ok, "requested_columns_API_equal": api_ok,
                       "null_nan_cases_equal": null_ok, "sample_equal_and_multi_call": sample_ok,
                       "empty_month_schema_support": False,
                       "whole_stage_fail_closed_atomicity": False,
                       "transform_months_trace_is_bounded_when_trace_none": False,
                       "overall_dynamic_loader_gate": "FAIL: edge/API and streaming behavior findings; scoped core/sample results remain separately recorded"}
    result["process_memory_after"] = process_memory_snapshot()
    (DYNAMIC / "dynamic_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"core_equal": core_ok, "api_equal": api_ok, "null_nan_equal": null_ok,
                      "sample_source_sha_match": result["actual_sample"]["source_sha_match"],
                      "sample_adapter_equal_values_and_index_labels": result["actual_sample"]["adapter_equals_AST_values_and_index_labels"]["equal"],
                      "sample_adapter_strict_dataframe_equal": result["actual_sample"]["adapter_equals_AST"]["equal"],
                      "sample_transform_batches_calls": result["actual_sample"]["actual_E_transform_batches_calls"],
                      "train_footer_rows": result["metadata_only_source_lineage"]["train_footer_total_rows"],
                      "late_failure_yielded_rows": result["streaming_and_late_failure"]["late_unsupported"]["yielded_rows_before_error"],
                      "trace_none_retained_indices": result["streaming_and_late_failure"]["trace_none_growth"]["observations"][-1]["retained_output_index_entries"],
                      "empty_month_schema_support": False, "overall_dynamic_loader_gate": "FAIL"}, ensure_ascii=False))
    if not (core_ok and api_ok and null_ok and sample_ok):
        return 2
    # A nonzero audit-script exit preserves the detected adapter contract defects.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())



