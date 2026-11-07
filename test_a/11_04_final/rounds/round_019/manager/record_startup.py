import datetime, hashlib, json, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'rounds/round_019/manager'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(n,v): (OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
thread=os.environ.get('CODEX_THREAD_ID'); session=os.environ.get('ORCA_AGENT_SESSION_ID')
evidence=[]
for p in Path('C:/Users/dlehs/.codex/sessions/2026/11/05').glob('*.jsonl'):
    meta=None
    with p.open(encoding='utf-8') as f:
        for i,line in enumerate(f):
            if i>12: break
            e=json.loads(line)
            if e.get('type')=='session_meta':
                meta=e['payload']; parent=meta.get('source',{})
                parent_id=parent.get('subagent',{}).get('thread_spawn',{}).get('parent_thread_id') if isinstance(parent,dict) else None
                if meta.get('id')!=thread and parent_id!=thread: break
            if e.get('type')=='turn_context' and meta:
                t=e['payload']; evidence.append(dict(source=str(p),session_id=meta.get('id'),parent=meta.get('source'),timestamp=e.get('timestamp'),host_model=t.get('model'),host_effort=t.get('effort',t.get('reasoning_effort')),cwd=t.get('cwd'))); break
save('host_turn_evidence.json',dict(utc=now,thread_id=thread,orca_session_id=session,request={'manager':{'model':'gpt-6-astra','effort':'high'},'author':{'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none'},'reviewer':{'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none'}},evidence=evidence,internal_model_authentication=False))
paths={r['path'] for r in read(ROOT/'rounds/round_018/manager/prior_files_before.json')}
paths.update(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'rounds/round_018').rglob('*') if p.is_file())
rows=[]
for name in sorted(paths):
    p=ROOT/name
    if p.suffix=='.pt': continue
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(65536),b''): h.update(b)
    rows.append(dict(path=name,bytes=p.stat().st_size,sha256=h.hexdigest()))
save('prior_files_before.json',rows)
incoming=read(OUT/'incoming_launch.json')
save('startup.json',dict(utc=now,thread=thread,session=session,incoming_session_matches=incoming['host_response']['result']['outcome']['sessionId']==session,handoff_sha256=hashlib.sha256((OUT/'incoming_NEXT_SESSION.md').read_bytes()).hexdigest(),existing_round019_before_claim=False,no_python_at_start=True,expected_peak_mib=200,estimate_basis='small stdlib JSON; streamed historical hashes; PS plus Python, not measured peak'))
s=read(ROOT/'STATUS.json')
s.update(updated_at_utc=now,current_round='round_019',round_status='in_progress_source_review',manager_session=session,current_task='Round019 deadline liveness and bounded termination evidence repair; model-zero smoke/mock/saved audit',next_task='Conditional round020 preselected M4-a full-estimator gate only after all model-zero gates',active_workers=['/root/author','/root/reviewer'])
s['assistant_model_policy']['current_runtime_assistants']=2
s['paths']['round']='rounds/round_019'
s['budget']={'started_utc':'2026-11-04T22:52:11Z','manager_minutes_max':25,'experiment_cutoff_utc':'2026-11-04T23:14:11Z','smoke_max_runs':1,'mock_max_runs':1,'audit_max_runs':1,'model_runs':0,'retries':0}
s['handoff'].update(ready=False,next_session_launched=False,next_round='round_020',launch_receipt='automation/receipts/round_019_launch.json',completed_session_id=session,next_session_id=None)
s['decision_rules']['current_round']='Minimal explicit post-deadline liveness and bounded termination provenance repair; independent exact-hash source approval before modes'
s['blockers']=['Round019 dynamic gates pending']
(ROOT/'STATUS.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
source=(ROOT/'rounds/round_018/manager/Invoke-ApprovedMode.ps1').read_text(encoding='utf-8-sig').replace('round_018','round_019').replace('round018','round019').replace('2026-11-04T22:55:15Z','2026-11-04T23:13:35Z')
(OUT/'Invoke-ApprovedMode.ps1').write_text(source,encoding='utf-8-sig')
source=(ROOT/'rounds/round_018/manager/collect_closeout.py').read_text(encoding='utf-8-sig').replace('round_018','round_019')
(OUT/'collect_closeout.py').write_text(source,encoding='utf-8')
save('delegation.json',dict(utc=now,author={'agent':'/root/author','model':'gpt-6-luna','effort':'xhigh','fork_turns':'none','owns':'rounds/round_019/code/*'},reviewer={'agent':'/root/reviewer','model':'gpt-6-luna','effort':'xhigh','fork_turns':'none','owns':'rounds/round_019/review/*'},manager_owns='Other round019 files and shared status/ledger/handoff',host_total_slots=4,total_used=3,user_assistant_limit=4,child_agents_forbidden=True,no_other_edits_reverted=True))
print(json.dumps({'evidence':evidence,'prior_file_count':len(rows),'startup_recorded':True},ensure_ascii=False))
