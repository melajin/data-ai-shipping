"""Testfit-only, disk-staged caller for the restricted batch adapter.

Round006 changes against the Round005 file
(sha256 76f3f7f8e3a39a27d8c24f1d3532b83181bf2e20470da38b7543b55a04795fea):

1. Empty-schema provenance. The caller can no longer hand in an arbitrary
   zero-row frame. It supplies the real Arrow source schema, and the canonical
   empty frame is *constructed here* by running the same `transform_batches`
   code path over a zero-row RecordBatch of that schema. An optionally supplied
   template is only ever a cross-check that must be strictly equal.
2. Bounded per-part metadata. Part metadata is appended to `parts.jsonl` in the
   scratch directory as each part is written. RAM retains O(1) state: a capped
   head window, the last entry, counters, the first part's schema and a rolling
   digest of the manifest lines.
"""
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

PARTS_FILE = "parts.jsonl"
DEFAULT_METADATA_RETAIN = 8


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


def canonical_output_columns(columns: list[str]) -> list[str]:
    """The canonical loader's output column order for a requested projection."""
    base_cols = [c for c in columns if c != "month"]
    out_cols = base_cols if "key_valid" in base_cols else base_cols + ["key_valid"]
    return out_cols + ["month"]


def canonical_empty_frame(source_schema: pa.Schema, *, columns: list[str], month: int,
                          key_valid_only: bool = True) -> pd.DataFrame:
    """Build the zero-row canonical output from the *real* Arrow source schema.

    Provenance: the frame is produced by the same `transform_batches` path used
    for real data, over a zero-row RecordBatch of the source schema. Nothing
    about its dtypes or index class is chosen by the caller.
    """
    if not isinstance(source_schema, pa.Schema):
        raise StageDenied("empty_source_schema must be a pyarrow.Schema from the real source")
    needed = [c for c in canonical_output_columns(columns) if c != "month"]
    missing = [c for c in needed if c not in source_schema.names]
    if missing:
        raise StageDenied(f"source schema lacks required columns: {missing}")
    empty = pa.RecordBatch.from_pydict(
        {name: pa.array([], type=source_schema.field(name).type) for name in needed},
        schema=pa.schema([source_schema.field(name) for name in needed]))
    frames = list(transform_batches([empty], month=month, columns=columns,
                                    key_valid_only=key_valid_only, trace=None))
    if len(frames) != 1:
        raise StageDenied("zero-row schema probe must yield exactly one frame")
    frame = frames[0]
    if len(frame) != 0:
        raise StageDenied("zero-row schema probe yielded rows")
    if type(frame.index) is not pd.RangeIndex:
        raise StageDenied(f"zero-row schema probe index class {type(frame.index).__name__} is not RangeIndex")
    if list(frame.columns) != canonical_output_columns(columns):
        raise StageDenied("zero-row schema probe column order is not canonical")
    return frame


def _assert_template_matches(template: pd.DataFrame, canonical: pd.DataFrame) -> None:
    """A caller-supplied empty template is a cross-check, never the source."""
    if len(template) != 0:
        raise ValueError("empty_template must have zero rows")
    if list(template.columns) != list(canonical.columns):
        raise ValueError("empty_template columns do not match canonical output order")
    bad = {c: (str(template[c].dtype), str(canonical[c].dtype))
           for c in canonical.columns if template[c].dtype != canonical[c].dtype}
    if bad:
        raise ValueError(f"empty_template dtypes differ from canonical schema: {bad}")
    if type(template.index) is not type(canonical.index):
        raise ValueError(f"empty_template index class {type(template.index).__name__} "
                         f"differs from canonical {type(canonical.index).__name__}")
    if str(template.index.dtype) != str(canonical.index.dtype):
        raise ValueError("empty_template index dtype differs from canonical schema")
    if template.index.name != canonical.index.name:
        raise ValueError("empty_template index name differs from canonical schema")


