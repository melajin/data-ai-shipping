from __future__ import annotations
import argparse, ast, csv, hashlib, json, math, os, sqlite3, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import psutil
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
PREP = ROUND / "preparation"
MANIFEST = PREP / "manifest.json"
IDS_PATH = PREP / "new_testB_ids_100.csv"
BATCH = 16384
SOURCE_CODE = Path(r"D:\repos\fishing-track-classification\code\tools\run_008_testB_20261101.py")
REMEASURE_CODE = Path(r"D:\repos\fishing-track-classification\code\tools\run_remeasure_20261031.py")
RUN005_CODE = Path(r"D:\repos\fishing-track-classification\code\tools\run_005_F156_merge_20261101.py")
FEATAC_CODE = Path(r"D:\repos\fishing-track-classification\code\tools\run_cycle4_3_featAC_20261101.py")
EXPECTED_SOURCE_HASHES = {
    str(SOURCE_CODE): "cca724154a4a479e445bbb3cfead6cb13b92849f364182d70abef91822f78fc8",
    str(REMEASURE_CODE): "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c",
    str(RUN005_CODE): "e14ddbae01864e4ae7bce0600e361aee0fbabb69cfe6d4ea4679db701d0c40a4",
    str(FEATAC_CODE): "8c454a8c1f87014007b85609d0667ff1126f68b8f23bbe30d05890032a7b04f3",
}

