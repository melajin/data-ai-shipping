"""A reference design is an algorithm, never an old prediction file."""
from fresh_hierarchy_round import *


def fit_reference(rd,s,base):
    build(rd)
    fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();y=s.y.to_numpy();qy=sub.y.to_numpy();result={}
    for v in VIEWS:
        compact=base[v].join(pd.read_csv(B/f'layout_features_{v}.csv',index_col='id')).reindex(s.index)
        state=compact.join(pd.read_csv(B/f'state_features_{v}.csv',index_col='id'))
        relation=state.join(pd.read_csv(rd/f'fresh_relation_{v}.csv',index_col='id'));assert relation.shape==(7372,402)
        pa=fit_arm(rd,'compact',v,compact,s);pb=fit_arm(rd,'state',v,state,s)
        alpha,w,key=policy(pa[0][tu],pa[1][tu],qy[tu])
        (beta,j16,p16,pr16),bc=choose_blend(*pa,*pb,alpha,w,qy,tu)
        pair=np.ones((len(sub),4,4))
        for a,b in itertools.combinations(range(4),2):
            ctx=fit&np.isin(y,[a,b]);pp,cc=fit_task(rd,f'relation_pair_{a}_{b}',v,relation,s,ctx,y[ctx],SEED+1100+10*a+b)
            assert list(cc)==[a,b];pair[:,a,b]=pp[:,0];pair[:,b,a]=1-pp[:,0]
        np.save(rd/f'relation_pair_{v}.npy',pair)
        (eta,j,p,pr),ec=choose_blend(j16,p16,j16,pair,alpha,w,qy,tu)
        cfg={'alpha':alpha,'weights':w.tolist(),'state_beta':beta,'state_candidates':bc,'relation_beta':eta,'relation_candidates':ec}
        dump(rd/f'fresh_reference_policy_{v}.json',cfg);np.save(rd/f'fresh_reference_joint_{v}.npy',j);np.save(rd/f'fresh_reference_pair_{v}.npy',p)
        result[v]={'state':state,'joint':j,'pair':p,'prediction':pr,'alpha':alpha,'weights':w,'policy':cfg}
        print('FRESH_REFERENCE_READY',v,json.dumps(cfg),flush=True)
    return result
