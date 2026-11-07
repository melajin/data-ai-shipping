from __future__ import annotations
import csv, gc, hashlib, io, json, math, pickle, platform, re, sys, time, zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/"testB"/"round_001"/"audit"/"v2_id_recheck_001"
ZIP_PATH=Path.home()/"Downloads"/"문제 데이터_수정_1103_v2.zip"
OLD_XLSX=next(p for p in Path("F:/").glob("*1027*/*/*") if p.is_file() and p.suffix.lower()==".xlsx" and p.stat().st_size<20000)
INTAKE=ROOT/"testB"/"intake"/"1103_v2"/"inspection_001"
ARCHIVE_MANIFEST=INTAKE/"archive_manifest.json"
EXTRACTED=INTAKE/"reference_02_제출샘플.xlsx"
CACHE=Path(r"D:\repos\fishing-track-classification\results\work_008\scored_rows.pkl")
SUBMISSION=Path(r"D:\repos\fishing-track-classification\results\submission_20261101\testB_submission.csv")
PARQUET_DIR=next(ROOT.glob("*29-30*/*/outputs/remeasure_20261031"))
PARSE_MANIFESTS=sorted(PARQUET_DIR.glob("parse_test_*.json"))

def digest(data): return hashlib.sha256(data).hexdigest()
def file_sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def json_write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
def csv_write(path,records,fields):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(records)
def ram_snapshot():
    import ctypes
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_=[("dwLength",ctypes.c_ulong),("dwMemoryLoad",ctypes.c_ulong),("ullTotalPhys",ctypes.c_ulonglong),("ullAvailPhys",ctypes.c_ulonglong),("ullTotalPageFile",ctypes.c_ulonglong),("ullAvailPageFile",ctypes.c_ulonglong),("ullTotalVirtual",ctypes.c_ulonglong),("ullAvailVirtual",ctypes.c_ulonglong),("ullAvailExtendedVirtual",ctypes.c_ulonglong)]
    m=MEMORYSTATUSEX();m.dwLength=ctypes.sizeof(m)
    ok=ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {"observed_local":datetime.now().astimezone().isoformat(),"available_bytes":int(m.ullAvailPhys) if ok else None,"total_bytes":int(m.ullTotalPhys) if ok else None,"load_percent":int(m.dwMemoryLoad) if ok else None}
def val_info(v):
    if v is None: raw=""
    elif isinstance(v,float) and math.isnan(v): raw="NaN"
    else: raw=str(v)
    trimmed=raw.strip() if isinstance(v,str) else raw
    safe=None
    if isinstance(v,bool): pass
    elif isinstance(v,int): safe=str(v)
    elif isinstance(v,float) and math.isfinite(v) and v.is_integer(): safe=str(int(v))
    elif isinstance(v,str) and re.fullmatch(r"[0-9]+",trimmed):
        # Never normalize a leading zero away.
        if trimmed=="0" or not trimmed.startswith("0"): safe=str(int(trimmed))
    key=safe if safe is not None else trimmed
    return raw,trimmed,safe,key,not bool(trimmed)
def norm_id(v): return val_info(v)[3]
def inspect_workbook(source,stream):
    wb=load_workbook(stream,read_only=True,data_only=True)
    sheets=list(wb.sheetnames); info={"sheet_names_in_order":sheets,"sheets":{}}
    out={}
    for sn in sheets:
        ws=wb[sn]; a1=ws["A1"].value
        clean=re.sub(r"\s+","",sn).casefold()
        kind="A" if ("testa" in clean or "테스트a" in clean) else ("B" if ("testb" in clean or "테스트b" in clean) else None)
        info["sheets"][sn]={"A1_value":a1,"A1_type":type(a1).__name__,"max_row":ws.max_row,"max_column":ws.max_column,"selected_as":kind}
        if kind:
            ids=[]; records=[]
            for r in range(2,102):
                cell=ws.cell(r,1); raw,trim,safe,key,blank=val_info(cell.value)
                records.append({"source":source,"sheet":sn,"cell":cell.coordinate,"raw_value":raw,"raw_type":type(cell.value).__name__,"trimmed_value":trim,"safe_integer_normalized":safe or "","comparison_key":key,"blank":blank})
                ids.append({"raw":cell.value,"key":key,"blank":blank,"row":r,"type":type(cell.value).__name__})
            out[kind]={"rows":ids,"records":records,"header":a1,"sheet":sn}
    wb.close()
    return info,out
