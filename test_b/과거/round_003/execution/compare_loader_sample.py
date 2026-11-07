from __future__ import annotations
import ast, gc, hashlib, json, sys, types
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = Path(r"D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py")
SOURCE_SHA = "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c"
PARQUET = Path(r"D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/分析 결과/outputs/remeasure_20261031/rows_train_1.parquet")
if not PARQUET.exists():
    PARQUET = Path(r"D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/outputs/remeasure_20261031/rows_train_1.parquet")
EXPECTED_ROWS = 16384
COLUMNS = ["row_index", "rfid_id", "part_dt", "rfid_time", "key_valid", "wkt_valid", "len_m", "bbox_m", "cen_lon", "cen_lat"]

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def extract_original_loader():
    source=SOURCE.read_bytes()
    actual=hashlib.sha256(source).hexdigest()
    if actual != SOURCE_SHA: raise RuntimeError(f"source hash mismatch {actual}")
    tree=ast.parse(source, filename=str(SOURCE))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="load_rows")
    module=ast.Module(body=[node],type_ignores=[])
    ns={"pd":pd,"np":np,"gc":gc,"log":lambda *_:None,"MONTHS":(1,),"pq":types.SimpleNamespace(),"parquet_path":lambda d,m:Path(f"injected:{d}:{m}")}
    exec(compile(module,str(SOURCE),"exec"),ns)
    return ns["load_rows"]

def compare_frames(a,b):
    findings={"columns_equal":list(a.columns)==list(b.columns),"row_count_equal":len(a)==len(b),"dtypes_original":{k:str(v) for k,v in a.dtypes.items()},"dtypes_bounded":{k:str(v) for k,v in b.dtypes.items()},"dtypes_equal":a.dtypes.equals(b.dtypes),"values_equal":bool(a.equals(b)),"nan_equal":True,"first_mismatch":None}
    if findings["columns_equal"] and len(a)==len(b):
        for col in a:
            neq=~((a[col].eq(b[col])) | (a[col].isna() & b[col].isna()))
            if neq.any():
                i=int(np.flatnonzero(neq.to_numpy())[0]); findings["first_mismatch"]={"column":col,"row":i,"original":str(a.iloc[i][col]),"bounded":str(b.iloc[i][col])}; findings["nan_equal"]=False; break
    return findings

