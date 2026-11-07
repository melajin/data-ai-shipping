"""Close the requested comparison; preserve unrelated runtime ownership state."""
import json,hashlib,shutil
from pathlib import Path
from datetime import datetime
P=Path(__file__).resolve().parent;R=P.parent;B=R.parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
v=read(P/'t3_verification.json');decision=read(P/'final_decision.json')
assert v['statistics_match'] and v['raw_status']['actual_raw_metrics_rebuilt'] and v['raw_status']['n_mismatches']==0
checks=[
 {'item':'76h guard of every accident / hod circular<=1 / exact n_rows / all controls / min15','result':'verified_for_3_metrics_primary_design','evidence':'t3_raw_recompute.json; 300 event-metric records match'},
 {'item':'required full indicator/design/stratum/width coverage','result':'available_in_Codex_output','evidence':'codex_independent/t1_gate_results.json 2520 cells, t2 2160 cells'},
 {'item':'zero-inflation suppression','result':'Gemini_original_failed; final_inference_corrected','evidence':'36 forbidden Gemini T1 grid cells, three T2 layers excluded'},
 {'item':'binary exact McNemar as originally named','result':'not_equivalent; explicit_posthoc_1_to_M_supplement','evidence':'fractional rounding rejected; mixture distinguished; M=1 reduction fixture passed'},
 {'item':'Bonferroni','result':'single_K7_candidate; literal_contract_double_correction_fails','evidence':'final_decision.json; both interpretations preserved'},
 {'item':'MDE','result':'approximate_planning_values_and_unattainable_status_reported','evidence':'mde_corrections.json; detailed reports'},
 {'item':'minimum 3 statistics independently implemented','result':'passed_6','evidence':'t3_event_recompute.json; stdlib Wilcoxon/sign/MDE'},
 {'item':'source-provenance and captured process exits','result':'Codex_and_current_audit_captured; Gemini_T1_original_unavailable','evidence':'codex_independent/*execution.json; phase_execution.json; source collision disclosed'},
 {'item':'separate-session independent reviewer','result':'not_performed','evidence':'same author, separate implementation only; original do-yourself constraint retained'},
 {'item':'official accident detection performance','result':'not_evaluated','evidence':'no new model, threshold, 2025 test use or submission'}]
v['source_gate_audit_pending_report']=False;v['acceptance_checks']=checks
v['comparison_task_completed']=True;v['all_original_formal_acceptance_conditions_claimed']=False
save(P/'t3_verification.json',v)
root_v=dict(v,canonical_evidence_root='comparison_20261105',note='Detailed records in comparison_20261105; same operator implementation audit, not separate reviewer session')
save(R/'t3_verification.json',root_v)
stamp=datetime.now().astimezone().isoformat()
record={'closed_at':stamp,'state':'comparison_and_implementation_audit_completed',
 'report':'testB/round_010_20261105/ROUND010_비교및결과보고_20261105.md',
 'final_report':'testB/round_010_20261105/ROUND_REPORT.md','T1':'testB/round_010_20261105/T1_결론상세보고_20261105.md',
 'T2':'testB/round_010_20261105/T2_결론상세보고_20261105.md','candidate':'lin_raw / Tier0_1 / follow-up validation only',
 'normal_Bonferroni':'raw p<0.05/7, adjusted p<0.05','literal_double_correction':'no metric passes; preserved as contract wording branch',
 'raw_independent_implementation_check':{'event_metric_records':v['raw_status']['n_event_metric_records'],'mismatches':v['raw_status']['n_mismatches']},
 'separate_session_reviewer':False,'formal_original_acceptance_all_claimed':False,'new_model_or_submission':False,
 'historical_runtime_ownership':'preexisting active_round/supervisor/workers are preserved; no liveness/ownership claim is made'}
save(P/'closeout_record.json',record)
for name in ['STATUS.json','LEDGER.md','NEXT_SESSION.md']:
    source=B/name;backup=P/('prior_global_'+name)
    if source.exists() and not backup.exists():shutil.copy2(source,backup)
