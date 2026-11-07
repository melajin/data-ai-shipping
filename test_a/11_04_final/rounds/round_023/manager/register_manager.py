import datetime, hashlib, json, os
from pathlib import Path
import psutil

R = Path(__file__).resolve().parents[1]
ROOT = R.parents[1]
def save(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt = json.loads((ROOT/'automation/receipts/round_022_launch.json').read_text(encoding='utf-8-sig'))
sid = os.environ.get('ORCA_AGENT_SESSION_ID')
assert receipt['accepted'] and receipt['host_response']['result']['outcome']['sessionId'] == sid
assert hashlib.sha256((ROOT/'NEXT_SESSION.md').read_bytes()).hexdigest().upper() == receipt['handoff_sha256']
claim = dict(utc=now, owner='/root', orca_session_id=sid, inherited_from='round_022', no_round023_existed_before_setup=True, live_training_processes_at_initial_check=0)
with (R/'manager/manager_claim.json').open('x', encoding='utf-8') as f: json.dump(claim,f,indent=2)
contexts=[]
for p in sorted(Path('C:/Users/dlehs/.codex/sessions/2026/11/05').glob('*.jsonl'),key=lambda p:p.stat().st_mtime,reverse=True)[:3]:
    meta=None
    with p.open(encoding='utf-8') as f:
        for line in f:
            j=json.loads(line)
            if j.get('type')=='session_meta':
                q=j['payload'];meta={k:q.get(k) for k in ('id','source','cwd')}
            if j.get('type')=='turn_context':
                q=j['payload'];contexts.append(dict(path=str(p),session_meta=meta,utc=j.get('timestamp'),context={k:q.get(k) for k in ('model','effort','cwd')}));break
save(R/'manager/host_turn_evidence.json',dict(utc=now,manager_requested={'model':'gpt-6-astra','effort':'high'},workers_requested={'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none','tasks':['/root/round023_code','/root/round023_review']},host_turn_context=contexts,internal_model_authentication=False,configuration_changes_runtime_model=False,host_total_slots=4,active_workers=2))
mem=psutil.virtual_memory()
save(R/'manager/initial_resource_check.json',dict(utc=now,available_gib=mem.available/2**30,expected_training_peak_gib=1.5,estimate_basis='inherited conservative budget; previous sampled peak0.427GiB, sequential4CV/8fits; matrices under5MiB plus sparse maps/library',active_heavy_jobs=0,worker_tasks='small source edits/read-only review',action='preparation and review; launch independently rechecks >=2.5GiB'))
s=json.loads((ROOT/'STATUS.json').read_text(encoding='utf-8-sig'))
s.update(updated_at_utc=now,current_round='round_023',round_status='preparing_fixed_gate_replay',manager_session=sid,paths={**s['paths'],'round':'rounds/round_023'})
s['handoff'].update(ready=False,next_round=None,note='round022 receipt accepted and matches current manager; round023 claimed',next_session_id=sid,accepted_at_utc=receipt['completed_at_utc'])
s['assistant_model_policy']['current_runtime_assistants']=2
save(ROOT/'STATUS.json',s)
print(json.dumps(dict(claim=claim,available_gib=mem.available/2**30,host_context=contexts)))
