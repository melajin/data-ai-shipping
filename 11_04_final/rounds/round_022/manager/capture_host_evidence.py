import datetime,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
target='01a1a956-8845-7db1-ab01-34aac2261237'
paths=list((Path.home()/'.codex/sessions/2026/11/05').glob('*.jsonl'))
records=[]
for p in paths:
 meta=None; context=None
 with p.open(encoding='utf8') as f:
  for i,line in enumerate(f):
   if i>100:break
   try:d=json.loads(line)
   except json.JSONDecodeError:continue
   if d.get('type')=='session_meta':meta=d.get('payload',{})
   if d.get('type')=='turn_context':
    pl=d.get('payload',{});context=dict(utc=d.get('timestamp'),model=pl.get('model'),effort=pl.get('effort'),cwd=pl.get('cwd'));break
 if not meta:continue
 source=meta.get('source');spawn=source.get('subagent',{}).get('thread_spawn',{}) if isinstance(source,dict) else {}
 if meta.get('id')==target or spawn.get('parent_thread_id')==target:
  records.append(dict(path=str(p),session_id=meta.get('id'),source=source,context=context))
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),manager_requested=dict(model='gpt-6-astra',effort='high'),worker_requested=dict(model='gpt-6-luna',effort='xhigh',fork_turns='none'),host_turn_context=records,internal_model_authentication=False,configuration_changes_runtime_model=False)
(R/'manager/host_turn_evidence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(out,ensure_ascii=False))
