"""Summarize saved JSON/JSONL; no model imports, prediction or input array read."""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

R = Path(__file__).resolve().parents[1]

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {}

receipt = read(R / 'logs/pilot_01/receipt.json')
child = read(R / 'artifacts/pilot_attempt_001/pilot_result.json')
mocks = [read(p) for p in sorted((R / 'logs').glob('mock_*/receipt.json'))]
if receipt.get('status') in ('preparing', 'running'):
    raise RuntimeError('Pilot still active')
events = Counter()
last_events = {}
journal_parse_errors = []
journal = R / 'artifacts/pilot_attempt_001/progress.jsonl'
if journal.exists():
    with journal.open(encoding='utf-8') as f:
        for line_number,line in enumerate(f,1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                journal_parse_errors.append({'line':line_number,'error':str(error)})
                continue
            kind = event.get('event', event.get('event_type', event.get('stage', 'unknown')))
            events[kind] += 1
            last_events[kind] = event
comparison = child.get('comparison') or {}
prob = child.get('probabilities') or {}
reference_evidence = child.get('reference_evidence') or {}
values = prob.get('values') or []
refs = [r['p0_p3'] for r in (child.get('reference_evidence') or {}).get('selected_reference_probability_rows', [])]
shape_ok = len(values) == 2 and all(len(r) == 4 for r in values)
reference_ok = len(refs) == 2 and all(len(r) == 4 for r in refs)
finite_range = shape_ok and all(math.isfinite(v) and 0 <= v <= 1 for r in values for v in r)
max_row_error = max(abs(sum(r)-1) for r in values) if finite_range else None
maxabs = max(abs(v-w) for r,s in zip(values,refs) for v,w in zip(r,s)) if finite_range and reference_ok else None
argmax = lambda r: max(range(4), key=lambda i:r[i])
argmax_equal = bool(finite_range and reference_ok and all(argmax(r)==argmax(s) for r,s in zip(values,refs)))
gates = {
    'one_bounded_pilot': receipt.get('launched') is True and receipt.get('timeout_seconds')==480 and receipt.get('compute_timeout_seconds')==470 and receipt.get('cleanup_max_seconds')==10,
    'matching_mock_gate': any(m.get('status')=='completed' and m.get('exit_code')==0 and m.get('stop_reason') is None and m.get('owned_tree_status')=='clear' and (m.get('approved_sources') or {}).get('sha256')==(receipt.get('approved_sources') or {}).get('sha256') and bool((m.get('approved_sources') or {}).get('sha256')) for m in mocks),
    'wrapper_completed': receipt.get('status')=='completed' and receipt.get('exit_code')==0 and receipt.get('stop_reason') is None,
    'owned_tree_clear': receipt.get('owned_tree_status')=='clear' and receipt.get('owned_tree_remaining')==[],
    'resource_complete': receipt.get('resource_sampling_complete') is True,
    'time_bound': receipt.get('postexit_within_timeout') is True and receipt.get('elapsed_seconds',float('inf'))<=480,
    'start_ram_gate': receipt.get('preflight_available_ram_gib',0)>=4,
    'sources_unchanged': all(receipt.get(k) is True for k in ('source_unchanged','adapter_source_unchanged','source_snapshot_unchanged')),
    'child_complete': child.get('status')=='PILOT_COMPLETE',
    'fit_and_predict_counts': child.get('fit_returned') is True and child.get('predict_proba_attempted_count')==1 and child.get('predict_proba_completed_count')==1,
    'restored': all(child.get(k) is True for k in ('adapter_restored','row_adapter_restored','icl_observer_restored','all_managers_restored')),
    'full_icl_context': child.get('full_icl_context_verified') is True,
    'input_shuffle_unchanged': child.get('input_and_shuffle_state_unchanged') is True,
    'canonical_class_order': prob.get('class_order')==[0,1,2,3] and child.get('class_order')==[0,1,2,3],
    'fixed_query_ids': prob.get('query_ids')==['36001915','31703435'],
    'fixed_reference_scope': reference_evidence.get('rows_read')==2 and reference_evidence.get('fields_used')==['rfid_id','p0','p1','p2','p3'] and reference_evidence.get('labels_used') is False and reference_evidence.get('label_fields_accessed') is False and [r.get('rfid_id') for r in reference_evidence.get('selected_reference_probability_rows',[])]==['36001915','31703435'],
    'finite_range_shape': finite_range,
    'row_sum': max_row_error is not None and max_row_error<=1e-5,
    'reference_tolerance': maxabs is not None and maxabs<=1e-4,
    'argmax_equal': argmax_equal,
    'reported_gate': comparison.get('small_replay_gate_pass') is True,
    'reported_values_agree': maxabs is not None and comparison.get('max_abs_probability_difference')==maxabs and comparison.get('argmax_equal')==argmax_equal and comparison.get('exact_numeric_equal_after_float64_parse')==(values==refs),
    'journal_complete': not journal_parse_errors,
}
passed = all(gates.values())
keys = ('status','exit_code','elapsed_seconds','stop_reason','launched',
        'owned_tree_remaining','owned_tree_status','termination_confirmed',
        'preflight_available_ram_gib','minimum_observed_available_ram_gib',
        'peak_sampled_tree_working_set_bytes','source_unchanged','source_snapshot_unchanged',
        'timeout_seconds','finished_utc','resource_sampling_complete')
result = {
    'schema':'round010_manager_result.v1',
    'updated_at_utc':datetime.now(timezone.utc).isoformat(),
    'status':'completed_fixed_actual_replay_pass' if passed else 'completed_with_limitations_replay_not_passed',
    'independent_saved_json_checks':{'gates':gates,'max_abs_probability_difference':maxabs,
        'max_abs_row_sum_error_float64':max_row_error,'argmax_equal':argmax_equal,
        'exact_numeric_equal':bool(finite_range and reference_ok and values==refs),
        'scope':'saved two-query JSON only; no new inference or F1'},
    'pilot':{k:receipt.get(k) for k in keys},
    'mocks':[{k:m.get(k) for k in keys} for m in mocks],
    'child':{k:child.get(k) for k in ('status','stage','current_stage','error','fit_returned',
              'predict_proba_attempted_count','predict_proba_completed_count',
              'adapter_restored','row_adapter_restored','icl_observer_restored','all_managers_restored',
              'comparison','input_and_shuffle_state_unchanged','latest_adapter_event',
              'last_completed_row_chunk','current_row_chunk','adapter_event_counts',
              'full_icl_context_verified','icl_forward_attempted_count','icl_forward_completed_count',
              'chunk_progress_summary')},
    'journal_event_counts':dict(events),
    'journal_parse_errors':journal_parse_errors,
    'last_event_by_kind':last_events,
    'evaluation':{'new_f1':None,'new_f1_evaluations':0,'parameter_training_fits':0,
                  'independent_f1':None,'official_f1':None,'goal_070_achieved':False},
    'scope':{'raw_data_read':False,'holdout_read':False,'hardware_validation':False,
             'pilot_runs':int(receipt.get('launched') is True),'pilot_retries':0,
             'mock_runs':sum(m.get('launched') is True for m in mocks)},
}
(R/'artifacts/result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='last_event_by_kind'},ensure_ascii=False,indent=2))
