import csv, datetime, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
RD=ROOT/'rounds/round_019'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ('ROUND_REPORT.md','review/FINAL_REVIEW.md','manager/closing_decision.json','manager/execution_closeout.json'):
    assert (RD/name).stat().st_size>20,name
assert 'Round020' in (ROOT/'NEXT_SESSION.md').read_text(encoding='utf-8-sig')
decision=read(RD/'manager/closing_decision.json')
closeout=read(RD/'manager/execution_closeout.json')
assert closeout['prior_selected_files_unchanged']
assert all(r['match'] for r in closeout['source_hashes'])
mode_results={}
for mode in ('smoke','mock','audit'):
    run=closeout['runs'][mode]
    outer=run.get('outer'); wrapper=run['files'].get('wrapper_receipt.json'); py=run['files'].get('receipt.json')
    passed=bool(outer and wrapper and py and outer['exit_code']==0 and outer['within_outer_wall_budget'] and outer['map_stable'] and wrapper['state']=='completed' and py['completed'] and outer['approved_map_sha256']==wrapper['approved_map_sha256']==py['approved_map_sha256'])
    mode_results[mode]={'attempted':outer is not None,'passed':passed,'outer_exit_code':outer.get('exit_code') if outer else None,'outer_wall_seconds':outer.get('outer_wall_seconds') if outer else None,'wrapper_state':wrapper.get('state') if wrapper else None,'python_completed':py.get('completed') if py else None,'wrapper_error':wrapper.get('error') if wrapper else None,'python_error':py.get('error') if py else None}
    if mode!='smoke' and mode_results[mode]['attempted']:
        assert mode_results['smoke']['passed']
    if mode=='audit' and mode_results[mode]['attempted']:
        assert mode_results['mock']['passed']
audit_path=RD/'artifacts/saved_m4_audit.json'
audit=read(audit_path) if audit_path.exists() else {}
probes_path=RD/'logs/smoke_01/probe_receipt.json'
probes=read(probes_path).get('probes',[]) if probes_path.exists() else []
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
result={'utc':now,'status':decision['status'],'source_review_approved':(RD/'review/approved_sources.json').exists(),'candidate_frozen':(RD/'code/author_freeze_ack.json').exists(),'modes':mode_results,'all_model_zero_gates_pass':all(v['passed'] for v in mode_results.values()),'probe_count':len(probes),'probe_pass_count':sum(p.get('completed') is True for p in probes),'probe_classifications':[p.get('classification') for p in probes],'model_runs':0,'checkpoint_access':0,'pt_deserialization':0,'project_data_access':0,'new_f1':None,'numeric_saved_checks_pass':audit.get('numeric_saved_checks_pass'),'saved_provenance_audit_pass':audit.get('saved_provenance_audit_pass'),'current_round015_source_matches':audit.get('current_round015_source_matches'),'historical_round015_wrapper_gate':False,'historical_round010_gate':False,'prior_selected_files_unchanged':True,'prior_selected_files_count':len(closeout['prior_files'])}
assert result['all_model_zero_gates_pass']==decision['all_model_zero_gates_pass']
save(RD/'artifacts/result.json',result)
s=read(ROOT/'STATUS.json')
s.update(updated_at_utc=now,current_round='round_019',round_status=result['status'],goal_status='in_progress_not_achieved',current_task=decision['current_task'],next_task=decision['next_task'],active_workers=[],latest_result_report='rounds/round_019/ROUND_REPORT.md',round_completed_at_utc=now,diagnostic_result=result,execution_summary=result)
s['assistant_model_policy']['current_runtime_assistants']=0
s['blockers']=decision['blockers']
s['decision_rules']['current_round']=decision['current_task']
s['decision_rules']['next_gate']=decision['next_task']
s['learning_status']={'learner_understanding_assessed':False,'technical_goal':decision['technical_goal'],'hardware_verified':False}
s['scores']['round_019']={'evaluation_kind':'model_zero_control_and_saved_evidence_audit','new_micro_f1':None,'new_macro_f1':None,'new_f1_evaluations':0,'candidate_adopted':False,'historical_scores_unchanged':True,'result':'rounds/round_019/artifacts/result.json'}
s['review']={'source':'rounds/round_019/review/SOURCE_REVIEW.md','final':'rounds/round_019/review/FINAL_REVIEW.md'}
s['m4_readiness']['next_step']=decision['next_task']
s['m4_readiness']['ready_for_bounded_synthetic_head_gate']=False
s['m4_readiness']['model_zero_saved_audit_pass']=result['all_model_zero_gates_pass']
s['handoff'].update(ready=True,next_session_launched=False,launch_receipt='automation/receipts/round_019_launch.json',next_round='round_020',pause_reason=None,next_session_id=None,accepted_at_utc=None,close_completed_session_status='Current orca agent help has no structured-chat close command; end this manager after accepted handoff; manually close only completed session tab if needed',note='Acceptance authority is round_019_launch.json. Stop after acceptance and do not modify shared state after recipient starts.')
s['next_round_budget']=decision['next_round_budget']
save(ROOT/'STATUS.json',s)
ledger=ROOT/'EXPERIMENT_LEDGER.csv'
with ledger.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
assert not any(r['round_id']=='round_019' for r in rows)
with ledger.open('a',encoding='utf-8',newline='') as f:
    csv.writer(f).writerow(['round_019','2026-11-04T22:52:11Z',now,result['status'],decision['ledger_hypothesis'],'','','model_zero_control_and_saved_audit_no_F1',0,'rounds/round_019/ROUND_REPORT.md',decision['next_task']])
save(RD/'manager/closeout_validation.json',dict(utc=now,required_reports_present=True,status_current_round=s['current_round'],handoff_ready=s['handoff']['ready'],active_workers=[],ledger_round019_rows=1,performance_unchanged=True,frozen_sources_match=True,prior_files_unchanged=True,new_f1=None))
print(json.dumps(result,ensure_ascii=False))
