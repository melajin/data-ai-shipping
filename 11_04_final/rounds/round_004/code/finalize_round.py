"""Manager-only final state publication after independent review; no model/data inference."""
import csv, hashlib, json, pathlib
from datetime import datetime,timezone
R=pathlib.Path(__file__).resolve().parents[3]
Q=R/'rounds/round_004'
def read(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def put(p,obj):
    p=pathlib.Path(p);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(p)
now=datetime.now(timezone.utc).isoformat()
install=read(Q/'environment/install.json')
gate=read(Q/'artifacts/smoke_resource_gate.json')
lineage=read(Q/'lineage/result.json')
review=read(Q/'review/review.json')
smoke=read(Q/'artifacts/smoke.json')
smoke_receipt=read(Q/'logs/smoke_01.receipt.json')
context=read(Q/'context_recovery/result.json')
replay_contract=read(Q/'runtime_author/replay_contract.json')
assert install['status']=='success' and install['elapsed_seconds']<=900
assert gate['free_ram_gib']>=gate['minimum']
assert smoke['status']=='completed' and smoke_receipt['exit_code']==0 and not smoke_receipt['timed_out']
assert len(list((Q/'logs').glob('smoke_0*.receipt.json')))==1
assert not lineage['mismatches']
assert review['review_status'].startswith('PASS'),review
assert not review.get('blocking_issues'),review.get('blocking_issues')
for rel,expected in review['reviewed_artifact_sha256'].items():
    assert digest(R/rel)==expected.lower(),f'Stale review: {rel}'
result={'round':'round_004','status':'completed_with_limitations','finished_utc':now,
 'installation':{'status':install['status'],'elapsed_seconds':install['elapsed_seconds'],'wheel_bytes':read(Q/'environment/wheels.json')['total_bytes'],'pip_check_exit_code':read(Q/'logs/05_pip_check.receipt.json')['exit_code'],'source':'environment/install.json'},
 'runtime_smoke':{'status':'passed_after_user_requested_ram_recheck','free_ram_gib':gate['free_ram_gib'],'minimum_free_ram_gib':gate['minimum'],'resource_checks_at_launch':2,'initial_free_ram_gib':2.1962547302246094,'smoke_processes_started':1,'checkpoint_loads':1,'synthetic_context_bindings':1,'elapsed_seconds':smoke_receipt['elapsed_seconds'],'parameter_count':smoke['model']['parameter_count'],'repeat_max_delta':smoke['checks']['repeat_max_absolute_probability_delta'],'source':'artifacts/smoke.json'},
 'lineage':{'status':lineage['status'],'counts':lineage['counts'],'source':'lineage/result.json','original_context_order_verified':False,'original_feature_rows_exactly_reproduced':False,'original_model_probabilities_replayed':False,'author_reported_successful_audit_invocations':8,'provenance_limitation':'Result metadata hardcodes iteration7; author transcript audit counts8. Seven earlier snapshots not separately retained. See lineage/DIAGNOSTIC_HISTORY.md.'},
 'new_parameter_fits':0,'real_vessel_inference_calls':0,'new_f1_evaluations':0,'independent_score':None,'official_score':None,
 'context_recovery':{'status':context['status'],'split_manifest_sha256':context['manifest']['sha256'],'manifest_matches_original_fingerprints':context['manifest']['matches_frozen_rule_and_seed42_parent_fingerprint'],'ordered_inner_digest_comparison_executed':context['ordered_inner_digest']['comparison_executed'],'export_executed':False,'candidate_source_sha256':context['candidate']['sha256'],'known_holdout_reused_metadata':True,'holdout_feature_label_probability_rows_read':0,'source':'context_recovery/result.json'},
 'replay_runtime_contract':{'status':replay_contract['status'],'source':'runtime_author/replay_contract.json','CPU_two_query_vs_historical_GPU_equivalence_measured':False},
 'review_status':review['review_status'],'learning_status':'technical preparation recorded; learner competency not assessed','next_round':'round_005',
 'next_task':'Frozen original-context and inference-contract replay on fixed small INNER query set, bounded CPU pilot; no new F1 or parameter training',
 'sources':{str(p.relative_to(R)):digest(p) for p in [Q/'ROUND_REPORT.md',Q/'NEXT_SESSION_DRAFT.md',Q/'lineage/result.json',Q/'review/review.json',Q/'environment/install.json',Q/'artifacts/smoke_resource_gate.json',Q/'artifacts/smoke.json',Q/'context_recovery/result.json',Q/'context_recovery/build_context.py',Q/'runtime_author/replay_contract.json',Q/'code/manage_runtime.py',Q/'code/probe_tabicl_runtime.py',Q/'USER_STEERING_AMENDMENT.json']}}
put(Q/'artifacts/result.json',result)
status=read(R/'STATUS.json')
status.update(updated_at_utc=now,current_round='round_004',round_status='completed_with_limitations',manager_session='codex_53b6ac45_0a2c_4a1a_b5d5_2624c7a28d9e',active_workers=[],current_task='Round004 environment/input audit and first CPU synthetic smoke completed after authorized RAM recheck',next_task=result['next_task'],goal_status='in_progress_not_achieved')
status['paths']['round']='rounds/round_004'
status['scores']['round_004']={'new_micro_f1':None,'new_macro_f1':None,'new_f1_evaluations':0,'candidate_adopted':False,'historical_scores_unchanged':True,'result':'rounds/round_004/artifacts/result.json'}
status['assistant_model_policy']['current_runtime_assistants']=0
status['budget']=read(Q/'configs/budget.json')
status['budget']['user_steering_amendment']='rounds/round_004/USER_STEERING_AMENDMENT.json'
status['decision_rules']={'current_round':'Runtime acquisition, one synthetic smoke and development-only lineage audit; no new F1','runtime_gate':'InitialRAM2.196GiB blocked; user requested recheck and launch gate4.045GiB passed; firstsmoke13.047s exit0','next_gate':'Original ordered FIT/INNER IDs and source-based transforms before real-vessel replay','holdout':'No individual feature/label/prediction reads before exposure audit and frozen evaluation plan'}
status['blockers']=[]
status['unresolved']=[s for s in status['unresolved'] if not s.startswith('Torch/TabICL absent') and not s.startswith('A original feature/context/order')]
status['unresolved']+=['CPU synthetic smoke passed; full3144-row FIT context cost and original saved probabilities not replayed','Candidate F156+missing312 path supported by source/schema and6median checks; original FIT/INNER order/internal permutations and saved output replay need context-recovery evidence and original-model replay','Lineage final audit independently checked; seven earlier diagnostic snapshots not retained and iteration metadata undercounts8 as7, see DIAGNOSTIC_HISTORY.md']
status['unresolved']+=['Original split manifest hash matches frozen rule and parent fingerprint; source-reviewed exporter not executed, orderedINNERdigest comparison pending','Split metadata known_holdout_reused=true; detailed holdout exposure/independence audit remains unresolved and no holdout individual values were read']
status['handoff']={'ready':True,'next_session_launched':False,'launch_receipt':'automation/receipts/round_004_launch.json','launcher_owner':'root','launcher':'automation/Start-NextSession.ps1','next_round':'round_005','receipt_directory':'automation/receipts/','pause_reason':None,'authorization':'User explicitly permits learning/local experiments/fresh-manager handoffs without repeated approval'}
status['learning_status']=result['learning_status']
ledger=R/'EXPERIMENT_LEDGER.csv'
with ledger.open(encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
assert not any(x['round_id']=='round_004' for x in rows),'Round already published'
rows.append({'round_id':'round_004','started_at_utc':'2026-11-04T16:45:47Z','finished_at_utc':now,'status':'completed_with_limitations','hypothesis':'Pinned CPU environment, successful first synthetic smoke and development-only F156 lineage support original replay preparation; no performance experiment','baseline_micro':'0.5930133966423605','candidate_micro':'','evaluation_kind':'synthetic_runtime_and_development_input_audit_no_new_F1','new_fits':'0','result_report':'rounds/round_004/ROUND_REPORT.md','next_task':result['next_task']})
tmp=ledger.with_suffix('.csv.tmp')
with tmp.open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
tmp.replace(ledger)
put(R/'STATUS.json',status)
nextpath=R/'NEXT_SESSION.md';nexttmp=R/'NEXT_SESSION.md.tmp';nexttmp.write_bytes((Q/'NEXT_SESSION_DRAFT.md').read_bytes());nexttmp.replace(nextpath)
print(json.dumps({'round':status['current_round'],'handoff_ready':status['handoff']['ready'],'result':str(Q/'artifacts/result.json'),'finished_utc':now,'next_session_sha256':digest(nextpath)}))
