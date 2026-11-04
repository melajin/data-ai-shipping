from __future__ import annotations
import csv, hashlib, importlib.util, json, math, sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "testB" / "round_001" / "audit" / "w1_w2_001"
W1 = ROOT / "testB" / "round_001" / "linkage_review"
W2 = ROOT / "testB" / "round_001" / "timing"
CANON = Path(r"D:\repos\fishing-track-classification\results\submission_20261101\testB_submission.csv")

def j(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    return h.hexdigest()

def run():
    checks=[]; issues=[]
    w1=rows(W1/"evidence_table.csv"); s1=j(W1/"summary.json")
    w1m=j(W1/"manifest.json"); w2m=j(W2/"input_split_manifest.json")
    hash_targets={Path(k) for k in w1m.get("inputs_pre",{})}
    hash_targets.update(Path(x["path"]) for x in w2m.get("sources",[]) if x.get("path"))
    if w1m.get("code",{}).get("path"): hash_targets.add(Path(w1m["code"]["path"]))
    hash_targets.update(W1/p for p in w1m.get("output_sha256_after_run",{}))
    hash_targets.update({W1/"evidence_table.csv",W1/"summary.json",W1/"manifest.json",W1/"run_linkage_review.py",W1/"process_result.json",W2/"comparison_readiness_100.csv",W2/"summary.json",W2/"input_split_manifest.json",W2/"input_split_manifest_addendum.json",W2/"timing_interface.py",W2/"readiness_report.md",W2/"code_lineage.json",W2/"publish_legacy_preparation.py",W2/"round_001"/"run_003"/"process_result.json"})
    w3receipt=ROOT/"testB"/"round_001"/"integration"/"runtime_receipts"/"W3_start.json"
    hash_targets.add(w3receipt)
    def snapshot():
        return {str(p):({"exists":True,"size_bytes":p.stat().st_size,"sha256":sha(p)} if p.is_file() else {"exists":False}) for p in sorted(hash_targets,key=str)}
    hashes_pre=snapshot()
    expected=set(s1["finding"]["priority_union_event_ids"])
    actual={r["event_id"] for r in w1 if r["scope_priority_union"]!="remaining_single_candidate_review"}
    stable=[r["event_id"] for r in w1 if r["same_single_candidate_all_nine_conditions"].lower()=="true"]
    widened=[r["event_id"] for r in w1 if r["baseline_single_becomes_multiple_when_time_widened"].lower()=="true"]
    multi=[r["event_id"] for r in w1 if r["reported_count_mismatch_flag"].lower()=="true"]
    keys_ok=all(len(json.loads(r["all_9_condition_relations_json"]))==9 for r in w1)
    checks.append({"item":"W1 rows, priority union, nine conditions and aggregates","status":"pass" if len(w1)==30 and len({r["event_id"] for r in w1})==30 and actual==expected and len(actual)==10 and keys_ok and len(stable)==1 and len(widened)==7 and len(multi)==3 else "fail","evidence":{"row_count":len(w1),"unique_ids":len({r["event_id"] for r in w1}),"priority_expected":sorted(expected),"priority_actual":sorted(actual),"priority_scope_counts":dict(Counter(r["scope_priority_union"] for r in w1)),"stable":stable,"time_widened":widened,"multi_vessel":multi,"nine_condition_keys":keys_ok}})
    sem=all(r["identity_confirmed"].lower()=="false" and r["development_use_allowed"].startswith("unknown") and r["normal_label_evidence_available"].startswith("false") and r["type_tonnage_filter_applied"].lower()=="false" for r in w1)
    checks.append({"item":"W1 identity/use/normal claims bounded","status":"pass" if sem and s1["finding"]["identity_confirmed_count"]==0 else "fail","evidence":{"all_rows_false_identity_unknown_use_no_normal":sem,"summary":s1["finding"],"scope_conclusion":s1["local_search"]["conclusion"]}})
    e=next((r for r in w1 if r["event_id"]=="E0023"),None)
    if e:
        rel=json.loads(e["all_9_condition_relations_json"]); ids={k:[x["rfid_id"] for x in v] for k,v in rel.items()}; cache=json.loads(e["selected_cache_shape_json"])
        ok=e["rfid_id"]=="31005928" and all(v==["31005928"] for v in ids.values()) and cache["row_found"] and cache["row_identity_matches"] and int(cache["n_coords"])==91 and abs(float(e["min_distance_m"])-435.9)<.1 and e["min_distance_row_source_index"]==str(cache["source_row_index"])
        checks.append({"item":"W1 E0023 trace/units/sample cache summary","status":"pass" if ok else "fail","evidence":{"rfid":e["rfid_id"],"nine_relations":ids,"distance_m":e["min_distance_m"],"time_start_minus_event_min":e["minrow_track_hour_start_minus_accident_minutes"],"cache":cache,"interpretation":"distance/time residual is linkage evidence, not detection error"}})
    else: checks.append({"item":"W1 E0023 trace","status":"fail","evidence":"missing"})
    # Directly inspect only E0023's accident source row and the already-selected cache row.
    if e:
        import pyarrow.parquet as pq
        from openpyxl import load_workbook
        xlsx=list(Path("F:/").glob("*1027*/*26*.xlsx"))
        parquet=list(ROOT.glob("*29-30*/*/outputs/remeasure_20261031/rows_train_6.parquet"))
        source_ok=False; cache_ok=False; xlsx_evidence={}; cache_evidence={}
        if len(xlsx)==1:
            wb=load_workbook(xlsx[0],read_only=True,data_only=True); ws=wb["Sheet1"]
            header=next(ws.iter_rows(min_row=1,max_row=1,values_only=True))
            raw=next(ws.iter_rows(min_row=24,max_row=24,values_only=True))
            xlsx_evidence={"path":str(xlsx[0]),"headers":list(header),"excel_row_24":list(raw)}
            source_ok=(raw[0].strftime("%Y-%m-%d %H:%M:%S")==e["accident_time"] and str(raw[9])==e["reported_accident_vessel_count"] and abs(raw[3]-float(e["accident_lat"]))<1e-6 and abs(raw[4]-float(e["accident_lon"]))<1e-6 and not any(k in header for k in ("RFID","선명","등록번호")))
            wb.close()
        if len(parquet)==1:
            pf=pq.ParquetFile(parquet[0]); idx=int(e["min_distance_row_source_index"]); offset=0; selected=None
            for rg in range(pf.num_row_groups):
                n=pf.metadata.row_group(rg).num_rows
                if offset<=idx<offset+n:
                    selected=pf.read_row_group(rg).slice(idx-offset,1).to_pylist()[0]; cache_evidence={"path":str(parquet[0]),"row_group":rg,"absolute_row_index":idx,"row":selected}; break
                offset+=n
            if selected:
                cache_ok=(selected["row_index"]==idx and selected["rfid_id"]==e["rfid_id"] and selected["part_dt"]=="20260604" and selected["rfid_time"]==12 and selected["n_coords"]==91 and selected["wkt_valid"] is True and abs(selected["len_m"]-float(json.loads(e["selected_cache_shape_json"])["len_m"]))<1e-8)
                R=6371000.0; lat1=math.radians(float(e["accident_lat"])); lat2=math.radians(selected["cen_lat"]); dlat=lat2-lat1; dlon=math.radians(selected["cen_lon"]-float(e["accident_lon"]))
                hav=2*R*math.asin(math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2))
                cache_evidence["independent_haversine_centroid_distance_m"]=hav
                cache_evidence["reported_centroid_distance_m"]=float(e["min_distance_m"])
                cache_ok=cache_ok and abs(hav-float(e["min_distance_m"]))<1e-3
        checks.append({"item":"W1 E0023 direct accident row and selected cache row","status":"pass" if source_ok and cache_ok else "fail","evidence":{"source_row_verified":source_ok,"selected_cache_row_verified":cache_ok,"accident_source":xlsx_evidence,"cache_source":cache_evidence,"distance_method_note":"independent haversine compared with cached linkage distance; not detection error"}})
    m1=w1m; bad=[]; missing=[]
    for mapping in (m1.get("inputs_pre",{}),m1.get("inputs_post",{})):
        for raw,rec in mapping.items():
            p=Path(raw)
            if not p.exists(): missing.append(raw)
            elif p.is_file() and (p.stat().st_size!=rec["size_bytes"] or sha(p)!=rec["sha256"]): bad.append(raw)
    p1=j(W1/"process_result.json")
    attempts={p.name:j(p).get("exit_code") for p in W1.glob("process_result_attempt*.json")}
    code_rec=m1.get("code",{}); code_path=Path(code_rec.get("path","")); code_hash=sha(code_path) if code_path.exists() else None
    code_ok=code_hash is not None and code_hash==code_rec.get("sha256_pre")==code_rec.get("sha256_post") and code_rec.get("unchanged") is True
    output_bad=[]
    for name,digest in m1.get("output_sha256_after_run",{}).items():
        p=W1/name
        if not p.is_file() or sha(p)!=digest: output_bad.append(name)
    fr=m1.get("final_process_record",{})
    logs_ok=Path(fr.get("stdout_path","")).is_file() and Path(fr.get("stderr_path","")).is_file()
    checks.append({"item":"W1 listed input/code/output hashes, final exit, attempts and environment","status":"pass" if not missing and not bad and p1.get("exit_code")==0 and fr.get("exit_code")==0 and attempts and code_ok and not output_bad and logs_ok else "fail","evidence":{"missing_paths":missing,"input_hash_mismatch":bad,"code_path":code_rec.get("path"),"code_sha256_current":code_hash,"code_pre_post_match":code_ok,"output_hash_mismatch":output_bad,"process_result_exit":p1.get("exit_code"),"final_record_exit":fr.get("exit_code"),"final_record_previous_attempts":fr.get("previous_attempts"),"attempt_exit_codes":attempts,"stdout_stderr_exist":logs_ok,"environment":m1.get("environment"),"model_request":m1.get("model_evidence",{}).get("receipt",{}).get("result",{})}})

    t=rows(W2/"comparison_readiness_100.csv"); c=rows(CANON) if CANON.exists() else []
    diffs=[]
    if len(t)==len(c)==100:
        for i,(a,b) in enumerate(zip(t,c),1):
            if (a["rfid_id"],a["baseline_A_timestamp"],a["baseline_A_score"])!=(b["rfid_id"],b["사고시각"],b["이상항적 점수"]): diffs.append(i)
    checks.append({"item":"W2 ordered 100 unique IDs and A values vs canonical CSV","status":"pass" if len(t)==100 and len({r["rfid_id"] for r in t})==100 and len(c)==100 and [r["rfid_id"] for r in t]==[r["rfid_id"] for r in c] and not diffs else "fail","evidence":{"table_rows":len(t),"canonical_rows":len(c),"unique_ids":len({r["rfid_id"] for r in t}),"A_differing_rows":diffs,"method":"submission CSV only; scored_rows.pkl not opened"}})
    empty=all(not any(r[k].strip() for k in ("B_timestamp","B_score","B_source_row","C_timestamp","C_score","C_source_row")) and r["B_status"]=="not_computed" and r["C_status"]=="not_computed" and r["B_unavailable_reason"] and r["C_unavailable_reason"] and r["internal_decision_status"]=="not_assessed_not_accident_label" for r in t)
    checks.append({"item":"W2 B/C are blank and not computed, no normal label","status":"pass" if empty else "fail","evidence":{"all_rows_consistent":empty,"summary":j(W2/"summary.json")}})

    man=j(W2/"input_split_manifest.json"); lin=j(W2/"code_lineage.json"); code=(W2/"timing_interface.py").read_text(encoding="utf-8-sig")
    tie=man.get("method_states",{}).get("ties_and_duplicates","")
    stale="earliest maximum" in tie.lower()
    generator=W2/"publish_legacy_preparation.py"
    generator_stale="earliest maximum" in generator.read_text(encoding="utf-8-sig").lower()
    split=man.get("split_design_pending",{}).get("actual_assignment")=="pending"
    over=j(W2/"summary.json").get("target_reference_id_overlap",{}).get("interpretation","")
    overlap_ok="membership only" in over and "unmeasured" in over
    tie_ok=not stale and "first maximum" in tie.lower() and "first maximum" in code.lower() and "first maximum" in lin.get("round_copy",{}).get("change","").lower()
    checks.append({"item":"W2 current tie contract, manifest generator, split pending, 95 overlap bounded","status":"pass" if tie_ok and not generator_stale and split and overlap_ok else "fail","evidence":{"manifest_tie_text":tie,"stale_manifest_earliest_maximum":stale,"manifest_generator":"publish_legacy_preparation.py","generator_stale_earliest_maximum":generator_stale,"code_lineage_first_max":tie_ok,"split_assignment":man.get("split_design_pending",{}).get("actual_assignment"),"overlap_interpretation":over}})
    if stale:
        issues.append({"severity":"blocking","file":"testB/round_001/timing/input_split_manifest.json","location":"method_states.ties_and_duplicates","reproduce":"Read current JSON field: says earliest maximum wins; code and lineage say first max in original input order.","impact":"Contract contradicts current A tie implementation and can select a different row.","suggested_fix":"Change to first maximum in original source order for A; stable timestamp+ordinal ordering is B/C only; retain duplicate rows and count unique timestamps for persistence."})
    if generator_stale:
        issues.append({"severity":"high","file":"testB/round_001/timing/publish_legacy_preparation.py","location":"line 94: method_states.ties_and_duplicates literal","reproduce":"Search this generator for 'earliest maximum wins'; it serializes the old rule into input_split_manifest.json.","impact":"Re-running the publisher can restore the contradictory earliest-maximum contract after a manifest-only correction.","suggested_fix":"Update the generator literal to first maximum in original input order for A; note timestamp sorting only affects B/C."})

    spec=importlib.util.spec_from_file_location("audited_timing_interface",W2/"timing_interface.py")
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    syn=[]
    def check(name,rs,ps,expected):
        x=mod.estimate_vessel(rs,ps); got={k:getattr(x,k) for k in expected}; syn.append({"case":name,"expected":expected,"observed":got,"pass":got==expected})
    check("A original-order tie", [{"ts":7,"score":.9,"source_row_id":"first"},{"ts":6,"score":.9,"source_row_id":"second"},{"ts":5,"score":.2,"source_row_id":"low"}],mod.TimingParams(.5,"gt",1,0,1,"synthetic"),{"a_source_row":"first","b_ts":6,"c_ts":6})
    check("B/C same segment and C=B", [{"ts":1,"score":.8,"source_row_id":"onset"},{"ts":2,"score":.9,"source_row_id":"peak"}],mod.TimingParams(.5,"gt",1,1,2,"synthetic"),{"b_ts":1,"c_ts":1,"status":"candidate_ready"})
    check("NaN breaks", [{"ts":0,"score":.8,"source_row_id":"before"},{"ts":1,"score":float("nan"),"source_row_id":"nan"},{"ts":2,"score":.9,"source_row_id":"peak"}],mod.TimingParams(.5,"gt",2,0,1,"synthetic"),{"b_ts":2,"segment_source_rows":["peak"]})
    check("missing interval over max splits", [{"ts":0,"score":.8,"source_row_id":"before"},{"ts":2,"score":.9,"source_row_id":"peak"}],mod.TimingParams(.5,"gt",1,0,1,"synthetic"),{"b_ts":2,"segment_source_rows":["peak"]})
    check("duplicate time not two persistence rows", [{"ts":4,"score":.9,"source_row_id":"a"},{"ts":4,"score":.8,"source_row_id":"b"}],mod.TimingParams(.5,"gt",1,0,2,"synthetic"),{"status":"persistence_not_met","c_ts":None,"duplicate_timestamp_rows":1})
    check("empty finite scores calculation unavailable", [{"ts":3,"score":None,"source_row_id":"missing"},{"ts":4,"score":float("nan"),"source_row_id":"nan"}],mod.TimingParams(.5,"gt",1,0,1,"synthetic"),{"status":"insufficient_data","reason":"no_finite_scores"})
    try:
        mod.estimate_vessel([{"ts":0,"score":.8}],mod.TimingParams(.5,"gt",1,0,1," "))
        req=False
    except mod.ContractError: req=True
    syn.append({"case":"parameter source required","pass":req})
    x=mod.estimate_vessel([{"ts":0,"score":1e-6}],mod.TimingParams(0.0,"gt",1,0,1,"synthetic"))
    syn.append({"case":"positive floor value remains ordinary finite score","pass":x.status=="candidate_ready","observed_status":x.status})
    checks.append({"item":"Independent synthetic timing checks (not self_check)","status":"pass" if all(x["pass"] for x in syn) else "fail","evidence":syn})
    checks.append({"item":"Duplicate-timestamp conflicting-score policy fully specified","status":"unknown","evidence":{"implemented":"stable timestamp/input-ordinal ordering; duplicate rows retained; persistence counts unique timestamps; A ties use original input order","unresolved":"no explicit rule for reconciling conflicting scores/records at the same timestamp before segment and persistence checks"}})
    checks.append({"item":"Positive score-floor semantics resolved for future evaluation","status":"unknown","evidence":{"contract":man.get("score_contract",{}).get("score_formula"),"timing_test":"1e-6 is accepted as an ordinary finite score and can cross a lower synthetic threshold","unresolved":"no approved real threshold/source or explicit floor/missing-value semantics for future candidate evaluation"}})
    gap=mod.estimate_vessel([{"ts":0,"score":.8},{"ts":2,"score":.9}],mod.TimingParams(.5,"gt",2,0,1,"synthetic"))
    checks.append({"item":"max_gap parameter can bridge unobserved time","status":"fail" if gap.b_ts==0 else "pass","evidence":{"timestamps":[0,2],"max_gap_hours":2,"B":gap.b_ts,"interpretation":"when delta <= max_gap, a missing bin may be bridged"}})
    issues.append({"severity":"open_design_limit","file":"testB/round_001/timing/timing_interface.py","location":"estimate_vessel gap comparison; TimingParams.max_gap_hours","reproduce":"Synthetic ts=0 and ts=2 above threshold with max_gap_hours=2 yields one segment (B=0).","impact":"A configured tolerance above nominal cadence connects across unobserved bins; this is unresolved against a strict no-missing-time policy.","suggested_fix":"Supervisor must explicitly choose supported cadence/gap semantics. If missing bins always break, require adjacent expected cadence rather than a variable tolerance."})

    p2=j(W2/"round_001"/"run_003"/"process_result.json"); env=j(W2/"round_001"/"run_003"/"environment.json")
    receipt=j(ROOT/"26_11_5"/"testb_next_experiment_20261105"/"integration"/"runtime_receipts"/"W2_start.json")
    checks.append({"item":"W2 observed synthetic exit, environment, request receipt","status":"pass" if p2.get("exit_code")==0 and receipt.get("result",{}).get("model")=="gpt-6-luna" and receipt.get("result",{}).get("effort")=="xhigh" else "fail","evidence":{"process":p2,"environment":env,"requested":receipt.get("result",{})}})
    lineage_path=Path(lin["round_copy"]["path"]); current_timing_sha=sha(W2/"timing_interface.py")
    round_hashes=j(W2/"summary.json").get("round_output_hashes",{})
    round_hash_bad={name: {"recorded":digest,"current":sha(W2/name) if (W2/name).is_file() else None} for name,digest in round_hashes.items() if not (W2/name).is_file() or sha(W2/name)!=digest}
    expected_code=p2.get("code",{}); run_logs=all(Path(p2[k]).is_file() for k in ("stdout","stderr"))
    lineage_ok=(lineage_path.as_posix().endswith("testB/round_001/timing/timing_interface.py") and lin["round_copy"].get("sha256")==current_timing_sha and lin["round_copy"].get("size_bytes")== (W2/"timing_interface.py").stat().st_size and j(W2/"summary.json").get("timing_interface_sha256")==current_timing_sha and expected_code.get("sha256")==current_timing_sha and expected_code.get("size_bytes")== (W2/"timing_interface.py").stat().st_size)
    checks.append({"item":"W2 round code lineage, output hashes and process logs are consistent","status":"pass" if lineage_ok and not round_hash_bad and run_logs else "fail","evidence":{"current_timing_sha256":current_timing_sha,"lineage_and_process_code_match":lineage_ok,"round_output_hash_mismatches":round_hash_bad,"stdout_stderr_exist":run_logs,"actual_exit":p2.get("exit_code")}})
    w3r=j(w3receipt).get("result",{})
    checks.append({"item":"W3 model/effort request receipt and dispatch identity","status":"pass" if w3r.get("model")=="gpt-6-luna" and w3r.get("effort")=="xhigh" and w3r.get("runId")=="run_131763108c81" else "fail","evidence":{"model":w3r.get("model"),"effort":w3r.get("effort"),"run_id":w3r.get("runId"),"task_id":w3r.get("taskId"),"dispatch_id":w3r.get("dispatchId")}})
    checks.append({"item":"Provider-internal actual runtime model independently observable","status":"unknown","evidence":"Orca receipt records requested gpt-6-luna/xhigh; provider internal runtime is not independently exposed in inspected artifacts."})
    source_bad=[]
    for s in man.get("sources",[]):
        p=Path(s["path"])
        if not p.exists(): source_bad.append({"path":s["path"],"reason":"missing"})
        elif p.is_file() and (p.stat().st_size!=s.get("size_bytes") or sha(p)!=s.get("sha256")): source_bad.append({"path":s["path"],"reason":"hash/size mismatch"})
    checks.append({"item":"W2 source manifest references resolve/hash-match","status":"pass" if not source_bad else "fail","evidence":{"mismatches":source_bad,"scope":"manifest-listed paths only; no raw/disk-wide certification"}})

    blocking=any(x["severity"]=="blocking" for x in issues) or any(x["status"]=="fail" for x in checks if x["item"]!="max_gap parameter can bridge unobserved time")
    status="fail" if blocking else "passed"
    hashes_post=snapshot()
    changed=[p for p in hashes_pre if hashes_pre[p]!=hashes_post[p]]
    (OUT/"inspection_hashes.json").write_text(json.dumps({"scope":"manifest-listed sources and inspected W1/W2 artifacts only; no disk-wide or full raw archive proof","pre":hashes_pre,"post":hashes_post,"changed_during_audit":changed},ensure_ascii=False,indent=2),encoding="utf-8")
    if changed:
        checks.append({"item":"Inspected W1/W2 target hashes unchanged during independent audit","status":"fail","evidence":{"changed_paths":changed}})
    else:
        checks.append({"item":"Inspected W1/W2 target hashes unchanged during independent audit","status":"pass","evidence":{"file_count":len(hash_targets),"changed_paths":[]}})
    # Recompute status after the pre/post snapshot finding.
    blocking=any(x["severity"]=="blocking" for x in issues) or any(x["status"]=="fail" for x in checks if x["item"]!="max_gap parameter can bridge unobserved time")
    status="fail" if blocking else "passed"
    review={"audit_status":status,"product_validation_status":"not passed; preparation only, no actual evaluation or split","requested_model_effort":{"model":"gpt-6-luna","effort":"xhigh","receipt":"testB/round_001/integration/runtime_receipts/W3_start.json"},"checks":checks,"actionable_issues":issues,"inspection_hashes":"inspection_hashes.json","scope":"legacy W1/W2 only; v2 excluded; scored_rows.pkl not opened; no threshold selection or actual evaluation"}
    (OUT/"review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    lines=["# W1/W2 독립 검산 보고서","",f"검산 상태: **{status}** (제품 검증 통과와 별개)","","## 결과"]
    lines += [f"- **{x['status'].upper()} — {x['item']}**" for x in checks]
    lines += ["","## 핵심 판단","",
    "- W1 30개 사건과 우선 합집합 10개를 표에서 다시 집계했다. 9조건 관계, 안정 1건, 시간확대 다후보 7건, 다선박 수 불일치 3건, 신원 확정 0건이 일치한다. 사용범위는 unknown이고 정상 근거가 없으며, 잔차는 후보 연결 근거다.",
    "- W2 A 순서/ID/시각/점수는 기존 제출 CSV와 대조했다. scored_rows.pkl은 열지 않았다. B/C 값은 비었고 not_computed이며 행별 사유와 not_assessed_not_accident_label 상태가 유지됐다.",
    "- W2 manifest의 ties_and_duplicates는 earliest maximum이라는 옛 문구가 남아 코드와 code_lineage의 원입력 순서 최초 최대 계약과 충돌한다. `publish_legacy_preparation.py`도 같은 옛 문구를 재생성하므로 둘 다 고쳐야 한다.",
    "- 독립 합성 검사에서는 동점 A, 동일 구간 B/C 및 C=B, NaN/시간간격 분절, 중복시각 지속행수, 파라미터 출처, 빈 점수 계산불가를 확인했다. 실제 점수 임계값은 선택하지 않았다.",
    "- max_gap_hours가 샘플 cadence보다 크면 미관측 구간을 연결한다. 중복 timestamp 값 충돌의 채택 정책은 미정이며, positive floor는 결측이 아닌 유한점수로 취급되어 임계값에 따라 판정을 바꿀 수 있다.",
    "","## 조치 필요"]
    for x in issues: lines.append(f"- **{x['severity']}** {x['file']} ({x['location']}): {x['impact']} 재현: {x['reproduce']} 제안: {x['suggested_fix']}")
    lines += ["","## 미확정 인터페이스 한도","","- `timing_interface.py`의 timestamp 정렬은 원행 ordinal을 유지하고 중복 시각은 행 추적에 남기며 지속 행수는 고유 시각 수로 센다. 그러나 같은 시각의 점수가 충돌할 때 사전 중복 제거·통합 규칙은 아직 없다. 적용 위치: `timing_interface.py` 79–87, 130–131행.","- `input_split_manifest.json`의 점수식 설명은 양수 floor를 언급하고, 인터페이스는 `1e-6`을 보통 유한 점수로 받아들인다. threshold가 승인되지 않았고 floor의 평가 의미도 고정되지 않아 실제 판정에 미칠 영향은 unknown이다. 실제 임계값은 선택하지 않았다.","","## 한계","","W0 v2, 원자료 전체, 디스크 전체, 전체 43+31 선행감사 재검산은 포함하지 않는다. actual split, 2026 실제 점수/사고 평가, 모델 학습, threshold 선택은 하지 않았다. Orca 영수증은 gpt-6-luna/xhigh 요청을 보여주며 provider 내부 모델 관찰은 별도 불가.",""]
    (OUT/"audit_report.md").write_text("\n".join(lines),encoding="utf-8")
    return {"audit_status":status,"counts":dict(Counter(x["status"] for x in checks)),"issue_count":len(issues),"checks":[{"item":x["item"],"status":x["status"]} for x in checks]}

if __name__=="__main__":
    try:
        result=run(); print(json.dumps(result,ensure_ascii=False,indent=2,default=str)); sys.exit(2 if result["audit_status"]=="fail" else 0)
    except Exception as e:
        print(f"VERIFIER_ERROR: {type(e).__name__}: {e}",file=sys.stderr); sys.exit(2)
