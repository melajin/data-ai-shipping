"""Apply one selected body to the identical20-task reference algorithm and fixed policy."""
from fresh_rounds import *
from experiment import model as make_public_estimator
from fresh_architecture_adapter import weight_digest

def prepare_deployment(rd):
    s,base=load();fit=s.split.eq('FIT').to_numpy();sub=s.loc[~fit]
    compact=base['full'].join(pd.read_csv(B/'layout_features_full.csv',index_col='id')).reindex(s.index)
    state=compact.join(pd.read_csv(B/'state_features_full.csv',index_col='id'))
    if (rd/'reference_pure_day_extension.npz').exists():
        from fresh_day_deployment_inputs import load_reference_day_extension
        state=state.join(load_reference_day_extension(rd,s.index))
    relation=state.join(pd.read_csv(rd/'fresh_relation_full.csv',index_col='id'))
    record_mode=(rd/'record_latents.npz').exists()
    if record_mode:
        from fresh_record_reference import load_record_latents
        assert not (rd/'reference_pure_day_extension.npz').exists()
        relation=relation.join(load_record_latents(rd,s))
    frames={'compact':compact,'state':state,'relation':relation};specs=[]
    calls=[json.loads(x) for x in (rd/'fresh_fit_calls.jsonl').read_text(encoding='utf-8').splitlines()]
    saved_policy=json.loads((rd/'fresh_reference_policy_full.json').read_text(encoding='utf-8'));assert len(calls)==saved_policy.get('reference_tasks',20)
    if record_mode:assert len(calls)==14
    for c in calls:
        arm=c['arm'];task=c['task'];ctx=fit.copy();frame=frames[arm if arm in frames else 'relation']
        if 'pair_' in task:ctx &= s.y.isin([int(task[-3]),int(task[-1])]).to_numpy()
        assert frame.shape[1]==c['n_features'] and hashlib.sha256(s.index[ctx].to_numpy().tobytes()).hexdigest()==c['context_ids_sha256']
        x=frame.loc[ctx].to_numpy(dtype=np.float32);q=frame.loc[sub.index].to_numpy(dtype=np.float32)
        specs.append({'arm':arm,'task':task,'seed':c['seed'],'X':np.where(np.isfinite(x),x,np.nan),'y':s.loc[ctx,'y'].to_numpy(),'query':np.where(np.isfinite(q),q,np.nan),
            'context_ids_sha256':c['context_ids_sha256'],'query_ids_sha256':c['query_ids_sha256'],'name':arm+'_'+task if arm in ['compact','state'] else task})
    return specs

def infer_one(owner,spec):
    inner=make_public_estimator(spec['seed'],4);inner.model_=owner.model_;inner.model_config_=owner.model_config_;inner.model_path_=owner.model_path_;inner._load_model=lambda:None
    inner.fit(spec['X'],spec['y']);p=np.concatenate([inner.predict_proba(spec['query'][j:j+1000]) for j in range(0,len(spec['query']),1000)])
    classes=inner.classes_.tolist();del inner;gc.collect();torch.cuda.empty_cache();return p,classes

def aggregate_deployed(outputs,policy):
    pairs={arm:np.ones((len(outputs['compact_head']),4,4)) for arm in (['compact','state','relation'] if 'state_head' in outputs else ['compact','relation'])}
    for arm in pairs:
        for a,b in itertools.combinations(range(4),2):
            key=f'{arm}_pair_{a}_{b}' if arm!='relation' else f'relation_pair_{a}_{b}';p=outputs[key]
            pairs[arm][:,a,b]=p[:,0];pairs[arm][:,b,a]=1-p[:,0]
    beta=policy['state_beta'];eta=policy['relation_beta']
    if 'state_head' in outputs:joint=(1-beta)*outputs['compact_head']+beta*outputs['state_head'];p=(1-beta)*pairs['compact']+beta*pairs['state']
    else:assert beta==0.;joint=outputs['compact_head'];p=pairs['compact']
    p=(1-eta)*p+eta*pairs['relation']
    if 'relation_head' in outputs:return (1-eta)*joint+eta*outputs['relation_head'],p
    return (1-eta)*joint+eta*joint,p

def infer_deployed(owner,rd,out_dir):
    out_dir.mkdir(exist_ok=True);specs=prepare_deployment(rd);outputs={};records=[];digest=weight_digest(owner.model_.state_dict())
    for i,spec in enumerate(specs):
        p,classes=infer_one(owner,spec);outputs[spec['name']]=p;np.save(out_dir/(spec['name']+'.npy'),p)
        records.append({k:spec[k] for k in ['arm','task','name','seed','context_ids_sha256','query_ids_sha256']})
        records[-1].update(classes=classes,n_context=len(spec['y']),n_query=len(p),features=spec['X'].shape[1],body_weights_sha256=digest,actual_current_body_context_and_preprocessor_fit=True)
        print('DEPLOYED_BODY_TASK',out_dir.name,i+1,'/'+str(len(specs)),spec['name'],flush=True)
    assert weight_digest(owner.model_.state_dict())==digest
    policy=json.loads((rd/'fresh_reference_policy_full.json').read_text(encoding='utf-8'));joint,pair=aggregate_deployed(outputs,policy)
    np.save(out_dir/'joint.npy',joint);np.save(out_dir/'pair.npy',pair);dump(out_dir/'actual_deployed_fit_calls.json',records);return joint,pair

def choose_deployed(reference,joint,pair,y,tu):
    choices=[];outputs={}
    for g in [0.,.25,.5,.75,1.]:
        j=(1-g)*reference['joint']+g*joint;p=(1-g)*reference['pair']+g*pair
        score=(1-reference['alpha'])*np.log(np.clip(j,1e-6,1))+reference['alpha']*np.log(np.clip(p,1e-6,1)).sum(2)/3+np.log(reference['weights'])
        pred=score.argmax(1);m=metrics(y[tu],pred[tu]);choices.append({'gamma':g,'TUNE_correct':int((pred[tu]==y[tu]).sum()),'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']});outputs[g]=(pred,score,j,p)
    best=max(choices[1:],key=lambda a:(a['TUNE_correct'],a['TUNE_macro'],-a['gamma']))
    return best,outputs[best['gamma']],choices,choices[0]['TUNE_correct']>best['TUNE_correct']
