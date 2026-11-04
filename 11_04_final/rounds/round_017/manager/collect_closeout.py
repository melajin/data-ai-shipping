import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[3]
rd=root/'rounds/round_017'
def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()
prior=[]
for row in read(rd/'manager/prior_files_before.json'):
    actual=sha(root/row['path'])
    prior.append({**row,'after_sha256':actual,'unchanged':actual==row['sha256']})
runs={}
for mode in ('smoke','mock','audit'):
    run_dir=rd/'logs'/f'{mode}_01'
    entries={}
    if run_dir.exists():
        for p in run_dir.glob('*.json'):
            try:
                entries[p.name]={'sha256':sha(p),'data':read(p)}
            except Exception as exc:
                entries[p.name]={'sha256':sha(p),'parse_error':str(exc)}
    runs[mode]={'files':entries,'claims':[str(p.relative_to(root)).replace('\\','/') for p in run_dir.glob('*.claim')] if run_dir.exists() else []}
sources=[]
ack_path=rd/'code/author_freeze_ack.json'
if ack_path.exists():
    ack=read(ack_path)
    for p,expected in ack.get('source_files_sha256',{}).items():
        actual=sha(root/p)
        sources.append({'path':p,'expected_sha256':expected,'actual_sha256':actual,'match':actual==expected})
artifact=rd/'artifacts/saved_m4_audit.json'
out={'utc':datetime.now(timezone.utc).isoformat(),'runs':runs,'source_hashes':sources,'prior_files':prior,'prior_selected_files_unchanged':all(x['unchanged'] for x in prior),'saved_audit':read(artifact) if artifact.exists() else None,'new_f1':None,'model_calls':0,'checkpoint_access':0,'pt_deserialization':0,'actual_data_access':0,'historical_round015_wrapper_gate':False,'historical_round010_gate':False}
(rd/'manager/execution_closeout.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'prior_files':len(prior),'prior_unchanged':out['prior_selected_files_unchanged'],'source_matches':sources,'runs':{mode:{'files':list(val['files']),'claims':val['claims']} for mode,val in runs.items()},'audit_present':artifact.exists()},ensure_ascii=False))
