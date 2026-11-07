from __future__ import annotations
import ast, gc, hashlib, json, types, os, ctypes
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

OUT=Path(__file__).resolve().parent
SOURCE=Path(r"D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py")
SOURCE_SHA="5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c"
PARQUET=Path(r"D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/분석 결과/outputs/remeasure_20261031/rows_train_1.parquet")
if not PARQUET.exists(): PARQUET=Path(r"D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/29-30일 모델 심층 분석/分析 결과/outputs/remeasure_20261031/rows_train_1.parquet")
SAMPLE_N=16384
BATCH=4096
SAMPLE_COLS=["row_index","rfid_id","part_dt","rfid_time","key_valid","wkt_valid","len_m","bbox_m","cen_lon","cen_lat"]

def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()

def rss_snapshot():
 class PMC(ctypes.Structure):
  _fields_=[("cb",ctypes.c_ulong),("PageFaultCount",ctypes.c_ulong),("PeakWorkingSetSize",ctypes.c_size_t),("WorkingSetSize",ctypes.c_size_t),("QuotaPeakPagedPoolUsage",ctypes.c_size_t),("QuotaPagedPoolUsage",ctypes.c_size_t),("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),("QuotaNonPagedPoolUsage",ctypes.c_size_t),("PagefileUsage",ctypes.c_size_t),("PeakPagefileUsage",ctypes.c_size_t)]
 info=PMC(); info.cb=ctypes.sizeof(info)
 get_current=ctypes.windll.kernel32.GetCurrentProcess
 get_current.restype=ctypes.c_void_p
 get_info=ctypes.windll.psapi.GetProcessMemoryInfo
 get_info.argtypes=[ctypes.c_void_p,ctypes.POINTER(PMC),ctypes.c_ulong]
 get_info.restype=ctypes.c_int
 ok=get_info(get_current(),ctypes.byref(info),info.cb)
 if not ok: return {"error":"GetProcessMemoryInfo failed"}
 return {"current_working_set_mib":round(info.WorkingSetSize/1048576,2),"peak_working_set_mib":round(info.PeakWorkingSetSize/1048576,2),"pagefile_mib":round(info.PagefileUsage/1048576,2),"peak_pagefile_mib":round(info.PeakPagefileUsage/1048576,2)}

def extract_loader():
 payload=SOURCE.read_bytes(); actual=hashlib.sha256(payload).hexdigest()
 if actual!=SOURCE_SHA: raise RuntimeError("canonical SHA mismatch: "+actual)
 tree=ast.parse(payload,filename=str(SOURCE)); fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="load_rows")
 ns={"pd":pd,"np":np,"gc":gc,"log":lambda *_:None,"MONTHS":(1,),"pq":types.SimpleNamespace(),"parquet_path":lambda d,m:Path("injected:%s:%s"%(d,m))}
 exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),ns)
 return ns["load_rows"]

def compare(a,b):
 ce=list(a.columns)==list(b.columns); re=len(a)==len(b); ve=ce and re and a.equals(b); first=None
 if ce and re and not ve:
  for col in a:
   neq=~((a[col].eq(b[col]))|(a[col].isna()&b[col].isna()))
   if bool(neq.any()):
    i=int(np.flatnonzero(neq.to_numpy())[0]); first={"position":i,"index":str(a.index[i]),"column":col,"original":repr(a.iloc[i][col]),"adapter":repr(b.iloc[i][col])}; break
 return {"columns_equal":ce,"rows_equal":re,"index_equal":a.index.equals(b.index),"dtypes_equal":a.dtypes.equals(b.dtypes),"values_nan_equal":ve,
 "original_columns":list(a.columns),"original_dtypes":{c:str(x) for c,x in a.dtypes.items()},"adapter_dtypes":{c:str(x) for c,x in b.dtypes.items()},"first_mismatch":first,
 "original_index":a.index.tolist(),"adapter_index":b.index.tolist()}

def records(ids,dates,keys=None,start=0):
 keys=keys if keys is not None else [True]*len(ids)
 return [dict(row_index=start+i,rfid_id=ids[i],part_dt=dates[i],rfid_time=i%24,key_valid=keys[i],wkt_valid=True,len_m=float(i),bbox_m=float(i),cen_lon=120+i/100000,cen_lat=30+i/100000) for i in range(len(ids))]

def arrow(recs):
 data={k:[r.get(k) for r in recs] for k in recs[0]}
 schema=pa.schema([("row_index",pa.int64()),("rfid_id",pa.string()),("part_dt",pa.string()),("rfid_time",pa.int16()),("key_valid",pa.bool_()),("wkt_valid",pa.bool_()),("len_m",pa.float64()),("bbox_m",pa.float64()),("cen_lon",pa.float64()),("cen_lat",pa.float64())])
 return pa.table(data,schema=schema)

