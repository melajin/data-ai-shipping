import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[3]
dest = root / 'rounds/round_017/manager'
def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def save(name, obj):
    (dest / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

previous=read(root/'rounds/round_016/manager/execution_closeout.json')
paths=[x['path'] for x in previous['prior_files']]
paths += [str(p.relative_to(root)).replace('\\','/') for p in (root/'rounds/round_016').rglob('*') if p.is_file() and p.suffix in {'.md','.json','.py','.ps1'}]
save('prior_files_before.json',[{'path':p,'bytes':(root/p).stat().st_size,'sha256':digest(root/p)} for p in sorted(set(paths))])

evidence=[]
thread=os.environ['CODEX_THREAD_ID']
for p in Path('C:/Users/dlehs/.codex/sessions/2026/11/05').glob('*.jsonl'):
    if p.stat().st_mtime < datetime(2026,11,4,22,14,tzinfo=timezone.utc).timestamp():
        continue
    meta=None
    with p.open(encoding='utf-8') as f:
        for line in f:
            row=json.loads(line)
            if row.get('type')=='session_meta':
                meta=row.get('payload',{})
                parent=meta.get('source',{})
                parent_id=parent.get('subagent',{}).get('thread_spawn',{}).get('parent_thread_id') if isinstance(parent,dict) else None
                if meta.get('id')!=thread and parent_id!=thread:
                    break
            if row.get('type')=='turn_context' and meta:
                payload=row['payload']
                evidence.append({'source':str(p),'session_id':meta.get('id'),'parent':meta.get('source'),'timestamp':row.get('timestamp'),'host_model':payload.get('model'),'host_effort':payload.get('effort'),'cwd':payload.get('cwd')})
                break
save('host_turn_evidence.json',{'request':{'manager':{'model':'gpt-6-astra','effort':'high'},'author':{'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none'},'reviewer':{'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none'}},'orca_session_id':os.environ.get('ORCA_AGENT_SESSION_ID'),'thread_id':thread,'evidence':evidence,'internal_model_authentication':False})
ps=read(dest/'worktree_ps.json')
agents=[a for w in ps['result']['worktrees'] if w['path'].replace('\\','/')==str(root.parent).replace('\\','/') for a in w.get('agents',[])]
save('duplicate_manager_check.json',{'utc':datetime.now(timezone.utc).isoformat(),'agents':agents,'truncated':ps['result'].get('truncated'),'incoming_session_matches':read(root/'automation/receipts/round_016_launch.json')['host_response']['result']['outcome']['sessionId']==os.environ.get('ORCA_AGENT_SESSION_ID'),'round017_preexisting_before_spawn':False})
s=read(root/'STATUS.json')
s.update({'updated_at_utc':datetime.now(timezone.utc).isoformat(),'round_status':'round017_in_progress_source_repair','manager_session':os.environ.get('ORCA_AGENT_SESSION_ID')})
s['handoff']['ready']=False
s['active_workers']=[{'task':'/root/author','model_request':'gpt-6-luna','effort_request':'xhigh','owns':'rounds/round_017/code'},{'task':'/root/reviewer','model_request':'gpt-6-luna','effort_request':'xhigh','owns':'rounds/round_017/review'}]
(root/'STATUS.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'protected_files':len(set(paths)),'model_evidence':evidence,'agents':[{'paneKey':a.get('paneKey'),'state':a.get('state')} for a in agents]},ensure_ascii=False))
