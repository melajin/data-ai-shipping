"""Persist reviewed round007 outcome; no data/model imports or computation."""
import csv
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
ROUND = ROOT / 'rounds/round_007'
def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))
def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

now = datetime.now(timezone.utc).isoformat()
result = read(ROUND/'artifacts/result.json')
verified = read(ROUND/'review/synthetic_artifact_verification.json')
review = read(ROUND/'review/final_review.json')
assert verified['all_checks_pass'] and review['disposition']=='synthetic_pair_and_artifacts_pass_with_limited_scope'
assert result['synthetic_pair']['comparison']['max_abs_probability_difference']==0
status = read(ROOT/'STATUS.json')
status.update(updated_at_utc=now, current_round='round_007', round_status='completed_synthetic_equivalence_pass',
    current_task='Round007 complete: source/mock/synthetic equivalence and independent saved-artifact verification passed',
    next_task='Round008 configure-before-install mock and one bounded chunk16 FIT3144/two-query actual replay; no training or F1',
    active_workers=[], latest_result_report='rounds/round_007/ROUND_REPORT.md', round_completed_at_utc=now, next_manager_session=None)
status['paths']['round']='rounds/round_007'
status['assistant_model_policy']['current_runtime_assistants']=0
status['scores']['round_007']={
    'evaluation_kind':'tiny_synthetic_equivalence_only', 'new_micro_f1':None, 'new_macro_f1':None,
    'actual_data_prediction_calls':0, 'synthetic_predict_attempted':2, 'synthetic_predict_completed':2,
    'synthetic_max_abs_probability_difference':0.0, 'synthetic_argmax_equal':True, 'synthetic_exact_numeric_equal':True,
    'candidate_adopted':False, 'goal_070_achieved':False, 'historical_scores_unchanged':True,
    'result':'rounds/round_007/artifacts/result.json'}
status['budget'].update(mock_actual_runs=2, synthetic_pair_actual_runs=1, synthetic_pair_seconds=30.078,
    checkpoint_loads=1, pretrained_context_fits=1, parameter_training_fits=0, predict_proba_attempted=2,
    predict_proba_completed=2, new_f1_evaluations=0, synthetic_artifact_verifications_completed=1)
status['decision_rules'].update(current_round='Source proof, corrected wrapper mock02 and one synthetic equivalence pair passed',
    runtime_gate='Pair start4.787761688GiB; observed minimum4.139598846GiB; completed30.078s; no guard stop; no owned process remains',
    next_gate='Explicit CPU COL configure before adapter install, source/mock review, then one full-context actual replay at historical probability tolerance1e-4')
status['blockers']=['Actual-vessel FIT3144 two-query CPU equivalence remains unmeasured',
    'Full-context adapter total memory requirement remains unmeasured; row/ICL stages unchanged']
status['unresolved']=['Actual-vessel CPU/CUDA probability equivalence remains unmeasured',
    'Small synthetic equality/memory observations do not prove full-context memory reduction',
    'Complete historical F156 pointwise equivalence remains limited to approved development lineage',
    'Holdout known_holdout_reused=true; exposure audit unresolved; individual values not opened',
    'No independent/official score and no actual F1>=0.7 evidence']
status['handoff']={'ready':True,'next_session_launched':False,'launch_receipt':'automation/receipts/round_007_launch.json',
    'launcher':'automation/Start-NextSession.ps1','launcher_owner':'current manager','next_round':'round_008','pause_reason':None,
    'authorization':'User authorizes local experiments and fresh Astra high handoffs without repeated approval',
    'close_completed_session_requested':True,'completed_session_id':status['manager_session'],
    'close_completed_session_status':'No supported structured-chat close API or terminal handle found; end manager after accepted handoff, manually close only completed tab if desired',
    'next_session_id':None,'accepted_at_utc':None,
    'note':'Canonical launch acceptance, when present, is the launch receipt. Shared STATUS is not mutated by the outgoing manager after recipient begins.'}
status['learning_status']={'technical_goal':'source/mock/tiny synthetic equivalence achieved','learner_understanding_assessed':False,
    'hardware_verified':False,'notes':'rounds/round_007/LEARNING_NOTES.md'}
status['diagnostic_result']={'kind':'synthetic_column_chunk_equivalence','pass':True,'max_abs_probability_difference':0.0,
    'new_f1':None,'limits':'Only32FIT/2query synthetic inputs; no real vessel outputs or full-context memory claim'}
status['next_round_budget']={'manager_minutes_max':30,'actual_replay_max_runs':1,'replay_seconds_max_including_cleanup':600,
    'mock_max_runs':2,'mock_seconds_max':30,'threads_max':3,'concurrent_compute_max':1,
    'start_available_ram_gib_min':3,'runtime_stop_available_ram_gib_below':1.5,
    'checkpoint_loads_max':1,'context_fits_max':1,'predict_proba_calls_max':1,'parameter_training_fits':0,'F1_evaluations':0}
status['review']={'precheck':'rounds/round_007/review/precheck.json',
    'wrapper_correction':'rounds/round_007/review/mock02_precheck.json',
    'synthetic_precheck':'rounds/round_007/review/synthetic_precheck.json',
    'saved_artifact_verification':'rounds/round_007/review/synthetic_artifact_verification.json',
    'saved_artifact_checks_passed':50,'final_review':'rounds/round_007/review/FINAL_REVIEW.md',
    'final_review_json':'rounds/round_007/review/final_review.json','final_review_pass':True}
status['execution_summary']={'mock_runs':2,'mock_assertions_passed_both':True,'first_wrapper_false_failure_corrected':True,
    'synthetic_pair_runs':1,'synthetic_pair_seconds':30.078,'synthetic_predict_calls_completed':2,'checkpoint_context_fit':1,
    'new_parameter_fits':0,'new_actual_data_predictions':0,'new_f1_evaluations':0,
    'synthetic_max_abs_probability_difference':0.0,'synthetic_argmax_equal':True,
    'source_snapshots_match':True,'all_owned_compute_processes_finished':True,
    'raw_data_read':False,'holdout_individual_rows_read':0,'new_independent_evaluation':False,'hardware_validation':False}
status['m4_readiness']['next_step']='Tiny synthetic chunk16 passed; one actual full-context replay after configure-before-install gate. M4 training remains gated.'
save(ROOT/'STATUS.json',status)
ledger=ROOT/'EXPERIMENT_LEDGER.csv'
with ledger.open(encoding='utf-8-sig',newline='') as stream:
    reader=csv.DictReader(stream); fields=reader.fieldnames; rows=list(reader)
assert not any(row['round_id']=='round_007' for row in rows), 'Round007 ledger already exists; do not append twice'
row=dict(round_id='round_007',started_at_utc=status['budget']['started_utc'],finished_at_utc=now,
    status='completed_synthetic_equivalence_pass',
    hypothesis='CPU column-only chunk16 preserves fixed tiny synthetic probabilities; source proof +2 bounded pure mocks +1 pair',
    baseline_micro='',candidate_micro='',evaluation_kind='tiny_synthetic_equivalence_only_no_F1',new_fits=0,
    result_report='rounds/round_007/ROUND_REPORT.md',
    next_task='round_008 configure-before-install and one bounded same FIT3144 two-query chunk16 actual replay; no M4 training yet')
with ledger.open('a',encoding='utf-8',newline='') as stream:
    csv.DictWriter(stream,fieldnames=fields).writerow(row)
print('Round007 complete; STATUS current_round=round_007; handoff.ready=true; ledger appended once.')
