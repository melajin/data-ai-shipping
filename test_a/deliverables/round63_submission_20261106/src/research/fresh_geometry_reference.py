"""Thirteen geometry-only reference fits:compact150 joint/pairs,relation402 pairs."""
from fresh_primary_reference import *


def geometry_frames(rd,s,base):
    compact=base['full'].join(pd.read_csv(B/'layout_features_full.csv',index_col='id')).reindex(s.index)
    state=compact.join(pd.read_csv(B/'state_features_full.csv',index_col='id'))
    return compact,state.join(pd.read_csv(rd/'fresh_relation_full.csv',index_col='id'))


def fit_geometry_reference(rd,s,base):
    build(rd,view_specs=[('full',10000)],retain_assignments=True);compact,relation=geometry_frames(rd,s,base)
    fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit];tu=sub.split.eq('TUNE').to_numpy();y=s.y.to_numpy();qy=sub.y.to_numpy()
    pa=fit_arm(rd,'compact','full',compact,s);alpha,w,_=policy(pa[0][tu],pa[1][tu],qy[tu]);pair=np.ones((len(sub),4,4))
    for a,b in itertools.combinations(range(4),2):
        ctx=fit&np.isin(y,[a,b]);pp,cc=fit_task(rd,f'relation_pair_{a}_{b}','full',relation,s,ctx,y[ctx],SEED+1100+10*a+b);assert list(cc)==[a,b];pair[:,a,b]=pp[:,0];pair[:,b,a]=1-pp[:,0]
    np.save(rd/'relation_pair_full.npy',pair);(eta,j,p,pr),ec=choose_blend(*pa,pa[0],pair,alpha,w,qy,tu)
    cfg={'alpha':alpha,'weights':w.tolist(),'state_beta':0.,'state_candidates':[],'state_arm_omitted_by_predeclared_design':True,'reference_tasks':13,'relation_beta':eta,'relation_candidates':ec,'primary_features':{'compact':150,'relation':402}}
    dump(rd/'fresh_reference_policy_full.json',cfg);np.save(rd/'fresh_reference_joint_full.npy',j);np.save(rd/'fresh_reference_pair_full.npy',p)
    return {'joint':j,'pair':p,'prediction':pr,'alpha':alpha,'weights':w,'policy':cfg}


def read_components(folder,tune_mask=None):
    j=np.load(folder/'compact_head.npy');pairs={}
    for arm in ['compact','relation']:
        p=np.ones((len(j),4,4))
        for a,b in itertools.combinations(range(4),2):
            pp=np.load(folder/f'{arm}_pair_{a}_{b}.npy');p[:,a,b]=pp[:,0];p[:,b,a]=1-pp[:,0]
        pairs[arm]=p
    return j,pairs['compact'],pairs['relation']
