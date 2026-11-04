import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROUND = Path(__file__).resolve().parent
ROOT = ROUND.parent.parent
def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

now = datetime.now(timezone.utc).isoformat()
status = read(ROOT / 'STATUS.json')
assert status['current_round'] == 'round_003'
assert status['manager_session'] == os.environ['ORCA_AGENT_SESSION_ID']
result = read(ROUND / 'artifacts/result.json')
review = read(ROUND / 'review/review.json')
comparison = read(ROUND / 'review/artifact_comparison.json')
assert comparison['review_status'] == 'PASS'
assert not comparison['mismatches']
assert not result['selected_vs_raw_progress_gate']['all_criteria_met']
assert (ROUND / 'ROUND_REPORT.md').is_file()
receipts = [read(p) for p in sorted((ROUND / 'logs').glob('launch_receipt_*.json'))]
assert all(r['exit_code'] == 0 and not r['timed_out'] for r in receipts)
scoring = [r for r in receipts if r['mode'] == 'score']
assert len(scoring) == 1
mean = result['metrics']['arithmetic_mean_across_seeds']['all']
status.update(updated_at_utc=now, goal_status='in_progress_not_achieved',
              current_round='round_003', round_status='completed_with_limitations_not_adopted',
              current_task='Round003 R0 completed and independently checked; next manager owns Round004',
              next_task='Round004 isolated CPU TabICL2.2.0 runtime acquisition, bounded synthetic smoke, development-only input lineage audit; no new actual-data F1 or parameter training',
              active_workers=[], latest_result_report='rounds/round_003/ROUND_REPORT.md',
              round_completed_at_utc=now)
status['paths']['round'] = 'rounds/round_003'
status['assistant_model_policy']['current_runtime_assistants'] = 0
status['scores']['round_003'] = {
    'evaluation_population': result['evaluation_population'], 'seeds': [42, 2026],
    'aggregation': 'arithmetic mean of seed metrics; not probability ensemble and not 11794 independent vessels',
    'mean_metrics': mean,
    'correct_by_seed': {s: {method: int(result['metrics']['by_seed'][s]['all'][method]['correct_weighted'])
                           for method in mean} for s in ['42', '2026']},
    'selected_factors': {'42': [1, 1.5, 1], '2026': [1, 1, 1]},
    'progress_gate': result['selected_vs_raw_progress_gate'], 'candidate_adopted': False,
    'result': 'rounds/round_003/artifacts/result.json',
    'historical_baseline_unchanged': True}
status['budget'] = {'manager_round_minutes':45, 'compute_minutes':15, 'max_new_fits':0,
                    'concurrent_large_compute':1, 'threads_max':3,
                    'minimum_free_ram_gib_before_large_compute':1.5,
                    'manager_deadline_utc':'2026-11-04T16:58:25Z', 'm4_readiness_minutes_max':10}
status['decision_rules'] = {'current_round':'Frozen saved probability R0; seed/fold INNER-only grid [1,1.5,2,2.5,3]',
    'selection':'micro maximum subject to no macro drop and class/day macro losses<=.01; tie nearest1 then smaller; support fallback raw',
    'advance':'mean micro gain>=.005; both seeds positive; paired CI lower>0; no mean macro loss; class/day losses<=.01',
    'holdout':'No individual feature/label/prediction reads before exposure audit and frozen evaluation plan'}
status['execution_summary'] = {'successful_model_fits_total':0, 'new_model_inference':False,
    'scoring_runs':1, 'preflight_runs':2, 'score_exit_code':0,
    'score_compute_seconds':scoring[0]['elapsed_seconds'],
    'all_runner_seconds':sum(r['elapsed_seconds'] for r in receipts),
    'all_owned_compute_processes_finished':True, 'new_independent_evaluation':False,
    'hardware_validation':False, 'note':'Runner durations exclude authoring, review and readiness metadata probes'}
status['review'] = {'verdict':'PASS_WITH_DOCUMENTED_LIMITATIONS', 'protocol':'PASS', 'adoption':'REJECT',
    'source':'rounds/round_003/review/review.json', 'artifact_comparison':'rounds/round_003/review/artifact_comparison.json',
    'independent_probability_metric_and_factor_checks':True, 'bootstrap_recomputed_by_reviewer':True}
status['blockers'] = []
for limitation in [
    'Historical INNER ID-list original ordering/digest not reconstructed; prediction file hashes and membership verified',
    'A original feature/context/order/class permutation replay incomplete; source and saved preprocessor imply312 columns but settings say no missing flags',
    'Torch/TabICL absent in three inspected local environments; exact checkpoint located; isolated CPU environment is feasible next step']:
    if limitation not in status['unresolved']:
        status['unresolved'].append(limitation)
status['next_round_budget'] = {'manager_minutes':45, 'installation_download_minutes_max':15,
    'new_download_bytes_max':1073741824, 'synthetic_smoke_max_runs':2,
    'synthetic_smoke_seconds_each_max':180, 'new_parameter_training_fits_max':0,
    'actual_data_f1_evaluations_max':0, 'concurrent_large_compute':1,'threads_max':3,
    'minimum_free_ram_gib_before_model_load':3, 'status':'authorized_continuation'}
status['m4_readiness'] = {'source':'rounds/round_003/m4_readiness/readiness.json',
    'checkpoint_exact_sha256_found':True, 'historical_cuda_runtime_reproduced':False,
    'ready_for_m4_training':False, 'next_step':'isolated CPU runtime and input lineage recovery'}
status['handoff'].update(ready=True, next_session_launched=False,
    launch_receipt='automation/receipts/round_003_launch.json', next_round='round_004',pause_reason=None)
status['learning_status'] = 'Technical audit completed; learner explanation competency not assessed; LEARNING_NOTES.md saved'

ledger = ROOT / 'EXPERIMENT_LEDGER.csv'
with ledger.open(encoding='utf-8-sig', newline='') as stream:
    reader = csv.DictReader(stream)
    fieldnames = reader.fieldnames
    rows = list(reader)
assert not any(row['round_id'] == 'round_003' for row in rows), 'Do not duplicate completed round ledger'
rows.append(dict(round_id='round_003', started_at_utc='2026-11-04T16:13:25Z',finished_at_utc=now,
    status='completed_with_limitations_not_adopted',
    hypothesis='Unchanged TabICL saved probabilities: raw vs old vs INNER-selected trap decision multiplier',
    baseline_micro=mean['A_raw']['micro_f1'],candidate_micro=mean['A_micro_select']['micro_f1'],
    evaluation_kind='repeated_development_saved_probability_decision_audit_two_seed_mean',
    new_fits=0,result_report='rounds/round_003/ROUND_REPORT.md',next_task=status['next_task']))
with ledger.open('w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader(); writer.writerows(rows)
handoff = (ROUND / 'NEXT_SESSION_DRAFT.md').read_text(encoding='utf-8')
(ROOT / 'NEXT_SESSION.md').write_text(handoff, encoding='utf-8')
write(ROOT / 'STATUS.json', status)
write(ROUND / 'completion_manifest.json', {'completed_at_utc':now,
    'files':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'STATUS.json',ledger,ROOT/'NEXT_SESSION.md',
    ROUND/'ROUND_REPORT.md',ROUND/'review/review.json',ROUND/'artifacts/result.json']},
    'score_process_finished':True,'next_session_not_yet_launched':True})
print(json.dumps({'status':'round003_saved_ready_for_handoff','completed_at_utc':now,'current_round':status['current_round']},ensure_ascii=False))