def fixture(key_only):
 from bounded_loader import transform_batches
 r1=records(["001","+2","-0003",None,"bad","9007199254740992","-9007199254740992"],["20250101","20250102","20250103","1.5","20250105","-2147483648","2147483647"],[True,True,True,True,False,True,True],0)
 r2=records(["4","5",None,"6","NaN"],["20250108","oops","1.5",None,"20250115"],[False,True,True,True,True],7)
 r3=records(["+0007","bad","8","10"],["20250109","1.5","20250111","NaN"],[True,True,True,True],12)
 r4=records(["9","10"],["20250112","20250113"],[True,False],14)
 tables={1:arrow(r1+r2),2:arrow(r3+r4)}
 batches={m:tables[m].to_batches(max_chunksize=3)+[pa.record_batch({c:pa.array([],type=tables[m].schema.field(c).type) for c in tables[m].column_names})] for m in tables}
 original=extract_loader(); original.__globals__["pq"].read_table=lambda p,columns:tables[int(str(p).rsplit(":",1)[1])].select(columns)
 cols=["row_index","rfid_id","part_dt","rfid_time","wkt_valid"]
 expected=original("train",cols,months=(1,2),key_valid_only=key_only)
 out=[]; trace=[]; offset=0
 for month in (1,2):
  parts=list(transform_batches(batches[month],month=month,columns=cols,key_valid_only=key_only,first_concat_ordinal=offset,trace=trace)); out.extend(parts)
  offset+=sum(b.num_rows if not key_only else int(b.column("key_valid").to_pandas().sum()) for b in batches[month])
 actual=pd.concat(out) if out else expected.iloc[:0].copy()
 c=compare(expected,actual); c.update({"case":"key_valid_only="+str(key_only),"batch_trace":trace,"canonical_ids":expected.rfid_id.astype(str).tolist()})
 return c

def reject(token,field="rfid_id"):
 from bounded_loader import transform_batches,UnsupportedDomain
 r=records([token if field=="rfid_id" else "1"],[token if field=="part_dt" else "20250101"])
 try: list(transform_batches(arrow(r).to_batches(max_chunksize=1),month=1,columns=["rfid_id","part_dt"],trace=[])); return {"token":token,"field":field,"stopped":False}
 except UnsupportedDomain as e: return {"token":token,"field":field,"stopped":True,"reason":str(e)}

def api_contract_cases():
 from bounded_loader import transform_months
 t1=arrow(records(["1.5",None],["1e3","oops"],start=20))
 t2=arrow(records(["+2"],["20250102"],start=22))
 loader=extract_loader(); loader.__globals__["pq"].read_table=lambda p,columns:{1:t1,2:t2}[int(str(p).rsplit(":",1)[1])].select(columns)
 expected=loader("train",["wkt_valid"],months=(1,2),key_valid_only=True)
 actual=pd.concat(list(transform_months((1,2),lambda m:{1:t1,2:t2}[m].to_batches(max_chunksize=1),columns=["wkt_valid"])))
 cmp=compare(expected,actual)
 empty_original=extract_loader();
 try: empty_original("train",["rfid_id"],months=()); orig_error=None
 except Exception as e: orig_error={"type":type(e).__name__,"message":str(e)}
 try: list(transform_months((),lambda _m:(),columns=["rfid_id"])); adapter_error=None
 except Exception as e: adapter_error={"type":type(e).__name__,"message":str(e)}
 return {"request_without_numeric_keys":{"requested":["wkt_valid"],"comparison":cmp,"returned_columns":list(actual.columns),"dtypes":{c:str(t) for c,t in actual.dtypes.items()},"unsupported_numeric_tokens_were_not_examined":True},
         "empty_months":{"original_error":orig_error,"adapter_error":adapter_error,"equal":orig_error==adapter_error}}