# Required projection for row trace and the scorer's unchanged wkt_valid admission rule.
PROJECTION = ["row_index", "part_dt", "rfid_id", "rfid_time", "key_valid", "wkt_valid", "n_coords", "len_m", "bbox_m", "cen_lon", "cen_lat"]
SCORE_NUMERIC = ["rfid_time", "cen_lon", "cen_lat", "len_m", "bbox_m"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_inputs():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    ids_bytes = IDS_PATH.read_bytes()
    ids_hash = hashlib.sha256(ids_bytes).hexdigest()
    expected = manifest["new_submission"]["ordered_ids_csv_sha256"]
    if ids_hash != expected:
        raise RuntimeError(f"ID list SHA mismatch: {ids_hash} != {expected}")
    with IDS_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # Preparation artifact is a one-column ordered list; preserve exact string IDs.
    id_field = "rfid_id" if rows and "rfid_id" in rows[0] else "raw_value"
    ids = [r[id_field] for r in rows]
    if len(ids) != 100 or len(set(ids)) != 100 or any(not x for x in ids):
        raise RuntimeError(f"Expected exactly 100 unique nonempty string IDs; got {len(ids)}")
    return manifest, ids, ids_hash


def scan(out: Path):
    manifest, ids, id_sha = load_inputs()
    proc = psutil.Process()
    start_rss = proc.memory_info().rss
    start_available = psutil.virtual_memory().available
    process_count = len(psutil.pids())
    peak_rss_sampled = start_rss
    lookup = pa.array(ids, type=pa.string())
    selected_dir = out / "selected_rows"
    selected_dir.mkdir(parents=True, exist_ok=True)
    db_path = out / "scratch" / f"selected_timestamp_keys_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{os.getpid()}.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("CREATE TABLE IF NOT EXISTS seen (rfid_id TEXT, part_dt TEXT, rfid_time INTEGER, occurrence INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(rfid_id,part_dt,rfid_time)) WITHOUT ROWID")
    n_by_id = {x: Counter() for x in ids}
    dates = {x: [None, None] for x in ids}
    months = {x: Counter() for x in ids}
    finite_bad = {x: Counter() for x in ids}
    value_ranges = {x: {k:[None,None] for k in SCORE_NUMERIC} for x in ids}
    index_stats = {}
    total_selected = 0
    duplicate_timestamp_rows = 0
    duplicate_timestamp_check_rows = 0
    files = []
    base_ordinal = 0
    for src in manifest["v2_csv_to_cache_lineage"]["months"]:
        month = int(src["month"])
        p = Path(src["parquet_path"])
        if not p.is_file():
            raise FileNotFoundError(p)
        pf = pq.ParquetFile(p)
        missing = sorted(set(PROJECTION) - set(pf.schema_arrow.names))
        if missing:
            raise RuntimeError(f"{p}: missing columns {missing}")
        writer = None
        seen_rows = 0
        min_idx = None
        max_idx = None
        previous_idx = None
        nonsequential = 0
        selected_month = 0
        batch_count = 0
        out_path = selected_dir / f"month_{month:02d}.parquet"
        for batch in pf.iter_batches(batch_size=BATCH, columns=PROJECTION, use_threads=False):
            peak_rss_sampled = max(peak_rss_sampled, proc.memory_info().rss)
            batch_count += 1
            seen_rows += batch.num_rows
            idx = batch.column(batch.schema.get_field_index("row_index"))
            if len(idx):
                vals = idx.to_numpy(zero_copy_only=False)
                lo, hi = int(vals.min()), int(vals.max())
                min_idx = lo if min_idx is None else min(min_idx, lo)
                max_idx = hi if max_idx is None else max(max_idx, hi)
                expected_start = 0 if previous_idx is None else previous_idx + 1
                nonsequential += int(np.count_nonzero(vals != np.arange(expected_start, expected_start + len(vals), dtype=vals.dtype)))
                previous_idx = int(vals[-1])
            colid = batch.column(batch.schema.get_field_index("rfid_id"))
            mask = pc.is_in(colid, value_set=lookup)
            picked = batch.filter(mask)
            if not picked.num_rows:
                continue
            ids_col = picked.column(picked.schema.get_field_index("rfid_id")).to_pylist()
            date_col = picked.column(picked.schema.get_field_index("part_dt")).to_pylist()
            time_col = picked.column(picked.schema.get_field_index("rfid_time")).to_pylist()
            idx_col = picked.column(picked.schema.get_field_index("row_index")).to_pylist()
            valid_col = picked.column(picked.schema.get_field_index("wkt_valid")).to_pylist()
            for field in ("key_valid", "wkt_valid", "n_coords", "row_index", "part_dt"):
                nulls=picked.column(picked.schema.get_field_index(field)).to_pylist()
                for rid, value in zip(ids_col, nulls):
                    if value is None: finite_bad[rid]["missing_"+field]+=1
            table = pa.Table.from_batches([picked])
            table = table.append_column("source_month", pa.array([month] * picked.num_rows, type=pa.int8()))
            table = table.append_column("source_file", pa.array([src["source_path"].split("\\")[-1]] * picked.num_rows, type=pa.string()))
            table = table.append_column("source_ordinal", pa.array([base_ordinal + int(x) for x in idx_col], type=pa.int64()))
            if writer is None:
                writer = pq.ParquetWriter(out_path, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=BATCH)
            selected_month += picked.num_rows
            total_selected += picked.num_rows
            # Exact duplicate timestamp keys are counted with an on-disk uniqueness index.
            entries = []
            for rid, day, hour in zip(ids_col, date_col, time_col):
                if day is not None and hour is not None:
                    entries.append((rid, str(day), int(hour)))
            db.executemany("INSERT INTO seen (rfid_id,part_dt,rfid_time,occurrence) VALUES (?,?,?,1) ON CONFLICT(rfid_id,part_dt,rfid_time) DO UPDATE SET occurrence=occurrence+1", entries)
            duplicate_timestamp_check_rows += len(entries)
            db.commit()
            for rid, day, hour, valid in zip(ids_col, date_col, time_col, valid_col):
                c = n_by_id[rid]
                c["raw_rows"] += 1
                months[rid][month] += 1
                if valid is True:
                    c["valid_rows"] += 1
                else:
                    c["invalid_wkt_rows"] += 1
                d = None if day is None else str(day)
                if d:
                    dates[rid][0] = d if dates[rid][0] is None else min(dates[rid][0], d)
                    dates[rid][1] = d if dates[rid][1] is None else max(dates[rid][1], d)
            # Check required numeric finiteness and timestamp parseability per row, without retaining rows.
            cols = {name: picked.column(picked.schema.get_field_index(name)).to_pylist() for name in SCORE_NUMERIC}
            dayvals = picked.column(picked.schema.get_field_index("part_dt")).to_pylist()
            for j, rid in enumerate(ids_col):
                numeric_ok = True
                for name in SCORE_NUMERIC:
                    v = cols[name][j]
                    if v is None or (isinstance(v, float) and not math.isfinite(v)):
                        finite_bad[rid][name] += 1
                        numeric_ok = False
                    else:
                        lo,hi=value_ranges[rid][name]
                        value_ranges[rid][name]=[v if lo is None else min(lo,v),v if hi is None else max(hi,v)]
                d = dayvals[j]
                dayok = d is not None and len(str(d)) == 8 and str(d).isdigit()
                if not dayok:
                    finite_bad[rid]["invalid_part_dt"] += 1
                if valid_col[j] is True and numeric_ok and dayok:
                    n_by_id[rid]["scorable_rows"] += 1
            if writer is not None:
                pass
        if writer is not None:
            writer.close()
        expected_rows = int(src["raw_rows"])
        index_stats[str(month)] = {"source_file": src["source_path"].split("\\")[-1], "parquet_path": str(p),
            "parquet_bytes": p.stat().st_size, "rows_scanned": seen_rows, "expected_from_prior_parse_manifest": expected_rows,
            "row_index_min": min_idx, "row_index_max": max_idx, "nonsequential_row_index_count": nonsequential,
            "batch_count": batch_count, "selected_rows": selected_month, "selected_output": str(out_path.relative_to(out)),
            "complete_against_prior_count": seen_rows == expected_rows and min_idx == 0 and max_idx == expected_rows - 1 and nonsequential == 0}
        files.append(index_stats[str(month)])
        base_ordinal += expected_rows
    duplicate_by_id = dict(db.execute("SELECT rfid_id, SUM(occurrence-1) FROM seen GROUP BY rfid_id"))
    duplicate_timestamp_rows = sum(int(x or 0) for x in duplicate_by_id.values())
    db.close()
    summary_path = out / "target_row_summary.csv"
    fields = ["target_order", "rfid_id", "raw_rows", "valid_wkt_rows", "invalid_wkt_rows", "scorable_finite_rows", "excluded_nonfinite_or_bad_date_rows", "month_row_counts", "date_min", "date_max", "duplicate_timestamp_rows_in_checked_keys", "missing_part_dt", "missing_key_valid", "missing_wkt_valid", "missing_n_coords", "missing_row_index", "missing_or_nonfinite_rfid_time", "missing_or_nonfinite_cen_lon", "missing_or_nonfinite_cen_lat", "missing_or_nonfinite_len_m", "missing_or_nonfinite_bbox_m", "invalid_part_dt", "rfid_time_min", "rfid_time_max", "cen_lon_min", "cen_lon_max", "cen_lat_min", "cen_lat_max", "len_m_min", "len_m_max", "bbox_m_min", "bbox_m_max"]
    with summary_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for order, rid in enumerate(ids, 1):
            c, bad = n_by_id[rid], finite_bad[rid]
            w.writerow({"target_order": order, "rfid_id": rid, "raw_rows": c["raw_rows"], "valid_wkt_rows": c["valid_rows"],
                "invalid_wkt_rows": c["invalid_wkt_rows"], "scorable_finite_rows": c["scorable_rows"],
                "excluded_nonfinite_or_bad_date_rows": c["valid_rows"] - c["scorable_rows"],
                "month_row_counts": json.dumps({str(m): months[rid][m] for m in range(1,7)}, separators=(",",":")),
                "date_min": dates[rid][0], "date_max": dates[rid][1],
                "duplicate_timestamp_rows_in_checked_keys": duplicate_by_id.get(rid, 0),
                "missing_part_dt": bad["missing_part_dt"], "missing_key_valid": bad["missing_key_valid"],
                "missing_wkt_valid": bad["missing_wkt_valid"], "missing_n_coords": bad["missing_n_coords"],
                "missing_row_index": bad["missing_row_index"],
                "missing_or_nonfinite_rfid_time": bad["rfid_time"], "missing_or_nonfinite_cen_lon": bad["cen_lon"],
                "missing_or_nonfinite_cen_lat": bad["cen_lat"], "missing_or_nonfinite_len_m": bad["len_m"],
                "missing_or_nonfinite_bbox_m": bad["bbox_m"], "invalid_part_dt": bad["invalid_part_dt"],
                **{f"{name}_min":value_ranges[rid][name][0] for name in SCORE_NUMERIC},
                **{f"{name}_max":value_ranges[rid][name][1] for name in SCORE_NUMERIC}})
    return {"memory_start_available_mib": round(start_available/1024**2,1), "memory_total_mib": round(psutil.virtual_memory().total/1024**2,1),
        "process_count_start": process_count, "self_rss_start_mib": round(start_rss/1024**2,1),
        "self_rss_peak_sampled_mib": round(peak_rss_sampled/1024**2,1),
        "self_rss_peak_sampled_delta_mib": round((peak_rss_sampled-start_rss)/1024**2,1),
        "peak_sampling": "resident set sampled once per processed parquet batch; may miss transient sub-batch peaks",
        "ids_sha256": id_sha, "ids_count":len(ids), "ids_unique":len(set(ids)), "rows_scanned":sum(x["rows_scanned"] for x in files),
        "selected_rows":total_selected, "selected_timestamp_keys_checked":duplicate_timestamp_check_rows,
        "duplicate_timestamp_rows":duplicate_timestamp_rows, "months":files, "summary_csv":str(summary_path.relative_to(out)),
        "selected_rows_dir":str(selected_dir.relative_to(out)), "row_index_ordinal_contract":"source_ordinal = sum prior monthly expected raw_rows + row_index; row_index is 0-based data-row ordinal within source monthly file"}


def safe_score_namespace():
    """AST-load original score_vessel and exact constants only; never import stock CLI modules."""
    src = SOURCE_CODE.read_bytes()
    score_hash = verify_source_bytes(src, str(SOURCE_CODE), EXPECTED_SOURCE_HASHES[str(SOURCE_CODE)])
    tree = ast.parse(src, filename=str(SOURCE_CODE))
    wanted = {"GRID_HARBOR","GRID_FINE","GRID_COARSE","T5_MIN_VESSELS","MIN_HIST_FOR_CHANGE","STOP_LEN_M","STOP_BBOX_M","HARBOR_NEAR_M","MOORING_NEAR_M","SEA_STOP_FAR_M","MOVE_LEN_M","MOVE_STRAIGHT","NIGHT_HOURS","score_vessel","lookup_density","robust_z","squash"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & wanted: nodes.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            nodes.append(node)
    code = compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE_CODE), "exec")
    # Minimal compatibility namespace for pure original score function dependencies.
    rm_src = REMEASURE_CODE.read_bytes()
    remeasure_hash = verify_source_bytes(rm_src, str(REMEASURE_CODE), EXPECTED_SOURCE_HASHES[str(REMEASURE_CODE)])
    rm_tree = ast.parse(rm_src, filename=str(REMEASURE_CODE))
    rm_wanted = {"EARTH_R", "haversine_m"}
    rm_nodes=[]
    for node in rm_tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in rm_wanted for t in node.targets): rm_nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in rm_wanted: rm_nodes.append(node)
    rm_ns={"math":math,"np":np}
    exec(compile(ast.Module(body=rm_nodes,type_ignores=[]),str(REMEASURE_CODE),"exec"),rm_ns)
    ns={"np":np,"pd":pd,"math":math,"remeasure":SimpleNamespace(**rm_ns)}
    exec(code,ns)
    return ns, score_hash, remeasure_hash


