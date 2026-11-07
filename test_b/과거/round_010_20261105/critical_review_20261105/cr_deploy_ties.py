"""Tie-aware version of the deployable localization test."""
from __future__ import annotations
import sys; sys.dont_write_bytecode=True
import json, pickle
import numpy as np
from scipy import stats as st

METRICS=['lin_raw','straight_win','speed_mean','step_mean','bearing_consistency','turn_rate','still_frac']
LIN=METRICS.index('lin_raw')
MIN_CTRL=15; SELF_GUARD=76; HOD_TOL=1
D=pickle.load(open('pools.pkl','rb')); lo=D['lo']

def candidate_scores(centers,n_rows,val):
    hod=(centers+lo)%24; f=np.isfinite(val)
    score=np.full(len(centers),np.nan)
    for n in np.unique(n_rows):
        for h in range(24):
            dd=np.abs(hod-h); circ=np.minimum(dd,24-dd)
            grp=np.flatnonzero((n_rows==n)&(circ<=HOD_TOL)&f)
            if len(grp)<MIN_CTRL+1: continue
            cand=np.flatnonzero((n_rows==n)&(hod==h)&f)
            if not len(cand): continue
            gv=val[grp]; gc=centers[grp]
            for c in cand:
                pool=gv[np.abs(gc-centers[c])>=SELF_GUARD]
                if len(pool)<MIN_CTRL: continue
                v=val[c]
                score[c]=(np.sum(pool<v)+0.5*np.sum(pool==v))/len(pool)
    return score

cache={}
out=[]
for r in D['pools'][3]:
    ft=r['full_track']; rid=r['rfid_id']
    if rid not in cache:
        cache[rid]=candidate_scores(ft['centers'],ft['n_rows'],ft['mat'][:,LIN])
    sc=cache[rid]; centers=ft['centers']; ap=ft['acc_pos']
    if not np.isfinite(sc[ap]): continue
    ok=np.flatnonzero(np.isfinite(sc))
    s=sc[ok]; c=centers[ok]; acc_c=int(centers[ap]); acc_s=float(sc[ap])
    smin=s.min()
    tied_min=np.flatnonzero(s==smin)
    strictly_better=int(np.sum(s<acc_s)); tied_with_acc=int(np.sum(s==acc_s))
    # expected hit with uniform random tie-breaking inside the minimum-score set
    hit_min=float(np.mean(np.abs(c[tied_min]-acc_c)<=6))
    out.append({'acc_id':r['acc_id'],'tier':r['tier'],'n_cand':int(len(ok)),
                'acc_score':acc_s,'min_score':float(smin),
                'n_tied_at_min':int(len(tied_min)),
                'acc_is_in_min_set':bool(acc_s==smin),
                'strictly_better_than_acc':strictly_better,
                'tied_with_acc':tied_with_acc,
                'expected_hit6_random_tiebreak_in_min_set':hit_min})
print('=== tie-aware deployable localization (lin_raw, promoted design applied per candidate hour) ===')
for label,sel in [('ALL',lambda e:True),('Tier0_1',lambda e:e['tier']<=1)]:
    s=[e for e in out if sel(e)]
    nc=np.array([e['n_cand'] for e in s]); tm=np.array([e['n_tied_at_min'] for e in s])
    sb=np.array([e['strictly_better_than_acc'] for e in s])
    inmin=np.array([e['acc_is_in_min_set'] for e in s])
    hit=np.array([e['expected_hit6_random_tiebreak_in_min_set'] for e in s])
    print(f'\n {label}: {len(s)} events')
    print(f'   candidate hours scored per vessel: median {np.median(nc):.0f}')
    print(f'   candidates TIED at the minimum score per vessel: median {np.median(tm):.0f} (min {tm.min()}, max {tm.max()})')
    print(f'   accident hour is inside that tied-minimum set: {int(inmin.sum())}/{len(s)} = {inmin.mean():.3f}')
    print(f'   candidate hours scoring strictly better than the accident hour: median {np.median(sb):.0f}')
    print(f'   expected hit within 6h when picking uniformly from the tied-minimum set: {hit.mean():.4f}')
    print(f'   chance baseline (13 of {np.median(nc):.0f} hours): {np.mean(13/nc):.4f}')
json.dump(out,open('cr_deploy_ties.json','w'),indent=2)
