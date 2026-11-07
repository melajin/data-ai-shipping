"""Resource-gated setup for a fresh manager. No training and no raw rescan."""
import datetime
import hashlib
import json
import os
import shutil
from pathlib import Path
import psutil

OLD = Path(__file__).resolve().parents[1]
ROOT = OLD.parents[1]
NEW = ROOT / 'rounds/round_024'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

assert not NEW.exists(), 'Existing round024: inspect owner/claim; never overwrite'
guard = json.loads((OLD/'manager/next_resource_contract.json').read_text(encoding='utf-8'))
memory = psutil.virtual_memory()
other_jobs = []
ancestors = {p.pid for p in psutil.Process().parents()} | {os.getpid()}
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        d = p.info
        if d['pid'] not in ancestors and 'python' in (d['name'] or '').lower():
            other_jobs.append({'pid':d['pid'], 'cmdline':d['cmdline']})
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
preflight = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), available_gib=memory.available/2**30,
                 required_entry_gib=guard['minimum_entry_available_gib'], other_python_jobs=other_jobs,
                 estimate_basis=guard['basis'], prepared=False)
write(OLD/'manager/round024_setup_preflight.json', preflight)
assert not other_jobs, 'Other Python jobs active: establish ownership/concurrency before setup'
assert memory.available >= guard['minimum_entry_available_gib']*2**30, 'Resource not ready: defer; do independent work then recheck, no RAM polling or repeated fresh-manager launches'
approval=json.loads((OLD/'review/gate_approved_sources.json').read_text(encoding='utf-8-sig'))
assert approval['approved']
for rel, expected in approval['source_hashes'].items():
    assert sha(ROOT/rel).lower()==expected.lower(), rel
files=['code/run_gate.py','code/s1_features.py','code/t5_rebuild.py','code/prepare_t5_cache.py',
       'configs/experiment.json','artifacts/t5_fishing_profiles.npz','artifacts/t5_fishing_profiles.manifest.json',
       'artifacts/t5_mask_equivalence.json','tmp/s1_profiles.sqlite','tmp/s1_profiles.sqlite.manifest.json',
       'review/verify_gate_result.py','code_author/supplement_metrics.py','manager/launch.py','manager/freeze_stage.py']
for rel in files:
    assert (OLD/rel).is_file(), rel
for folder in ['code','configs','artifacts','tmp','review','manager','logs','code_author']:
    (NEW/folder).mkdir(parents=True, exist_ok=True)
copied={}
for rel in files:
    shutil.copyfile(OLD/rel,NEW/rel)
    assert sha(OLD/rel)==sha(NEW/rel)
    copied[rel]=sha(NEW/rel)
now=datetime.datetime.now(datetime.timezone.utc)
contract=dict(started_utc=now.isoformat(),compute_deadline_utc=(now+datetime.timedelta(minutes=40)).isoformat(),
              manager_deadline_utc=(now+datetime.timedelta(minutes=45)).isoformat(),compute_seconds_max=1800,
              job_seconds_max=900,threads_max=3,concurrency=1,minimum_available_gib=2.5,
              minimum_entry_available_gib=guard['minimum_entry_available_gib'],expected_peak_gib=1.5,
              production_fits_max=8,retries=0,full3fold=0,s2=0,
              procedure='One fixed S1 8-fit replay only after stronger resource admission; round0222fits and round0230fits preserved; no tuning/raw rescan')
write(NEW/'manager/runtime_contract.json',contract)
launcher=(NEW/'manager/launch.py').read_text(encoding='utf-8')
old_guard="if memory.available<2.5*2**30:raise RuntimeError('RAM gate: defer stage and do independent work before recheck')"
new_guard="if memory.available<float(json.loads((R/'manager/runtime_contract.json').read_text(encoding='utf-8'))['minimum_entry_available_gib'])*2**30:raise RuntimeError('Strong entry RAM gate: defer before claim/job; do independent work then recheck')"
assert launcher.count(old_guard)==1
(NEW/'manager/launch.py').write_text(launcher.replace(old_guard,new_guard),encoding='utf-8')
write(NEW/'manager/copied_inputs.json',dict(copied_sha256_before_launcher_guard_change=copied,
      source_round='round023',prior_round022_fits=2,prior_round023_fits=0,
      launcher_change='Only entry guard now reads minimum_entry_available_gib from runtime_contract; stage guards/model code unchanged',
      launcher_sha256_after_change=sha(NEW/'manager/launch.py'),
      source_approval='pending independent reviewer; no approval fabricated by setup'))
shutil.copyfile(OLD/'review/gate_approved_sources.json', NEW/'manager/inherited_gate_approval.json')
(NEW/'ROUND_PLAN.md').write_text('# Round024 — resource-admitted fixed S1 gate\n\nOne paired8fit FIT3144 internal4fold/seed42 replay. Model and feature sources unchanged. Original022 completed2fits; round023 stopped before all fits at cv0 resource guard, not a performance failure. No search, retries, raw rescans, full3fold orS2. Gate remains candidate>=1833 AND candidate-matched_baseline>=16; centroid/record-time proxy only. Runtime and initial RAM thresholds are in manager/runtime_contract.json. Recheck strong entry threshold immediately before launch; preserve per-stage2.5GiB and peak1.5GiB guards. If insufficient, do independent verification/documentation, recheck once at task transition, then record external resource block if unresolved; do not spawn RAM-only manager loops.\n\nTechnical goal: complete and independently verify8models and pairedCV output. Learning goal: distinguish resource interruption, prediction evidence, fold-local label preprocessing, fixed reference and matched baseline. No independent-data/official/hardware claim.\n', encoding='utf-8')
preflight['prepared']=True
write(OLD/'manager/round024_setup_preflight.json',preflight)
print(json.dumps(dict(prepared=str(NEW),copied_files=len(files),contract=contract)))
