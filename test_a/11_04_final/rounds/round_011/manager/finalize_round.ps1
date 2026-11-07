$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $taskRoot
$audit=Get-Content -Raw -Encoding UTF8 'rounds/round_011/artifacts/provenance_audit.json'|ConvertFrom-Json
$mock=Get-Content -Raw -Encoding UTF8 'rounds/round_011/logs/mock_01/receipt.json'|ConvertFrom-Json
if(Test-Path 'rounds/round_011/logs/mock_02/receipt.json'){$mock=Get-Content -Raw -Encoding UTF8 'rounds/round_011/logs/mock_02/receipt.json'|ConvertFrom-Json}
$execution=Get-Content -Raw -Encoding UTF8 'rounds/round_011/logs/audit_01/receipt.json'|ConvertFrom-Json
if(-not $mock.completed -or -not $execution.completed -or -not $audit.audit_integrity_passed){throw 'Round completion gates missing'}
foreach($path in @('rounds/round_011/review/FINAL_REVIEW.md','rounds/round_011/review/M4_REVIEW.md','rounds/round_011/ROUND_REPORT.md')){if(-not (Test-Path -LiteralPath $path)){throw "Missing $path"}}
$now=[DateTime]::UtcNow.ToString('o')
$summary=[ordered]@{status='completed_provenance_audit_and_m4_contract';audit_integrity_passed=$audit.audit_integrity_passed;executed_snapshot_matches_approved=$audit.executed_snapshot_matches_approved;live_source_unchanged=$audit.live_source_unchanged;saved_numeric_replay_passed=$audit.saved_numeric_replay_passed;historical_round010_overall_gate=$audit.historical_overall_gate;model_calls=0;new_f1=$null;mock_runs=@(Get-ChildItem 'rounds/round_011/logs' -Directory|Where-Object {$_.Name -match '^mock_0[12]$'}).Count;saved_audit_runs=1;mock_seconds=$mock.elapsed_seconds;audit_seconds=$execution.elapsed_seconds;report='rounds/round_011/ROUND_REPORT.md';m4_contract='rounds/round_011/m4_contract/M4_CONTRACT.md'}
$summary|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 'rounds/round_011/artifacts/result.json'
$s=Get-Content -Raw -Encoding UTF8 'STATUS.json'|ConvertFrom-Json
$s.updated_at_utc=$now
$s.current_round='round_011'
$s.round_status=$summary.status
$s.manager_session=$env:ORCA_AGENT_SESSION_ID
$s.paths.round='rounds/round_011'
$s.assistant_model_policy.current_runtime_assistants=0
$s.active_workers=@()
$s.budget=[ordered]@{manager_minutes_max=20;started_utc='2026-11-04T20:04:05Z';deadline_utc='2026-11-04T20:24:05Z';mock_max_runs=2;mock_seconds_max_each=30;saved_audit_max_runs=1;saved_audit_seconds_max=30;model_calls=0;new_f1_evaluations=0}
$s.decision_rules=[ordered]@{current_round='Saved execution snapshots intact; live wrapper drift and historical overall failure preserved; numeric JSON replay passed';next_gate='Source-approved finite tiny synthetic M4-a/b detached-head nochange/gradient/merge/head-only reload; no vessel training/F1';holdout='Do not read individual values without exposure history and frozen plan';ram_policy='Check before compute/parallelism; if insufficient do independent work then recheck, never polling-only cycles'}
$s.current_task='Completed source provenance audit and source-grounded M4 synthetic contract; no model rerun'
$s.next_task='Round012 implement and execute one bounded tiny synthetic detached-readout M4-a/b mechanics probe under M4_CONTRACT.md'
$s.blockers=@('No exposure-verified independent evaluation opened','M4 synthetic gradient/merge/head reload and later full integration are not yet measured')
$s.unresolved=@('round010 numerical two-query replay passed but overall source-freeze failure remains historical fact','No full5897-vessel CPU/CUDA replay or new F1 this round','Tiny synthetic head mechanics are not candidate generalization or complete model integration','Historical T5 transductive feature lineage is not FIT-only preprocessing','Holdout exposure history unresolved; individual values not opened','Independent/official scores null; goal0.7 not achieved')
$s.learning_status=[ordered]@{technical_goal='Provenance audit and M4 source contract complete';learner_understanding_assessed=$false;hardware_verified=$false;notes='rounds/round_011/ROUND_REPORT.md'}
$s.diagnostic_result=$summary
$s.execution_summary=$summary
$s.next_round_budget=[ordered]@{manager_minutes_max=30;mock_max_runs=2;mock_seconds_max_each=30;synthetic_max_runs=1;synthetic_seconds_total=180;checkpoint_loads=1;context_fits=1;predict_calls=1;full_forwards_max=4;detached_head_calls_max=12;backwards=4;real_data_reads=0;new_f1_evaluations=0;start_available_ram_gib=3;stop_available_ram_gib=1.5;expected_peak_gib_assumption=1.5}
$s.latest_result_report='rounds/round_011/ROUND_REPORT.md'
$s.round_completed_at_utc=$now
$s.review=[ordered]@{source='rounds/round_011/review/SOURCE_REVIEW.md';final='rounds/round_011/review/FINAL_REVIEW.md';m4='rounds/round_011/review/M4_REVIEW.md'}
$s.m4_readiness.next_step=$s.next_task
$s.m4_readiness.ready_for_m4_training=$false
$s.handoff=[ordered]@{ready=$true;next_round='round_012';next_session_launched=$false;launch_receipt='automation/receipts/round_011_launch.json';launcher='automation/Start-NextSession.ps1';launcher_owner='current manager';pause_reason=$null;authorization='User authorizes local experiments and fresh Astra high handoffs without repeated approval';completed_session_id=$env:ORCA_AGENT_SESSION_ID;close_completed_session_requested=$true;close_completed_session_status='No supported structured-chat close command; end manager after accepted handoff; manually close only completed session tab if needed';next_session_id=$null;accepted_at_utc=$null;note='Canonical launch acceptance is automation receipt; do not mutate shared state after recipient starts'}
$s.next_manager_session=$null
$s|ConvertTo-Json -Depth 60|Set-Content -Encoding UTF8 'STATUS.json'
if(@(Import-Csv 'EXPERIMENT_LEDGER.csv'|Where-Object {$_.round_id -eq 'round_011'}).Count){throw 'Ledger already has round011'}
[pscustomobject][ordered]@{round_id='round_011';started_at_utc='2026-11-04T20:04:05Z';finished_at_utc=$now;status=$summary.status;hypothesis='Saved snapshot/live drift/numeric replay are independently auditable; prepare bounded M4 readout mechanics';baseline_micro='';candidate_micro='';evaluation_kind='saved_json_source_provenance_audit_no_model_no_F1';new_fits=0;result_report='rounds/round_011/ROUND_REPORT.md';next_task='round012 one tiny synthetic M4-a/b head nochange/gradient/merge/reload; no vessel data/F1'}|Export-Csv -LiteralPath 'EXPERIMENT_LEDGER.csv' -Append -NoTypeInformation -Encoding UTF8
Copy-Item -LiteralPath 'rounds/round_011/manager/NEXT_SESSION_candidate.md' -Destination 'NEXT_SESSION.md'
$summary|ConvertTo-Json -Depth 6
