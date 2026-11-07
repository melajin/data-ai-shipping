"""Joint geometry/time distributions and transitions of truly adjacent observed hours.

States describe measured line length/linearity, never inferred fishing actions or speed.
"""
from pathlib import Path
import json,hashlib,time,gc
import numpy as np,pandas as pd
from build_inputs import NAMES
B=Path(__file__).resolve().parent


def state_codes(length,linearity,valid):
    out=np.searchsorted([.05,1.,5.],length,side='right')*2+(linearity>=.5).astype(int)
    return np.where(valid,out,-1)


def adjacent_pairs(ids,hours,states):
    return (ids[1:]==ids[:-1])&(hours[1:]-hours[:-1]==1)&(states[:-1]>=0)&(states[1:]>=0)


def extract(a,ids):
    a=a.sort_values(['id','ordinal_hour']).reset_index(drop=True);n=len(ids);pos=np.searchsorted(ids,a.id.to_numpy());st=a.state.to_numpy();valid=st>=0
    coverage=np.bincount(pos,minlength=n);count=np.bincount(pos[valid],minlength=n);den=np.maximum(count,1)
    def hist(codes,size,mask=valid,normalizer=den):
        values=np.bincount(pos[mask]*size+codes[mask],minlength=n*size).reshape(n,size)
        return values/np.maximum(normalizer[:,None],1)
    sf=hist(st,8);out={f'state_fraction_{i}':sf[:,i] for i in range(8)}
    hs=hist((a.hour.to_numpy()//4)*8+st,48)
    out.update({f'hour_state_{i}':hs[:,i] for i in range(48)})
    pairs=adjacent_pairs(a.id.to_numpy(),a.ordinal_hour.to_numpy(),st)
    pcount=np.bincount(pos[1:][pairs],minlength=n)
    tr=np.bincount(pos[1:][pairs]*64+st[:-1][pairs]*8+st[1:][pairs],minlength=n*64).reshape(n,64)/np.maximum(pcount[:,None],1)
    out.update({f'adjacent_hour_transition_{i}':tr[:,i] for i in range(64)})
    out['valid_geometry_fraction']=count/coverage;out['adjacent_pair_count']=pcount;out['adjacent_pair_fraction']=pcount/np.maximum(coverage-1,1)
    assert np.allclose(sf.sum(1)[count>0],1) and np.allclose(hs.sum(1)[count>0],1) and np.allclose(tr.sum(1)[pcount>0],1)
    # One run stops at every actual timestamp gap; it is not duration of a latent action.
    continue_run=np.r_[False,pairs&(st[1:]==st[:-1])]
    run_id=np.cumsum(~continue_run)
    runs=a.assign(run_id=run_id).loc[valid].groupby(['id','state','run_id']).size().rename('rows').reset_index()
    runq=runs.groupby(['id','state']).rows.quantile([.5,.9]).unstack(['state',-1]).reindex(index=ids,columns=pd.MultiIndex.from_product([range(8),[.5,.9]]))
    runq.columns=[f'state_{k}_observed_run_q{int(q*100)}' for k,q in runq.columns]
    # State-conditioned shape, and state location relative to this same target's mean center.
    validrows=a.loc[valid].copy();means=validrows.groupby('id')[['center_lon','center_lat']].mean()
    validrows['relative_east_km']=(validrows.center_lon.to_numpy()-means.loc[validrows.id,'center_lon'].to_numpy())*111.32*np.cos(np.deg2rad(means.loc[validrows.id,'center_lat'].to_numpy()))
    validrows['relative_north_km']=(validrows.center_lat.to_numpy()-means.loc[validrows.id,'center_lat'].to_numpy())*110.574
    cols=['turn_abs','axis_strength','relative_east_km','relative_north_km']
    shape=validrows.groupby(['id','state'])[cols].mean().unstack('state').reindex(index=ids,columns=pd.MultiIndex.from_product([cols,range(8)]))
    shape.columns=[f'state_{k}_{c}' for c,k in shape.columns]
    # Variation of state mixtures across the observed days, with absent states as real zeros.
    day=validrows.groupby(['id','date','state']).size().unstack(fill_value=0).reindex(columns=range(8),fill_value=0)
    day=day.div(day.sum(axis=1),axis=0)
    daily=day.groupby(level='id').agg(['std','max']).reindex(ids)
    daily.columns=[f'day_state_{k}_{stat}' for k,stat in daily.columns]
    result=pd.DataFrame(out,index=pd.Index(ids,name='id')).join(runq).join(shape).join(daily)
    assert result.shape==(n,187) and not np.isinf(result.to_numpy()).any()
    return result,{'rows':len(a),'valid_geometry_rows':int(count.sum()),'adjacent_hour_pairs':int(pcount.sum()),'max_ordinal_hour_gap_in_used_pairs':1,'histograms_normalized':True}


def main():
    t=time.time()
    assert adjacent_pairs(np.array([1,1,1,2,2]),np.array([10,11,13,14,15]),np.array([0,1,2,3,-1])).tolist()==[True,False,False,False]
    assert state_codes(np.array([0.,.1,2.,6.]),np.array([0.,.6,.2,.9]),np.ones(4,dtype=bool)).tolist()==[0,3,4,7]
    chunks=[]
    for p in sorted((B/'new_row_inputs').glob('chunk_*.npz')):
        with np.load(p) as z:
            d=pd.DataFrame(z['x'],columns=NAMES);d['id']=z['id'];d['date']=z['date'];d['hour']=z['hour'];chunks.append(d)
    d=pd.concat(chunks,ignore_index=True);del chunks;gc.collect()
    d['day_rank']=d.groupby('id').date.rank(method='dense').astype('int16')
    d['ordinal_hour']=pd.to_datetime(d.date.astype(str),format='%Y%m%d').to_numpy().astype('datetime64[h]').astype(np.int64)+d.hour.to_numpy()
    d['state']=state_codes(d.length_km.to_numpy(),d.linearity.to_numpy(),np.isfinite(d[['length_km','linearity','center_lon','center_lat']]).all(axis=1).to_numpy())
    assert not d.duplicated(['id','ordinal_hour']).any()
    ids=pd.read_csv(B/'fixed_split.csv').id.to_numpy();audit=[]
    for v,k in [('full',10000),('d1',1),('d3',3),('d7',7)]:
        f,info=extract(d.loc[d.day_rank<=k],ids);f.to_csv(B/f'state_features_{v}.csv',float_format='%.9g')
        audit.append({'view':v,'features':f.shape[1],**info});print('STATE_FEATURES',json.dumps(audit[-1]),flush=True)
    spec={'passed':True,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source':'Own official-raw-derived new_row_inputs; y array deliberately not read','label_free':True,'states':'4 measured-line-length bins at .05/1/5 km x linearity >=.5; missing geometry excluded','transitions':'Only identical vessel and consecutive actual ordinal hour; no invented paths, speeds, timestamp interpolation or fishing action labels','views':audit,'elapsed_seconds':time.time()-t}
    (B/'state_input_spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
