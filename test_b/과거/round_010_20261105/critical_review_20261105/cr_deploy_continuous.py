"""Does the tie coarseness explain the lost localization? Test a continuous matched score."""
from __future__ import annotations
import sys; sys.dont_write_bytecode=True
import json, pickle
import numpy as np
from scipy import stats as st

METRICS=['lin_raw','straight_win','speed_mean','step_mean','bearing_consistency','turn_rate','still_frac']
LIN=METRICS.index('lin_raw')
MIN_CTRL=15; SELF_GUARD=76; HOD_TOL=1
D=pickle.load(open('pools.pkl','rb')); lo=D['lo']

def scores(centers,n_rows,val):
    hod=(centers+lo)%24; f=np.isfinite(val)
    pct=np.full(len(centers),np.nan); z=np.full(len(centers),np.nan)
    for n in np.unique(n_rows):
        for h in range(24):
            dd=np.abs(hod-h); circ=np.minimum(dd,24-dd)
            grp=np.flatnonzero((n_rows==n)&(circ<=HOD_TOL)&f)
            if len(grp)<MIN_CTRL+1: continue
            cand=np.flatnonzero((n_rows==n)&(hod==h)&f)
            gv=val[grp]; gc=centers[grp]
            for c in cand:
                pool=gv[np.abs(gc-centers[c])>=SELF_GUARD]
                if len(pool)<MIN_CTRL: continue
                v=val[c]
                pct[c]=(np.sum(pool<v)+0.5*np.sum(pool==v))/len(pool)
                sd=pool.std(ddof=1)
                z[c]=(v-pool.mean())/sd if sd>0 else 0.0
    return pct,z

cache={}; rows=[]
for r in D['pools'][3]:
    ft=r['full_track']; rid=r['rfid_id']
    if rid not in cache: cache[rid]=scores(ft['centers'],ft['n_rows'],ft['mat'][:,LIN])
    pct,z=cache[rid]; centers=ft['centers']; ap=ft['acc_pos']
    acc_c=int(centers[ap])
    rec={'acc_id':r['acc_id'],'tier':r['tier']}
    for name,s in (('pct',pct),('z',z),('raw',ft['mat'][:,LIN])):
        ok=np.flatnonzero(np.isfinite(s))
        if ap not in ok: rec[name]=None; continue
        sv=s[ok]; c=centers[ok]
        order=np.argsort(sv,kind='stable')
        rec[name]={'n':int(len(ok)),
                   'strictly_better':int(np.sum(sv<s[ap])),
                   'pctile':float(np.sum(sv<s[ap])/ (len(sv)-1)),
                   'topk':{k:int(np.min(np.abs(c[order[:k]]-acc_c))) for k in (1,5,10,20,50,100)}}
    rows.append(rec)

print('=== continuous vs tied score, deployable localization (Tier0-1 and ALL) ===')
for label,sel in [('ALL',lambda e:True),('Tier0_1',lambda e:e['tier']<=1)]:
    print(f'\n--- {label} ---')
    for name in ('pct','z','raw'):
        s=[e[name] for e in rows if sel(e) and e.get(name)]
        n=np.array([e['n'] for e in s]); sb=np.array([e['strictly_better'] for e in s])
        pc=np.array([e['pctile'] for e in s])
        line=(f'  {name:4s} n_events={len(s):3d}  acc percentile among candidates: mean={pc.mean():.4f} '
              f'median={np.median(pc):.4f}  p={st.wilcoxon(pc-0.5,zero_method="wilcox",mode="approx").pvalue:.5g}')
        print(line)
        print(f'       hours strictly better than truth: median {np.median(sb):.0f} of {np.median(n):.0f}')
        for k in (1,5,10,20,50,100):
            hit=np.array([e['topk'][k]<=6 for e in s])
            ch=np.mean(1-(1-13/n)**k)
            flag='  <-- above chance' if hit.mean()>ch else ''
            print(f'       top-{k:3d} within 6h: {hit.mean():.3f} ({int(hit.sum())}/{len(s)})  chance {ch:.3f}{flag}')
json.dump(rows,open('cr_deploy_continuous.json','w'),indent=2)
