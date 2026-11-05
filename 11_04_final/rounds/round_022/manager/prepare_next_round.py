"""Run once by the fresh round023 manager; no training, source cache reuse only."""
import datetime,hashlib,json,shutil
from pathlib import Path
OLD=Path(__file__).resolve().parents[1];ROOT=OLD.parents[1];NEW=ROOT/'rounds/round_023'
assert not NEW.exists(),'Existing round023: inspect its owner/claim, never overwrite'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
approval=json.loads((OLD/'review/gate_approved_sources.json').read_text(encoding='utf-8-sig'))
assert approval['approved'] is True
for p,h in approval['source_hashes'].items():assert sha(ROOT/p).lower()==h.lower(),p
for folder in ['code','configs','manager','review','artifacts','logs','tmp']:(NEW/folder).mkdir(parents=True,exist_ok=True)
files=['code/run_gate.py','code/s1_features.py','code/t5_rebuild.py','code/prepare_t5_cache.py','configs/experiment.json','artifacts/t5_fishing_profiles.npz','artifacts/t5_fishing_profiles.manifest.json','artifacts/t5_mask_equivalence.json','tmp/s1_profiles.sqlite','tmp/s1_profiles.sqlite.manifest.json','review/verify_gate_result.py']
copied={}
for name in files:
 source=OLD/name;dest=NEW/name;assert source.is_file(),name
 shutil.copyfile(source,dest);assert sha(source)==sha(dest);copied[name]=sha(dest)
now=datetime.datetime.now(datetime.timezone.utc)
contract=dict(started_utc=now.isoformat(),compute_deadline_utc=(now+datetime.timedelta(minutes=40)).isoformat(),manager_deadline_utc=(now+datetime.timedelta(minutes=45)).isoformat(),compute_seconds_max=1800,job_seconds_max=900,threads_max=3,concurrency=1,minimum_available_gib=2.5,expected_peak_gib=1.5,production_fits_max=8,retries=0,full3fold=0,s2=0,procedure='Fixed8fit replay after round0222fit budget interruption; no model/feature/threshold search; no raw geometry rescan')
(NEW/'manager/runtime_contract.json').write_text(json.dumps(contract,indent=2)+'\n',encoding='utf8')
launcher=(OLD/'manager/launch.py').read_text(encoding='utf8')
oldline='deadline=datetime.datetime(2026,11,5,2,10,0,tzinfo=datetime.timezone.utc)'
assert oldline in launcher
launcher=launcher.replace(oldline,"deadline=datetime.datetime.fromisoformat(json.loads((R/'manager/runtime_contract.json').read_text(encoding='utf-8'))['compute_deadline_utc'])")
(NEW/'manager/launch.py').write_text(launcher,encoding='utf8')
shutil.copyfile(OLD/'manager/freeze_stage.py',NEW/'manager/freeze_stage.py')
shutil.copyfile(OLD/'review/gate_approved_sources.json',NEW/'manager/inherited_gate_approval.json')
(NEW/'manager/copied_inputs.json').write_text(json.dumps(dict(source_round='round022',copied_sha256=copied,prior_fits_completed=2,new_fits_limit=8,training_started=False,approved_model_sources_unchanged=True,launcher_change='deadline read from new runtime contract only'),indent=2)+'\n',encoding='utf8')
(NEW/'ROUND_PLAN.md').write_text('# Round023 — fixed S1 gate procedural recovery\n\nReuse round022 reviewed code and prepared caches unchanged. Previous round completed2/8 fits before its deadline; current runner has no resume API. Preregister one full8fit replay, no tuning and no preparation rescan. Preserve previous2models/evidence in round022. Same3144FIT, StratifiedKFold4/seed42, same T5 strict leave-self-out and centroid S1 proxy, same1817reference and BOTH candidate>=1833 AND delta>=16 numeric gate. No full3fold orS2 in this round. Follow manager/runtime_contract.json. Independent saved-output verification is required; proxy failure is not an impossibility proof.\n',encoding='utf8')
print(json.dumps(dict(prepared=str(NEW),copied_files=len(files),contract=contract)))
