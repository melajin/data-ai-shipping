from __future__ import annotations
import ast, hashlib, gc, json, os, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa

from bounded_loader import transform_batches, transform_months, UnsupportedDomain
from isolated_stage import run_testfit, StageDenied, EmptySchemaUnavailable, _atomic_noreplace

ROOT = Path(__file__).resolve().parent
SOURCE = Path(r"D:/repos/fishing-track-classification/code/tools/run_remeasure_20261031.py")
SOURCE_SHA = "5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def rss():
    import ctypes
    class PMC(ctypes.Structure):
        _fields_=[("cb",ctypes.c_ulong),("PageFaultCount",ctypes.c_ulong),("PeakWorkingSetSize",ctypes.c_size_t),("WorkingSetSize",ctypes.c_size_t),("QuotaPeakPagedPoolUsage",ctypes.c_size_t),("QuotaPagedPoolUsage",ctypes.c_size_t),("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),("QuotaNonPagedPoolUsage",ctypes.c_size_t),("PagefileUsage",ctypes.c_size_t),("PeakPagefileUsage",ctypes.c_size_t)]
    i=PMC(); i.cb=ctypes.sizeof(i); k=ctypes.windll.kernel32; p=ctypes.windll.psapi
    k.GetCurrentProcess.restype=ctypes.c_void_p
    p.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(PMC),ctypes.c_ulong]
    p.GetProcessMemoryInfo.restype=ctypes.c_int
    h=k.GetCurrentProcess()
    if not p.GetProcessMemoryInfo(h,ctypes.byref(i),i.cb): raise ctypes.WinError()
    return {"current_working_set_mib":round(i.WorkingSetSize/1048576,2),"peak_working_set_mib":round(i.PeakWorkingSetSize/1048576,2),"pagefile_mib":round(i.PagefileUsage/1048576,2),"peak_pagefile_mib":round(i.PeakPagefileUsage/1048576,2)}

def load_original():
    raw=SOURCE.read_bytes(); actual=hashlib.sha256(raw).hexdigest()
    if actual != SOURCE_SHA: raise RuntimeError(f"pinned canonical hash mismatch: {actual}")
    tree=ast.parse(raw,filename=str(SOURCE))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="load_rows")
    import gc, types, pyarrow.parquet as pq
    ns={"pd":pd,"np":np,"gc":gc,"log":lambda *_:None,"MONTHS":(1,),"pq":types.SimpleNamespace(),"parquet_path":lambda d,m:f"fixture:{d}:{m}"}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),ns)
    return ns["load_rows"]

def table(rows):
    schema=pa.schema([("row_index",pa.int64()),("rfid_id",pa.string()),("part_dt",pa.string()),("rfid_time",pa.int16()),("key_valid",pa.bool_()),("wkt_valid",pa.bool_()),("speed",pa.float64())])
    return pa.Table.from_pylist(rows,schema=schema)

def rows(ids, dates, keys=None, start=0):
    keys=keys or [True]*len(ids)
    return [dict(row_index=start+i,rfid_id=ids[i],part_dt=dates[i],rfid_time=i,wkt_valid=(i%2==0),speed=float(i),key_valid=keys[i]) for i in range(len(ids))]

def frame_for(months, tables, columns, key_only=True):
    original=load_original()
    original.__globals__["pq"].read_table=lambda path,columns:tables[int(path.rsplit(":",1)[1])].select(columns)
    return original("testfit",columns,months=months,key_valid_only=key_only)

def strict_compare(a,b):
    pd.testing.assert_frame_equal(a,b,check_exact=True,check_index_type=True,check_column_type=True,check_frame_type=True,check_names=True)

def stream_frame(months,tables,columns,key_only=True):
    parts=list(transform_months(months,lambda m:tables[m].select([c for c in columns if c!="month"]+([] if "key_valid" in columns else ["key_valid"])).to_batches(max_chunksize=2),columns=columns,key_valid_only=key_only))
    if not parts: return None
    combined=pd.concat(parts,axis=0,copy=False)
    expected_start=0
    contiguous=True
    for part in parts:
        if type(part.index) is not pd.RangeIndex or (len(part) and part.index.tolist()!=list(range(expected_start,expected_start+len(part)))):
            contiguous=False; break
        expected_start+=len(part)
    if contiguous:
        combined.index=pd.RangeIndex(0,len(combined))
    return combined

