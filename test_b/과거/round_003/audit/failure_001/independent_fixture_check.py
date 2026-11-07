from __future__ import annotations
import ast
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import types

import numpy as np
import pandas as pd
import pyarrow as pa

ROOT = Path(__file__).resolve().parents[4]
CANONICAL = Path(r"D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py")
EXPECTED_SHA = "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c"
BOUNDED = ROOT / "testB/round_003/execution/bounded_loader.py"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_load_rows_for(tables: dict[int, pa.Table]):
    raw = CANONICAL.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA:
        raise RuntimeError(f"canonical hash mismatch: {actual}")
    tree = ast.parse(raw, filename=str(CANONICAL))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_rows")
    module = ast.Module(body=[node], type_ignores=[])

    class InjectedParquet:
        def read_table(self, path, columns):
            month = int(str(path).rsplit(":", 1)[1])
            return tables[month].select(columns)

    ns = {
        "pd": pd,
        "np": np,
        "gc": gc,
        "log": lambda *_args, **_kwargs: None,
        "MONTHS": tuple(sorted(tables)),
        "pq": InjectedParquet(),
        "parquet_path": lambda _dataset, month: f"synthetic:{month}",
    }
    exec(compile(module, str(CANONICAL), "exec"), ns)
    return ns["load_rows"]


def load_bounded_transform():
    spec = importlib.util.spec_from_file_location("round003_bounded_loader_fixture", BOUNDED)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.transform_batch


def table(rows):
    return pa.table({
        "rfid_id": [r[0] for r in rows],
        "part_dt": [r[1] for r in rows],
        "key_valid": [r[2] for r in rows],
    })


def independent_reference(tables, months, columns, key_valid_only):
    """Independent contract derivation: assemble admitted strings first, then convert whole key columns."""
    requested = [name for name in columns if name != "month"]
    pieces = []
    for month in months:
        cols = requested if "key_valid" in requested else requested + ["key_valid"]
        frame = tables[month].select(cols).to_pandas()
        if key_valid_only:
            frame = frame.loc[frame["key_valid"]]
        frame["month"] = np.int8(month)
        ordered = requested if "key_valid" in requested else requested + ["key_valid"]
        pieces.append(frame[ordered + ["month"]])
    out = pd.concat(pieces, ignore_index=True, copy=False)
    if "rfid_id" in out:
        parsed = pd.to_numeric(out["rfid_id"], errors="coerce")
        keep = parsed.notna()
        out = out.loc[keep]
        parsed = parsed.loc[keep]
        out["rfid_id"] = parsed.astype(np.int64)
    if "part_dt" in out:
        parsed = pd.to_numeric(out["part_dt"], errors="coerce")
        keep = parsed.notna()
        out = out.loc[keep]
        parsed = parsed.loc[keep]
        out["part_dt"] = parsed.astype(np.int32)
    return out


def compare(a, b):
    return {
        "columns_equal": list(a.columns) == list(b.columns),
        "rows_equal": len(a) == len(b),
        "dtypes_a": {c: str(t) for c, t in a.dtypes.items()},
        "dtypes_b": {c: str(t) for c, t in b.dtypes.items()},
        "dtypes_equal": a.dtypes.equals(b.dtypes),
        "values_equal_including_index": a.equals(b),
        "index_a": a.index.tolist(),
        "index_b": b.index.tolist(),
        "values_equal_after_reset_index": a.reset_index(drop=True).equals(b.reset_index(drop=True)),
    }