def verify_source_bytes(source: bytes, label: str, expected: str) -> str:
    actual=hashlib.sha256(source).hexdigest()
    if actual != expected:
        raise RuntimeError(f"source lineage mismatch for {label}: {actual} != {expected}")
    return actual


def assert_reference_fit_partition(partition: str, frame_partition: str | None = None):
    """Hard boundary for every future common-reference builder entry point."""
    if partition != "train" or (frame_partition is not None and frame_partition != "train"):
        raise ValueError("common references may be fit from 2026 train rows only")


def numeric_target_ids(raw_ids: list[str]) -> dict[str,int]:
    """Keep raw IDs unchanged; normalize decimal IDs only for int64 train-array lookup."""
    out={}
    for raw in raw_ids:
        if not raw.isascii() or not raw.isdigit():
            raise ValueError(f"target ID is not an ASCII decimal string: {raw!r}")
        out[raw]=int(raw,10)
    inverse={}
    for raw,num in out.items():
        inverse.setdefault(num,[]).append(raw)
    aliases={n:rs for n,rs in inverse.items() if len(rs)>1}
    if aliases:
        raise ValueError(f"distinct raw IDs collapse to the same numeric train ID: {aliases}")
    return out


def membership_from_preloaded_ids(raw_ids: list[str], train_rids, labels: dict[str,str], *, train_loader=None):
    """Pure membership comparison; requires preloaded train IDs and never loads train data itself."""
    if train_loader is not None:
        raise ValueError("membership comparison accepts preloaded train IDs only; no train loader allowed")
    numeric=numeric_target_ids(raw_ids)
    label_membership={raw:raw in labels for raw in raw_ids}
    train_membership={raw:bool(np.any(train_rids==num)) for raw,num in numeric.items()}
    return {"raw_ids_in_order":list(raw_ids),"numeric_id_lookup":numeric,
        "label_membership_by_raw_id":label_membership,"train_reference_membership_by_raw_id":train_membership}


