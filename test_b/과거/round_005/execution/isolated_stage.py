"""Testfit-only, disk-staged caller for the restricted batch adapter."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid
from pathlib import Path
from typing import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from bounded_loader import transform_batches, transform_months


class StageDenied(RuntimeError):
    pass


class EmptySchemaUnavailable(RuntimeError):
    pass


def _atomic_noreplace(source: Path, destination: Path) -> None:
    """Use Windows' no-replace rename semantics; unknown platforms fail closed."""
    if platform.system() != "Windows":
        raise StageDenied("atomic no-clobber directory rename is only enabled on verified Windows")
    os.rename(source, destination)


def _has_link_component(path: Path) -> bool:
    """Reject symlink or Windows junction at any existing path component."""
    probe = Path(os.path.abspath(path))
    while True:
        is_junction = getattr(probe, "is_junction", lambda: False)()
        if probe.is_symlink() or is_junction:
            return True
        if probe == probe.parent:
            return False
        probe = probe.parent


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _paths(allowed_root: Path, final_path: Path) -> tuple[Path, Path]:
    if _has_link_component(allowed_root):
        raise StageDenied("allowed root may not be a symlink")
    root = allowed_root.resolve(strict=True)
    qroot = root / "quarantine"
    if _has_link_component(qroot):
        raise StageDenied("quarantine path may not contain a symlink or junction")
    if qroot.exists() and not qroot.is_dir():
        raise StageDenied("quarantine path exists but is not a directory")
    raw_final = Path(os.path.abspath(final_path))
    if _has_link_component(raw_final):
        raise StageDenied("final path contains a symlink or junction")
    final = raw_final.resolve(strict=False)
    if final == root or root not in final.parents:
        raise StageDenied("final path must be a new child of the explicitly allowed root")
    if final.drive.lower() != root.drive.lower():
        raise StageDenied("scratch and final path must be on the same volume")
    if final.exists():
        raise FileExistsError(f"final path already exists: {final}")
    return root, final