def main():
    bounded = load_bounded_transform()
    result = {
        "canonical_source": str(CANONICAL),
        "canonical_sha256": sha256(CANONICAL),
        "method": "compile the exact canonical load_rows AST against injected in-memory Arrow tables; separately derive a contract oracle with whole-column pd.to_numeric; compare to bounded_loader.transform_batch per explicit batch",
        "source_data_read": False,
    }

    # Minimal inference counterexample, deliberately split at the two-row batch boundary.
    precision_table = table([
        ("9007199254740993", "20250101", True),
        ("1.5", "20250102", True),
    ])
    precision_tables = {1: precision_table}
    original_loader = canonical_load_rows_for(precision_tables)
    canonical = original_loader("train", ["rfid_id", "part_dt", "key_valid"], months=(1,), key_valid_only=True)
    oracle = independent_reference(precision_tables, (1,), ["rfid_id", "part_dt", "key_valid"], True)
    batches = [precision_table.slice(0, 1), precision_table.slice(1, 1)]
    batch_frames = [bounded(b, month=1, columns=["rfid_id", "part_dt", "key_valid"], key_valid_only=True) for b in batches]
    bounded_concat = pd.concat(batch_frames, ignore_index=False)
    batch_values_reset = bounded_concat.reset_index(drop=True)
    global_raw = pd.to_numeric(pd.Series(["9007199254740993", "1.5"]), errors="coerce")
    separate_raw = [
        pd.to_numeric(pd.Series(["9007199254740993"]), errors="coerce"),
        pd.to_numeric(pd.Series(["1.5"]), errors="coerce"),
    ]
    result["precision_counterexample"] = {
        "input_ids": ["9007199254740993", "1.5"],
        "canonical_ast_equals_independent_whole_column_oracle": canonical.equals(oracle),
        "global_pd_to_numeric_dtype": str(global_raw.dtype),
        "global_pd_to_numeric_values": [float(v) for v in global_raw],
        "global_then_int64": [int(v) for v in global_raw.astype(np.int64)],
        "batch_pd_to_numeric_dtypes": [str(s.dtype) for s in separate_raw],
        "batch_then_int64": [int(v) for s in separate_raw for v in s.astype(np.int64)],
        "canonical_ast_ids_after_int64": canonical["rfid_id"].astype(str).tolist(),
        "bounded_per_batch_ids_after_int64": bounded_concat["rfid_id"].astype(str).tolist(),
        "canonical_dtypes": {c: str(t) for c, t in canonical.dtypes.items()},
        "batch_dtypes": {c: str(t) for c, t in bounded_concat.dtypes.items()},
        "canonical_index": canonical.index.tolist(),
        "batch_concat_index": bounded_concat.index.tolist(),
        "same_values_after_reset_index": canonical.reset_index(drop=True).equals(batch_values_reset),
    }
    assert result["precision_counterexample"]["canonical_ast_equals_independent_whole_column_oracle"]
    assert result["precision_counterexample"]["global_pd_to_numeric_dtype"] == "float64"
    assert result["precision_counterexample"]["global_then_int64"][0] == 9007199254740992
    assert result["precision_counterexample"]["batch_then_int64"][0] == 9007199254740993
    assert result["precision_counterexample"]["canonical_ast_ids_after_int64"] != result["precision_counterexample"]["bounded_per_batch_ids_after_int64"]

    # Check both key_valid modes, sequential ID-drop then date-drop, column ordering, dtypes and index labels.
    multi = {
        1: table([
            ("11", "20250101", True),
            ("bad", "20250102", True),
            ("13", "bad-date", True),
            ("14", "20250104", False),
        ]),
        2: table([
            ("21", "20250201", True),
            ("22", "20250202", False),
            (None, "20250203", True),
            ("24", "20250204", True),
        ]),
    }
    load_multi = canonical_load_rows_for(multi)
    modes = {}
    for key_only in (True, False):
        cases = {}
        for cols, expected_cols in [
            (["rfid_id", "part_dt", "month"], ["rfid_id", "part_dt", "key_valid", "month"]),
            (["key_valid", "rfid_id", "part_dt", "month"], ["key_valid", "rfid_id", "part_dt", "month"]),
        ]:
            actual = load_multi("train", cols, months=(1, 2), key_valid_only=key_only)
            oracle = independent_reference(multi, (1, 2), cols, key_only)
            parts = [bounded(multi[m], month=m, columns=cols, key_valid_only=key_only) for m in (1, 2)]
            chunk_join = pd.concat(parts, ignore_index=False)
            key = "requested=" + ",".join(cols)
            cases[key] = {
                "canonical_equals_independent_oracle": actual.equals(oracle),
                "canonical_columns": list(actual.columns),
                "expected_columns": expected_cols,
                "column_order_ok": list(actual.columns) == expected_cols,
                "canonical_dtype": {c: str(t) for c, t in actual.dtypes.items()},
                "independent_oracle_dtype_equal": actual.dtypes.equals(oracle.dtypes),
                "rows": len(actual),
                "canonical_ids": actual["rfid_id"].tolist(),
                "canonical_dates": actual["part_dt"].tolist(),
                "canonical_months": actual["month"].tolist(),
                "comparison_to_per_month_batch_transform": compare(actual, chunk_join),
            }
            assert cases[key]["canonical_equals_independent_oracle"]
            assert cases[key]["column_order_ok"]
            assert cases[key]["independent_oracle_dtype_equal"]
        modes[str(key_only).lower()] = cases
    result["key_filter_date_order_and_index"] = modes

    # The allowed-domain case has null/nonnumeric values, causing global float inference;
    # all accepted integer values are <= 2**53 and int32-safe, so conversion/cast is exact.
    allowed = result["key_filter_date_order_and_index"]["true"]["requested=rfid_id,part_dt,month"]
    raw_ids = pd.to_numeric(pd.Series(["11", "bad", "13", "21", None, "24"]), errors="coerce")
    raw_dates = pd.to_numeric(pd.Series(["20250101", "bad-date", "20250201", "20250204"]), errors="coerce")
    result["restricted_domain_null_nonnumeric"] = {
        "whole_series_id_inference": str(raw_ids.dtype),
        "whole_series_date_inference_after_valid_id_filter": str(raw_dates.dtype),
        "all_supported_ids_abs_le_2pow53": True,
        "all_retained_dates_in_int32_range": True,
        "canonical_final_id_and_date_dtypes": allowed["canonical_dtype"],
        "final_retained_rows": allowed["rows"],
        "canonical_oracle_equal": allowed["canonical_equals_independent_oracle"],
        "domain_claim_scope": "This two-month fixture supports only this finite synthetic domain; actual train domain remains unknown.",
    }
    assert result["restricted_domain_null_nonnumeric"]["whole_series_id_inference"] == "float64"
    assert result["restricted_domain_null_nonnumeric"]["whole_series_date_inference_after_valid_id_filter"] == "float64"
    result["verdict"] = "synthetic counterexample reproduced; bounded per-batch numeric inference is not equivalent; restricted-domain proof is conditional and does not establish actual train coverage"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
