"""Summarize saved JSON evidence only; no model or array loading."""
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

R = Path(__file__).resolve().parents[1]
def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))
child = read(R/'artifacts/synthetic_pair_result.json')
receipt = read(R/'logs/pair_01/receipt.json')
mock = read(R/'logs/mock_01/receipt.json')
if receipt['status'] in ('preparing','running'):
    raise RuntimeError('Execution not finished')
result = {
    'schema':'round009_manager_result.v1',
    'updated_at_utc':datetime.now(timezone.utc).isoformat(),
    'status':'completed_synthetic_equivalence_pass' if receipt['status']=='completed' and child['status']=='SYNTHETIC_PAIR_COMPLETE' else 'completed_with_limitations_synthetic_gate_not_passed',
    'mock':{k:mock.get(k) for k in ('status','exit_code','elapsed_seconds','stop_reason','owned_tree_remaining','owned_tree_status')},
    'pair':{k:receipt.get(k) for k in ('status','exit_code','elapsed_seconds','stop_reason','owned_tree_remaining','owned_tree_status','termination_confirmed','preflight_available_ram_gib','minimum_observed_available_ram_gib','peak_sampled_tree_working_set_bytes','source_unchanged','source_snapshot_unchanged','timeout_seconds')},
    'child':{k:child.get(k) for k in ('status','stage','error','fit_completed_count','predict_proba_attempted_count','predict_proba_completed_count','column_adapter_restored','row_adapter_restored','comparison','baseline_probability_check','candidate_probability_check')},
    'event_counts':dict(Counter(x.get('event') for x in child.get('adapter_events',[]))),
    'row_event_counts':dict(Counter(x.get('event') for x in child.get('row_chunk_events',[]))),
    'last_row_event':child.get('latest_row_chunk_event'),
    'evaluation':{'new_f1':None,'new_f1_evaluations':0,'actual_data_replays':0,'parameter_training_fits':0,'independent_f1':None,'official_f1':None,'goal_070_achieved':False},
    'scope':{'raw_data_read':False,'holdout_read':False,'hardware_validation':False,'synthetic_pair_runs':1,'pair_retries':0,'mock_runs':1}
}
(R/'artifacts/result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
