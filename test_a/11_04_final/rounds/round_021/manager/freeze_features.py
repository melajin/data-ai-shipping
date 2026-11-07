import argparse,datetime,hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
p=argparse.ArgumentParser();p.add_argument('--role',choices=['INNER_SELECT','OUTER'],required=True);a=p.parse_args()
reviewpath=R/'review/spatial_features_approved_sources.json';review=read(reviewpath);assert review['approved']
for name,h in review['hashes'].items():assert sha(ROOT/name)==h.lower(),name
original=read(R/'manager/snapshot_fit_baseline/input_manifest.json');cfg=read(R/'configs/experiment.json')
paths=[Path(cfg['paths']['round002_feature_root'])/f'fold_{f}_features.npz' for f in range(3)]+[ROOT/cfg['paths']['round002_roster']]
for path in paths:
    old=next(x for x in original['files'] if Path(x['path'])==path)
    assert sha(path)==old['sha256'],str(path)
profiles=ROOT/cfg['paths']['spatial_profiles'];assert sha(profiles)==read(profiles.with_suffix('.csv.manifest.json'))['output_sha256']
if a.role=='OUTER':
    for name in ['baseline_fit.json','candidate_fit.json']:
        fit=read(R/'artifacts'/name);assert len(fit['fit_records'])==3 and all(x['reload_check_pass'] for x in fit['fit_records'])
out=R/'manager'/('snapshot_spatial_'+a.role.lower());out.mkdir(exist_ok=False)
for path in [R/'code/build_spatial_features.py',reviewpath,R/'configs/experiment.json',R/'ROUND_PLAN.md',R/'manager/launch.py']:
    shutil.copyfile(path,out/path.name)
evidence=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),role=a.role,review=review,input_hashes={str(p):sha(p) for p in paths+[profiles,profiles.with_suffix('.csv.manifest.json')]},note='FIT labels only in prototype construction; query labels only exact contract validation; no OUTER probabilities or scores')
(out/'freeze.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen':True,'role':a.role,'utc':evidence['utc']}))