def main():
    # Safe injection: the extracted canonical loader receives a table containing
    # only the first 16,384 train rows; its canonical whole-dataset path is never called.
    pf=pq.ParquetFile(PARQUET)
    batches=[]; have=0
    for rb in pf.iter_batches(batch_size=8192,columns=COLUMNS):
        take=min(rb.num_rows,EXPECTED_ROWS-have)
        if take:
            batches.append(rb.slice(0,take)); have+=take
        if have==EXPECTED_ROWS: break
    if have!=EXPECTED_ROWS: raise RuntimeError(f"sample rows found {have}")
    injected=pa.Table.from_batches(batches)
    orig=extract_original_loader()
    orig.__globals__["pq"].read_table=lambda path,columns: injected.select(columns)
    original=orig("train",COLUMNS,months=(1,),key_valid_only=True)
    from bounded_loader import transform_batch
    bounded=transform_batch(injected,month=1,columns=COLUMNS,key_valid_only=True)
    actual={"sample_scope":{"source":str(PARQUET),"source_sha256":sha(PARQUET),"month":1,"selection":"first 16,384 row_index-ordered rows from ParquetFile.iter_batches(8192), columns projected exactly as listed","selected_input_rows":have,"canonical_full_load_rows_called":False},"comparison":compare_frames(original,bounded)}
    input_rows=set(injected.column("row_index").to_pylist())
    original_rows=set(original.row_index.to_list()); bounded_rows=set(bounded.row_index.to_list())
    actual["comparison"]["excluded_source_row_indices_original"]=sorted(input_rows-original_rows)
    actual["comparison"]["excluded_source_row_indices_bounded"]=sorted(input_rows-bounded_rows)
    actual["comparison"]["excluded_sets_equal"]=(input_rows-original_rows)==(input_rows-bounded_rows)
    del original,bounded,injected,batches; gc.collect()
    # Boundary fixture checks per-batch inference against canonical whole-series conversion.
    from bounded_loader import transform_batch as bounded_transform
    boundary=pa.table({"rfid_id":["001","+2","9223372036854775808",None,"bad","3","9007199254740993","1.5"],"part_dt":["20250101","20250102","20250103","20250104","20250105","2147483648","20250106","20250107"],"key_valid":[True,True,True,True,False,True,True,True]})
    batch1=boundary.slice(0,2); batch2=boundary.slice(2,2); batch3=boundary.slice(4,2); batch4=boundary.slice(6,1); batch5=boundary.slice(7,1)
    # Do not force the invalid year/day through cast? canonical only checks numeric coercibility.
    whole=boundary.to_pandas(); whole=whole[whole.key_valid].copy(); whole["month"]=np.int8(1); whole=whole[["rfid_id","part_dt","key_valid","month"]]
    ni=pd.to_numeric(whole.rfid_id,errors="coerce"); good=ni.notna(); whole=whole.loc[good].copy(); ni=ni.loc[good]; whole["rfid_id"]=ni.astype(np.int64)
    nd=pd.to_numeric(whole.part_dt,errors="coerce"); good=nd.notna(); whole=whole.loc[good].copy(); nd=nd.loc[good]; whole["part_dt"]=nd.astype(np.int32)
    bparts=[]; errors=[]
    for rb in (batch1,batch2,batch3,batch4,batch5):
        try: bparts.append(bounded_transform(rb,month=1,columns=["rfid_id","part_dt","key_valid"]))
        except Exception as e: errors.append(type(e).__name__+":"+str(e))
    actual["boundary_fixture"]={"values":{"rfid_id":["001","+2","9223372036854775808",None,"bad","3","9007199254740993","1.5"],"part_dt":["20250101","20250102","20250103","20250104","20250105","2147483648","20250106","20250107"],"key_valid":[True,True,True,True,False,True,True,True]},"original_whole":{"rows":len(whole),"dtypes":{k:str(v) for k,v in whole.dtypes.items()},"ids":whole.rfid_id.astype(str).tolist(),"dates":whole.part_dt.astype(str).tolist()},"bounded_errors":errors,"batch_count":5,"interpretation":"boundary fixture highlights conversion/overflow and cross-batch inference behavior; it is not production equivalence proof"}
    if bparts:
        try:
            bb=pd.concat(bparts,ignore_index=True); wi=whole.reset_index(drop=True); bi=bb.reset_index(drop=True); actual["boundary_fixture"]["bounded_concat"]={"rows":len(bb),"dtypes":{k:str(v) for k,v in bb.dtypes.items()},"ids":bb.rfid_id.astype(str).tolist(),"dates":bb.part_dt.astype(str).tolist(),"equal_after_reset_index":bool(wi.equals(bi)),"first_value_difference":{"original_id":str(wi.rfid_id.iloc[4]),"bounded_id":str(bi.rfid_id.iloc[4])} if len(wi)>4 and len(bi)>4 and wi.rfid_id.iloc[4]!=bi.rfid_id.iloc[4] else None}
        except Exception as e: actual["boundary_fixture"]["bounded_concat_error"]=type(e).__name__+":"+str(e)
    (OUT/"sample_comparison.json").write_text(json.dumps(actual,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(actual,ensure_ascii=False))
    if not actual["comparison"]["values_equal"] or not actual["comparison"]["dtypes_equal"]: return 2
    if not actual["boundary_fixture"].get("bounded_concat",{}).get("equal_after_reset_index",False): return 2
    return 0

if __name__=="__main__": raise SystemExit(main())
