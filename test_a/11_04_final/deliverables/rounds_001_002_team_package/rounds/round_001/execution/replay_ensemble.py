from __future__ import annotations
import hashlib, json, os, platform, sys, time
from datetime import datetime, timezone
from pathlib import Path
import lightgbm as lgb
import numpy as np
import pandas as pd

WORK=Path(__file__).resolve().parent
TASK=Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104")
MODEL_DIR=TASK/"artifacts"/"exp01"/"sqrt_macro"/"models"
SEED_DIR=TASK/"artifacts"/"exp01"/"sqrt_macro"/"seed_predictions"
AGG_CSV=TASK/"artifacts"/"exp01"/"sqrt_macro"/"outer_predictions.csv"
VALIDATION=TASK/"reports"/"exp01"/"data_validation.json"
T5_COLS=["t5_main_연안복합","t5_main_자망","t5_main_통발","t5_main_채낚기연승낚시","t5_month_연안복합","t5_month_자망","t5_month_통발","t5_month_채낚기연승낚시","t5_fine_grid_ok_ratio","t5_log1p_fishing_rows"]
FOLDS=(0,1,2); SEEDS=(1,7,42,2024,2026)

def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()
def snap(paths):
 out={}
 for p in sorted(set(paths),key=str):
  s=p.stat(); out[str(p)]={"bytes":s.st_size,"mtime_ns":s.st_mtime_ns,"sha256":sha(p)}
 return out
def score(y,pred):
 correct=int(np.count_nonzero(y==pred)); n=len(y); f1=[]; recall=[]
 for c in range(4):
  tp=int(np.count_nonzero((y==c)&(pred==c))); fp=int(np.count_nonzero((y!=c)&(pred==c))); fn=int(np.count_nonzero((y==c)&(pred!=c)))
  f1.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0); recall.append(tp/(tp+fn) if tp+fn else 0.0)
 return {"n":n,"correct":correct,"micro_f1":correct/n if n else None,"macro_f1":float(np.mean(f1)),"class_recall":recall,"class_f1":f1}
def prob_stats(a,b):
 d=np.abs(np.asarray(a)-np.asarray(b)); return {"shape":list(d.shape),"max_abs":float(d.max()) if d.size else 0.0,"mean_abs":float(d.mean()) if d.size else 0.0,"exact_rows_changed":int(np.count_nonzero(np.any(a!=b,axis=1))),"allclose_1e_12":bool(np.allclose(a,b,atol=1e-12,rtol=0))}
