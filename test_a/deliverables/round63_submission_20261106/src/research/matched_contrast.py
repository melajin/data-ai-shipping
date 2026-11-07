"""Round 11: observation-matched FIT contexts + six pairwise contrast tasks.

No REPORT-based choices. The same 150 summary/layout columns as round 9.
Joint-only outputs are controls, never the proposed final decision rule.
"""
from experiment import *

def policy(joint,pair,y):
    # Each class gets evidence from its three independently trained pair tasks.
    # No candidate is excluded by the preliminary names.
    contrast=np.log(np.clip(pair,1e-6,1)).sum(axis=2)/3
    best=None
    for alpha in [.25,.5,.75,1.]:
        logits=(1-alpha)*np.log(np.clip(joint,1e-6,1))+alpha*contrast
        for g,t,d in itertools.product([.8,1.,1.2,1.4],[1.,1.5,2.,2.5],[.8,1.,1.2]):
            w=np.array([1.,g,t,d]);pr=(logits+np.log(w)).argmax(1)
            # Competition primary objective first; macro only breaks exact ties.
            key=(int(np.sum(pr==y)),f1_score(y,pr,labels=range(4),average='macro',zero_division=0),-float(np.abs(np.log(w)).sum()),-abs(alpha-.5))
            if best is None or key>best[0]:best=(key,alpha,w)
    return best[1],best[2],best[0]

def apply_policy(joint,pair,alpha,w):
    logits=(1-alpha)*np.log(np.clip(joint,1e-6,1))+alpha*np.log(np.clip(pair,1e-6,1)).sum(axis=2)/3+np.log(w)
    return logits.argmax(1)

def bootstrap_delta(a,b,y):
    diff=(a==y).astype(float)-(b==y).astype(float);rng=np.random.default_rng(SEED+1101)
    means=np.array([diff[rng.integers(len(y),size=len(y))].mean() for _ in range(5000)])
    return {'delta':float(diff.mean()),'paired_vessel_bootstrap_95_percentile_interval':np.quantile(means,[.025,.975]).tolist(),
            'rescued':int(np.sum((a==y)&(b!=y))),'damaged':int(np.sum((a!=y)&(b==y))),
            'warning':'Development-set paired sampling interval, not an independent post-selection generalization guarantee.'}