def build_train_references(*, allow_reference_rebuild: bool = False):
    """Prepare the original builders behind an explicit later-run gate; never called by this task."""
    if not allow_reference_rebuild:
        raise RuntimeError("reference rebuild requires a separate supervisor production gate")
    for path, expected in EXPECTED_SOURCE_HASHES.items():
        actual=sha256(Path(path))
        if actual != expected:
            raise RuntimeError(f"source lineage mismatch: {path} {actual} != {expected}")
    import importlib
    import sys
    tools=str(SOURCE_CODE.parent)
    if tools not in sys.path: sys.path.insert(0,tools)
    # Original module imports only define functions/constants/read small classes metadata;
    # never invoke any stage/main entry point. Builder inputs are fenced to train below.
    remeasure=importlib.import_module("run_remeasure_20261031")
    featac=importlib.import_module("run_cycle4_3_featAC_20261101")
    m=importlib.import_module("run_005_F156_merge_20261101")
    source=importlib.import_module("run_008_testB_20261101")
    original_load_rows=remeasure.load_rows
    original_load_arrays=featac._load_year_arrays
    def train_rows(dataset, *args, **kwargs):
        assert_reference_fit_partition(dataset,dataset)
        return original_load_rows(dataset,*args,**kwargs)
    def train_arrays(dataset):
        assert_reference_fit_partition(dataset,dataset)
        return original_load_arrays(dataset)
    remeasure.load_rows=train_rows
    featac._load_year_arrays=train_arrays
    m._TRAIN_ARRAYS=None
    # Exact original train-only builders. No Test row is an argument to these calls.
    nearest, harbor_meta, harbor_points=source.build_train_harbors()
    dens01,dens05,_unused_ref_density,density_meta=source.build_train_fishing_density_dicts()
    del _unused_ref_density
    gap_h,jump_m=source.build_gap_jump_reference()
    norm_gap,gap_meta=source.build_quantile_normalizer(gap_h)
    norm_jump,jump_meta=source.build_quantile_normalizer(jump_m)
    del gap_h,jump_m
    _id_manifest,target_ids,_id_sha=load_inputs()
    labels=m.load_labels()
    # Source ID membership uses train arrays only and is reported separately from labels.
    train_arrays_cache=m._train_arrays()
    membership=membership_from_preloaded_ids(target_ids,train_arrays_cache["rid"],labels)
    m._TRAIN_ARRAYS=None
    del train_arrays_cache
    return {"nearest_harbor_m":nearest,"harbor_meta":harbor_meta,"harbor_points":harbor_points,
        "dens_map01":dens01,"dens_map05":dens05,"density_meta":density_meta,
        "norm_gap":norm_gap,"norm_jump":norm_jump,"gap_meta":gap_meta,"jump_meta":jump_meta,
        "membership":membership,"source_hashes":EXPECTED_SOURCE_HASHES.copy(),"test_fit_calls":0}


