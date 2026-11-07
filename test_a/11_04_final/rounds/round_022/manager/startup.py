import datetime, hashlib, json, os, sys
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1]; ROOT=R.parents[1]
def save(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
claim=R/'manager/manager_claim.json'
assert not claim.exists(), 'Existing round022 manager claim: inspect before continuing'
save(claim,dict(round='round_022',claimed_utc=now,manager='/root/round022_manager',provider_thread='01a1a956-8845-7db1-ab01-34aac2261237',parent_orca_session='codex_f1807b56_2615_44fd_bb39_3110d63343de',requested_model='gpt-6-astra',requested_effort='high',host_evidence='Parent collaboration spawn assigned astra_decision; parent Orca worktree ps identifies live provider thread. Separate internal model attestation not available.',authorization='Explicit user resume and rev1 approval relayed by root',manager_start_utc='2026-11-05T01:30:00Z',manager_deadline_utc='2026-11-05T02:15:00Z',compute_deadline_utc='2026-11-05T02:10:00Z',aggregate_compute_seconds_max=1800))
save(R/'manager/delegation.json',dict(utc=now,workers=[dict(task='/root/round022_manager/s1_implementation',requested_model='gpt-6-luna',requested_effort='xhigh',fork_turns='none',owns=['code/s1_features.py','code/run_gate.py']),dict(task='/root/round022_manager/s1_review',requested_model='gpt-6-luna',requested_effort='xhigh',fork_turns='none',owns=['review/*'])],host_evidence='collaboration.spawn_agent returned canonical task names; effective role policy luna_worker specifies model and effort; no separate model internals attestation',manager_owns=['manager/*','configs/*','ROUND_PLAN.md','ROUND_REPORT.md','STATUS.json','NEXT_SESSION.md','EXPERIMENT_LEDGER.csv'],total_slots=4,do_not_revert_others=True))
procs=[]
for p in psutil.process_iter(['pid','name','cmdline','memory_info','create_time']):
 try:
  if 'python' in (p.info['name'] or '').lower(): procs.append(dict(pid=p.pid,argv=p.info['cmdline'],rss=p.info['memory_info'].rss,create_time=p.info['create_time']))
 except (psutil.NoSuchProcess,psutil.AccessDenied): pass
save(R/'manager/initial_resources.json',dict(utc=now,available_bytes=psutil.virtual_memory().available,other_python=procs,expected_peak_bytes=int(1.5*2**30),estimate_status='preliminary: small FIT matrices and sparse profiles plus imported libraries; exact cache needs source inspection',action='source coding and review only; no data loading/training yet',prior_external_job='Root identified s2_devset.py as separate Claude Test B task; do not terminate'))
save(R/'configs/experiment.json',dict(stage='S1_gate',cv_folds=4,seed=42,fit_population=3144,fixed_reference_correct=1817,min_delta_micro=.005,min_delta_correct=16,resolutions=[.01,.05,.10],alpha=5,threads=3,gate_fits_max=8,full_fits_max=6,full_requires_gate_pass=True,s2_fits=0,retries=0,lgbm=dict(objective='multiclass',num_class=4,n_estimators=300,learning_rate=.05,num_leaves=31,colsample_bytree=.7,subsample=.8,subsample_freq=1,random_state=42,n_jobs=3,verbose=-1)))
s=json.loads((ROOT/'STATUS.json').read_text(encoding='utf-8-sig'))
s.update(updated_at_utc=now,goal_status='active_not_achieved',current_round='round_022',round_status='source_preparation',manager_session='/root/round022_manager',latest_result_report='rounds/round_021/ROUND_REPORT.md')
s['paths']['round']='rounds/round_022';s['active_workers']=['/root/round022_manager/s1_implementation','/root/round022_manager/s1_review']
s['user_pause'].update(effective=False,requested=False,resume_instruction='User explicitly resumed approved rev1 S1 FIT internal4fold gate',resumed_at_utc=now)
s['handoff'].update(ready=False,next_session_launched=False,pause_reason=None,next_round=None,note='Round022 active. Root coordinates next fresh Astra session only after this manager completes; no duplicate launches.',launcher_owner='root')
s['latest_user_steering']=dict(source='docs/20261105_CODEX_인계_0.7_실행계획.md rev1 + explicit user resume',diagnostic_protection=dict(TP0=2389,TP3=90),final_5seed_protection=dict(TP0=2381,TP3=92),change_reason='User approved policy; not a mathematical impossibility claim',scope='S1 gate first, no S2 in round022')
s['execution_summary']=dict(round='round_022',status='source_preparation',fits=0,outer_evaluations=0,new_micro_f1=None)
save(ROOT/'STATUS.json',s)
print(json.dumps(dict(claim_created=True,utc=now,available_gib=psutil.virtual_memory().available/2**30)))
