"""Fail-closed restricted integer adapter for the pinned canonical load_rows.

This is a small-domain experiment, not a production loader. It preserves the
canonical post-key-filter concat ordinal and refuses tokens whose conversion
semantics cannot be proven equivalent within the declared integer domain.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator

import numpy as np
import pandas as pd

ID_LIMIT = 2**53
DATE_MIN, DATE_MAX = -(2**31), 2**31 - 1
MAX_TOKEN_CHARS = 128
_INTEGER = re.compile(r"[+-]?[0-9]+\Z", re.ASCII)
_CLEAR_NONNUMERIC = re.compile(r"[A-Za-z_]+\Z", re.ASCII)


class UnsupportedDomain(ValueError):
    """Input is not in the proven domain; caller must stop the whole stage."""


def _nullish(value) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, (float, np.floating)):
        return math.isnan(float(value))
    return False


def _integer_or_missing(value, *, column: str, row_index: int, lo: int, hi: int):
    """Return (integer, valid); only clear textual junk is safely coerced bad."""
    if _nullish(value):
        return None, False
    if isinstance(value, (bool, np.bool_)):
        raise UnsupportedDomain(f"{column} row {row_index}: bool unsupported")
    if isinstance(value, (int, np.integer)):
        n = int(value)
    elif isinstance(value, str):
        if len(value) > MAX_TOKEN_CHARS:
            raise UnsupportedDomain(f"{column} row {row_index}: token length {len(value)} > {MAX_TOKEN_CHARS}")
        if _INTEGER.fullmatch(value):
            # int() is exact and accepts the declared ASCII signs/leading zeroes.
            n = int(value, 10)
        elif _CLEAR_NONNUMERIC.fullmatch(value):
            # Ask pandas only whether this word is coercible; never use its
            # inferred value. Thus "abc" is safely invalid, while "inf" is
            # numeric-but-outside this domain and fails closed.
            coerced = pd.to_numeric(pd.Series([value], dtype=object), errors="coerce").iloc[0]
            if pd.isna(coerced):
                return None, False
            raise UnsupportedDomain(f"{column} row {row_index}: coercible word unsupported {value!r}")
        else:
            raise UnsupportedDomain(f"{column} row {row_index}: unsupported token {value!r}")
    else:
        raise UnsupportedDomain(f"{column} row {row_index}: unsupported value type {type(value).__name__}")
    if n < lo or n > hi:
        raise UnsupportedDomain(f"{column} row {row_index}: integer outside [{lo}, {hi}]")
    return n, True


def transform_batches(batches: Iterable, *, month: int, columns: list[str],
                      key_valid_only: bool = True, first_concat_ordinal: int = 0,
                      trace: list[dict] | None = None) -> Iterator[pd.DataFrame]:
    """Transform real batches sequentially, indexing like canonical concat.

    `first_concat_ordinal` is the post-key-filter global concat index for this
    month's first row. Caller advances it by each yielded batch's admitted row
    count, including rows later dropped by numeric coercion.
    """
    base_cols = [c for c in columns if c != "month"]
    out_cols = base_cols if "key_valid" in base_cols else base_cols + ["key_valid"]
    output_cols = out_cols + ["month"]
    offset = first_concat_ordinal
    for batch_number, batch in enumerate(batches):
        if batch is None or batch.num_rows == 0:
            if trace is not None:
                trace.append({"batch": batch_number, "input_rows": 0, "admitted_rows": 0,
                              "concat_offset": offset, "output_index": []})
            continue
        frame = batch.select(out_cols).to_pandas()
        if key_valid_only:
            frame = frame[frame["key_valid"]]
        admitted = len(frame)
        frame["month"] = np.int8(month)
        frame = frame[output_cols]
        frame.index = pd.RangeIndex(offset, offset + admitted)
        offset += admitted
        if "rfid_id" in frame.columns:
            ids, keep = [], []
            for ix, value in frame["rfid_id"].items():
                n, ok = _integer_or_missing(value, column="rfid_id", row_index=int(ix), lo=-ID_LIMIT, hi=ID_LIMIT)
                ids.append(n); keep.append(ok)
            keep_s = pd.Series(keep, index=frame.index, dtype=bool)
            frame = frame.loc[keep_s].copy()
            frame["rfid_id"] = np.asarray([v for v, ok in zip(ids, keep) if ok], dtype=np.int64)
        if "part_dt" in frame.columns:
            dates, keep = [], []
            for ix, value in frame["part_dt"].items():
                n, ok = _integer_or_missing(value, column="part_dt", row_index=int(ix), lo=DATE_MIN, hi=DATE_MAX)
                dates.append(n); keep.append(ok)
            keep_s = pd.Series(keep, index=frame.index, dtype=bool)
            frame = frame.loc[keep_s].copy()
            frame["part_dt"] = np.asarray([v for v, ok in zip(dates, keep) if ok], dtype=np.int32)
        if trace is not None:
            trace.append({"batch": batch_number, "input_rows": batch.num_rows,
                          "admitted_rows": admitted, "concat_offset_end": offset,
                          "output_rows": len(frame), "output_index": frame.index.tolist(),
                          "columns": list(frame.columns), "dtypes": {c: str(t) for c, t in frame.dtypes.items()}})
        yield frame


def transform_months(months: Iterable[int], batches_for_month, *, columns: list[str],
                     key_valid_only: bool = True, trace: list[dict] | None = None) -> Iterator[pd.DataFrame]:
    """Stream months in caller order while carrying one concat ordinal.

    The source loader's `pd.concat([])` raises ValueError; preserve that empty
    month-list failure instead of silently returning an empty frame.
    """
    month_list = tuple(months)
    if not month_list:
        raise ValueError("No objects to concatenate")
    offset = 0
    for month in month_list:
        local_trace: list[dict] = []
        yield from transform_batches(batches_for_month(month), month=month, columns=columns,
                                     key_valid_only=key_valid_only,
                                     first_concat_ordinal=offset, trace=local_trace)
        offset += sum(int(item["admitted_rows"]) for item in local_trace)
        if trace is not None:
            for item in local_trace:
                trace.append({"month": month, **item})