def order_for_scoring(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"ts", "rfid_time", "source_ordinal"}
    if not required.issubset(frame.columns):
        raise ValueError(f"missing order columns: {sorted(required-set(frame.columns))}")
    return frame.sort_values(["ts", "rfid_time", "source_ordinal"], kind="mergesort").reset_index(drop=True)


def choose_a(frame: pd.DataFrame) -> dict:
    """Choose first input-row maximum, withholding A for timestamp score conflicts."""
    required = {"ts", "rfid_time", "source_ordinal", "score"}
    if not required.issubset(frame.columns):
        raise ValueError(f"missing A-selection columns: {sorted(required-set(frame.columns))}")
    conflicts=[]
    for key, group in frame.groupby(["ts", "rfid_time"], dropna=False, sort=False):
        vals=group["score"].to_numpy(dtype=float)
        finite=np.isfinite(vals)
        if finite.any() and (not finite.all() or len(np.unique(vals[finite])) > 1):
            conflicts.append({"ts":str(key[0]),"rfid_time":str(key[1]),"source_ordinals":group["source_ordinal"].astype(int).tolist(),"scores":[None if not np.isfinite(x) else float(x) for x in vals]})
    if conflicts:
        return {"status":"data_conflict","candidate":None,"conflicts":conflicts}
    finite=frame[np.isfinite(pd.to_numeric(frame["score"],errors="coerce"))]
    if finite.empty:
        return {"status":"no_valid_score","candidate":None,"conflicts":[]}
    maximum=float(finite["score"].max())
    winner=finite[finite["score"] == maximum].sort_values("source_ordinal",kind="mergesort").iloc[0]
    return {"status":"candidate","candidate":{"source_ordinal":int(winner["source_ordinal"]),"score":maximum},"conflicts":[]}