def list_summary(group):
    ids=[x["key"] for x in group["rows"] if not x["blank"]]; freq=Counter(ids)
    return {"sheet":group.get("sheet"),"header_A1":group.get("header"),"data_rows":len(group["rows"]),"nonblank_rows":len(ids),"blank_rows":sum(x["blank"] for x in group["rows"]),"unique_ids":len(freq),"duplicate_id_values":{k:v for k,v in freq.items() if v>1},"value_types":dict(Counter(x["type"] for x in group["rows"])),"first_5_raw":[{"row":x["row"],"type":x["type"],"raw":x["raw"],"comparison_key":x["key"]} for x in group["rows"][:5]]}
def group_from_records(sid,selected):
    return {"source":sid,"sheet":selected["sheet"],"header":selected["header"],"rows":selected["rows"],"records":selected["records"]}
def compare_pair(name,left,right):
    a={x["key"] for x in left["rows"] if not x["blank"]}; b={x["key"] for x in right["rows"] if not x["blank"]}
    return {"comparison":name,"left_rows":len(left["rows"]),"right_rows":len(right["rows"]),"left_unique":len(a),"right_unique":len(b),"intersection_count":len(a&b),"left_only_count":len(a-b),"right_only_count":len(b-a),"intersection_ids":";".join(sorted(a&b)),"left_only_ids":";".join(sorted(a-b)),"right_only_ids":";".join(sorted(b-a))}
def csv_ids(path):
    with path.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    if not rows or "rfid_id" not in rows[0]: raise ValueError("submission CSV has no rfid_id header")
    ids=[r["rfid_id"] for r in rows]
    return {"rows":[{"raw":x,"key":norm_id(x),"blank":not bool(x.strip()),"type":"str","row":i+2} for i,x in enumerate(ids)],"header":list(rows[0]),"row_count":len(rows)}
