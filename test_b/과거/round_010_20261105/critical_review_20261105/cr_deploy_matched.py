"""Deployable localization: apply the promoted design's own matching to EVERY candidate hour.

At test time the accident hour is unknown, so the hod/row-count matched pool must be
rebuilt per candidate center. This is the operational analogue of the promoted cell.
"""
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
    """percentile of each candidate against its own hod+rowcount matched pool"""
    hod=(centers+lo)%24
    f=np.isfinite(val)
    score=np.full(len(centers),np.nan)
    for n in np.unique(n_rows):
        for h in range(24):
            dd=np.abs(hod-h); circ=np.minimum(dd,24-dd)
            grp=np.flatnonzero((n_rows==n)&(circ<=HOD_TOL)&f)
            if len(grp)<MIN_CTRL+1: continue
            cand=np.flatnonzero((n_rows==n)&(hod==h)&f)
            if not len(cand): continue
            gv=val[grp]; gc=centers[grp]
            order=np.argsort(gv,kind='stable'); sv=gv[order]
            for c in cand:
                keep=np.abs(gc-centers[c])>=SELF_GUARD
                pool=gv[keep]
                if len(pool)<MIN_CTRL: continue
                v=val[c]
                score[c]=(np.sum(pool<v)+0.5*np.sum(pool==v))/len(pool)
    return score

out=[]
seen=set()
for r in D['pools'][3]:
    ft=r['full_track']
    key=r['rfid_id']
    centers=ft['centers']; nr=ft['n_rows']; val=ft['mat'][:,LIN]
    if key not in seen:
        cache=candidate_scores(centers,nr,val); seen.add(key)
        SCORES={key:cache}
    sc=SCORES[key] if key in SCORES else candidate_scores(centers,nr,val)
    SCORES={key:sc}
    ap=ft['acc_pos']
    if not np.isfinite(sc[ap]): 
        out.append({'acc_id':r['acc_id'],'tier':r['tier'],'scored':False}); continue
    ok=np.flatnonzero(np.isfinite(sc))
    order=ok[np.argsort(sc[ok],kind='stable')]
    acc_c=int(centers[ap])
    topk={k:int(np.min(np.abs(centers[order[:k]]-acc_c))) for k in (1,5,10,20,50)}
    out.append({'acc_id':r['acc_id'],'tier':r['tier'],'scored':True,
                'n_scored_candidates':int(len(ok)),
                'acc_score':float(sc[ap]),
                'acc_rank_among_candidates':int(np.searchsorted(np.sort(sc[ok]),sc[ap],'left')),
                'argmin_err_h':int(abs(int(centers[order[0]])-acc_c)),'topk_err':topk})

print('=== deployable: promoted design applied to every candidate hour (hod+-1, exact n_rows, 76h self-guard) ===')
for label,sel in [('ALL',lambda e:True),('Tier0_1',lambda e:e['tier']<=1)]:
    s=[e for e in out if e['scored'] and sel(e)]
    nc=np.array([e['n_scored_candidates'] for e in s])
    rk=np.array([e['acc_rank_among_candidates'] for e in s])
    pct=rk/np.maximum(nc-1,1)
    err=np.array([e['argmin_err_h'] for e in s])
    print(f'\n {label}: {len(s)} events scored; median scorable candidate hours/vessel = {np.median(nc):.0f}')
    print(f'   accident-hour rank percentile among candidates: mean={pct.mean():.4f} median={np.median(pct):.4f} '
          f'(null 0.5), Wilcoxon p={st.wilcoxon(pct-0.5,zero_method="wilcox",mode="approx").pvalue:.5g}')
    print(f'   accident is the single lowest-scoring hour: {int((rk==0).sum())}/{len(s)} = {(rk==0).mean():.3f} '
          f'(chance {np.mean(1/nc):.4f})')
    for k in (1,5,10,20,50):
        hit=np.array([e['topk_err'][k]<=6 for e in s])
        print(f'   any of top-{k:2d} lowest-scoring hours within 6h of truth: {hit.mean():.3f} '
              f'({int(hit.sum())}/{len(s)}); chance = {np.mean(1-(1-13/nc)**k):.4f}')
json.dump(out,open('cr_deploy_matched.json','w'),indent=2)
