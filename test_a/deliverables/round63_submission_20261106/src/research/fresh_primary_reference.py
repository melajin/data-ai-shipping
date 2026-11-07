"""Twenty fresh fits reproduce only the primary full-view reference algorithm.

Reduced scopes use separately declared matched original-body controls. No old
prediction,learned basis or preprocessing is read. Default historical80-fit code
is unchanged;this path is for future rounds under the time-saving request.
"""
from fresh_best_reference import *

def fit_primary_reference(rd,s,base,retain_assignments=False,extra_state_features=None):
    build(rd,view_specs=[('full',10000)],retain_assignments=retain_assignments)
    fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();qy=sub.y.to_numpy();y=s.y.to_numpy();v='full'
    compact=base[v].join(pd.read_csv(B/f'layout_features_{v}.csv',index_col='id')).reindex(s.index)
    state=compact.join(pd.read_csv(B/f'state_features_{v}.csv',index_col='id'))
    if extra_state_features is not None:
        from fresh_day_deployment_inputs import load_reference_day_extension
        stored=load_reference_day_extension(rd,s.index)
        assert extra_state_features.index.equals(s.index) and extra_state_features.shape==(7372,20)
        assert np.array_equal(stored.to_numpy(),extra_state_features.to_numpy(),equal_nan=True) and stored.columns.equals(extra_state_features.columns)
        state=state.join(extra_state_features)
    relation=state.join(pd.read_csv(rd/'fresh_relation_full.csv',index_col='id'))
    pa=fit_arm(rd,'compact',v,compact,s);pb=fit_arm(rd,'state',v,state,s)
    alpha,w,_=policy(pa[0][tu],pa[1][tu],qy[tu]);(beta,j16,p16,_),bc=choose_blend(*pa,*pb,alpha,w,qy,tu)
    pair=np.ones((len(sub),4,4))
    for a,b in itertools.combinations(range(4),2):
        ctx=fit&np.isin(y,[a,b]);pp,cc=fit_task(rd,f'relation_pair_{a}_{b}',v,relation,s,ctx,y[ctx],SEED+1100+10*a+b)
        assert list(cc)==[a,b];pair[:,a,b]=pp[:,0];pair[:,b,a]=1-pp[:,0]
    np.save(rd/'relation_pair_full.npy',pair)
    (eta,j,p,pr),ec=choose_blend(j16,p16,j16,pair,alpha,w,qy,tu)
    cfg={'alpha':alpha,'weights':w.tolist(),'state_beta':beta,'state_candidates':bc,'relation_beta':eta,'relation_candidates':ec}
    if extra_state_features is not None:cfg.update(pure_day_extension_sha256=sha(rd/'reference_pure_day_extension.npz'),primary_features={'compact':150,'state':357,'relation':422})
    dump(rd/'fresh_reference_policy_full.json',cfg);np.save(rd/'fresh_reference_joint_full.npy',j);np.save(rd/'fresh_reference_pair_full.npy',p)
    print('FRESH_PRIMARY_REFERENCE_READY',json.dumps(cfg),flush=True)
    return {'state':state,'joint':j,'pair':p,'prediction':pr,'alpha':alpha,'weights':w,'policy':cfg}

def short_original_reference(rd,v,original,y,tu,persist=True):
    # TUNE class weights only,without reference pair-training for short views.
    pair=np.ones((len(y),4,4));best=None;choices=[]
    for g,t,d in itertools.product([.8,1.,1.2,1.4],[1.,1.5,2.,2.5],[.8,1.,1.2]):
        w=np.array([1.,g,t,d]);pr=(np.log(np.clip(original,1e-6,1))+np.log(w)).argmax(1)
        m=metrics(y[tu],pr[tu]);key=(int((pr[tu]==y[tu]).sum()),m['macro_f1'],-float(abs(np.log(w)).sum()))
        choices.append({'weights':w.tolist(),'TUNE_correct':key[0],'TUNE_macro':key[1]})
        if best is None or key>best[0]:best=(key,w,pr)
    _,w,pr=best;cfg={'alpha':0.,'weights':w.tolist(),'short_control':'Full FIT context,own short-view query;matched original body. Not the former observation-matched80-fit reference.','candidates':choices}
    if persist:dump(rd/f'short_reference_policy_{v}.json',cfg)
    return {'joint':original,'pair':pair,'alpha':0.,'weights':w,'prediction':pr,'policy':cfg}
