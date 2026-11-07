import csv, datetime, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
RD=ROOT/'rounds/round_018'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for path in ('review/FINAL_REVIEW.md','review/NEXT_REPAIR_SCOPE.md','ROUND_REPORT.md'):
    assert (RD/path).stat().st_size>50,path
assert 'Round019' in (ROOT/'NEXT_SESSION.md').read_text(encoding='utf-8-sig')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
outer=read(RD/'manager/smoke_launch.json')
wrapper=read(RD/'logs/smoke_01/wrapper_receipt.json')
probes=read(RD/'logs/smoke_01/probe_receipt.json')['probes']
closeout=read(RD/'manager/execution_closeout.json')
assert outer['exit_code']==1 and wrapper['state']=='failed' and len(probes)==4
assert all(p['completed'] for p in probes[:3]) and probes[3]['classification']=='indeterminate'
assert not (RD/'logs/mock_01/execution.claim').exists()
assert not (RD/'logs/audit_01/execution.claim').exists()
assert closeout['prior_selected_files_unchanged'] and all(r['match'] for r in closeout['source_hashes'])
result=dict(status='completed_smoke_timeout_indeterminate',source_review_approved=True,candidate_frozen=True,first_writer_fixed=True,smoke_wrapper_attempts=1,smoke_probe_children=4,expected_normal_probe_passes=3,timeout_classification='indeterminate',timeout_os_code_recorded=-1,timeout_exit_timestamp_valid=False,timeout_wait_false_elapsed_seconds=probes[3]['wait_returned_elapsed_seconds'],timeout_deadline_observed_seconds=probes[3]['deadline_observed_elapsed_seconds'],timeout_exit_observed_seconds=probes[3]['exit_observed_elapsed_seconds'],auditor_calls=0,mock_runs=0,saved_audit_runs=0,model_runs=0,new_f1=None,numeric_saved_checks_pass=None,saved_provenance_audit_pass=None,historical_round015_wrapper_gate=False,historical_round010_overall_gate=False,prior_selected_files_unchanged=True,prior_selected_files_count=len(closeout['prior_files']),outer_exit_code=outer['exit_code'],outer_wall_seconds=outer['outer_wall_seconds'],whole_mode_budget_pass=outer['within_outer_wall_budget'])
(RD/'artifacts').mkdir(exist_ok=True)
save(RD/'artifacts/result.json',dict(utc=now,**result))
s=read(ROOT/'STATUS.json')
s.update(updated_at_utc=now,current_round='round_018',round_status=result['status'],goal_status='in_progress_not_achieved',current_task='Round018 completed: boolean writer repaired; three expected normal probes passed; timeout remained indeterminate',next_task='Round019 minimal explicit deadline-liveness and bounded terminal-evidence repair, then model-zero smoke/mock/saved audit',active_workers=[],latest_result_report='rounds/round_018/ROUND_REPORT.md',round_completed_at_utc=now,diagnostic_result=result)
s['assistant_model_policy']['current_runtime_assistants']=0
s['decision_rules']['current_round']='Frozen boolean repair runtime-tested; smoke failed at timeout classifier; no retries, mock/audit/model unexecuted'
s['decision_rules']['next_gate']='Separate deadline liveness from last Wait; verify terminal evidence; same-map model-zero smoke/mock/audit before estimator integration'
s['blockers']=['Timeout classifier requires last short wait to reach deadline; monitor-overrun path is indeterminate','Killed probe ExitTime is 1601 sentinel; terminal evidence requires bounded wait and validity separation','Saved numeric/provenance audit unexecuted; no full-estimator integration yet']
s['learning_status']={'learner_understanding_assessed':False,'technical_goal':'Partial: first writer and 3 expected normal probes pass; timeout and saved-audit gates incomplete','hardware_verified':False}
s['execution_summary']={'process_smoke_runs':1,'process_smoke_completed':False,'smoke_probe_children':4,'normal_probe_passes':3,'auditor_calls':0,'mock_runs':0,'saved_audit_runs':0,'model_runs':0,'checkpoint_access':0,'pt_deserialization':0,'project_data_access':0,'new_f1':None,'source_frozen':True,'source_approved':True,'outer_exit_code':outer['exit_code'],'outer_wall_seconds':outer['outer_wall_seconds']}
s['scores']['round_018']={'evaluation_kind':'model_zero_process_control_smoke','new_micro_f1':None,'new_macro_f1':None,'new_f1_evaluations':0,'candidate_adopted':False,'historical_scores_unchanged':True,'result':'rounds/round_018/artifacts/result.json'}
s['review']={'source':'rounds/round_018/review/SOURCE_REVIEW.md','final':'rounds/round_018/review/FINAL_REVIEW.md'}
s['m4_readiness']['next_step']=s['next_task']
s['m4_readiness']['ready_for_bounded_synthetic_head_gate']=False
s['handoff'].update(ready=True,next_session_launched=False,launch_receipt='automation/receipts/round_018_launch.json',next_round='round_019',pause_reason=None,next_session_id=None,accepted_at_utc=None,note='Acceptance authority is round_018_launch.json; stop after prompt acceptance and do not mutate shared state after recipient starts.')
s['next_round_budget']={'manager_minutes_max':25,'document_reserve_minutes':3,'process_probe_batch_max':1,'probe_children_max':4,'probe_seconds_max':15,'mock_max_runs':1,'mock_seconds_max':30,'saved_audit_max_runs':1,'saved_audit_seconds_max':30,'model_calls':0,'checkpoint_access':0,'actual_data_or_f1':0,'start_available_ram_gib_min':0.5,'expected_peak_mib':200,'retries':0}
save(ROOT/'STATUS.json',s)
ledger=ROOT/'EXPERIMENT_LEDGER.csv'
with ledger.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
assert not any(r['round_id']=='round_018' for r in rows),'Do not duplicate ledger row'
with ledger.open('a',encoding='utf-8',newline='') as f:
    csv.writer(f).writerow(['round_018','2026-11-04T22:38:50Z',now,result['status'],'Minimal boolean fix passed first writer; three probes passed; monitor-overrun timeout classification and terminal timestamp unresolved','','','model_zero_smoke_no_F1',0,'rounds/round_018/ROUND_REPORT.md',s['next_task']])
save(RD/'manager/closeout_validation.json',dict(utc=now,required_reports_present=True,status_current_round=s['current_round'],handoff_ready=s['handoff']['ready'],active_workers=s['active_workers'],ledger_round018_rows=1,performance_unchanged=True,frozen_sources_match=True,prior_files_unchanged=True,new_f1=None))
print(json.dumps({'completed':True,'result':result,'handoff_ready':True},ensure_ascii=False))
