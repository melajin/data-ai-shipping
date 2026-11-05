import datetime,json,os,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'rounds/round_021/manager'
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
thread=os.environ['CODEX_THREAD_ID']; session=os.environ['ORCA_AGENT_SESSION_ID']
evidence=[]
for p in Path('C:/Users/dlehs/.codex/sessions/2026/11/05').glob('*.jsonl'):
    meta=None
    with p.open(encoding='utf-8') as f:
        for i,line in enumerate(f):
            if i>12: break
            e=json.loads(line)
            if e.get('type')=='session_meta':
                meta=e['payload']; src=meta.get('source',{})
                parent=src.get('subagent',{}).get('thread_spawn',{}).get('parent_thread_id') if isinstance(src,dict) else None
                if meta.get('id')!=thread and parent!=thread: break
            if e.get('type')=='turn_context' and meta:
                t=e['payload'];evidence.append(dict(path=str(p),session_id=meta.get('id'),parent=meta.get('source'),utc=e.get('timestamp'),model=t.get('model'),effort=t.get('effort',t.get('reasoning_effort')),cwd=t.get('cwd')));break
save(OUT/'host_turn_evidence.json',dict(utc=now,thread_id=thread,orca_session_id=session,requested_manager={'model':'gpt-6-astra','effort':'high'},requested_assistants={'model':'gpt-6-luna','effort':'xhigh','fork_turns':'none'},host_turn_context=evidence,internal_model_authentication=False))
save(OUT/'delegation.json',dict(utc=now,author={'name':'/root/author','model':'gpt-6-luna','effort':'xhigh','fork_turns':'none','owns':['code/*','configs/*']},reviewer={'name':'/root/reviewer','model':'gpt-6-luna','effort':'xhigh','fork_turns':'none','owns':['review/*']},manager_owns='remaining round021 files and root STATUS/LEDGER/NEXT',host_slots=4,total_used=3,user_assistant_max=4,no_child_agents=True))
incoming=json.loads((OUT/'incoming_launch.json').read_text(encoding='utf-8-sig'))
save(OUT/'startup.json',dict(utc=now,session=session,incoming_session_matches=incoming['host_response']['result']['outcome']['sessionId']==session,incoming_sha256=hashlib.sha256((OUT/'incoming_NEXT_SESSION.md').read_bytes()).hexdigest(),duplicate_round_directory_before_claim=False,matching_computation_processes_at_start=[],initial_available_ram_kib=4245096,expected_peak_gib=1.5,estimate_basis='~10000 rows x12 float probabilities plus small sklearn model and library reserve; not measured peak',read_only_paths=['F:/문제 데이터_수정_1027','D:/repos/fishing-track-classification']))
s=json.loads((ROOT/'STATUS.json').read_text(encoding='utf-8-sig'))
s.update(updated_at_utc=now,current_round='round_021',round_status='in_progress_input_and_source_review',manager_session=session,current_task='Fixed SELECT-only 12 logprob logistic stacker; actual development F1',next_task='Frozen round021 current2026 spatialprototype8 controlled addition if below0.7',active_workers=['/root/author','/root/reviewer'])
s['paths']['round']='rounds/round_021';s['assistant_model_policy']['current_runtime_assistants']=2
s['handoff'].update(ready=False,next_session_launched=False,next_round='round_022',launch_receipt='automation/receipts/round_021_launch.json',completed_session_id=session,next_session_id=None,accepted_at_utc=None)
s['budget']={'manager_minutes_max':45,'started_utc':json.loads((OUT/'manager_claim.json').read_text())['claimed_utc'],'compute_seconds_max':1800,'base_fits':0,'meta_fits_max':6,'fit_seconds_max':120,'retries':0,'threads_max':3,'compute_concurrency':1,'expected_peak_gib':1.5,'start_available_gib_min':2.5}
s['blockers']=[]
save(ROOT/'STATUS.json',s)
print(json.dumps({'host_evidence':evidence,'recorded':True},ensure_ascii=False))
