import datetime,json,sys
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1]
available=psutil.virtual_memory().available
pre=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),available_bytes=available,expected_peak_bytes=128*2**20,basis='NumPy and tiny six-vessel fixtures only; no data files, models or training',other_python=[dict(pid=p.pid,name=p.info['name']) for p in psutil.process_iter(['name']) if 'python' in (p.info['name'] or '').lower()])
(R/'logs/synthetic_preflight.json').write_text(json.dumps(pre,indent=2)+'\n',encoding='utf8')
assert available>=1.5*2**30
sys.path.insert(0,str(R/'code'))
import numpy as np
import s1_features as s1
from t5_rebuild import make_rebuilder
class Store:
 n_rows=6
 def period_profiles(self,month):
  if month not in (0,1,2):return [[{} for _ in range(6)] for r in range(3)]
  result=[]
  for r,res in enumerate(s1.RESOLUTIONS):
   common=(int(np.floor(1.234/res)),int(np.floor(2.345/res)))
   private=(int(np.floor(9.876/res)),int(np.floor(8.765/res)))
   result.append([{common:.5,private:.5},{common:1.},{common:1.},{common:1.},{common:1.},{private:1.}])
  return result
tr=np.array([0,1,2,3]);labels=np.array([0,1,2,3]);allq=np.arange(6)
original=s1.build_features(Store(),allq,tr,labels)
changed=labels.copy();changed[0]=1
after=s1.build_features(Store(),allq,tr,changed)
assert np.allclose(original[0],after[0],rtol=0,atol=1e-7,equal_nan=True),'S1 own label leaked'
assert not np.allclose(original[4],after[4],rtol=0,atol=1e-7,equal_nan=True),'S1 negative control insensitive'
rev=s1.build_features(Store(),allq,tr[::-1],labels[::-1])
assert np.allclose(original,rev,rtol=0,atol=1e-7,equal_nan=True),'S1 donor order changed meaning'
# Validation labels are deliberately changed in the enclosing label pool, then
# CV-train-only labels are selected again: feature matrix must remain unchanged.
pool=np.r_[labels,[0,3]];pool2=pool.copy();pool2[4:]=[2,1]
permuted=s1.build_features(Store(),allq,tr,pool2[tr])
assert np.array_equal(original,permuted,equal_nan=True)
records=[]
for m in (1,2):
 for r in range(5):records.append((r,m,123,234,24,46,2))
 records.extend([(0,m,987,876,197,175,2),(5,m,987,876,197,175,2)])
rebuild=make_rebuilder(6,records);t0=rebuild(tr,labels);t1=rebuild(tr,changed)
assert np.allclose(t0[0],t1[0],rtol=0,atol=1e-12,equal_nan=True),'T5 self prior/count leak'
assert not np.allclose(t0[4],t1[4],rtol=0,atol=1e-12,equal_nan=True),'T5 negative control insensitive'
assert np.array_equal(t0,rebuild(tr,pool2[tr]),equal_nan=True)
assert np.allclose(t0,rebuild(tr[::-1],labels[::-1]),rtol=0,atol=1e-12,equal_nan=True)
result=dict(passed=True,scope='synthetic six-vessel fixtures; no real score',checks=['S1 own-label change invariance including coarse/global fallback','T5 own-label change invariance including smoothing prior','validation label permutation invariance with fixed CV-train indices','donor-label change positive control','donor order invariance'],s1_shape=list(original.shape),t5_shape=list(t0.shape),real_data_used=False,training_fits=0,utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(R/'artifacts/synthetic_checks.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result))
