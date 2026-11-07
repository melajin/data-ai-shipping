"""Bind independently reviewed stage to current inputs without fitting/scoring."""
import argparse,datetime,hashlib,importlib.util,json,shutil,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--review',required=True);a=p.parse_args()
review_path=ROOT/a.review;review=read(review_path);assert review['approved'] is True
runner=R/'code/run_performance.py';config=R/'configs/experiment.json'
for source in [runner,config,R/'manager/launch.py']:
    assert review['hashes'][source.relative_to(ROOT).as_posix()].lower()==sha(source),'Review hash mismatch: '+str(source)
for name,digest in review['hashes'].items():assert sha(ROOT/name)==digest.lower(),name
spec=importlib.util.spec_from_file_location('round021_run',runner);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
cfg=read(config);manifest=mod.build_input_manifest(cfg,config)
prepared=read(R/'manager/prepare_input_manifest.json')
old={x['path']:x for x in prepared['files']}
for row in manifest['files']:
    if row['path'] in old and Path(row['path']) not in [runner,config]:
        assert old[row['path']]['sha256']==row['sha256'],'Input changed since successful prepare: '+row['path']
snapshot=R/'manager'/('snapshot_'+a.stage);snapshot.mkdir(exist_ok=False)
sources=list((R/'code').glob('*.py'))+[config,R/'ROUND_PLAN.md',R/'manager/launch.py',review_path]
for src in sources:shutil.copyfile(src,snapshot/src.name)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
save(snapshot/'input_manifest.json',manifest);save(R/'artifacts/input_manifest.json',manifest)
approval=dict(round='round_021',status='approved',utc=now,allowed_stage=a.stage,runner_sha256=manifest['runner_sha256'],config_sha256=manifest['config_sha256'],input_manifest_sha256=manifest['fingerprint_sha256'],independent_review_sha256=sha(review_path),condition='Baseline/candidate fitting stages do not authorize OUTER. Evaluation only after final independent review and all six save/reload records; no post-OUTER tuning.')
save(R/'manager/outer_read_approval.json',approval);save(snapshot/'approval.json',approval)
save(snapshot/'freeze.json',dict(utc=now,stage=a.stage,source_hashes={x.relative_to(ROOT).as_posix():sha(x) for x in sources},input_fingerprint=manifest['fingerprint_sha256'],review=str(review_path),outer_probability_values_read=False))
print(json.dumps(dict(frozen=True,stage=a.stage,utc=now,manifest=manifest['fingerprint_sha256'])))
