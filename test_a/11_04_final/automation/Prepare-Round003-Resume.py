"""Record the user's explicit resumption before the single fresh-session handoff."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

root = Path(__file__).resolve().parents[1]
receipts = root / 'automation/receipts'
status_path = root / 'STATUS.json'
status = json.loads(status_path.read_text(encoding='utf-8-sig'))
assert status['current_round'] == 'round_002'
assert not status.get('active_workers')
assert not (receipts / 'round_002_launch.json').exists()
assert not (receipts / 'round_002_launch.claim').exists()
record_path = receipts / 'round_003_resume_authorization.json'
assert not record_path.exists(), 'Resume already prepared; inspect existing record instead of overwriting'
receipts.mkdir(exist_ok=True)
now = datetime.now(timezone.utc).isoformat()
before = receipts / 'round_002_STATUS_before_resume.json'
assert not before.exists()
before.write_bytes(status_path.read_bytes())
document = 'docs/20261105_추가조건_검토및3차실험_수정제안.md'
handoff = root / 'NEXT_SESSION.md'
record = {
    'recorded_at_utc': now,
    'user_instruction': '3차 돌려보자 일단 새 세션 오픈해서',
    'from_round': 'round_002', 'target_round': 'round_003',
    'requested_model': 'gpt-6-astra', 'requested_effort': 'high',
    'assistant_policy': 'gpt-6-luna / xhigh only, host concurrency limit applies',
    'worktree_id': '694309e1-3a51-45ba-b9c8-19f164cfd785::D:\\obsidian\\claude\\obsidian_export\\DATA AI SHIPPING',
    'duplicate_check': 'Orca worktree ps reported current manager plus separate TestB sessions; no other round003 manager observed. No round003 folder or round002 launch receipt/claim existed.',
    'corrected_explanation': document,
    'corrected_explanation_sha256': hashlib.sha256((root / document).read_bytes()).hexdigest(),
    'handoff_sha256': hashlib.sha256(handoff.read_bytes()).hexdigest(),
    'scope': 'Round003 R0: saved TabICL A probabilities, raw/old/INNER-selected decision comparison, then bounded M4 readiness; no new fits',
    'same_vessel_historical_profile_route': 'excluded by user constraint',
    'prior_round_reports_and_zip': 'preserved as historical snapshots',
    'launch_status': 'not_yet_launched',
}
status['updated_at_utc'] = now
status['goal_status'] = 'resumed_by_user_not_achieved'
status['current_task'] = 'Round002 complete; user resumed; preparing fresh Astra high manager for round003 R0'
status['next_task'] = record['scope']
status['handoff'].update({'ready': True, 'next_session_launched': False, 'launch_receipt': None,
                          'pause_reason': None, 'resume_authorization': str(record_path.relative_to(root)).replace('\\', '/')})
status['user_pause'].update({'effective': False, 'resumed_at_utc': now, 'resume_instruction': record['user_instruction']})
status['next_round_budget'].update({'status': 'authorized_by_explicit_user_resume', 'new_fits_max': 0,
                                   'manager_minutes': 45, 'compute_minutes': 15,
                                   'm4_readiness_minutes_max': 10})
status['latest_user_steering_before_resume'] = status.get('latest_user_steering')
status['latest_user_steering'] = {
    'instruction': record['user_instruction'], 'recorded_at_utc': now,
    'corrected_explanation': document,
    'corrected_explanation_sha256': record['corrected_explanation_sha256'],
    'existing_059_is_vessel_disjoint_development_evaluation': True,
    'retain_existing_split_and_improve_accuracy': True,
    'same_vessel_historical_profile_route_forbidden': True,
    'source_report': '../26_11_5/20261105_팀원자료_검토보고서.md',
    'round002_contract_unchanged': True,
}
record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'resume_record': str(record_path), 'handoff_ready': True,
                  'handoff_sha256': record['handoff_sha256'], 'launched': False}, ensure_ascii=True))
