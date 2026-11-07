"""Baseline reproduction + exchangeability permutation with selective (max-T) correction."""
from __future__ import annotations
import sys; sys.dont_write_bytecode=True
import json, pickle
import numpy as np
from scipy import stats as st

METRICS=['lin_raw','straight_win','speed_mean','step_mean','bearing_consistency','turn_rate','still_frac']
PRIMARY='hod_1/nrows_matched'
MIN_CTRL=15

D=pickle.load(open('pools.pkl','rb'))
pools=D['pools'][3]

def event_percentiles(rec, design):
    """percentile vector over all exchangeable placements j=0(real accident),1..M"""
    blk=rec[design]
    comb=np.vstack([blk['acc'][None,:], blk['mat']])   # (M+1, 7)
    out={}
    for mi,m in enumerate(METRICS):
        col=comb[:,mi]; f=np.isfinite(col)
        nf=int(f.sum())
        pct=np.full(len(col),np.nan); valid=np.zeros(len(col),bool)
        if nf>=MIN_CTRL+1:
            vals=col[f]; order=np.argsort(vals,kind='stable'); sv=vals[order]
            less=np.searchsorted(sv,vals,'left')
            eq=np.searchsorted(sv,vals,'right')-less
            den=nf-1
            p=(less+0.5*(eq-1))/den
            idxf=np.flatnonzero(f)
            pct[idxf]=p; valid[idxf]=den>=MIN_CTRL
        out[m]=(pct,valid)
    return out

def cell_stats(pcts, zero_vals):
    """Wilcoxon on pct-0.5 with the zero-inflation rule of the contract."""
    if len(pcts)<6: return None
    if np.mean(np.asarray(zero_vals)==0.0)>0.5: return None   # zero-inflated: no percentile inference
    d=np.asarray(pcts)-0.5
    if np.all(d==0): return None
    return st.wilcoxon(d,zero_method='wilcox',mode='approx').pvalue, float(np.mean(d)), len(d)

# ---- precompute placements
pre=[]
for rec in pools:
    ep=event_percentiles(rec,PRIMARY)
    blk=rec[PRIMARY]
    comb=np.vstack([blk['acc'][None,:],blk['mat']])
    pre.append({'tier':rec['tier'],'acc_id':rec['acc_id'],'rfid':rec['rfid_id'],'ep':ep,
                'raw':comb,'M1':comb.shape[0]})

STRATA={'ALL':lambda e:True,'Tier0_1':lambda e:e['tier']<=1}

def run(choice):
    """choice[i] = placement index for event i; returns dict cell->(p,delta,n)"""
    res={}
    for sname,sel in STRATA.items():
        for mi,m in enumerate(METRICS):
            ps=[]; raws=[]
            for i,e in enumerate(pre):
                if not sel(e): continue
                j=choice[i]
                pct,valid=e['ep'][m]
                if valid[j]:
                    ps.append(pct[j]); raws.append(e['raw'][j,mi])
            r=cell_stats(ps,raws)
            if r: res[(m,sname)]=r
    return res

obs=run(np.zeros(len(pre),int))
print('=== baseline reproduction (primary design hod_1/nrows_matched, w=3) ===')
for (m,s),(p,d,n) in sorted(obs.items(),key=lambda kv:kv[1][0]):
    print(f'  {m:20s} {s:8s} n={n:3d} delta={d:+.6f} p={p:.8f}  p*7={min(1,7*p):.6f} p*12={min(1,12*p):.6f}')
obs_min=min(v[0] for v in obs.values())
K_obs=len(obs)
print(f'  testable cells (zero-inflation rule applied) = {K_obs}; observed min p = {obs_min:.8f}')

rng=np.random.default_rng(20261105)
B=4000
null_min=np.empty(B); null_lin=np.empty(B)
Ms=np.array([e['M1'] for e in pre])
for b in range(B):
    choice=rng.integers(0,Ms)
    r=run(choice)
    null_min[b]=min(v[0] for v in r.values()) if r else 1.0
    null_lin[b]=r.get(('lin_raw','Tier0_1'),(1.0,))[0]
    if (b+1)%500==0: print('  perm',b+1,flush=True)

sel_p=float((null_min<=obs_min).mean())
marg_p=float((null_lin<=obs['lin_raw','Tier0_1'][0]).mean())
print()
print('=== exchangeability permutation (accident window swapped with a matched control) ===')
print(f'  marginal permutation p for lin_raw/Tier0_1       = {marg_p:.5f}   (B={B})')
print(f'  selective max-T p (min over {K_obs} pre-registered cells) = {sel_p:.5f}')
print(f'  null min-p quantiles 5/50/95%: {np.percentile(null_min,[5,50,95])}')
json.dump({'B':B,'observed':{f'{m}|{s}':{'p':v[0],'delta':v[1],'n':v[2]} for (m,s),v in obs.items()},
           'observed_min_p':obs_min,'testable_cells':K_obs,
           'marginal_permutation_p_lin_raw_Tier0_1':marg_p,'selective_maxT_p':sel_p,
           'null_min_p_quantiles':{q:float(np.percentile(null_min,q)) for q in (1,5,25,50,75,95)}},
          open('cr_maxt.json','w'),indent=2)