def synthetic_checks():
    # Contract tie order: timestamp order differs from original input order; A uses source ordinal.
    rows=pd.DataFrame({"ts":[2,1,1],"rfid_time":[0,0,0],"source_ordinal":[0,1,2],"score":[.9,.9,.9]})
    ordered=order_for_scoring(rows)
    assert ordered.source_ordinal.tolist()==[1,2,0]
    assert choose_a(rows)["candidate"]["source_ordinal"]==0
    conflict=pd.DataFrame({"ts":[1,1],"rfid_time":[0,0],"source_ordinal":[4,5],"score":[.8,.7]})
    assert choose_a(conflict)["status"]=="data_conflict"
    missing=pd.DataFrame({"ts":[1,1],"rfid_time":[0,0],"source_ordinal":[4,5],"score":[.8,np.nan]})
    assert choose_a(missing)["status"]=="data_conflict"
    assert choose_a(missing.assign(score=np.nan))["status"]=="no_valid_score"
    raw_ids=["001","2"]
    train_rids=np.asarray([1,3],dtype=np.int64)
    labels={"001":"A"}
    stub_calls=[]
    def no_train_load_stub(*args,**kwargs):
        stub_calls.append((args,kwargs))
        raise AssertionError("membership helper must not load train rows")
    membership=membership_from_preloaded_ids(raw_ids,train_rids,labels)
    assert membership["raw_ids_in_order"]==raw_ids
    assert membership["numeric_id_lookup"]=={"001":1,"2":2}
    assert membership["label_membership_by_raw_id"]=={"001":True,"2":False}
    assert membership["train_reference_membership_by_raw_id"]=={"001":True,"2":False}
    try:
        membership_from_preloaded_ids(raw_ids,train_rids,labels,train_loader=no_train_load_stub)
    except ValueError:
        pass
    else:
        raise AssertionError("membership input boundary accepted a train loader")
    assert stub_calls==[]
    try:
        numeric_target_ids(["01","1"])
    except ValueError:
        pass
    else:
        raise AssertionError("leading-zero numeric alias collision was not rejected")
    try:
        verify_source_bytes(b"changed", "synthetic source", "0"*64)
    except RuntimeError:
        pass
    else:
        raise AssertionError("AST source hash mismatch was not rejected")
    called=[]
    try:
        assert_reference_fit_partition("test", "test")
    except ValueError:
        pass
    else:
        raise AssertionError("Test reference fit was not blocked")
    def fit_marker(partition):
        called.append(partition)
    assert_reference_fit_partition("train", "train"); fit_marker("train")
    assert called==["train"]
    try:
        build_train_references()
    except RuntimeError as exc:
        assert "separate supervisor" in str(exc)
    else:
        raise AssertionError("reference rebuild ran without a later gate")
    # Output isolation rejects sibling/canonical paths.
    try:
        validate_output_path(HERE.parent / "canonical")
    except ValueError:
        pass
    else:
        raise AssertionError("outside output path was accepted")
    ns, score_hash, remeasure_hash=safe_score_namespace()
    # Small synthetic invocation of the original scorer; no source data/reference is loaded.
    sub=pd.DataFrame({"rfid_id":["synthetic"],"part_dt":["20250101"],"rfid_time":[12],"wkt_valid":[True],
        "cen_lon":[127.0],"cen_lat":[36.0],"len_m":[100.0],"bbox_m":[80.0],"ts":[1],"source_ordinal":[0]})
    out=ns["score_vessel"](sub,lambda lon,lat:np.full(len(lon),np.inf),None,{}, {},lambda x:np.asarray(x)*0,lambda x:np.asarray(x)*0)
    assert len(out)==1 and np.isfinite(out.score.iloc[0]) and out.score.iloc[0]>=1e-6
    assert out.source_ordinal.iloc[0]==0
    haversine_calls=[]
    original_haversine=ns["remeasure"].haversine_m
    def tracked_haversine(*args):
        haversine_calls.append(args)
        return original_haversine(*args)
    ns["remeasure"].haversine_m=tracked_haversine
    sub2=pd.DataFrame({"rfid_id":["synthetic","synthetic"],"part_dt":["20250101","20250101"],"rfid_time":[22,23],"wkt_valid":[True,True],
        "cen_lon":[127.0,127.1],"cen_lat":[36.0,36.0],"len_m":[20.0,20.0],"bbox_m":[20.0,20.0],"ts":[1,2],"source_ordinal":[0,1]})
    out2=ns["score_vessel"](sub2,lambda lon,lat:np.full(len(lon),100000.0),None,{}, {},lambda x:np.asarray(x)*0,lambda x:np.asarray(x)*0)
    assert len(out2)==2 and np.isfinite(out2.score.to_numpy()).all() and len(haversine_calls)>=3
    return {"status":"passed","checks":["time-sort preserves source ordinal","A first maximum by original order","same-timestamp conflicting scores withheld","valid/missing duplicate withheld","all-missing score withheld","Test fit denied before builder call","reference rebuild denied without later gate","output path constrained to execution/","membership uses preloaded train IDs and preserves raw leading-zero ID/order","membership rejects a train loader without calling it","numeric leading-zero alias collision rejected","AST source hash mismatch rejected","original score_vessel invoked with synthetic prior visit/night mooring requiring haversine calls"],"synthetic_score_one_row":float(out.score.iloc[0]),"synthetic_score_two_rows":out2.score.astype(float).tolist(),"haversine_calls_two_row_case":len(haversine_calls),"source_sha256":score_hash,"remeasure_source_sha256":remeasure_hash,"actual_data_scored":False}