status=read(B/'STATUS.json')
status['latest_completed_analysis_round']='round_010_20261105'
status['round010_comparison_closeout']=record
save(B/'STATUS.json',status)
ledger=B/'LEDGER.md';text=ledger.read_text(encoding='utf-8-sig')
marker='## Round010 Gemini–Codex 비교 완료'
if marker not in text:
    text+='\n\n'+marker+'\n\n'
    text+='| 라운드 | 완료 범위 | 판단과 한계 | 결과 경로 |\n|---|---|---|---|\n'
    text+='| round_010_20261105 | Gemini/Codex 비교, 별도 구현 통계 6개와 원자료 300 사건·지표 기록 재검산, 불일치 0 | K=7 단일 Bonferroni에서 lin_raw/Tier0-1만 후속 후보; 전체·다른 지표 미승격. 이중 보정 문구·1:M 검정 사후 보완·별도 검토자 미참여를 공개 | [최종 보고](round_010_20261105/ROUND_REPORT.md), [상세 비교](round_010_20261105/ROUND010_비교및결과보고_20261105.md) |\n'
    text+='\n이 완료는 비교·계산 감사 범위다. 사고 탐지 성능·실제 표류/예인·공식 제출 또는 원 계약의 모든 독립 검토 조건을 충족했다고 선언하지 않는다. 기존 런타임 감독 소유권·생존 상태는 변경하거나 새로 확인하지 않았다.\n'
    ledger.write_text(text,encoding='utf-8')
next_path=B/'NEXT_SESSION.md';old=next_path.read_text(encoding='utf-8-sig')
heading='# 최신 결과 진입점 — Round010 비교 완료'
if not old.startswith(heading):
    intro=heading+'\n\n사용자의 Round010 완료·Gemini 비교 요청에 대한 최신 결과는 [Round010 최종 보고](round_010_20261105/ROUND_REPORT.md)와 [결론별 상세 비교](round_010_20261105/ROUND010_비교및결과보고_20261105.md)다. T1·T2 상세 결론과 원자료 재계산 증거를 함께 읽는다.\n\n'
    intro+='lin_raw/Tier0-1을 후속 검증 후보로 유지하며, 새 모델·임계값·2025 테스트·공식 제출은 수행하지 않았다. 별도 검토자 세션 승인은 미확인이다. 다음 검증은 [Round010/NEXT_ROUND.md](round_010_20261105/NEXT_ROUND.md)를 따른다. 이 문서는 기존 세션의 소유권 이전 또는 활성화를 대신하지 않는다.\n\n'
    intro+='---\n\n## 보존한 이전 런타임 인계 기록\n\n'
    next_path.write_text(intro+old,encoding='utf-8')
lines=['# Round010 수용 조건 및 완료 범위','',
 '사용자 요청의 비교·결론 보고·계산 감사를 완료했다. 아래에서 원 계약의 계산 충족과 세션/통계 방법의 미해결 조건을 분리한다. 모든 조건이 충족됐다는 표시를 만들지 않는다.','',
 '|항목|판정|증거|','|---|---|---|']
for x in checks:lines.append('|'+x['item']+'|'+x['result']+'|'+x['evidence']+'|')
lines+=['','별도 세션 검토와 모호한 검정 문구를 새 결과를 보기 전에 고정하는 절차는 남아 있다. 원래 Gemini 보고서는 사본에 보존하고 정정 내용은 최신 보고서가 우선한다.']
(R/'ROUND010_수용조건점검_20261105.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
manifest={}
for file in sorted(P.rglob('*')):
    if file.is_file() and file.suffix!='.log' and file.name not in ['closeout_manifest.json','phase_execution.json','final_artifact_checks.json']:manifest[str(file.relative_to(R))]=hashlib.sha256(file.read_bytes()).hexdigest()
for file in [R/n for n in ['README.md','ROUND_REPORT.md','ROUND010_실행보고_20261105.md','ROUND010_비교및결과보고_20261105.md','T1_결론상세보고_20261105.md','T2_결론상세보고_20261105.md','t1_report.md','t2_report.md','t3_audit_report.md','t3_verification.json','t3_recompute.py','ROUND010_수용조건점검_20261105.md','NEXT_ROUND.md','REPRODUCE.md']]:manifest[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
inputs={}
for file in [B/'round_008_linkage_audit_20261105/dev_hourly_scores.parquet',B/'round_008_linkage_audit_20261105/devset_positives.csv',B/'round 9/task1_linkage_audit_167.csv',B/'round 9/verify_round9_review.py']:
    sha=hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):sha.update(block)
    inputs[str(file.relative_to(B))]={'sha256':sha.hexdigest(),'bytes':file.stat().st_size}
save(P/'closeout_manifest.json',{'created_at':stamp,'outputs':manifest,'inputs':inputs,'source_original_T1_Gemini_unavailable':True})
print(json.dumps({'closed':True,'raw_records':v['raw_status']['n_event_metric_records'],'raw_mismatches':v['raw_status']['n_mismatches'],'output_hashes':len(manifest)},ensure_ascii=False))
