import datetime, hashlib, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'rounds/round_018/manager'
def save(name, obj):
    (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
thread = os.environ.get('CODEX_THREAD_ID')
session = os.environ.get('ORCA_AGENT_SESSION_ID')
evidence = []
for p in Path('C:/Users/dlehs/.codex/sessions/2026/11/05').glob('*.jsonl'):
    meta = None
    with p.open(encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i > 10:
                break
            event = json.loads(line)
            if event.get('type') == 'session_meta':
                meta = event['payload']
                parent = meta.get('source', {})
                parent_id = parent.get('subagent', {}).get('thread_spawn', {}).get('parent_thread_id') if isinstance(parent, dict) else None
                if meta.get('id') != thread and parent_id != thread:
                    break
            if event.get('type') == 'turn_context' and meta:
                turn = event['payload']
                evidence.append(dict(source=str(p), session_id=meta.get('id'), parent=meta.get('source'), timestamp=event.get('timestamp'), host_model=turn.get('model'), host_effort=turn.get('effort', turn.get('reasoning_effort')), cwd=turn.get('cwd')))
                break
save('host_turn_evidence.json', dict(utc=now, request={'manager':{'model':'gpt-6-astra','effort':'high'},'author':{'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none'},'reviewer':{'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none'}}, thread_id=thread, orca_session_id=session, evidence=evidence, internal_model_authentication=False))
old = read(ROOT/'rounds/round_017/manager/execution_closeout.json')
paths = {x['path'] for x in old['prior_files']}
paths.update(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'rounds/round_017').rglob('*') if p.is_file())
rows=[]
for name in sorted(paths):
    p=ROOT/name
    if p.suffix == '.pt':
        continue
    data=p.read_bytes()
    rows.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
save('prior_files_before.json',rows)
incoming=read(ROOT/'automation/receipts/round_017_launch.json')
save('startup.json',dict(utc=now,thread=thread,session=session,incoming_session_matches=incoming['host_response']['result']['outcome']['sessionId']==session,handoff_sha256=hashlib.sha256((OUT/'incoming_NEXT_SESSION.md').read_bytes()).hexdigest(),exclusive_claim='manager_claim.json', existing_round018_before_start=False, process_check='Only inspecting shell matched round018/runner search; no pre-existing experiment', model_metadata_source='host turn_context, not internal authentication'))
s=read(ROOT/'STATUS.json')
s.update(updated_at_utc=now,current_round='round_018',round_status='in_progress_source_review',manager_session=session,current_task='Round018 minimal PowerShell boolean repair then model-zero smoke/mock/saved audit',next_task='Conditional round019 full-estimator M4-a integration only after all gates',active_workers=['/root/author','/root/reviewer'])
s['assistant_model_policy']['current_runtime_assistants']=2
s['paths']['round']='rounds/round_018'
s['budget']={'started_utc':'2026-11-04T22:38:50Z','manager_minutes_max':20,'experiment_cutoff_utc':'2026-11-04T22:55:50Z','smoke_max_runs':1,'mock_max_runs':1,'audit_max_runs':1,'model_runs':0}
s['handoff'].update(ready=False,next_session_launched=False,next_round='round_019',launch_receipt='automation/receipts/round_018_launch.json',completed_session_id=session)
s['decision_rules']['current_round']='One minimal boolean fix; independent source approval required before model-zero modes'
s['decision_rules']['next_gate']='All same-map smoke/mock/audit gates before full-estimator integration'
s['blockers']=['Round018 dynamic gates pending']
(ROOT/'STATUS.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'evidence':evidence,'prior_files':len(rows),'startup_recorded':True},ensure_ascii=False))
