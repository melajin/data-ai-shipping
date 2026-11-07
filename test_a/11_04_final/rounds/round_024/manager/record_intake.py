"""Small streaming host evidence capture; no data/model reads."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

R = Path(__file__).resolve().parents[1]
ROOT = R.parents[1]
def save(name, value):
    (R / 'manager' / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

receipt = json.loads((ROOT/'automation/receipts/round_024_model_switch_sol_high_launch.json').read_text(encoding='utf-8-sig'))
session = os.environ.get('ORCA_AGENT_SESSION_ID')
expected = receipt['host_response']['result']['outcome']['sessionId']
assert receipt['accepted'] and session == expected, 'Receipt owner mismatch; investigate duplicate session'
handoff = ROOT/'NEXT_SESSION.md'
digest = hashlib.sha256(handoff.read_bytes()).hexdigest().upper()
assert digest == receipt['handoff_sha256']
evidence=[]
session_dir=Path(os.environ['CODEX_HOME'])/'sessions/2026/11/05'
for p in session_dir.glob('*.jsonl'):
    role=None
    with p.open(encoding='utf-8') as f:
        first=json.loads(next(f))
        meta=first.get('payload',{})
        thread=meta.get('id')
        if thread == os.environ.get('CODEX_THREAD_ID'):
            role='manager'
        else:
            source=meta.get('source',{})
            spawn=source.get('subagent',{}).get('thread_spawn',{}) if isinstance(source,dict) else {}
            if spawn.get('parent_thread_id') == os.environ.get('CODEX_THREAD_ID'):
                role=spawn.get('agent_path', 'worker')
        if role:
            for line in f:
                item=json.loads(line)
                if item.get('type')=='turn_context':
                    payload=item['payload']
                    evidence.append(dict(role=role,thread_id=thread,source_path=str(p),utc=item.get('timestamp'),model=payload.get('model'),effort=payload.get('effort')))
                    break
save('host_turn_evidence.json',dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),manager_request=dict(model='gpt-6.1-sol',effort='high'),worker_request=dict(model='gpt-6-luna',effort='xhigh',roles=['code_author','reviewer'],host_total_slots=4),host_turn_context=evidence,backend_authenticated=False,scope='Host-recorded configuration, not backend model authentication'))
save('intake_receipt.json',dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),orca_session_id=session,thread_id=os.environ.get('CODEX_THREAD_ID'),receipt_owner_matches=True,handoff_sha256=digest,prepare_rerun=False,previous_manager_relinquished=True,training_not_started_at_intake=True))
print(json.dumps(dict(owner_match=True,handoff_sha256=digest,host_context=evidence)))