def cases():
    t1=table(rows(["001","+2","bad",None,"4"],["20250101","20250102","bad","1.5","20250105"],[True,True,True,True,False],0))
    t2=table(rows(["5","6","7"],["20250106","oops","20250108"],[True,True,False],5))
    empty=table([])
    result=[]
    for name,months,tables,cols,keyonly in [
        ("months_and_drops",(1,2),{1:t1,2:t2},["row_index","rfid_id","part_dt","rfid_time","wkt_valid"],True),
        ("request_without_numeric",(1,2),{1:t1,2:t2},["wkt_valid","speed"],True),
        ("id_only",(1,),{1:t1},["rfid_id","key_valid"],True),
        ("date_only",(2,),{2:t2},["part_dt"],False),
        ("no_filter",(1,),{1:t1},["rfid_id","part_dt","key_valid","month"],False),
        ("empty_month",(1,),{1:empty},["row_index","rfid_id","part_dt","wkt_valid"],True),
        ("all_empty",(1,2),{1:empty,2:empty},["row_index","rfid_id","part_dt","wkt_valid"],True),
    ]:
        expected=frame_for(months,tables,cols,keyonly)
        actual=stream_frame(months,tables,cols,keyonly)
        if actual is None:
            # Stream contract is zero yielded frames; materialization is verified through explicit empty_template below.
            assert len(expected)==0
            result.append({"case":name,"pass":True,"stream_parts":0,"materialized_rows":0,
                           "columns":list(expected.columns),"dtypes":{c:str(t) for c,t in expected.dtypes.items()},
                           "index_class":type(expected.index).__name__})
            continue
        strict_compare(expected,actual)
        result.append({"case":name,"pass":True,"rows":len(actual),"columns":list(actual.columns),"dtypes":{c:str(t) for c,t in actual.dtypes.items()},"index_class":type(actual.index).__name__,"index_values":actual.index.tolist()})
    no_drop=table(rows(["1","2"],["20250101","20250102"],start=0))
    a=frame_for((1,),{1:no_drop},["rfid_id","part_dt"])
    b=stream_frame((1,),{1:no_drop},["rfid_id","part_dt"])
    strict_compare(a,b); assert type(a.index) is pd.RangeIndex
    # Drop one post-key-filter numeric row: ordinal hole and pandas Index class must remain.
    hole=table(rows(["1","bad","3"],["20250101","1.5","20250103"],start=0))
    a=frame_for((1,),{1:hole},["rfid_id","part_dt"])
    b=stream_frame((1,),{1:hole},["rfid_id","part_dt"])
    strict_compare(a,b); assert type(a.index) is pd.Index and a.index.tolist()==[0,2]
    result.extend([{"case":"no_drop_range_index","pass":True,"index_class":type(a.index).__name__ if False else "RangeIndex"},{"case":"numeric_drop_hole","pass":True,"index_class":type(b.index).__name__,"index_values":b.index.tolist()}])
    # Empty months must preserve canonical pandas concat exception type/message.
    original=load_original()
    try: original("testfit",["rfid_id"],months=())
    except Exception as oe: original_error=(type(oe).__name__,str(oe))
    try: list(transform_months((),lambda m:(),columns=["rfid_id"]))
    except Exception as ae: adapter_error=(type(ae).__name__,str(ae))
    assert original_error==adapter_error,(original_error,adapter_error)
    result.append({"case":"empty_month_list_error","pass":True,"error":original_error})
    # Prove trace=None retains no event/index collections; capped trace remains bounded.
    trace=[]
    list(transform_batches(no_drop.to_batches(max_chunksize=1),month=1,columns=["rfid_id"],trace=None))
    list(transform_batches(no_drop.to_batches(max_chunksize=1),month=1,columns=["rfid_id"],trace=trace,trace_limit=1))
    assert len(trace)==1 and "output_index" not in trace[0]
    result.append({"case":"trace_bounded","pass":True,"trace_records":len(trace),"trace_fields":list(trace[0])})
    return result

