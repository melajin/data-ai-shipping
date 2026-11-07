"""Fourteen fresh compact/record-latent tasks,omitting the state-only arm by design."""
from fresh_primary_reference import *


def load_record_latents(rd,s):
    with np.load(rd/'record_latents.npz') as z:
        assert np.array_equal(z['ids'],s.index)
        return pd.DataFrame(z['full'],index=s.index,columns=z['columns'])


def fit_record_reference(rd,s,base):
    build(rd,view_specs=[('full',10000)],retain_assignments=True)
    fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();qy=sub.y.to_numpy();y=s.y.to_numpy()
    compact=base['full'].join(pd.read_csv(B/'layout_features_full.csv',index_col='id')).reindex(s.index)
    state=compact.join(pd.read_csv(B/'state_features_full.csv',index_col='id'))
    relation=state.join(pd.read_csv(rd/'fresh_relation_full.csv',index_col='id')).join(load_record_latents(rd,s));assert relation.shape==(7372,434)
    pa=fit_arm(rd,'compact','full',compact,s);alpha,w,_=policy(pa[0][tu],pa[1][tu],qy[tu]);pair=np.ones((len(sub),4,4))
    record_head,cc=fit_task(rd,'relation_head','full',relation,s,fit,y[fit],SEED+910);assert list(cc)==[0,1,2,3]
    for a,b in itertools.combinations(range(4),2):
        ctx=fit&np.isin(y,[a,b]);pp,cc=fit_task(rd,f'relation_pair_{a}_{b}','full',relation,s,ctx,y[ctx],SEED+1100+10*a+b)
        assert list(cc)==[a,b];pair[:,a,b]=pp[:,0];pair[:,b,a]=1-pp[:,0]
    np.save(rd/'relation_pair_full.npy',pair);(eta,j,p,pr),ec=choose_blend(*pa,record_head,pair,alpha,w,qy,tu)
    cfg={'alpha':alpha,'weights':w.tolist(),'state_beta':0.,'state_candidates':[],'state_arm_omitted_by_predeclared_design':True,'relation_beta':eta,'relation_candidates':ec,
         'reference_tasks':14,'record_head_in_primary':True,'primary_features':{'compact':150,'relation':434},'fresh_supervised_record_latents_sha256':sha(rd/'record_latents.npz')}
    dump(rd/'fresh_reference_policy_full.json',cfg);np.save(rd/'fresh_reference_joint_full.npy',j);np.save(rd/'fresh_reference_pair_full.npy',p)
    return {'state':state,'joint':j,'pair':p,'prediction':pr,'alpha':alpha,'weights':w,'policy':cfg}


def rebuild_record_reference(rd,s):
    sub=s.loc[s.split!='FIT'];tu=sub.split.eq('TUNE').to_numpy();qy=sub.y.to_numpy();j=np.load(rd/'compact_full_head.npy');p=np.ones((len(sub),4,4));r=np.ones_like(p)
    for a,b in itertools.combinations(range(4),2):
        q=np.load(rd/f'compact_full_pair_{a}_{b}.npy');p[:,a,b]=q[:,0];p[:,b,a]=1-q[:,0]
        q=np.load(rd/f'relation_pair_{a}_{b}_full.npy');r[:,a,b]=q[:,0];r[:,b,a]=1-q[:,0]
    head=np.load(rd/'relation_head_full.npy');alpha,w,_=policy(j[tu],p[tu],qy[tu]);(eta,j,p,pr),ec=choose_blend(j,p,head,r,alpha,w,qy,tu);cfg=json.loads((rd/'fresh_reference_policy_full.json').read_text(encoding='utf-8'))
    assert cfg['state_arm_omitted_by_predeclared_design'] and cfg['reference_tasks']==14 and cfg['record_head_in_primary'] and cfg['state_beta']==0 and cfg['state_candidates']==[]
    assert alpha==cfg['alpha'] and np.array_equal(w,cfg['weights']) and eta==cfg['relation_beta'] and ec==cfg['relation_candidates']
    assert np.array_equal(j,np.load(rd/'fresh_reference_joint_full.npy')) and np.array_equal(p,np.load(rd/'fresh_reference_pair_full.npy'))
    return {'joint':j,'pair':p,'alpha':alpha,'weights':w,'prediction':pr,'policy':cfg}
