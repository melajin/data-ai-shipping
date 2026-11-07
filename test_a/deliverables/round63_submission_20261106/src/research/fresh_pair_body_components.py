"""Unmeasured components for supervised pair-task broad body adaptation."""
from fresh_rounds import *

def fit_asinh_transform(rd,train,crop,queries,fit_ids,columns):
    finite=np.where(np.isfinite(train),train,np.nan)
    median=np.nan_to_num(np.nanmedian(finite,axis=0));q1,q3=np.nanquantile(finite,[.25,.75],axis=0)
    scale=np.where(np.isfinite(q3-q1)&(q3-q1>1e-6),q3-q1,1.)
    np.savez(rd/'pair_body_numeric_transform.npz',median=median,scale=scale,FIT_ids=fit_ids,columns=np.asarray(columns,dtype=str))
    def transform(x):
        out=np.arcsinh((x.astype(np.float64)-median)/scale)
        out=np.where(np.isfinite(x),out,np.nan).astype(np.float32)
        assert np.isfinite(out[np.isfinite(x)]).all();return out
    np.savez(rd/'pair_body_raw_inputs.npz',raw_train=train,raw_crop=crop,FIT_ids=fit_ids,
        **{f'raw_query_{v}':x for v,x in queries.items()})
    return transform(train),transform(crop),{v:transform(x) for v,x in queries.items()}

def infer_body_pairs(owner,encoded_train,y,encoded_queries,out_dir,prefix):
    pair=np.ones((len(encoded_queries),4,4));call=[]
    for a,b in itertools.combinations(range(4),2):
        ctx=np.isin(y,[a,b]);inner=owner._build_inner_estimator(owner.model_,4,torch.device('cuda'))
        inner.fit(encoded_train[ctx],y[ctx]);assert list(inner.classes_)==[a,b]
        p=np.concatenate([inner.predict_proba(encoded_queries[j:j+1000]) for j in range(0,len(encoded_queries),1000)])
        pair[:,a,b]=p[:,0];pair[:,b,a]=p[:,1]
        np.save(out_dir/f'{prefix}_pair_{a}_{b}.npy',p)
        call.append({'a':a,'b':b,'context_ids':owner.fit_ids[ctx].tolist(),'n_query':len(encoded_queries),'checkpoint_weights_same_for_all_six':True})
        del inner;gc.collect();torch.cuda.empty_cache()
    np.save(out_dir/f'{prefix}_pairs.npy',pair);dump(out_dir/f'{prefix}_pair_contexts.json',call)
    return pair

def choose_positive_pairs(reference,newpairs,y,tu):
    choices=[];out={}
    for gamma in [0.,.25,.5,.75,1.]:
        pair=(1-gamma)*reference['pair']+gamma*newpairs
        scores=(1-reference['alpha'])*np.log(np.clip(reference['joint'],1e-6,1))+reference['alpha']*np.log(np.clip(pair,1e-6,1)).sum(2)/3+np.log(reference['weights'])
        pred=scores.argmax(1);m=metrics(y[tu],pred[tu])
        choices.append({'gamma':gamma,'TUNE_correct':int((pred[tu]==y[tu]).sum()),'TUNE_micro':m['micro_f1'],'TUNE_macro':m['macro_f1']});out[gamma]=(pred,scores,pair)
    best=max(choices[1:],key=lambda z:(z['TUNE_correct'],z['TUNE_macro'],-z['gamma']))
    assert reference['alpha']>0
    return best,out[best['gamma']],choices,choices[0]['TUNE_correct']>best['TUNE_correct']