def atomic_cases():
    base=Path(tempfile.mkdtemp(prefix="r005-fixture-"))
    root=base/"allowed"; root.mkdir()
    good=table(rows(["1","2"],["20250101","20250102"],start=0)).to_batches(max_chunksize=1)
    outputs=[]
    success=run_testfit(batches=good,month=1,columns=["rfid_id","part_dt"],allowed_root=root,final_path=root/"success",stage="testfit")
    m=json.loads((root/"success"/"manifest.json").read_text(encoding="utf-8")); assert success["published"] and len(m["files"])==2
    outputs.append({"case":"normal_commit","pass":True,"published":success["published"],"parts":len(m["files"]),"manifest_sha256":sha(root/"success"/"manifest.json")})
    # Rebuild from persisted parts and the manifest's explicit index contract.
    loaded=[]
    for item in m["files"]:
        part=pd.read_parquet(root/"success"/item["name"])
        idx=part.pop("__canonical_index__").to_numpy()
        part.index=pd.Index(idx)
        loaded.append(part)
    rebuilt=pd.concat(loaded,axis=0,copy=False)
    if m["index_range_reconstructable"]:
        rebuilt.index=pd.RangeIndex(0,len(rebuilt))
    expected=frame_for((1,),{1:table(rows(["1","2"],["20250101","20250102"],start=0))},["rfid_id","part_dt"])
    strict_compare(expected,rebuilt)
    outputs[-1]["reconstruction_strict_equal"]=True
    late=table(rows(["1.5"],["20250102"],start=1)).to_batches(max_chunksize=1)
    def mixed():
        yield from table(rows(["1"],["20250101"],start=0)).to_batches(max_chunksize=1)
        yield from late
    for name,batch_iter,exc in [("late_unsupported",mixed(),UnsupportedDomain)]:
        final=root/name
        try: run_testfit(batches=batch_iter,month=1,columns=["rfid_id","part_dt"],allowed_root=root,final_path=final,stage="testfit")
        except exc: pass
        else: raise AssertionError(name+" did not fail")
        assert not final.exists()
        q=list((root/"quarantine").glob("*/receipt.json")); rec=json.loads(q[-1].read_text(encoding="utf-8")); assert rec["quarantined"] and rec["batches"]==1
        outputs.append({"case":name,"pass":True,"final_absent":True,"quarantine_receipt":str(q[-1]),"committed_batches_before_failure":rec["batches"]})
    def err_after_one():
        yield from table(rows(["1"],["20250101"])).to_batches(max_chunksize=1)
        raise RuntimeError("fixture late error")
    final=root/"generic_error"
    try: run_testfit(batches=err_after_one(),month=1,columns=["rfid_id"],allowed_root=root,final_path=final,stage="testfit")
    except RuntimeError: pass
    else: raise AssertionError("generic exception not propagated")
    assert not final.exists(); outputs.append({"case":"late_generic_error","pass":True,"final_absent":True})
    def fail_commit(src,dst): raise OSError("fixture commit failure")
    final=root/"commit_failure"
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=final,stage="testfit",commit=fail_commit)
    except OSError: pass
    else: raise AssertionError("commit failure not propagated")
    assert not final.exists(); outputs.append({"case":"commit_failure","pass":True,"final_absent":True,"quarantine_dirs":len(list((root/"quarantine").iterdir()))})
    def compete(src,dst):
        dst.mkdir(); (dst/"sentinel.txt").write_text("untouched",encoding="utf-8")
        _atomic_noreplace(src,dst)
    final=root/"commit_race"
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=final,stage="testfit",commit=compete)
    except OSError: pass
    else: raise AssertionError("commit race should fail without replacing target")
    assert (final/"sentinel.txt").read_text(encoding="utf-8")=="untouched"
    outputs.append({"case":"commit_target_race_no_clobber","pass":True,"sentinel":"untouched"})
    try: run_testfit(batches=iter([None]),month=1,columns=["rfid_id"],allowed_root=root,final_path=root/"all_none",stage="testfit")
    except EmptySchemaUnavailable: pass
    else: raise AssertionError("schema-less all-None stream was published")
    assert not (root/"all_none").exists(); outputs.append({"case":"all_none_schema_denied","pass":True,"final_absent":True})
    empty_tables={1:table([]),2:table([])}
    empty_expected=frame_for((1,2),empty_tables,["row_index","rfid_id","part_dt","wkt_valid"])
    empty_success=run_testfit(months=(1,2),batches_for_month=lambda m:empty_tables[m].to_batches(),
                              columns=["row_index","rfid_id","part_dt","wkt_valid"],allowed_root=root,
                              final_path=root/"all_empty_with_schema",stage="testfit",empty_template=empty_expected)
    emp_manifest=json.loads((root/"all_empty_with_schema"/"manifest.json").read_text(encoding="utf-8"))
    emp=pd.read_parquet(root/"all_empty_with_schema"/emp_manifest["files"][0]["name"])
    emp_index=emp.pop("__canonical_index__").to_numpy(); emp.index=pd.RangeIndex(0,0) if emp_manifest["index_range_reconstructable"] else pd.Index(emp_index)
    strict_compare(empty_expected,emp)
    outputs.append({"case":"all_empty_canonical_template_commit","pass":True,"rows":0,"columns":list(emp.columns),"dtypes":{c:str(t) for c,t in emp.dtypes.items()},"index_class":type(emp.index).__name__})
    def fail_write(*a,**k): raise OSError("fixture parquet write failure")
    final=root/"write_failure"
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=final,stage="testfit",parquet_writer=fail_write)
    except OSError: pass
    else: raise AssertionError("scratch write failure not propagated")
    assert not final.exists(); outputs.append({"case":"scratch_write_failure","pass":True,"final_absent":True})
    def fail_mkdir(_path): raise OSError("fixture stage create failure")
    final=root/"stage_create_failure"
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=final,stage="testfit",stage_create=fail_mkdir)
    except OSError: pass
    else: raise AssertionError("stage create failure not propagated")
    assert not final.exists(); outputs.append({"case":"stage_create_failure_receipt","pass":True,"final_absent":True})
    existing=root/"already_exists"; existing.mkdir(); sentinel=existing/"sentinel.txt"; sentinel.write_text("preserve",encoding="utf-8")
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=existing,stage="testfit")
    except FileExistsError: pass
    else: raise AssertionError("existing final path accepted")
    assert sentinel.read_text(encoding="utf-8")=="preserve"; outputs.append({"case":"existing_final_unchanged","pass":True,"sentinel":"preserve"})
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=base/"escape",stage="testfit")
    except StageDenied: pass
    else: raise AssertionError("path escape accepted")
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=root/"wrong_stage",stage="train")
    except StageDenied: pass
    else: raise AssertionError("non-testfit stage accepted")
    outputs.extend([{"case":"path_escape_denied_preflight","pass":True},{"case":"non_testfit_denied_preflight","pass":True}])
    for name,cols in [("duplicate_columns",["rfid_id","rfid_id"]),("reserved_index_column",["__canonical_index__"])]:
        try: run_testfit(batches=good,month=1,columns=cols,allowed_root=root,final_path=root/name,stage="testfit")
        except StageDenied: pass
        else: raise AssertionError(name+" accepted")
        outputs.append({"case":name+"_denied","pass":True})
    try: run_testfit(batches=good,month=1,columns=["rfid_id"],allowed_root=root,final_path=root,stage="testfit")
    except StageDenied: pass
    else: raise AssertionError("root directory accepted as final")
    outputs.append({"case":"root_final_denied","pass":True})
    return outputs

def main():
    result={"source":str(SOURCE),"source_sha256":sha(SOURCE),"python":sys.version,"pandas":pd.__version__,"numpy":np.__version__,"pyarrow":pa.__version__,"started_unix":__import__('time').time(),"rss_before":rss()}
    result["frame_contract_cases"]=cases()
    result["atomic_cases"]=atomic_cases()
    result["rss_after"]=rss()
    result["process_peak_rss_mib"]=result["rss_after"]["peak_working_set_mib"]
    out=ROOT/"fixture_result.json"; out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"frame_cases":len(result["frame_contract_cases"]),"atomic_cases":len(result["atomic_cases"]),"all_pass":True,"peak_rss_mib":result["process_peak_rss_mib"]},ensure_ascii=False))

if __name__=="__main__":
    try: main()
    except Exception:
        traceback.print_exc(); raise
