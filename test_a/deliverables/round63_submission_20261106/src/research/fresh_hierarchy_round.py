"""Round24: reproduce the strongest previous design from fresh fits, then
test a conditional class task. No previous-round learned artifact is read.
"""
from fresh_rounds import *
from fresh_relation_basis import build


def fit_task(rd,name,v,x,s,ctx,labels,seed):
    q=s.split.ne('FIT').to_numpy();assert not set(s.index[ctx])&set(s.index[q]);begun=now()
    p,cc=predict(x.loc[ctx],labels,x.loc[q],seed,4);np.save(rd/f'{name}_{v}.npy',p)
    call={'arm':name,'view':v,'task':name,'started':begun,'finished':now(),'seed':seed,'n_context':int(ctx.sum()),'n_query':int(q.sum()),'n_features':x.shape[1],
        'context_ids_sha256':hashlib.sha256(s.index[ctx].to_numpy().tobytes()).hexdigest(),'query_ids_sha256':hashlib.sha256(s.index[q].to_numpy().tobytes()).hexdigest(),
        'context_label_sha256':hashlib.sha256(np.asarray(labels,dtype=np.int64).tobytes()).hexdigest(),'classes':cc.tolist(),
        'original_checkpoint':str(CHECKPOINT),'fresh_fit':True,'gradient_updates':False}
    with (rd/'fresh_fit_calls.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(call)+'\n')
    return p,cc


def choose_blend(j0,p0,j1,p1,alpha,w,y,tu):
    best=None;candidates=[]
    for beta in [0.,.25,.5,.75,1.]:
        j=(1-beta)*j0+beta*j1;p=(1-beta)*p0+beta*p1;pr=apply_policy(j,p,alpha,w);m=metrics(y[tu],pr[tu]);key=(int((pr[tu]==y[tu]).sum()),m['macro_f1'],-beta)
        candidates.append({'beta':beta,'TUNE_correct':key[0],'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']})
        if best is None or key>best[0]:best=(key,beta,j,p,pr)
    return best[1:],candidates


def hierarchy_scores(joint,pair,hierarchy,alpha,w,gamma):
    base=(1-alpha)*np.log(np.clip(joint,1e-6,1))+alpha*np.log(np.clip(pair,1e-6,1)).sum(2)/3+np.log(w)
    conditional=np.log(np.clip(hierarchy,1e-6,1))+np.log(w)
    return (1-gamma)*base+gamma*conditional


def main():
    rd=start(24,'Fresh reproduction of compact/state/shape-region reinspection, plus conditional C-vs-rest and G/P/D classification tasks')
    shutil.copy2(Path(__file__),rd/Path(__file__).name);shutil.copy2(B/'fresh_relation_basis.py',rd/'fresh_relation_basis.py')
    dump(rd/'predeclared_protocol.json',{'baseline':'Fresh compact150 policy, fresh state337 blending, fresh FIT-only6shape/8region prototypes, fresh402 pair tasks and TUNE blend; all previous-design operations recomputed.',
        'primary_change':'Two new402-feature tasks: C versus nonC on all FIT, and G/P/D conditional classification on nonC FIT. Chain-rule probabilities combined with baseline log evidence.',
        'hierarchy_selection':'Five gamma values0,.25,.5,.75,1 on TUNE Micro, macro tie-break, smaller gamma. Baseline weights remain fixed after fresh TUNE compact policy selection.',
        'conditional_probability':'P(C)=1-P(nonC); P(k)=P(nonC)*P(k|nonC), k=G/P/D. Every query goes to both tasks; no hard exclusion.',
        'model_fits':88,'learned_transforms':'All4 views: fresh median/clipping/scaler and6shape/8region prototypes from FIT rows only','gradient_updates':False})
    restrict_old_rounds(24);build(rd)
    s,base=load();fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();y=s.y.to_numpy();qy=sub.y.to_numpy()
    prob={};pairs={};final={};decisions={};controls={};inputs={}
    for v in VIEWS:
        compact=base[v].join(pd.read_csv(B/f'layout_features_{v}.csv',index_col='id')).reindex(s.index)
        state=compact.join(pd.read_csv(B/f'state_features_{v}.csv',index_col='id'))
        relation=state.join(pd.read_csv(rd/f'fresh_relation_{v}.csv',index_col='id'));assert relation.shape==(7372,402)
        pa=fit_arm(rd,'compact',v,compact,s);pb=fit_arm(rd,'state',v,state,s)
        alpha,w,key=policy(pa[0][tu],pa[1][tu],qy[tu])
        (beta,j16,p16,pr16),bchoices=choose_blend(*pa,*pb,alpha,w,qy,tu)
        pc=np.ones((len(sub),4,4))
        for a,b in itertools.combinations(range(4),2):
            ctx=fit&np.isin(y,[a,b]);pp,cc=fit_task(rd,f'relation_pair_{a}_{b}',v,relation,s,ctx,y[ctx],SEED+1100+10*a+b)
            assert list(cc)==[a,b];pc[:,a,b]=pp[:,0];pc[:,b,a]=1-pp[:,0]
        np.save(rd/f'relation_pair_{v}.npy',pc)
        (eta,j19,p19,pr19),echoices=choose_blend(j16,p16,j16,pc,alpha,w,qy,tu)
        root,cc=fit_task(rd,'hierarchy_root',v,relation,s,fit,(y[fit]!=0).astype(int),SEED+2410);assert list(cc)==[0,1]
        ctx=fit&(y!=0);branch,cc=fit_task(rd,'hierarchy_branch',v,relation,s,ctx,y[ctx],SEED+2411);assert list(cc)==[1,2,3]
        hp=np.column_stack([1-root[:,1],root[:,1,None]*branch]);assert np.allclose(hp.sum(1),1,atol=1e-5)
        np.save(rd/f'hierarchy_prob_{v}.npy',hp)
        best=None;choices=[]
        for gamma in [0.,.25,.5,.75,1.]:
            scores=hierarchy_scores(j19,p19,hp,alpha,w,gamma);pr=scores.argmax(1);m=metrics(qy[tu],pr[tu]);key=(int((pr[tu]==qy[tu]).sum()),m['macro_f1'],-gamma)
            choices.append({'gamma':gamma,'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']})
            if best is None or key>best[0]:best=(key,gamma,pr,scores)
        _,gamma,final[v],scores=best;prob[v]=j19;pairs[v]=p19;np.save(rd/f'final_scores_{v}.npy',scores)
        decisions[v]={'alpha':alpha,'weights':w.tolist(),'state_beta':beta,'state_candidates':bchoices,'relation_beta':eta,'relation_candidates':echoices,'hierarchy_gamma':gamma,'hierarchy_candidates':choices}
        controls[v]={'fresh_compact_prediction':apply_policy(*pa,alpha,w),'fresh_state_blend_prediction':pr16,'fresh_best_design_prediction':pr19,'hierarchy_only_prediction':hierarchy_scores(j19,p19,hp,alpha,w,1).argmax(1)}
        inputs[v]={'columns':relation.columns.tolist(),'shared_deterministic_sha':{str(p):sha(p) for p in [B/f'features_{v}.csv',B/f'layout_features_{v}.csv',B/f'state_features_{v}.csv']}}
        print('FRESH_HIERARCHY_SELECTION',v,json.dumps(decisions[v]),flush=True)
    dump(rd/'input_audit.json',inputs)
    complete(rd,s,base,prob,pairs,final,decisions,controls)


if __name__=='__main__':main()