def main():
    started=datetime.now().astimezone().isoformat()
    zip_stat=lambda:{"size_bytes":ZIP_PATH.stat().st_size,"mtime_ns":ZIP_PATH.stat().st_mtime_ns}
    input_paths=[OLD_XLSX,EXTRACTED,ARCHIVE_MANIFEST,CACHE,SUBMISSION,*PARSE_MANIFESTS]
    archive_before=zip_stat() # Metadata only; do not rehash the large archive.
    pre={str(p):{"exists":p.is_file(),"size_bytes":p.stat().st_size if p.is_file() else None,"mtime_ns":p.stat().st_mtime_ns if p.is_file() else None,"sha256":file_sha(p) if p.is_file() else None} for p in input_paths}
    manifest=json.loads(ARCHIVE_MANIFEST.read_text(encoding="utf-8-sig"))
    member_matches=[]
    with zipfile.ZipFile(ZIP_PATH,"r") as zf:
        for zi in zf.infolist():
            if zi.filename.endswith("제출샘플.xlsx") and not zi.is_dir():
                data=zf.read(zi) # Read only the selected small member.
                member_matches.append((zi,data))
    if len(member_matches)!=1: raise RuntimeError(f"expected exactly one submission sample member, got {len(member_matches)}")
    zi,member_bytes=member_matches[0]
    entry=next((e for e in manifest.get("entries",[]) if e.get("name")==zi.filename),None)
    if entry is None: raise RuntimeError("ZIP sample member missing from archive manifest")
    extracted_bytes=EXTRACTED.read_bytes()
    member_sha=digest(member_bytes); extracted_sha=digest(extracted_bytes)
    manifest_copy_ok=(Path(entry.get("extracted_reference_path","")).resolve()==EXTRACTED.resolve() and entry.get("uncompressed_bytes")==len(member_bytes) and entry.get("new_sha256")==member_sha and entry.get("zip_crc32","").lower()==f"{zi.CRC:08x}" and member_bytes==extracted_bytes)
    zinfo={"archive_path":str(ZIP_PATH),"archive_metadata_before":archive_before,"member":zi.filename,"member_uncompressed_bytes":zi.file_size,"member_compressed_bytes":zi.compress_size,"member_crc32":f"{zi.CRC:08x}","member_sha256":member_sha,"intake_copy_sha256":extracted_sha,"manifest_entry":entry,"member_matches_intake_copy_and_manifest":manifest_copy_ok}
    old_info,old_groups=inspect_workbook("old_F_sample",OLD_XLSX)
    new_info,new_groups=inspect_workbook("new_zip_member",io.BytesIO(member_bytes))
    intake_info,intake_groups=inspect_workbook("new_intake_copy",io.BytesIO(extracted_bytes))
    groups={}
    for source,inspected in (("old",old_groups),("new",new_groups),("intake",intake_groups)):
        for kind,g in inspected.items(): groups[source+kind]=group_from_records(source+"_"+kind,g)
    groups["submission"]=csv_ids(SUBMISSION)
    id_records=[]
    for group in groups.values():
        if "records" in group: id_records.extend(group["records"])
        else:
            for x in group["rows"]:
                raw,trim,safe,key,blank=val_info(x["raw"])
                id_records.append({"source":"existing_submission_csv","sheet":"CSV","cell":f"rfid_id row {x['row']}","raw_value":raw,"raw_type":x["type"],"trimmed_value":trim,"safe_integer_normalized":safe or "","comparison_key":x["key"],"blank":blank})
    # Check available RAM immediately before loading the compact historical pickle.
    ram_cache=ram_snapshot(); expected_pickle_peak=200*1024*1024
    cache_status="not_loaded_low_ram"
    cache_meta={"path":str(CACHE),"size_bytes":CACHE.stat().st_size,"expected_peak_bytes":expected_pickle_peak,"ram_before_load":ram_cache}
    if ram_cache["available_bytes"] is not None and ram_cache["available_bytes"]>=max(512*1024*1024,expected_pickle_peak*2):
        with CACHE.open("rb") as f: obj=pickle.load(f)
        obj_type=type(obj).__name__; cache_rows=None
        if hasattr(obj,"columns"):
            cache_rows=int(len(obj))
            if "rfid_id" in obj.columns: vals=obj["rfid_id"].dropna().unique().tolist()
            elif getattr(obj.index,"name",None)=="rfid_id": vals=obj.index.unique().tolist()
            else: raise RuntimeError(f"cache object has no rfid_id key column/index; cols={list(obj.columns)}")
        elif isinstance(obj,dict):
            # This pickle is keyed by vessel ID; inspect only the top-level key set.
            vals=list(obj.keys()); cache_rows=None
        else: raise RuntimeError(f"unrecognized cache object for key-only read: {obj_type}")
        unique_map={norm_id(x):x for x in vals if not val_info(x)[4]}
        groups["score_cache"]={"rows":[{"raw":raw,"key":key,"blank":False,"type":type(raw).__name__,"row":""} for key,raw in unique_map.items()],"sheet":"cache keys","header":"rfid_id"}
        for key,raw in unique_map.items():
            raw_s,trim,safe,_,blank=val_info(raw)
            id_records.append({"source":"scored_rows.pkl_unique_key","sheet":"cache","cell":"","raw_value":raw_s,"raw_type":type(raw).__name__,"trimmed_value":trim,"safe_integer_normalized":safe or "","comparison_key":key,"blank":blank})
        cache_status="loaded_keys_only"
        cache_meta.update({"object_type":obj_type,"row_count":cache_rows,"container_key_role":"top-level vessel IDs (values were not traversed)","key_column":"rfid_id","unique_key_count":len(unique_map),"key_value_types":dict(Counter(type(x).__name__ for x in vals))})
        del obj; gc.collect()
    else:
        cache_meta["reason"]="available RAM below conservative 512 MiB minimum; cache ID comparison deferred"
    compare_rows=[]
    pairs=[("oldB_vs_newB","oldB","newB"),("oldA_vs_newA","oldA","newA"),("oldA_vs_newB","oldA","newB"),("oldB_vs_newA","oldB","newA"),("newB_vs_intakeB","newB","intakeB"),("oldB_vs_submission_csv","oldB","submission"),("newB_vs_submission_csv","newB","submission")]
    if cache_status=="loaded_keys_only": pairs += [("oldB_vs_score_cache_keys","oldB","score_cache"),("newB_vs_score_cache_keys","newB","score_cache")]
    for name,a,b in pairs: compare_rows.append(compare_pair(name,groups[a],groups[b]))
    if cache_status!="loaded_keys_only":
        compare_rows += [{"comparison":"oldB_vs_score_cache_keys","status":"unknown_cache_not_read"},{"comparison":"newB_vs_score_cache_keys","status":"unknown_cache_not_read"}]
    oldb=groups["oldB"]["rows"]; newb=groups["newB"]["rows"]
    raw_row_matches=sum(1 for a,b in zip(oldb,newb) if not a["blank"] and not b["blank"] and a["raw"]==b["raw"])
    norm_row_matches=sum(1 for a,b in zip(oldb,newb) if not a["blank"] and not b["blank"] and a["key"]==b["key"])
    # Other required work is complete; check RAM again immediately before optional parquet coverage.
    ram_parquet=ram_snapshot(); expected_parquet_peak=256*1024*1024
    parquet_files=sorted(PARQUET_DIR.glob("rows_test_*.parquet"))
    parquet_result={"status":"not_run_low_ram","cache_dir":str(PARQUET_DIR),"file_count":len(parquet_files),"expected_peak_bytes":expected_parquet_peak,"ram_before_scan":ram_parquet,"files":[]}
    target_new={x["key"] for x in groups["newB"]["rows"] if not x["blank"]}
    parquet_hash_pre={str(p):{"size_bytes":p.stat().st_size,"sha256":file_sha(p)} for p in parquet_files}
    if ram_parquet["available_bytes"] is not None and ram_parquet["available_bytes"]>=max(768*1024*1024,expected_parquet_peak*2):
        import pyarrow.parquet as pq
        present=set(); total=0; cache_unique=set()
        for p in parquet_files:
            pf=pq.ParquetFile(p); file_rows=0; file_keys=set(); file_hits=set()
            for batch in pf.iter_batches(batch_size=65536,columns=["rfid_id"]):
                vals=batch.column(0).to_pylist(); file_rows+=len(vals); total+=len(vals)
                for v in vals:
                    if v is not None:
                        k=norm_id(v); file_keys.add(k)
                        if k in target_new: present.add(k); file_hits.add(k)
            cache_unique.update(file_keys)
            parquet_result["files"].append({"path":str(p),"rows_scanned":file_rows,"unique_rfid_keys":len(file_keys),"newB_keys_present":len(file_hits),"matched_ids":";".join(sorted(file_hits))})
        parquet_result.update({"status":"scanned_projected_rfid_only","rows_scanned":total,"unique_rfid_keys_union":len(cache_unique),"newB_unique_ids":len(target_new),"newB_ids_present":len(present),"newB_ids_absent_from_this_legacy_cache":len(target_new-present),"matched_ids":";".join(sorted(present)),"source_scope":"legacy rows_test parquet derived from 1027 inputs per parse_test_1..6; not proof about v2 ZIP tracks"})
    else:
        parquet_result["reason"]="available RAM below conservative 768 MiB minimum; optional scan deferred"
    parquet_hash_post={str(p):{"size_bytes":p.stat().st_size,"sha256":file_sha(p)} for p in parquet_files}
    parquet_result["file_hashes_pre_post_unchanged"]=parquet_hash_pre==parquet_hash_post
    parse_records=[]
    parse_by_month={}
    for mp in PARSE_MANIFESTS:
        d=json.loads(mp.read_text(encoding="utf-8-sig")); month=int(d.get("month",0)); parse_by_month[month]=d
        n=next((x.get("rows_scanned") for x in parquet_result.get("files",[]) if Path(x["path"]).stem==f"rows_test_{month}"),None)
        parse_records.append({"manifest_path":str(mp),"dataset":d.get("dataset"),"month":month,"complete":d.get("complete"),"original_source_path":d.get("path"),"source_bytes_recorded":d.get("bytes"),"source_sha256_recorded":d.get("sha256"),"prior_source_hash_match_recorded":d.get("sha256_match"),"source_hash_recomputed_now":False,"manifest_raw_rows":d.get("raw_count"),"parquet_rows_scanned":n,"row_count_matches_manifest":n==d.get("raw_count") if n is not None else None})
    parquet_result["source_parse_manifest_evidence"]=parse_records
    parquet_result["all_parquet_row_counts_match_parse_manifests"]=bool(parquet_files) and all(x["row_count_matches_manifest"] is True for x in parse_records) if parquet_result.get("status")=="scanned_projected_rfid_only" else None
    csv_write(OUT/"source_id_rows.csv",id_records,["source","sheet","cell","raw_value","raw_type","trimmed_value","safe_integer_normalized","comparison_key","blank"])
    csv_write(OUT/"set_comparisons.csv",compare_rows,["comparison","status","left_rows","right_rows","left_unique","right_unique","intersection_count","left_only_count","right_only_count","intersection_ids","left_only_ids","right_only_ids"])
    workbook_details={"old_F_sample":old_info,"new_zip_member":new_info,"new_intake_copy":intake_info}
    sheet_summaries={name:list_summary(g) for name,g in groups.items() if name in {"oldA","oldB","newA","newB","intakeA","intakeB"}}
    if "score_cache" in groups: sheet_summaries["score_cache"]=list_summary(groups["score_cache"])
    sheet_summaries["submission"]={"sheet":"CSV","header":groups["submission"]["header"],"data_rows":groups["submission"]["row_count"],"nonblank_rows":sum(not x["blank"] for x in groups["submission"]["rows"]),"blank_rows":sum(x["blank"] for x in groups["submission"]["rows"]),"unique_ids":len({x["key"] for x in groups["submission"]["rows"] if not x["blank"]}),"duplicate_id_values":{k:v for k,v in Counter(x["key"] for x in groups["submission"]["rows"] if not x["blank"]).items() if v>1},"value_types":dict(Counter(x["type"] for x in groups["submission"]["rows"]))}
    archive_after=zip_stat()
    post={str(p):{"exists":p.is_file(),"size_bytes":p.stat().st_size if p.is_file() else None,"mtime_ns":p.stat().st_mtime_ns if p.is_file() else None,"sha256":file_sha(p) if p.is_file() else None} for p in input_paths}
    changed=[p for p in pre if pre[p]!=post[p]]
    own_receipt=ROOT/"testB"/"round_001"/"integration"/"runtime_receipts"/"W3_start.json"
    follow_receipt=ROOT/"testB"/"round_001"/"integration"/"runtime_receipts"/"V2_ID_recheck_send.json"
    receipt=json.loads(own_receipt.read_text(encoding="utf-8-sig"))
    follow=json.loads(follow_receipt.read_text(encoding="utf-8-sig"))
    summary={"status":"completed" if manifest_copy_ok and not changed else "failed_or_changed_inputs","started_local":started,"finished_local":datetime.now().astimezone().isoformat(),"model_request":{"model":receipt.get("result",{}).get("model"),"effort":receipt.get("result",{}).get("effort"),"original_run_receipt_path":str(own_receipt),"original_receipt_dispatch_id":receipt.get("result",{}).get("dispatchId"),"original_receipt_task_id":receipt.get("result",{}).get("taskId"),"current_follow_up_receipt_path":str(follow_receipt),"current_dispatch_id":follow.get("result",{}).get("dispatchId"),"current_task_id":follow.get("result",{}).get("taskId"),"run_id":follow.get("result",{}).get("runId"),"provider_internal_runtime_model":"unknown"},"zip_member":zinfo,"workbooks":workbook_details,"sheet_id_summaries":sheet_summaries,"row_order":{"oldB_newB_rows_compared":min(len(oldb),len(newb)),"raw_value_same_position_count":raw_row_matches,"normalized_id_same_position_count":norm_row_matches,"oldB_order_matches_newB_order":len(oldb)==len(newb)==100 and norm_row_matches==100},"set_comparisons":compare_rows,"score_cache_key_only":cache_meta,"parquet_coverage":parquet_result,"input_hashes_pre":pre,"input_hashes_post":post,"inputs_changed_during_check":changed,"zip_metadata_after":archive_after,"zip_metadata_unchanged":archive_before==archive_after,"script_sha256":file_sha(Path(__file__)),"actual_scope":{"zip_member_only_read":"selected small submission sample member read into BytesIO; no archive extraction; archive not rehashed","score_cache":"ID keys only; no scores/A recomputation","parquet":"only rfid_id column, sequential 65,536-row batches if RAM gate allowed","raw_v2_csvs":"not read, rehashed or parsed"}}
    json_write(OUT/"summary.json",summary)
    pairs_map={r["comparison"]:r for r in compare_rows}; oldnew=pairs_map["oldB_vs_newB"]
    report=["# Test B ID 교집합 독립 재검산","","## 먼저 답","","기존 제출샘플의 Test B ID 100개와 새 ZIP 제출샘플의 Test B ID 100개를 직접 비교한 교집합은 **"+str(oldnew.get("intersection_count","unknown"))+"개**입니다. 이 0은 제출샘플 두 시트의 ID 명부 교집합만 뜻하며, 원항적 파일에 새 ID가 없다는 뜻은 아닙니다.",""]
    for r in compare_rows:
        report.append(f"- **{r['comparison']}**: 교집합 {r.get('intersection_count','unknown')}개, 왼쪽만 {r.get('left_only_count','unknown')}개, 오른쪽만 {r.get('right_only_count','unknown')}개"+(f" (status {r['status']})" if r.get("status") else ""))
    report += ["","## 시트·타입 확인","","- ZIP 내부의 작은 제출샘플 member를 ZIP에서 직접 읽어 openpyxl read_only 모드로 열었다. 전체 ZIP 추출이나 ZIP 전체 해시는 하지 않았다.","- ZIP member SHA-256과 intake의 reference_02_제출샘플.xlsx, archive manifest의 크기/SHA/CRC/경로를 대조했다. 결과: "+("일치." if manifest_copy_ok else "불일치; 확인 필요."),"- 원본 F: 제출샘플과 ZIP 내부 workbook 각각 sheet 순서, A1, A2:A101 값·타입·공백·중복을 확인했다. 비교 CSV에는 원값, 타입, 공백 제거값, 선행0를 변경하지 않는 안전한 정수표현, 비교키를 함께 남겼다.","- oldB/newB 같은 행 위치 ID 일치: 원값 "+str(raw_row_matches)+"/"+str(min(len(oldb),len(newb)))+"; 안전 정규화 후 "+str(norm_row_matches)+"/"+str(min(len(oldb),len(newb)))+".","","## 기존 캐시와 원항적 해석","","- scored_rows.pkl은 점수/A를 재계산하지 않고 rfid_id 키만 읽었다. 이는 기존 점수 캐시에 키가 존재하는지 뜻하며 원항적 전체 존재와 같은 주장이 아니다.","- parquet coverage: "+str(parquet_result.get("status"))+"; "+str(parquet_result.get("newB_ids_present","미측정"))+"/"+str(len(target_new))+" newB 고유 ID가 이 legacy rows_test parquet에서 보였다. 해당 parquet은 parse manifest에 기재된 F: 1027 CSV 입력 기반 캐시이며 v2 ZIP 원항적을 검증하지 않는다.","- parse_test_1..6 명부의 각 원본 경로/기록 SHA는 1027 입력을 가리키고, 각 행수와 현재 parquet 투영 스캔 행수의 대응을 summary에 보존했다. 원본 CSV SHA는 재계산하지 않았다.","- W0의 구/신 Test B ID 교집합 0 주장은 직접 workbook 재검산으로 "+("확인됐다." if oldnew.get("intersection_count")==0 else "정정이 필요하다: 직접 계산값은 "+str(oldnew.get("intersection_count"))+"개다.")+"","- ZIP 메타데이터 변경 여부: "+("변경 없음." if archive_before==archive_after else "변경 감지.")+" 비교 입력 SHA 전/후 변경: "+(str(changed) if changed else "없음.")+"",""]
    (OUT/"recheck_report.md").write_text("\n".join(report),encoding="utf-8")
    return {"status":summary["status"],"oldB_newB_intersection":oldnew.get("intersection_count"),"comparisons":{r["comparison"]:r.get("intersection_count",r.get("status")) for r in compare_rows},"cache_status":cache_status,"parquet_status":parquet_result.get("status"),"newB_parquet_present":parquet_result.get("newB_ids_present"),"inputs_changed":changed,"manifest_member_match":manifest_copy_ok}

if __name__=="__main__":
    try:
        result=main();print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result["status"]=="completed" and result["manifest_member_match"] and not result["inputs_changed"] else 2)
    except Exception as e:
        print(f"RECHECK_ERROR: {type(e).__name__}: {e}",file=sys.stderr);sys.exit(2)
