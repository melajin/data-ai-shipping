import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
R = ROOT / 'rounds/round_008'
def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

if __name__ == '__main__':
    receipt = read(R/'logs/pilot_01/receipt.json')
    pilot = read(R/'artifacts/pilot_attempt_001/pilot_result.json')
    mock_path = R/'logs/mock_02/receipt.json'
    mock = read(mock_path if mock_path.exists() else R/'logs/mock_01/receipt.json')
    passed = bool((pilot.get('comparison') or {}).get('small_replay_gate_pass')) and receipt['status'] == 'completed'
    events = pilot.get('adapter_events', [])
    counts = {k: sum(e.get('event') == k for e in events) for k in ['column_chunk_call_started', 'column_chunk_started', 'column_chunk_completed', 'column_chunk_call_completed']}
    now = datetime.now(timezone.utc).isoformat()
    result = {
        'schema': 'round008_manager_result.v1', 'updated_at_utc': now,
        'status': 'completed_actual_replay_pass' if passed else 'completed_with_limitations_replay_not_passed',
        'mock': {k: mock.get(k) for k in ['run_id','status','exit_code','elapsed_seconds','owned_tree_remaining']},
        'pilot': {k: receipt.get(k) for k in ['status','exit_code','elapsed_seconds','stop_reason','preflight_available_ram_gib','minimum_observed_available_ram_gib','peak_sampled_tree_working_set_bytes','owned_tree_remaining','termination_confirmed']},
        'child_last_stage': pilot.get('stage'), 'child_raw_status': pilot.get('status'),
        'predict_proba_attempted_count': pilot.get('predict_proba_attempted_count',0),
        'predict_proba_completed_count': pilot.get('predict_proba_completed_count',0),
        'chunk_event_counts': counts, 'last_adapter_event': pilot.get('latest_adapter_event'),
        'last_completed_chunk': pilot.get('last_completed_column_chunk'),
        'current_chunk': pilot.get('current_chunk'),
        'adapter_restored_recorded': pilot.get('adapter_restored',False),
        'probabilities': pilot.get('probabilities'), 'comparison': pilot.get('comparison'),
        'actual_replay_gate_pass': passed,
        'evaluation': {'new_f1':None,'new_f1_evaluations':0,'new_parameter_training_fits':0,'independent_f1':None,'official_f1':None,'goal_070_achieved':False,'historical_scores_unchanged':True},
        'scope': {'holdout_rows_read':0,'raw_data_read':False,'reexports':0,'full_input_reverification_runs':0,'hardware_validation':False,'pilot_retries':0},
    }
    write(R/'artifacts/result.json',result)
    s=read(ROOT/'STATUS.json')
    s.update(updated_at_utc=now,current_round='round_008',round_status=result['status'],round_completed_at_utc=now,latest_result_report='rounds/round_008/ROUND_REPORT.md',active_workers=[])
    s['assistant_model_policy']['current_runtime_assistants']=0
    s['paths']['round']='rounds/round_008'
    s['scores']['round_008']={'evaluation_kind':'fixed_development_two_query_chunk16_replay','new_micro_f1':None,'new_macro_f1':None,'actual_replay_gate_pass':passed,'predict_attempted':result['predict_proba_attempted_count'],'predict_completed':result['predict_proba_completed_count'],'candidate_adopted':False,'historical_scores_unchanged':True,'result':'rounds/round_008/artifacts/result.json'}
    s['execution_summary']=result
    s['m4_readiness']['ready_for_m4_training']=False
    s['m4_readiness']['next_step']='See NEXT_SESSION.md; no automatic M4 training expansion'
    s['handoff'].update(ready=True,next_session_launched=False,next_round='round_009',launch_receipt='automation/receipts/round_008_launch.json',completed_session_id=s['manager_session'],next_session_id=None,accepted_at_utc=None)
    s['next_manager_session']=None
    s['review']={'final_review':'rounds/round_008/review/FINAL_REVIEW.md','final_review_json':'rounds/round_008/review/final_review.json'}
    write(ROOT/'STATUS.json',s)
    ledger=ROOT/'EXPERIMENT_LEDGER.csv'
    with ledger.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f)); fields=list(rows[0])
    if any(row['round_id']=='round_008' for row in rows):
        raise RuntimeError('Ledger already includes round008; do not duplicate')
    with ledger.open('a',encoding='utf-8',newline='') as f:
        csv.DictWriter(f,fieldnames=fields).writerow(dict(round_id='round_008',started_at_utc=read(R/'manager/startup.json')['started_utc'],finished_at_utc=now,status=result['status'],hypothesis='Fixed full FIT context two-query replay using only verified column chunk16',baseline_micro='',candidate_micro='',evaluation_kind='fixed_development_replay_diagnostic_no_F1',new_fits=0,result_report='rounds/round_008/ROUND_REPORT.md',next_task='See frozen NEXT_SESSION.md for changed hypothesis and finite resource budget'))
    print(json.dumps(result,ensure_ascii=False,indent=2))
