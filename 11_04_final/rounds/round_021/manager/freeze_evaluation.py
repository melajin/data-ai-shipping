import datetime,hashlib,importlib.util,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
review_path=R/'review/evaluation_approved_sources.json';review=read(review_path);assert review['approved']
for name,h in review['hashes'].items():assert sha(ROOT/name)==h.lower(),name
runner=R/'code/run_performance.py';evaluator=R/'code/evaluate_round021.py';config=R/'configs/experiment.json'
assert runner.relative_to(ROOT).as_posix() in review['hashes'] and evaluator.relative_to(ROOT).as_posix() in review['hashes']
spec=importlib.util.spec_from_file_location('round021_run',runner);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
cfg=read(config);manifest=mod.build_input_manifest(cfg,config)
prior=read(R/'manager/snapshot_fit_candidate/input_manifest.json')
for row in prior['files']:
    assert sha(Path(row['path']))==row['sha256'],'Input/source changed since candidate fit: '+row['path']
additional=[R/'artifacts/baseline_fit.json',R/'artifacts/candidate_fit.json',R/'artifacts/spatial_features_OUTER.csv',R/'artifacts/spatial_features_OUTER.csv.manifest.json']
for name in ['baseline_fit.json','candidate_fit.json']:
    fit=read(R/'artifacts'/name);assert len(fit['fit_records'])==3 and all(x['reload_check_pass'] for x in fit['fit_records'])
    for record in fit['fit_records']:
        p=Path(record['model_path']);assert sha(p)==record['model_sha256'];additional.append(p)
out=R/'manager/snapshot_evaluation';out.mkdir(exist_ok=False)
sources=list((R/'code').glob('*.py'))+[config,R/'ROUND_PLAN.md',R/'manager/launch.py',review_path]
for p in sources:shutil.copyfile(p,out/p.name)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
approval=dict(round='round_021',status='approved',allowed_stage='evaluation',utc=now,runner_sha256=manifest['runner_sha256'],evaluation_sha256=sha(evaluator),config_sha256=manifest['config_sha256'],input_manifest_sha256=manifest['fingerprint_sha256'],independent_review_sha256=sha(review_path),additional_input_hashes={str(p):sha(p) for p in additional},condition='All6 models verified/reloaded; one OUTER evaluation; no fitting or parameter/rowwise selection after reading scores')
save(R/'manager/outer_read_approval.json',approval);save(out/'approval.json',approval);save(out/'input_manifest.json',manifest);save(R/'artifacts/input_manifest.json',manifest)
save(out/'freeze.json',dict(utc=now,hashes={p.relative_to(ROOT).as_posix():sha(p) for p in sources},input_hashes=approval['additional_input_hashes'],meta_fits=6,prior_outer_probability_scoring=0))
print(json.dumps({'frozen':True,'stage':'evaluation','utc':now,'evaluation_sha256':sha(evaluator)}))