class _BoundedManifest:
    """Stream part metadata to disk; retain O(1) state in RAM."""

    def __init__(self, stage_dir: Path, retain: int):
        if not isinstance(retain, int) or isinstance(retain, bool) or retain < 1:
            raise StageDenied("metadata_retain must be a positive integer cap")
        self.path = stage_dir / PARTS_FILE
        self.retain = retain
        self.head: list[dict] = []
        self.last: dict | None = None
        self.count = 0
        self.rows = 0
        self.lines_digest = hashlib.sha256()
        self.schema: dict | None = None
        self._handle = self.path.open("ab")

    def append(self, info: dict) -> None:
        if self.schema is None:
            self.schema = {"columns": info["columns"], "dtypes": info["dtypes"]}
        elif info["columns"] != self.schema["columns"] or info["dtypes"] != self.schema["dtypes"]:
            raise StageDenied("batch output schema drifted; whole stage refused")
        line = (json.dumps(info, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        self._handle.write(line)
        self._handle.flush()
        self.lines_digest.update(line)
        self.count += 1
        self.rows += info["rows"]
        if len(self.head) < self.retain:
            self.head.append(info)
        self.last = info

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()

    def summary(self) -> dict:
        """Bounded description of every part; the full list lives in PARTS_FILE."""
        return {"parts_file": PARTS_FILE,
                "parts_file_sha256": self.lines_digest.hexdigest(),
                "parts_file_lines": self.count,
                "metadata_retain_limit": self.retain,
                "files_head": list(self.head),
                "files_last": self.last,
                "files_total": self.count,
                "files_retention": ("full" if self.count <= self.retain
                                    else f"head {self.retain} of {self.count} retained; "
                                         f"complete list in {PARTS_FILE}")}


def run_testfit(*, columns: list[str],
                allowed_root: Path, final_path: Path, stage: str,
                dataset: str = "testfit", key_valid_only: bool = True,
                batches: Iterable | None = None, month: int | None = None,
                months: Iterable[int] | None = None, batches_for_month=None,
                commit=_atomic_noreplace, trace_sink=None,
                stage_create=Path.mkdir, parquet_writer=pq.write_table,
                empty_source_schema: pa.Schema | None = None,
                empty_template: pd.DataFrame | None = None,
                metadata_retain: int = DEFAULT_METADATA_RETAIN) -> dict:
    """Write each transformed batch to private scratch, then atomically publish directory.

    The only enabled caller is an isolated `testfit` fixture. This entry point
    deliberately cannot target train/test datasets or production stage names.
    Returned stream parts are never accumulated into a full in-memory frame, and
    per-part metadata is not accumulated in memory either.
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
    if empty_template is not None and empty_source_schema is None:
        raise StageDenied("empty_template is only a cross-check; the real source schema is required")
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
               "batches": 0, "rows": 0, "_range_index_reconstructable": True}
    manifest_log: _BoundedManifest | None = None
    try:
        manifest_log = _BoundedManifest(stage_dir, metadata_retain)
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
            expected_start = receipt["rows"]
            manifest_log.append(info)
            receipt["batches"] = manifest_log.count
            receipt["rows"] = manifest_log.rows
            if (info["index_type"] != "RangeIndex" or
                (len(frame) and info["index_first_last"] != [expected_start, expected_start + len(frame) - 1])):
                receipt["_range_index_reconstructable"] = False

        for n, frame in enumerate(frames):
            persist_part(n, frame)
        if receipt["batches"] == 0 and empty_source_schema is not None:
            canonical = canonical_empty_frame(empty_source_schema, columns=columns,
                                              month=(0 if month is None else month),
                                              key_valid_only=key_valid_only)
            if empty_template is not None:
                _assert_template_matches(empty_template, canonical)
            canonical.attrs.update({"admitted_rows": 0, "concat_offset_start": 0, "concat_offset_end": 0})
            persist_part(0, canonical)
            receipt["empty_schema_provenance"] = (
                "zero-row RecordBatch of the supplied real Arrow source schema, "
                "transformed by the same adapter path"
                + ("; caller template cross-checked equal" if empty_template is not None else ""))
        receipt["pandas_contract"] = {
            "stream": "one DataFrame per non-None input RecordBatch; no cross-batch materialization",
            "reconstruction": f"read {PARTS_FILE} lines in order, read those parts, concatenate without "
                              "ignore_index, set index from __canonical_index__",
            "index_metadata": "per part: original pandas index class/dtype/name and first/last label; explicit labels persisted",
            "combined_index_reconstruction": "RangeIndex(0, rows) iff index_range_reconstructable is true; otherwise pandas Index of the explicit labels",
            "metadata_bound": f"per-part metadata is appended to {PARTS_FILE} on disk; in-memory retention is "
                              "capped at metadata_retain_limit entries plus the last entry",
            "empty": "zero-row RecordBatch parts preserve schema; if the input yields no batches, "
                     "materialization requires the real Arrow source schema and the empty frame is "
                     "constructed by this module, not accepted from the caller; absent schema fails closed"}
        if receipt["batches"] == 0:
            raise EmptySchemaUnavailable("no RecordBatch supplied and no source schema; exact empty schema is unknown, refusing publication")
        receipt["columns"] = manifest_log.schema["columns"]
        receipt["dtypes"] = manifest_log.schema["dtypes"]
        receipt["index_range_reconstructable"] = receipt.pop("_range_index_reconstructable")
        receipt["manifest_version"] = 2
        receipt.update(manifest_log.summary())
        manifest_log.close()
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
        if manifest_log is not None:
            failure_summary = manifest_log.summary()
            manifest_log.close()
        else:
            failure_summary = {}
        failure = {**receipt, **failure_summary, "error_type": type(exc).__name__, "error": str(exc),
                   "published": False, "quarantined": True}
        qpath = _quarantine(stage_dir, root, failure)
        failure["quarantine_path"] = str(qpath)
        # Preserve a receipt outside the staged data even if scratch is damaged.
        (qpath / "receipt.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
