import datetime,hashlib,json,shutil,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
runner=R/'code/run_performance.py';config=R/'configs/experiment.json'
manifest=read(R/'artifacts/input_manifest.json');review=read(R/'review/approved_sources.json')
assert review['approved'] is True
for source in [runner,config,R/'manager/launch.py']:
    assert review['hashes'][str(source.relative_to(ROOT)).replace('\\','/')]==sha(source)
assert manifest['runner_sha256']==sha(runner) and manifest['config_sha256']==sha(config)
for row in manifest['files']:
    assert sha(Path(row['path']))==row['sha256'],row['path']
files=[runner,config,R/'ROUND_PLAN.md',R/'manager/ROUND021_FIXED_BRANCH.md',R/'manager/USER_PROTECTION_AMENDMENT.md']
hashes={str(x.relative_to(ROOT)):sha(x) for x in files}
snapshot=R/'manager/execution_snapshot';snapshot.mkdir(exist_ok=False)
for source in files+[R/'manager/launch.py',R/'review/approved_sources.json',R/'artifacts/input_manifest.json']:
    dest=snapshot/source.name;shutil.copyfile(source,dest);assert sha(dest)==sha(source)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
freeze=dict(utc=now,hashes=hashes,review_approved=True,review_sha256=sha(R/'review/approved_sources.json'),input_manifest_fingerprint_sha256=manifest['fingerprint_sha256'],argv=[sys.executable,'-B','-X','utf8',str(runner),'--config',str(config),'--run'],source_snapshot=str(snapshot),outer_probabilities_opened=False,outer_label_metadata_preload_disclosed=True,meta_fit_max=3,retries=0)
save(R/'manager/execution_freeze.json',freeze)
approval=dict(round='round_020',status='approved',utc=now,runner_sha256=manifest['runner_sha256'],config_sha256=manifest['config_sha256'],input_manifest_sha256=manifest['fingerprint_sha256'],independent_review_sha256=sha(R/'review/approved_sources.json'),condition='All three meta models saved and reload checked before OUTER probability read; no tuning; both reference protected TP0>=2389/TP3>=92')
save(R/'manager/outer_read_approval.json',approval)
print(json.dumps({'frozen':True,'utc':now,'manifest':manifest['fingerprint_sha256']}))
