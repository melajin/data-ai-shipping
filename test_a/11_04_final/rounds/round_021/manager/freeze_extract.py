import datetime,hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
review=read(R/'review/spatial_extract_approved_sources.json');assert review['approved']
for name,h in review['hashes'].items():assert sha(ROOT/name)==h.lower(),name
manifest=read(R/'manager/snapshot_fit_baseline/input_manifest.json')
cfg=read(R/'configs/experiment.json')
paths=[Path(cfg['paths']['round002_feature_root'])/'fold_0_features.npz',Path(cfg['paths']['spatial_parquet'])]
for p in paths:
    old=next(x for x in manifest['files'] if Path(x['path'])==p)
    assert sha(p)==old['sha256'],str(p)
out=R/'manager/snapshot_spatial_extract';out.mkdir(exist_ok=False)
for p in [R/'code/extract_spatial_profiles.py',R/'configs/experiment.json',R/'review/spatial_extract_approved_sources.json',R/'ROUND_PLAN.md',R/'manager/launch.py']:
    shutil.copyfile(p,out/p.name)
evidence=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),review=review,input_hashes={str(p):sha(p) for p in paths},stage='spatial_extract',approval='filtered2026development profiles only; no labels or predictions',python='C:/Users/dlehs/AppData/Local/Programs/Python/Python313/python.exe')
(out/'freeze.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
print(json.dumps(evidence))
