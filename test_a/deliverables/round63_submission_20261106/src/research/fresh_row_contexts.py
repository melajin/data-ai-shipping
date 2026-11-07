"""Actual hourly records as learning units, scored once per unseen vessel.

Only geometry from that exact record and its supplied hour are features.
No cross-row geometry or full-window summaries are mixed into a row version.
"""
from fresh_rounds import *
from build_inputs import NAMES


def pool_rows(prob,owner,n):
    count=np.bincount(owner,minlength=n);assert (count>0).all()
    result=np.zeros((n,4),dtype=float);np.add.at(result,owner,prob)
    result/=count[:,None];assert np.allclose(result.sum(1),1,atol=1e-5)
    return result


def build_inputs(rd,s):
    chunks=[];hashes={};fitids=s.index[s.split=='FIT'].to_numpy();qids=s.index[s.split!='FIT'].to_numpy()
    for p in sorted((B/'new_row_inputs').glob('chunk_*.npz')):
        hashes[p.name]=sha(p)
        with np.load(p) as z:
            a=pd.DataFrame(z['x'],columns=NAMES);a['id']=z['id'];a['date']=z['date'];a['hour']=z['hour'];chunks.append(a)
    d=pd.concat(chunks,ignore_index=True);del chunks;gc.collect();d['source_row']=np.arange(len(d))
    assert set(d.id)==set(s.index) and not d.duplicated(['id','date','hour']).any()
    d=d.sort_values(['id','date','hour']);d['day_rank']=d.groupby('id').date.rank(method='dense').astype('int16')
    d['hour_sin']=np.sin(d.hour*2*np.pi/24);d['hour_cos']=np.cos(d.hour*2*np.pi/24);cols=NAMES+['hour_sin','hour_cos'];aud=[]
    for vi,(v,k) in enumerate([('full',10000),('d1',1),('d3',3),('d7',7)]):
        a=d.loc[d.day_rank<=k].reset_index(drop=True);allgroups=a.groupby('id',sort=True).indices
        lengths=a.length_km.to_numpy();groups={};fallback=set()
        for boat,ix in allgroups.items():
            eligible=ix[np.isfinite(lengths[ix])&(lengths[ix]>.05)]
            groups[boat]=eligible if len(eligible) else ix
            if not len(eligible):fallback.add(boat)
        rng=np.random.default_rng(SEED+2600+vi);aa=[];bb=[]
        for boat in fitids:
            ix=groups[boat];j=int(rng.integers(len(ix)));h=int(rng.integers(len(ix)-1)) if len(ix)>1 else j
            if len(ix)>1:h+=int(h>=j)
            aa.append(ix[j]);bb.append(ix[h])
        aa=np.array(aa);bb=np.array(bb)
        assert np.array_equal(a.iloc[aa].id.to_numpy(),fitids) and np.array_equal(a.iloc[bb].id.to_numpy(),fitids)
        qq=[];owner=[]
        for j,boat in enumerate(qids):
            ix=groups[boat];sel=np.unique(np.rint(np.linspace(0,len(ix)-1,min(8,len(ix)))).astype(int))
            qq.extend(ix[sel]);owner.extend([j]*len(sel))
        qq=np.array(qq);owner=np.array(owner);assert not set(a.iloc[qq].id)&set(fitids)
        assert np.array_equal(a.iloc[qq].id.to_numpy(),qids[owner])
        x=a[cols].to_numpy(dtype=np.float32);x=np.where(np.isfinite(x),x,np.nan)
        np.savez(rd/f'row_inputs_{v}.npz',context_a=x[aa],context_b=x[bb],query=x[qq],owner=owner,fit_ids=fitids,query_ids=qids)
        for name,ix in [('context_a',aa),('context_b',bb),('query',qq)]:
            a.iloc[ix][['id','date','hour','source_row']].to_csv(rd/f'{name}_actual_rows_{v}.csv',index=False)
        changed=np.any(~np.isclose(x[aa],x[bb],equal_nan=True),axis=1)
        aud.append({'view':v,'features':18,'context_boats':len(fitids),'query_boats':len(qids),'actual_query_rows':len(qq),
            'different_context_records':int((aa!=bb).sum()),'different_context_features':int(changed.sum()),'max_query_rows_per_boat':int(np.bincount(owner).max()),'context_query_id_overlap':0,
            'FIT_fallback_to_all_records':len(set(fitids)&fallback),'query_fallback_to_all_records':len(set(qids)&fallback)})
        print('FRESH_ROW_INPUTS',json.dumps(aud[-1]),flush=True)
    dump(rd/'row_input_spec.json',{'views':aud,'columns':cols,'raw_derived_cache_hashes':hashes,'code_sha256':sha(Path(__file__)),
        'labels':'Official vessel gear labels, not a claim about action during each record',
        'context':'One actual record per FIT vessel in each context; alternative is a different actual record where available. Prefer measured length>0.05km, fallback to all records for boats with no such record. This is not a fishing-action label. Labels not used to select records.',
        'query':'Same measured-length eligibility/fallback rule; up to8 distinct actual records at evenly spaced chronological eligible-record positions; arithmetic probability mean per vessel; score each vessel once.',
        'coherence':'All18 features come from the selected original record only. No full-bundle statistics are inserted into a sampled record.'})


def row_arm(rd,s,v,arm):
    assert arm in ['diverse','repeat_control'];fit=s.split.eq('FIT').to_numpy();fy=s.y.to_numpy()[fit];sub=s.loc[~fit]
    with np.load(rd/f'row_inputs_{v}.npz') as z:
        ca=z['context_a'];cb=z['context_b'];query=z['query'];owner=z['owner'];assert np.array_equal(z['fit_ids'],s.index[fit]) and np.array_equal(z['query_ids'],sub.index)
    pieces=[]
    for k in range(2):
        context=cb if arm=='diverse' and k==1 else ca;seed=SEED+2610+k;begun=now();m=model(seed,4);m.fit(context,fy)
        assert list(m.classes_)==[0,1,2,3];pp=[]
        for i in range(0,len(query),1000):
            pp.append(m.predict_proba(query[i:i+1000]))
            if i%5000==0:print('ROW_QUERY_PROGRESS',v,arm,k,i,len(query),flush=True)
        p=np.concatenate(pp);del m;gc.collect();torch.cuda.empty_cache();np.save(rd/f'{arm}_{v}_rows_{k}.npy',p);pieces.append(p)
        call={'arm':arm,'view':v,'task':f'row_head_{k}','seed':seed,'started':begun,'finished':now(),'fresh_fit':True,'gradient_updates':False,
            'context_record':'B' if arm=='diverse' and k==1 else 'A','n_context':len(fy),'n_query_rows':len(query),'n_query_boats':len(sub),'n_features':18,
            'context_ids_sha256':hashlib.sha256(s.index[fit].to_numpy().tobytes()).hexdigest(),'query_boat_ids_sha256':hashlib.sha256(sub.index.to_numpy().tobytes()).hexdigest(),'original_checkpoint':str(CHECKPOINT)}
        with (rd/'fresh_fit_calls.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(call)+'\n')
    pooled=pool_rows((pieces[0]+pieces[1])/2,owner,len(sub));np.save(rd/f'{arm}_vessel_prob_{v}.npy',pooled)
    return pooled


if __name__=='__main__':
    p=np.array([[.8,.1,.05,.05],[.2,.4,.3,.1],[.1,.2,.3,.4]]);o=np.array([0,0,1]);z=pool_rows(p,o,2)
    assert np.allclose(z[0],(p[0]+p[1])/2) and np.allclose(z[1],p[2]);print('Passed one-score-per-vessel probability pooling')
