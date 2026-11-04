"""Experimental bounded loader for Round003; never enabled for production here.

This prototype performs the canonical load_rows row admission and casts a
projected Arrow RecordBatch at a time. Batch inference is explicitly *not*
claimed equivalent to whole-Series pandas inference; the production gate stays
closed until exact inference semantics are solved for all input partitions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def transform_batch(table, *, month: int, columns: list[str], key_valid_only: bool = True):
    """Transform one Arrow table/batch, preserving requested column order."""
    base_cols = [c for c in columns if c != "month"]
    out_cols = base_cols + (["key_valid"] if "key_valid" not in base_cols else [])
    df = table.select(out_cols).to_pandas()
    if key_valid_only:
        df = df[df["key_valid"]]
    df["month"] = np.int8(month)
    df = df[out_cols + ["month"]]
    if "rfid_id" in df.columns:
        numeric_id = pd.to_numeric(df["rfid_id"], errors="coerce")
        good = numeric_id.notna()
        df = df.loc[good].copy()
        numeric_id = numeric_id.loc[good]
        df["rfid_id"] = numeric_id.astype(np.int64)
    if "part_dt" in df.columns:
        numeric_dt = pd.to_numeric(df["part_dt"], errors="coerce")
        good = numeric_dt.notna()
        df = df.loc[good].copy()
        numeric_dt = numeric_dt.loc[good]
        df["part_dt"] = numeric_dt.astype(np.int32)
    return df


def transform_batches(batches, *, month: int, columns: list[str], key_valid_only: bool = True):
    """Yield frames sequentially; caller owns a single batch at a time."""
    for batch in batches:
        yield transform_batch(batch, month=month, columns=columns, key_valid_only=key_valid_only)
