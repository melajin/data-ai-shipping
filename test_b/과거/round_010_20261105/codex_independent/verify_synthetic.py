"""Small mathematical checks, NOT dev results or T3 independent verification."""
import sys
sys.dont_write_bytecode=True
import ctypes,json,math,itertools
from datetime import datetime
from pathlib import Path
P=Path(__file__).resolve().parent
class Mem(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('available',ctypes.c_ulonglong),('tp',ctypes.c_ulonglong),('ap',ctypes.c_ulonglong),('tv',ctypes.c_ulonglong),('av',ctypes.c_ulonglong),('ext',ctypes.c_ulonglong)]
m=Mem();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
rec={'checked_at':datetime.now().astimezone().isoformat(),'stage':'small_synthetic_math_check','available_mib':m.available/2**20,
 'estimated_maximum_increment_mib':256,'reserve_mib':1024,'estimate_basis':'scientific imports plus 36-hour synthetic arrays and 8-pairing enumeration; no parquet or dev evaluation',
 'other_experiment':'T1 deferred; no own parallel experiment','allowed':m.available/2**20>=1280}
(P/'synthetic_memory.json').write_text(json.dumps(rec,indent=2),encoding='utf-8')
if not rec['allowed']:print('synthetic validation deferred');sys.exit(75)
import numpy as np
import pandas as pd
import t1_decompose as t
from scipy import stats as st

def distance(a,b,c,d):
    p,q=math.radians(a),math.radians(c);x=math.sin((q-p)/2)**2+math.cos(p)*math.cos(q)*math.sin(math.radians(d-b)/2)**2
    return 12742000*math.asin(math.sqrt(min(1,max(0,x))))

ts=np.array([0,1,3,4,5,9,10,13,14,15,16,20,21,22,26,27,28,29])
n=len(ts);lm=np.array([0,.5,4,9,3,12,0,7,9,20,1,5,0,8,2,9,13,4.])
g=pd.DataFrame({'rfid_id_int':1,'ts':ts,'len_m':lm,'bbox_m':lm*.6,
 'cen_lat':35+np.sin(np.arange(n))*.001,'cen_lon':127+np.cos(np.arange(n))*.001,
 'state':'이동','score':0.})
comparisons=0
for half in [3,6,12]:
    W,_=t.make_windows(g,half,0,35)
    for j,c in enumerate(W['center']):
        sub=g.loc[(g.ts>=c-half)&(g.ts<=c+half)];L=sub.len_m.to_numpy();la=sub.cen_lat.to_numpy();lo=sub.cen_lon.to_numpy();times=sub.ts.to_numpy()
        expected={'lin_raw':np.mean(sub.loc[sub.len_m>=1,'bbox_m']/sub.loc[sub.len_m>=1,'len_m']),
          'speed_mean':np.mean(L) if len(L) else np.nan,'still_frac':np.mean(L<np.quantile(lm,.1)) if len(L) else np.nan,
          'straight_win':distance(la[0],lo[0],la[-1],lo[-1])/sum(L) if len(L)>=2 and sum(L)>0 else np.nan}
        steps=[distance(la[k],lo[k],la[k+1],lo[k+1])/(times[k+1]-times[k]) for k in range(len(L)-1)]
        angles=[]
        for k in range(len(L)-1):
            p,q=math.radians(la[k]),math.radians(la[k+1]);dl=math.radians(lo[k+1]-lo[k])
            angles.append(math.atan2(math.sin(dl)*math.cos(q),math.cos(p)*math.sin(q)-math.sin(p)*math.cos(q)*math.cos(dl)))
        expected['step_mean']=np.mean(steps) if steps else np.nan
        expected['bearing_consistency']=abs(sum(complex(math.cos(x),math.sin(x)) for x in angles)/len(angles)) if angles else np.nan
        changes=[abs((b-a+math.pi)%(2*math.pi)-math.pi) for a,b in zip(angles[:-1],angles[1:])]
        expected['turn_rate']=np.mean(changes) if changes else np.nan
        for metric,v in expected.items():
            assert np.isclose(v,W[metric][j],atol=1e-8,rtol=1e-8,equal_nan=True),(half,c,metric,v,W[metric][j])
            comparisons+=1
fake={'center':np.arange(400),'n_rows':np.full(400,7)}
mask=t.ctrl_mask(fake,400,[100,200],72,7,True)
assert np.array_equal(mask,(np.abs(fake['center']-100)>=76)&(np.abs(fake['center']-200)>=76))
assert t.pct_rank(2,np.array([1,2,2,3.]))==.5
a=np.array([True,False,True]);q=np.array([.2,.7,.4]);direct=0.
for combo in itertools.product([False,True],repeat=3):
    c=np.array(combo);prob=float(np.prod(np.where(c,q,1-q)));b=int((a&~c).sum());d=int((~a&c).sum())
    direct+=prob*(float(st.binomtest(b,b+d,.5).pvalue) if b+d else 1.)
mixed=t.mcnemar_all_controls(a,q)
assert abs(direct-mixed['mcnemar_pairing_expected_exact_p'])<1e-12
result={'status':'passed','scalar_oracle_metric_window_comparisons':comparisons,'guard_h_actual':76,
 'midrank_tie_checked':True,'McNemar_pairings_enumerated':8,'exact_p_mixture_matches_enumeration':True,
 'scope':'small synthetic mathematical verification only; not actual dev evaluation or separate T3'}
(P/'synthetic_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
