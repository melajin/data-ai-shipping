"""(a) design/width sensitivity on a FIXED event set; (b) deployable full-track localization."""
from __future__ import annotations
import sys; sys.dont_write_bytecode=True
import json, pickle
import numpy as np
from scipy import stats as st

METRICS=['lin_raw','straight_win','speed_mean','step_mean','bearing_consistency','turn_rate','still_frac']
LIN=METRICS.index('lin_raw')
PRIMARY='hod_1/nrows_matched'
DESIGNS=[f'hod_{h}/nrows_{"matched" if m else "unmatched"}' for h in (0,1,2,3,'none') for m in (True,False)]
D=pickle.load(open('pools.pkl','rb')); lo=D['lo']

def pct_of_acc(blk,mi):
    acc=blk['acc'][mi]; ctrl=blk['mat'][:,mi]; ctrl=ctrl[np.isfinite(ctrl)]
    if not np.isfinite(acc) or len(ctrl)<15: return None
    return float((np.sum(ctrl<acc)+0.5*np.sum(ctrl==acc))/len(ctrl))

# ---------- (a) fixed event set ----------
base=[r for r in D['pools'][3] if r['tier']<=1 and pct_of_acc(r[PRIMARY],LIN) is not None]
fixed={r['acc_id'] for r in base}
print(f'=== (a) lin_raw, Tier0-1, FIXED event set = the {len(fixed)} events that define the promoted cell ===')
print(f"{'width':>5} {'design':24s} {'n_kept':>6} {'delta':>9} {'wilcoxon_p':>11}   {'(all-eligible n)':>16} {'delta_all':>9}")
rows=[]
for half in (3,6,12):
    for dsg in DESIGNS:
        p_fix=[];p_all=[]
        for r in D['pools'][half]:
            if r['tier']>1: continue
            v=pct_of_acc(r[dsg],LIN)
            if v is None: continue
            p_all.append(v)
            if r['acc_id'] in fixed: p_fix.append(v)
        if len(p_fix)<6: continue
        d=np.array(p_fix)-0.5
        p=st.wilcoxon(d,zero_method='wilcox',mode='approx').pvalue
        rows.append({'half':half,'design':dsg,'n_fixed':len(p_fix),'delta_fixed':float(d.mean()),
                     'p_fixed':float(p),'n_all':len(p_all),'delta_all':float(np.mean(p_all)-0.5)})
        print(f'{half:5d} {dsg:24s} {len(p_fix):6d} {d.mean():+9.4f} {p:11.6f}   {len(p_all):16d} {np.mean(p_all)-0.5:+9.4f}')

w3=[r for r in rows if r['half']==3]
dd=np.array([r['delta_fixed'] for r in w3])
print(f'\n  w=3 across 10 designs on the fixed 48: delta range [{dd.min():+.4f}, {dd.max():+.4f}], '
      f'median {np.median(dd):+.4f}; promoted cell = {[r["delta_fixed"] for r in w3 if r["design"]==PRIMARY][0]:+.4f}')
print(f'  promoted cell is the most negative of the 10 designs: '
      f'{bool([r["delta_fixed"] for r in w3 if r["design"]==PRIMARY][0]==dd.min())}')

# ---------- (b) deployable localization ----------
print('\n=== (b) deployability: rank of the accident window among ALL windows of the same vessel (w=3) ===')
res=[]
for r in D['pools'][3]:
    ft=r['full_track']; col=ft['mat'][:,LIN]; centers=ft['centers']; ap=ft['acc_pos']
    f=np.isfinite(col)
    if not f[ap]: continue
    v=col[f]; c=centers[f]
    acc=col[ap]
    pct=float((np.sum(v<acc)+0.5*np.sum(v==acc)-0.5)/(len(v)-1))
    order=np.argsort(v,kind='stable')
    rank=int(np.searchsorted(v[order],acc,'left'))
    argmin_center=int(c[order[0]])
    err=abs(argmin_center-int(centers[ap]))
    # best |error| achievable inside the top-k candidates
    topk_err={k:int(np.min(np.abs(c[order[:k]]-centers[ap]))) for k in (1,5,10,20,50)}
    res.append({'acc_id':r['acc_id'],'tier':r['tier'],'n_windows':len(v),'pct_full_track':pct,
                'rank':rank,'argmin_err_h':err,'topk_err':topk_err})
for label,sel in [('ALL',lambda e:True),('Tier0_1',lambda e:e['tier']<=1)]:
    s=[e for e in res if sel(e)]
    nw=np.array([e['n_windows'] for e in s]); pc=np.array([e['pct_full_track'] for e in s])
    err=np.array([e['argmin_err_h'] for e in s])
    print(f'\n {label}: n={len(s)} events, median windows/vessel={np.median(nw):.0f}')
    print(f'   mean full-track percentile = {pc.mean():.4f} (null 0.5), median = {np.median(pc):.4f}, '
          f'Wilcoxon p = {st.wilcoxon(pc-0.5,zero_method="wilcox",mode="approx").pvalue:.6g}')
    print(f'   argmin-of-lin_raw hit rate within 6h of the true accident hour: '
          f'{(err<=6).mean():.3f}  ({int((err<=6).sum())}/{len(s)});  chance = {np.mean(13/nw):.4f}')
    for k in (1,5,10,20,50):
        hit=np.array([e['topk_err'][k]<=6 for e in s])
        print(f'   any of top-{k:2d} lowest-lin_raw windows within 6h: {hit.mean():.3f} '
              f'({int(hit.sum())}/{len(s)});  chance = {np.mean(1-(1-13/nw)**k):.4f}')
json.dump({'design_sensitivity_fixed_event_set':rows,'deployability':res},open('cr_design_deploy.json','w'),indent=2)
