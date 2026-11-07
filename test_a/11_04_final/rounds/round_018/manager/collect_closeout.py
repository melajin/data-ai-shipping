import datetime, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
RD=ROOT/'rounds/round_018'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
prior=read(RD/'manager/prior_files_before.json')
for row in prior:
    row['after_sha256']=digest(ROOT/row['path'])
    row['unchanged']=row['sha256']==row['after_sha256']
runs={}
for mode in ('smoke','mock','audit'):
    d=RD/f'logs/{mode}_01'
    runs[mode]={'claims':[str(p.relative_to(ROOT)) for p in d.glob('*.claim')],'files':{}}
    for name in ('receipt.json','wrapper_receipt.json'):
        p=d/name
        if p.exists(): runs[mode]['files'][name]=read(p)
    p=RD/f'manager/{mode}_launch.json'
    if p.exists(): runs[mode]['outer']=read(p)
sources=[]
mp=RD/'review/approved_sources.json'
if mp.exists():
    for path,expected in read(mp)['sha256'].items():
        actual=digest(ROOT/path)
        sources.append(dict(path=path,expected_sha256=expected,actual_sha256=actual,match=expected==actual))
obj=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),runs=runs,source_hashes=sources,prior_files=prior,prior_selected_files_unchanged=all(r['unchanged'] for r in prior),new_f1=None,model_calls=0,checkpoint_access=0,pt_deserialization=0,actual_data_access=0,historical_round015_wrapper_gate=False,historical_round010_gate=False)
(RD/'manager/execution_closeout.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(prior_files=len(prior),unchanged=obj['prior_selected_files_unchanged'],source_match=all(r['match'] for r in sources),runs=runs),ensure_ascii=False))