def _quarantine(stage: Path, root: Path, receipt: dict) -> Path:
    qroot = root / "quarantine"
    if _has_link_component(qroot):
        raise StageDenied("refusing to write quarantine receipt through a symlink or junction")
    qroot.mkdir(exist_ok=True)
    resolved_qroot = qroot.resolve(strict=True)
    if resolved_qroot.parent != root.resolve(strict=True):
        raise StageDenied("quarantine root resolved outside allowed root")
    target = qroot / stage.name.removeprefix(".stage-")
    if target.exists() or _has_link_component(target):
        raise StageDenied("quarantine receipt target already exists or traverses a link")
    if stage.exists():
        (stage / "QUARANTINED.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        os.rename(stage, target)
    else:
        target.mkdir(exist_ok=True)
        (target / "QUARANTINED.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return target


def run_testfit(*, columns: list[str],
                allowed_root: Path, final_path: Path, stage: str,
                dataset: str = "testfit", key_valid_only: bool = True,
                batches: Iterable | None = None, month: int | None = None,
                months: Iterable[int] | None = None, batches_for_month=None,
                commit=_atomic_noreplace, trace_sink=None,
                stage_create=Path.mkdir, parquet_writer=pq.write_table,
                empty_template: pd.DataFrame | None = None) -> dict:
    """Write each transformed batch to private scratch, then atomically publish directory.

    The only enabled caller is an isolated `testfit` fixture. This entry point
    deliberately cannot target train/test datasets or production stage names.
    Returned stream parts are never accumulated into a full in-memory frame.
    """
    if stage != "testfit" or dataset != "testfit":
        raise StageDenied("default deny: only explicit stage=dataset='testfit' is enabled")
    if months is None and (batches is None or month is None):
        raise StageDenied("supply exactly a month batch stream or ordered months callback")
    if months is not None and batches_for_month is None:
        raise StageDenied("ordered month callback is required with months")
    if len(columns) != len(set(columns)):
        raise StageDenied("duplicate requested columns are ambiguous and are denied")
    if "__canonical_index__" in columns:
        raise StageDenied("reserved output column __canonical_index__ was requested")
    root, final = _paths(Path(allowed_root), Path(final_path))
    stage_dir = root / (".stage-" + uuid.uuid4().hex)
    try:
        stage_create(stage_dir)
    except BaseException as exc:
        failure = {"stage": stage, "dataset": dataset, "published": False,
                   "error_type": type(exc).__name__, "error": str(exc),
                   "quarantined": True, "failure_phase": "scratch_create"}
        qpath = _quarantine(stage_dir, root, failure)
        (qpath / "receipt.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        (qpath / "QUARANTINED.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    receipt = {"stage": stage, "dataset": dataset, "final_path": str(final),
               "published": False, "commit_point": "same-volume atomic directory rename",
               "files": [], "batches": 0, "rows": 0, "_range_index_reconstructable": True}
    try:
        frames = (transform_batches(batches, month=month, columns=columns,
                                    key_valid_only=key_valid_only, trace=trace_sink)
                  if months is None else
                  transform_months(months, batches_for_month, columns=columns,
                                   key_valid_only=key_valid_only, trace=trace_sink))
        def persist_part(n: int, frame: pd.DataFrame) -> None:
            # Persist original concat ordinals explicitly; Parquet has no pandas index contract.
            output = frame.copy()
            output.insert(0, "__canonical_index__", frame.index.to_numpy(copy=True))
            target = stage_dir / f"part-{n:06d}.parquet"
            table = pa.Table.from_pandas(output, preserve_index=False)
            parquet_writer(table, target, compression="zstd")
            info = {"name": target.name, "sha256": _sha256(target), "rows": len(frame),
                    "admitted_rows": int(frame.attrs["admitted_rows"]),
                    "concat_offset_start": int(frame.attrs["concat_offset_start"]),
                    "concat_offset_end": int(frame.attrs["concat_offset_end"]),
                    "index_type": type(frame.index).__name__, "index_dtype": str(frame.index.dtype),
                    "index_name": frame.index.name,
                    "index_first_last": None if not len(frame) else [int(frame.index[0]), int(frame.index[-1])],
                    "columns": list(frame.columns), "dtypes": {c: str(t) for c, t in frame.dtypes.items()}}
            if receipt["files"] and (info["columns"] != receipt["files"][0]["columns"] or
                                     info["dtypes"] != receipt["files"][0]["dtypes"]):
                raise StageDenied("batch output schema drifted; whole stage refused")
            receipt["files"].append(info)
            receipt["batches"] += 1
            receipt["rows"] += len(frame)
            expected_start = receipt["rows"] - len(frame)
            if (info["index_type"] != "RangeIndex" or
                (len(frame) and info["index_first_last"] != [expected_start, expected_start + len(frame) - 1])):
                receipt["_range_index_reconstructable"] = False

        for n, frame in enumerate(frames):
            persist_part(n, frame)
        if receipt["batches"] == 0 and empty_template is not None:
            if len(empty_template) != 0:
                raise ValueError("empty_template must have zero rows")
            if list(empty_template.columns) != [c for c in columns if c != "month"] + ([] if "key_valid" in columns else ["key_valid"]) + ["month"]:
                raise ValueError("empty_template columns do not match canonical output order")
            template = empty_template.copy()
            template.attrs.update({"admitted_rows": 0, "concat_offset_start": 0, "concat_offset_end": 0})
            persist_part(0, template)
        receipt["pandas_contract"] = {
            "stream": "one DataFrame per non-None input RecordBatch; no cross-batch materialization",
            "reconstruction": "read parts in manifest order, concatenate without ignore_index, set index from __canonical_index__",
            "index_metadata": "per part: original pandas index class/dtype/name and first/last label; explicit labels persisted",
            "combined_index_reconstruction": "RangeIndex(0, rows) iff index_range_reconstructable is true; otherwise pandas Index of the explicit labels",
            "empty": "zero-row RecordBatch parts preserve schema; if the input yields no batches, materialization requires an explicit zero-row canonical empty_template; absent template fails closed"}
        if receipt["batches"] == 0:
            raise EmptySchemaUnavailable("no RecordBatch supplied; exact empty schema is unknown, refusing publication")
        receipt["columns"] = receipt["files"][0]["columns"]
        receipt["dtypes"] = receipt["files"][0]["dtypes"]
        receipt["index_range_reconstructable"] = receipt.pop("_range_index_reconstructable")
        receipt["manifest_version"] = 1
        manifest = {k: v for k, v in receipt.items() if k != "published"}
        manifest["publication_semantics"] = "public only when this complete directory is visible at final_path after atomic rename"
        (stage_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        # Recheck destination immediately before commit; rename itself fails if another directory appears.
        if final.exists():
            raise FileExistsError(f"final path appeared before commit: {final}")
        commit(stage_dir, final)
        receipt["published"] = True
        receipt["commit_point"] = "atomic rename completed; committed manifest is the public result"
        return receipt
    except BaseException as exc:
        failure = {**receipt, "error_type": type(exc).__name__, "error": str(exc),
                   "published": False, "quarantined": True}
        qpath = _quarantine(stage_dir, root, failure)
        failure["quarantine_path"] = str(qpath)
        # Preserve a receipt outside the staged data even if scratch is damaged.
        (qpath / "receipt.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        raise