def main():
 t0=time.perf_counter(); validation=json.loads(VALIDATION.read_text(encoding="utf-8"))
 csvs={}
 for f in FOLDS:
  matches=[Path(k) for k in validation.get("input_hashes",{}) if f"fold_{f}_t5.csv" in k]
  if len(matches)!=1: raise RuntimeError(f"fold {f} T5 path count={len(matches)}")
  csvs[f]=matches[0]
 folds={f:TASK/"artifacts"/"exp01"/f"fold_{f}_features.npz" for f in FOLDS}
 models={(f,s):MODEL_DIR/f"fold_{f}_seed_{s}.txt" for f in FOLDS for s in SEEDS}
 seednpz={(f,s):SEED_DIR/f"fold_{f}_seed_{s}.npz" for f in FOLDS for s in SEEDS}
 inputs=[VALIDATION,AGG_CSV,*csvs.values(),*folds.values(),*models.values(),*seednpz.values()]
 missing=[str(p) for p in inputs if not p.is_file()]
 if missing: raise FileNotFoundError("; ".join(missing))
 before=snap(inputs)
 per_model=[]; pooled_ids=[]; pooled_y=[]; pooled_base=[]; pooled_rt=[]; pooled_ref=[]; fold_results={}
 for f in FOLDS:
  with np.load(folds[f],allow_pickle=False) as z:
   ids=z["rfid_ids"].astype(str); y=z["y"].astype(int); roles=z["roles"].astype(str); X=z["X"].astype(np.float64,copy=True); names=z["feature_names"].astype(str).tolist()
  if names[156:166]!=T5_COLS: raise RuntimeError(f"fold {f}: T5 order mismatch")
  oi=np.flatnonzero(roles=="OUTER"); oids=ids[oi]; oy=y[oi]
  expected_outer={0:1966,1:1966,2:1965}[f]
  if len(oi)!=expected_outer or len(set(oids))!=expected_outer: raise RuntimeError(f"fold {f}: invalid outer roster")
  frame0=pd.read_csv(csvs[f],dtype={"rfid_id":str})
  frame1=pd.read_csv(csvs[f],dtype={"rfid_id":str},float_precision="round_trip")
  if frame0["rfid_id"].tolist()!=ids.tolist() or frame1["rfid_id"].tolist()!=ids.tolist(): raise RuntimeError(f"fold {f}: ID mismatch")
  Xrt=X.copy(); Xrt[:,156:166]=frame1[T5_COLS].to_numpy(dtype=np.float64)
  p0_by_seed=[]; p1_by_seed=[]
  saved_checks=[]
  for s in SEEDS:
   model=lgb.Booster(model_file=str(models[(f,s)]))
   p0=np.asarray(model.predict(X[oi],num_threads=1),dtype=np.float64)
   p1=np.asarray(model.predict(Xrt[oi],num_threads=1),dtype=np.float64)
   with np.load(seednpz[(f,s)],allow_pickle=False) as saved:
    sid=saved["outer_ids"].astype(str); sp=saved["outer_probs"].astype(np.float64)
   if sid.tolist()!=oids.tolist():
    pos={rid:i for i,rid in enumerate(sid.tolist())}
    if set(pos)!=set(oids.tolist()): raise RuntimeError(f"fold {f} seed {s}: saved outer IDs mismatch")
    sp=sp[np.array([pos[x] for x in oids])]
   saved_checks.append({"seed":s,"saved_probability_vs_model_replay":prob_stats(sp,p0)})
   p0_by_seed.append(p0); p1_by_seed.append(p1)
   per_model.append({"fold":f,"seed":s,"outer_rows":len(oi),"probability_delta":prob_stats(p0,p1),"outer_argmax_changed":int(np.count_nonzero(p0.argmax(1)!=p1.argmax(1)))})
  e0=np.mean(np.stack(p0_by_seed),axis=0); e1=np.mean(np.stack(p1_by_seed),axis=0)
  agg=pd.read_csv(AGG_CSV,dtype={"rfid_id":str},float_precision="round_trip")
  ref=agg[(agg["fold"]==f)&(agg["role"]=="OUTER")].copy()
  if set(ref["rfid_id"].tolist())!=set(oids.tolist()) or len(ref)!=len(oids): raise RuntimeError(f"fold {f}: reference aggregate roster mismatch")
  ref=ref.set_index("rfid_id").loc[oids]
  ref_probs=ref[["p0","p1","p2","p3"]].to_numpy(dtype=np.float64)
  ref_pred=ref["pred"].to_numpy(dtype=np.int64)
  base_pred=e0.argmax(1); rt_pred=e1.argmax(1)
  base_score=score(oy,base_pred); rt_score=score(oy,rt_pred)
  fold_results[str(f)]={
   "outer_rows":len(oi),"saved_seed_prediction_checks":saved_checks,
   "five_seed_mean_vs_stored_outer_predictions":prob_stats(ref_probs,e0),
   "outer_probability_delta_individual_seed_max_abs":max(m["probability_delta"]["max_abs"] for m in per_model if m["fold"]==f),
   "outer_probability_delta_five_seed_mean":prob_stats(e0,e1),
   "stored_outer_prediction_argmax_matches_baseline_ensemble":int(np.count_nonzero(ref_pred!=base_pred))==0,
   "baseline_ensemble_score":base_score,"round_trip_ensemble_score":rt_score,
   "argmax_changed":int(np.count_nonzero(base_pred!=rt_pred)),
   "gains_correct":int(np.count_nonzero((base_pred!=oy)&(rt_pred==oy))),
   "losses_correct":int(np.count_nonzero((base_pred==oy)&(rt_pred!=oy))),
   "net_correct_delta":int(np.count_nonzero(rt_pred==oy)-np.count_nonzero(base_pred==oy)),
   "micro_delta":rt_score["micro_f1"]-base_score["micro_f1"],
   "macro_delta":rt_score["macro_f1"]-base_score["macro_f1"],
  }
  pooled_ids.extend(oids.tolist()); pooled_y.extend(oy.tolist()); pooled_base.extend(base_pred.tolist()); pooled_rt.extend(rt_pred.tolist()); pooled_ref.extend(ref_pred.tolist())
  del X,Xrt,p0_by_seed,p1_by_seed
 pooled_ids=np.asarray(pooled_ids,dtype=str); y=np.asarray(pooled_y,dtype=np.int64); b=np.asarray(pooled_base,dtype=np.int64); r=np.asarray(pooled_rt,dtype=np.int64); refpred=np.asarray(pooled_ref,dtype=np.int64)
 if len(pooled_ids)!=5897 or len(set(pooled_ids.tolist()))!=5897: raise RuntimeError("pooled OUTER roster is not 5897 unique development vessels")
 pooled={"outer_rows":len(y),"stored_baseline_outer_prediction_match_count":int(np.count_nonzero(b==refpred)),"baseline_ensemble_score":score(y,b),"round_trip_ensemble_score":score(y,r),"argmax_changed":int(np.count_nonzero(b!=r)),"gains_correct":int(np.count_nonzero((b!=y)&(r==y))),"losses_correct":int(np.count_nonzero((b==y)&(r!=y))),"net_correct_delta":int(np.count_nonzero(r==y)-np.count_nonzero(b==y)),"micro_delta":score(y,r)["micro_f1"]-score(y,b)["micro_f1"],"macro_delta":score(y,r)["macro_f1"]-score(y,b)["macro_f1"]}
 after=snap(inputs); changed=[p for p in before if before[p]!=after[p]]
 if changed: raise RuntimeError("source inputs changed: "+"; ".join(changed))
 result={"experiment":"supplemental five-seed ensemble inference comparison","status":"completed","started_utc":datetime.fromtimestamp(time.time()-(time.perf_counter()-t0),timezone.utc).isoformat(),"finished_utc":datetime.now(timezone.utc).isoformat(),"elapsed_seconds":time.perf_counter()-t0,"scope":{"development_only":True,"outer_rows":5897,"holdout_rows_read":0,"raw_parsing":False,"training":False,"round_trip_reader":"pandas float_precision=round_trip","stored_prediction_reference":str(AGG_CSV)},"environment":{"python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"pandas":pd.__version__,"lightgbm":lgb.__version__,"prediction_threads":1,"PYTHONDONTWRITEBYTECODE":os.environ.get("PYTHONDONTWRITEBYTECODE"),"PYTHONPYCACHEPREFIX":os.environ.get("PYTHONPYCACHEPREFIX"),"TEMP":os.environ.get("TEMP"),"TMP":os.environ.get("TMP")},"input_hashes_before":before,"input_hashes_after":after,"source_files_changed":changed,"fold_results":fold_results,"pooled_development_outer":pooled,"per_model_outer_replay":per_model,"interpretation":["Baseline 5-seed model probabilities were compared with existing stored seed and outer aggregate artifacts before interpreting the parser perturbation.","Round-trip predictions are parser-sensitivity re-inference on the same development OUTER roster, not new independent performance evidence.","No dynamic original T5 array was reconstructed; this supplemental run only isolates CSV parser and ensemble effects."]}
 (WORK/"supplemental_ensemble.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"status":result["status"],"elapsed_seconds":result["elapsed_seconds"],"pooled":pooled,"output":str(WORK/"supplemental_ensemble.json")},ensure_ascii=False),flush=True)
if __name__=="__main__": main()