def validate_output_path(out: Path):
    out=out.resolve()
    if out != HERE and HERE not in out.parents:
        raise ValueError("Output must remain under this execution directory")
    return out


def main():
    ap=argparse.ArgumentParser(description="Isolated target-row scan and gated scorer namespace preparation")
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--scan", action="store_true", help="scan selected target rows only; bounded batches")
    ap.add_argument("--check-score-namespace", action="store_true", help="AST-load original score function; no scoring")
    ap.add_argument("--self-check", action="store_true", help="small synthetic boundary checks; no actual data scoring")
    args=ap.parse_args(); out=args.out.resolve()
    try: out=validate_output_path(out)
    except ValueError as exc: raise SystemExit(str(exc))
    out.mkdir(parents=True,exist_ok=True)
    receipts={"started_utc":datetime.now(timezone.utc).isoformat(),"cwd":str(Path.cwd()),"output_root":str(out),"batch_size":BATCH,"scan":None,"namespace_check":None}
    if args.scan: receipts["scan"]=scan(out)
    if args.check_score_namespace:
        ns,score_hash,remeasure_hash=safe_score_namespace()
        # Compile-only namespace check: no actual data passed to scorer.
        receipts["namespace_check"]={"score_vessel_loaded":callable(ns.get("score_vessel")),"source_sha256":score_hash,"remeasure_source_sha256":remeasure_hash,"actual_score_call":False}
    if args.self_check: receipts["self_check"]=synthetic_checks()
    if not args.scan and not args.check_score_namespace and not args.self_check: ap.error("select --scan, --check-score-namespace and/or --self-check")
    (out/"scan_result.json").write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(receipts,ensure_ascii=False))

if __name__=="__main__": main()