def actual_sample():
 if not PARQUET.exists(): raise FileNotFoundError(str(PARQUET))
 pf=pq.ParquetFile(PARQUET); raw=[]; have=0; reads=0
 for rb in pf.iter_batches(batch_size=BATCH,columns=SAMPLE_COLS):
  take=min(rb.num_rows,SAMPLE_N-have)
  if take: raw.append(rb.slice(0,take)); have+=take
  reads+=1
  if have==SAMPLE_N: break
 if have!=SAMPLE_N: raise RuntimeError("sample row count %d"%have)
 injected=pa.Table.from_batches(raw); original=extract_loader(); original.__globals__["pq"].read_table=lambda p,columns:injected.select(columns)
 cols=["rfid_id","part_dt","rfid_time","wkt_valid","len_m","bbox_m","cen_lon","cen_lat"]
 expected=original("train",cols,months=(1,),key_valid_only=True)
 from bounded_loader import transform_batches
 out=[]; trace=[]; offset=0; source_offset=0
 for bi,rb in enumerate(raw):
  parts=list(transform_batches([rb],month=1,columns=cols,key_valid_only=True,first_concat_ordinal=offset,trace=trace)); out.extend(parts)
  offset+=int(rb.column("key_valid").to_pandas().sum())
  trace[-1].update({"source_batch_number":bi,"source_row_offset":source_offset,"source_row_index_first_last":[int(rb.column("row_index")[0].as_py()),int(rb.column("row_index")[-1].as_py())]}); source_offset+=rb.num_rows
 actual=pd.concat(out) if out else expected.iloc[:0].copy(); c=compare(expected,actual)
 return {"scope":{"parquet":str(PARQUET),"parquet_sha256":sha(PARQUET),"month":1,"selection":"first 16,384 physical input rows; projected required columns","selected_rows":have,"input_batch_size_limit":BATCH,"parquet_read_batch_calls":reads,"adapter_transform_batches_calls":len(raw),"full_loader_called":False},"comparison":c,"batch_trace":trace,
 "original_output_sha256":hashlib.sha256(expected.to_csv(index=True).encode()).hexdigest(),"adapter_output_sha256":hashlib.sha256(actual.to_csv(index=True).encode()).hexdigest(),"excluded_concat_indices":sorted(set(range(offset))-set(actual.index.tolist()))}

def main():
 from bounded_loader import transform_batches
 rss={"process_start":rss_snapshot()}
 result={"canonical_source":str(SOURCE),"canonical_source_sha256":sha(SOURCE),"versions":{"pandas":pd.__version__,"numpy":np.__version__,"pyarrow":pa.__version__},
 "fixtures":[fixture(True),fixture(False)],"unsupported":[reject("9007199254740993"),reject("-9007199254740993"),reject("1.5"),reject("1e3"),reject(" 2"),reject("2 "),reject("9"*129),reject("2147483648","part_dt"),reject("9223372036854775808")]}
 result["api_contract_cases"]=api_contract_cases()
 try: result["actual_sample"]=actual_sample()
 except Exception as exc: result["actual_sample"]={"stopped":True,"error_type":type(exc).__name__,"error":str(exc),"partial_scope":"actual sample halted at first unsupported domain value"}
 rss["after_actual_sample"]=rss_snapshot()
 one=arrow(records(["01",None],["20250101","20250102"]))
 single=list(transform_batches(one.to_batches(max_chunksize=1),month=1,columns=["rfid_id"]))
 result["missing_column_request"]={"requested":["rfid_id"],"returned_columns":list(single[0].columns),"dtypes":{k:str(v) for k,v in single[0].dtypes.items()}}
 result["rss_observed"]=rss
 (OUT/"comparison_result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"fixture_equal":[all(x[k] for k in ("columns_equal","rows_equal","index_equal","dtypes_equal","values_nan_equal")) for x in result["fixtures"]],"unsupported_stopped":[x["stopped"] for x in result["unsupported"]],"actual_equal":False if result["actual_sample"].get("stopped") else all(result["actual_sample"]["comparison"][k] for k in ("columns_equal","rows_equal","index_equal","dtypes_equal","values_nan_equal")),"actual_stop":result["actual_sample"].get("error"),"actual_transform_calls":None if result["actual_sample"].get("stopped") else result["actual_sample"]["scope"]["adapter_transform_batches_calls"]},ensure_ascii=False))
 if not all(all(x[k] for k in ("columns_equal","rows_equal","index_equal","dtypes_equal","values_nan_equal")) for x in result["fixtures"]): return 2
 if not all(x["stopped"] for x in result["unsupported"]): return 3
 if not result["api_contract_cases"]["empty_months"]["equal"]: return 6
 if not all(result["api_contract_cases"]["request_without_numeric_keys"]["comparison"][k] for k in ("columns_equal","rows_equal","index_equal","dtypes_equal","values_nan_equal")): return 7
 if result["actual_sample"].get("stopped"): return 5
 if not all(result["actual_sample"]["comparison"][k] for k in ("columns_equal","rows_equal","index_equal","dtypes_equal","values_nan_equal")): return 4
 return 0

if __name__=="__main__": raise SystemExit(main())
