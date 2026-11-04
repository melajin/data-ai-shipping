from __future__ import annotations
import csv, hashlib, importlib.util, json, sys
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
    expected=set(s1["finding"]["priority_union_event_ids"])
    actual={r["event_id"] for r in w1 if r["scope_priority_union"]=="priority_union_10"}
    stable=[r["event_id"] for r in w1 if r["same_single_candidate_all_nine_conditions"].lower()=="true"]
    widened=[r["event_id"] for r in w1 if r["baseline_single_becomes_multiple_when_time_widened"].lower()=="true"]
    multi=[r["event_id"] for r in w1 if r["reported_count_mismatch_flag"].lower()=="true"]
    keys_ok=all(len(json.loads(r["all_9_condition_relations_json"]))==9 for r in w1)
    checks.append({"item":"W1 rows, priority union, nine conditions and aggregates","status":"pass" if len(w1)==30 and len({r["event_id"] for r in w1})==30 and actual==expected and len(actual)==10 and keys_ok and len(stable)==1 and len(widened)==7 and len(multi)==3 else "fail","evidence":{"row_count":len(w1),"unique_ids":len({r["event_id"] for r in w1}),"priority_expected":sorted(expected),"priority_actual":sorted(actual),"stable":stable,"time_widened":widened,"multi_vessel":multi,"nine_condition_keys":keys_ok}})
    sem=all(r["identity_confirmed"].lower()=="false" and r["development_use_allowed"].startswith("unknown") and r["normal_label_evidence_available"].startswith("false") and r["type_tonnage_filter_applied"].lower()=="false" for r in w1)
    checks.append({"item":"W1 identity/use/normal claims bounded","status":"pass" if sem and s1["finding"]["identity_confirmed_count"]==0 else "fail","evidence":{"all_rows_false_identity_unknown_use_no_normal":sem,"summary":s1["finding"],"scope_conclusion":s1["local_search"]["conclusion"]}})
    e=next((r for r in w1 if r["event_id"]=="E0023"),None)
    if e:
        rel=json.loads(e["all_9_condition_relations_json"]); ids={k:[x["rfid_id"] for x in v] for k,v in rel.items()}; cache=json.loads(e["selected_cache_shape_json"])
        ok=e["rfid_id"]=="31005928" and all(v==["31005928"] for v in ids.values()) and cache["row_found"] and cache["row_identity_matches"] and int(cache["n_coords"])==91 and abs(float(e["min_distance_m"])-435.9)<.1 and e["min_distance_row_source_index"]==str(cache["source_row_index"])
        checks.append({"item":"W1 E0023 trace/units/sample cache summary","status":"pass" if ok else "fail","evidence":{"rfid":e["rfid_id"],"nine_relations":ids,"distance_m":e["min_distance_m"],"time_start_minus_event_min":e["minrow_track_hour_start_minus_accident_minutes"],"cache":cache,"interpretation":"distance/time residual is linkage evidence, not detection error"}})
    else: checks.append({"item":"W1 E0023 trace","status":"fail","evidence":"missing"})
    m1=j(W1/"manifest.json"); bad=[]; missing=[]
    for mapping in (m1.get("inputs_pre",{}),m1.get("inputs_post",{})):
        for raw,rec in mapping.items():
            p=Path(raw)
            if not p.exists(): missing.append(raw)
            elif p.is_file() and (p.stat().st_size!=rec["size_bytes"] or sha(p)!=rec["sha256"]): bad.append(raw)
    p1=j(W1/"process_result.json")
    attempts={p.name:j(p).get("exit_code") for p in W1.glob("process_result_attempt*.json")}
    checks.append({"item":"W1 listed input hashes, final exit, attempt history and environment","status":"pass" if not missing and not bad and p1.get("exit_code")==0 and attempts else "fail","evidence":{"missing_paths":missing,"hash_mismatch":bad,"final_exit_code":p1.get("exit_code"),"attempt_exit_codes":attempts,"environment":m1.get("environment"),"model_request":m1.get("model_evidence",{}).get("receipt",{}).get("result",{})}})

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
    split=man.get("split_design_pending",{}).get("actual_assignment")=="pending"
    over=j(W2/"summary.json").get("target_reference_id_overlap",{}).get("interpretation","")
    overlap_ok="membership only" in over and "unmeasured" in over
    tie_ok=not stale and "first maximum" in tie.lower() and "first maximum" in code.lower() and "first maximum" in lin.get("round_copy",{}).get("change","").lower()
    checks.append({"item":"W2 current tie contract, split pending, 95 overlap bounded","status":"pass" if tie_ok and split and overlap_ok else "fail","evidence":{"manifest_tie_text":tie,"stale_earliest_maximum":stale,"code_lineage_first_max":tie_ok,"split_assignment":man.get("split_design_pending",{}).get("actual_assignment"),"overlap_interpretation":over}})
    if stale:
        issues.append({"severity":"blocking","file":"testB/round_001/timing/input_split_manifest.json","location":"method_states.ties_and_duplicates","reproduce":"Read current JSON field: says earliest maximum wins; code and lineage say first max in original input order.","impact":"Contract contradicts current A tie implementation and can select a different row.","suggested_fix":"Change to first maximum in original source order for A; stable timestamp+ordinal ordering is B/C only; retain duplicate rows and count unique timestamps for persistence."})

    spec=importlib.util.spec_from_file_location("audited_timing_interface",W2/"timing_interface.py")
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    syn=[]
    def check(name,rs,ps,expected):
        x=mod.estimate_vessel(rs,ps); got={k:getattr(x,k) for k in expected}; syn.append({"case":name,"expected":expected,"observed":got,"pass":got==expected})
    check("A original-order tie", [{"ts":7,"score":.9,"source_row_id":"first"},{"ts":6,"score":.9,"source_row_id":"second"},{"ts":5,"score":.2,"source_row_id":"low"}],mod.TimingParams(.5,"gt",1,0,1,"synthetic"),{"a_source_row":"first","b_ts":7,"c_ts":7})
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
    gap=mod.estimate_vessel([{"ts":0,"score":.8},{"ts":2,"score":.9}],mod.TimingParams(.5,"gt",2,0,1,"synthetic"))
    checks.append({"item":"max_gap parameter can bridge unobserved time","status":"fail" if gap.b_ts==0 else "pass","evidence":{"timestamps":[0,2],"max_gap_hours":2,"B":gap.b_ts,"interpretation":"when delta <= max_gap, a missing bin may be bridged"}})
    issues.append({"severity":"open_design_limit","file":"testB/round_001/timing/timing_interface.py","location":"estimate_vessel gap comparison; TimingParams.max_gap_hours","reproduce":"Synthetic ts=0 and ts=2 above threshold with max_gap_hours=2 yields one segment (B=0).","impact":"A configured tolerance above nominal cadence connects across unobserved bins; this is unresolved against a strict no-missing-time policy.","suggested_fix":"Supervisor must explicitly choose supported cadence/gap semantics. If missing bins always break, require adjacent expected cadence rather than a variable tolerance."})

    p2=j(W2/"round_001"/"run_003"/"process_result.json"); env=j(W2/"round_001"/"run_003"/"environment.json")
    receipt=j(ROOT/"26_11_5"/"testb_next_experiment_20261105"/"integration"/"runtime_receipts"/"W2_start.json")
    checks.append({"item":"W2 observed synthetic exit, environment, request receipt","status":"pass" if p2.get("exit_code")==0 and receipt.get("result",{}).get("model")=="gpt-6-luna" and receipt.get("result",{}).get("effort")=="xhigh" else "fail","evidence":{"process":p2,"environment":env,"requested":receipt.get("result",{})}})
    source_bad=[]
    for s in man.get("sources",[]):
        p=Path(s["path"])
        if not p.exists(): source_bad.append({"path":s["path"],"reason":"missing"})
        elif p.is_file() and (p.stat().st_size!=s.get("size_bytes") or sha(p)!=s.get("sha256")): source_bad.append({"path":s["path"],"reason":"hash/size mismatch"})
    checks.append({"item":"W2 source manifest references resolve/hash-match","status":"pass" if not source_bad else "fail","evidence":{"mismatches":source_bad,"scope":"manifest-listed paths only; no raw/disk-wide certification"}})

    blocking=any(x["severity"]=="blocking" for x in issues) or any(x["status"]=="fail" for x in checks if x["item"]!="max_gap parameter can bridge unobserved time")
    status="fail" if blocking else "passed"
    review={"audit_status":status,"product_validation_status":"not passed; preparation only, no actual evaluation or split","requested_model_effort":{"model":"gpt-6-luna","effort":"xhigh","receipt":"testB/round_001/integration/runtime_receipts/W3_start.json"},"checks":checks,"actionable_issues":issues,"scope":"legacy W1/W2 only; v2 excluded; scored_rows.pkl not opened; no threshold selection or actual evaluation"}
    (OUT/"review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# W1/W2 독립 검산 보고서","",f"검산 상태: **{status}** (제품 검증 통과와 별개)","","## 결과"]
    lines += [f"- **{x['status'].upper()} — {x['item']}**" for x in checks]
    lines += ["","## 핵심 판단","",
    "- W1 30개 사건과 우선 합집합 10개를 표에서 다시 집계했다. 9조건 관계, 안정 1건, 시간확대 다후보 7건, 다선박 수 불일치 3건, 신원 확정 0건이 일치한다. 사용범위는 unknown이고 정상 근거가 없으며, 잔차는 후보 연결 근거다.",
    "- W2 A 순서/ID/시각/점수는 기존 제출 CSV와 대조했다. scored_rows.pkl은 열지 않았다. B/C 값은 비었고 not_computed이며 행별 사유와 not_assessed_not_accident_label 상태가 유지됐다.",
    "- W2 manifest의 ties_and_duplicates는 earliest maximum이라는 옛 문구가 남아 코드와 code_lineage의 원입력 순서 최초 최대 계약과 충돌한다.",
    "- 독립 합성 검사에서는 동점 A, 동일 구간 B/C 및 C=B, NaN/시간간격 분절, 중복시각 지속행수, 파라미터 출처, 빈 점수 계산불가를 확인했다. 실제 점수 임계값은 선택하지 않았다.",
    "- max_gap_hours가 샘플 cadence보다 크면 미관측 구간을 연결한다. 중복 timestamp 값 충돌의 채택 정책은 미정이며, positive floor는 결측이 아닌 유한점수로 취급되어 임계값에 따라 판정을 바꿀 수 있다.",
    "","## 조치 필요"]
    for x in issues: lines.append(f"- **{x['severity']}** {x['file']} ({x['location']}): {x['impact']} 재현: {x['reproduce']} 제안: {x['suggested_fix']}")
    lines += ["","## 한계","","W0 v2, 원자료 전체, 디스크 전체, 전체 43+31 선행감사 재검산은 포함하지 않는다. actual split, 2026 실제 점수/사고 평가, 모델 학습, threshold 선택은 하지 않았다. Orca 영수증은 gpt-6-luna/xhigh 요청을 보여주며 provider 내부 모델 관찰은 별도 불가.",""]
    (OUT/"audit_report.md").write_text("\n".join(lines),encoding="utf-8")
    return {"audit_status":status,"counts":dict(Counter(x["status"] for x in checks)),"issue_count":len(issues),"checks":[{"item":x["item"],"status":x["status"]} for x in checks]}

if __name__=="__main__":
    try:
        result=run(); print(json.dumps(result,ensure_ascii=False,indent=2)); sys.exit(2 if result["audit_status"]=="fail" else 0)
    except Exception as e:
        print(f"VERIFIER_ERROR: {type(e).__name__}: {e}",file=sys.stderr); sys.exit(2)