def main():
    s,base=load();fit=s.split.eq('FIT').to_numpy();q=~fit;sub=s.loc[q];tu=sub.split.eq('TUNE').to_numpy();re=~tu;y=s.y.to_numpy()
    x={v:base[v].join(pd.read_csv(B/f'layout_features_{v}.csv',index_col='id').reindex(s.index)) for v in VIEWS}
    rd=B/'round_11'
    if not rd.exists():
        rd=setup_round(11,{'design':'observation-matched contexts and all-class pairwise contrast reinspection',
            'core_change_from_previous':'Replace mixed-budget proposal-correctness routing by six direct class-pair discrimination tasks. Match FIT and query observation windows; all four classes remain eligible, including absent candidate names.',
            'training_task':'Shared four-class candidate head plus six pair-specific TabICLv2 contexts using official FIT labels only; no learned correctness gating and no self-generated FIT labels.',
            'features':'Exactly same S+L 150 columns as round9, no new features for this causal comparison.',
            'ensemble':4,'primary':'Matched context + joint and pairwise log-evidence fusion, at least .25 pair evidence weight; fixed before scoring.',
            'selection':'Separately for each view, 192 policies on TUNE only, Micro first, macro tie-break. No REPORT-based candidate or method selection.',
            'controls':'Mixed round9 shared head vs matched shared head, same raw features/seed/ensemble. Joint-only is diagnostic. Baseline round9 final differs in multiple mechanisms.',
            'scope':'Same conditional retrospective research scope and fixed splits; not official or online evaluation.'})
        shutil.copy2(Path(__file__),rd/Path(__file__).name)
        dump(rd/'predeclared_protocol.json',{'views':VIEWS,'matched_reference':'For query view v, every FIT vessel uses its own v view. No target label or query-to-context identity matching.',
            'input_hashes':{v:sha(B/f'layout_features_{v}.csv') for v in VIEWS},'FIT_ids_sha256':sha(B/'fixed_split.csv'),
            'no_report_choice':True,'pair_task_contexts':{f'{a}-{b}':int((fit&np.isin(y,[a,b])).sum()) for a,b in itertools.combinations(range(4),2)}})
    prob={};pairs={};final={};decisions={};ts=[]
    for v in VIEWS:
        jf=rd/f'prob_{v}.npy'
        if jf.exists():p=np.load(jf)
        else:
            p,cc=predict(x[v].loc[fit],y[fit],x[v].loc[q],SEED+910,4);assert list(cc)==[0,1,2,3];np.save(jf,p)
        prob[v]=p;pair=np.ones((q.sum(),4,4))
        for a,b in itertools.combinations(range(4),2):
            fn=rd/f'pair_{v}_{a}_{b}.npy';ctx=fit&np.isin(y,[a,b])
            assert not(set(s.index[ctx])&set(s.index[q]))
            if fn.exists():pa=np.load(fn)
            else:
                pp,cc=predict(x[v].loc[ctx],y[ctx],x[v].loc[q],SEED+1100+10*a+b,4)
                pa=pp[:,list(cc).index(a)];np.save(fn,pa)
            pair[:,a,b]=pa;pair[:,b,a]=1-pa
        pairs[v]=pair;np.save(rd/f'pair_{v}.npy',pair)
        alpha,w,key=policy(p[tu],pair[tu],sub.y.to_numpy()[tu]);final[v]=apply_policy(p,pair,alpha,w)
        decisions[v]={'pair_log_evidence_weight':alpha,'class_weights':w.tolist(),'TUNE_micro':key[0]/tu.sum(),'TUNE_macro':key[1]}
        print('TUNE_POLICY',v,json.dumps(decisions[v]),flush=True)
    dump(rd/'decision_policy.json',decisions) # Freeze before REPORT scoring.
    # Names are descriptive (same 90% pooled TUNE recall construction as round9).
    tp=np.concatenate([prob[v][tu] for v in VIEWS]);ty=np.tile(sub.y.to_numpy()[tu],4)
    ts=np.array([np.quantile(tp[ty==c,c],.1,method='lower') for c in range(4)])
    dump(rd/'thresholds.json',ts.tolist())
    extra={v:{'proposal':prob[v].argmax(1),'pair_unweighted_proposal':np.log(np.clip(pairs[v],1e-6,1)).sum(2).argmax(1)} for v in VIEWS}
    m=evaluate(rd,s,base,prob,ts,final,extra)
    controls={}
    for v in VIEWS:
        old=np.load(B/'round_09'/f'prob_{v}.npy');controls[v]={}
        for sp,z in [('TUNE',tu),('REPORT',re)]:
            yy=sub.y.to_numpy()[z];controls[v][sp]={
                'mixed_shared_head_only':metrics(yy,old[z].argmax(1)),
                'matched_shared_head_only':metrics(yy,prob[v][z].argmax(1)),
                'matched_pair_only_unweighted':metrics(yy,extra[v]['pair_unweighted_proposal'][z]),
                'final':m[v][sp]}
    dump(rd/'controlled_diagnostics.json',controls)
    cmp={};yy=sub.y.to_numpy()[re]
    for n in [2,9,10]:
        old=pd.read_csv(B/f'round_{n:02}'/'predictions_full.csv',index_col='id').reindex(sub.index[re]);assert np.array_equal(old.y.to_numpy(),yy)
        cmp[f'round{n}']=bootstrap_delta(final['full'][re],old.prediction.to_numpy(),yy)
    dump(rd/'paired_comparisons.json',cmp)
    finish_round(11,m,'Separately diagnosed matched observation reference and contrast reinspection. Primary rule selected on TUNE Micro first. Original joint-only argmax remains a control; proposed output requires independent pair evidence. No claim that data-processing errors are the sole cause.')
    print('DIAGNOSTIC_FULL',json.dumps({k:{n:z['micro_f1'] for n,z in val.items()} for k,val in controls['full'].items()}),flush=True)
    print('PAIRED_COMPARISONS',json.dumps(cmp),flush=True)

if __name__=='__main__':main()
