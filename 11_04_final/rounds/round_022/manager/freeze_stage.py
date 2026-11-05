import argparse,datetime,hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--approval',required=True);a=p.parse_args()
approval=Path(a.approval).resolve();assert approval.is_relative_to(R/'review')
j=json.loads(approval.read_text(encoding='utf-8-sig'));assert j.get('approved') is True
paths=j['source_hashes'];assert paths
for name,h in paths.items():
 path=(ROOT/name).resolve();assert path.is_relative_to(ROOT);assert sha(path).lower()==h.lower(),(name,'Source changed since approval')
snap=R/'manager'/('snapshot_'+a.stage);snap.mkdir(exist_ok=False)
for name,h in paths.items():
 dest=snap/Path(name).name;assert not dest.exists(),'Duplicate basenames';shutil.copyfile(ROOT/name,dest)
shutil.copyfile(approval,snap/'approval.json')
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage=a.stage,approval=str(approval.relative_to(ROOT)),approval_sha256=sha(approval),source_hashes=paths)
(snap/'freeze.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(stage=a.stage,frozen_files=len(paths))))
