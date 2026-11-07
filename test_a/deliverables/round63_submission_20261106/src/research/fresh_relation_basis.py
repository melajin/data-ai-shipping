"""Refit every relation prototype from original raw-derived FIT observations.

Equivalent feature definition to the previous broad-region idea, no fitted
prototype or observation assignment is loaded from any older round.
"""
from pathlib import Path
import sys,json,gc,hashlib
B=Path(__file__).resolve().parent;sys.path.insert(0,str(B/'vendor'))
import numpy as np,pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import RobustScaler
from threadpoolctl import threadpool_limits
from build_inputs import NAMES
COLS=['length_km','extent_km','linearity','axis_strength','direction_strength','turn_abs','turn_reversal','zero_step_fraction','short_step_fraction']


def block(a,ids):
    z=a.loc[(a.shape_code>=0)&(a.region_code>=0)];pos=np.searchsorted(ids,z.id.to_numpy());n=len(ids)
    count=np.bincount(pos,minlength=n)
    hist=np.bincount(pos*48+z.shape_code.to_numpy()*8+z.region_code.to_numpy(),minlength=n*48).reshape(n,6,8)/np.maximum(count[:,None,None],1)
    sm=hist.sum(2);rm=hist.sum(1)
    total=a.groupby('id').size().reindex(ids).to_numpy();days=z.groupby('id').date.nunique().reindex(ids,fill_value=0).to_numpy()
    cols=[f'relation_shape_{i}' for i in range(6)]+[f'relation_region_{i}' for i in range(8)]+[f'relation_joint_{i}_{j}' for i in range(6) for j in range(8)]+['relation_valid_rows','relation_observed_days','relation_unassigned_fraction']
    out=pd.DataFrame(np.column_stack([sm,rm,hist.reshape(n,48),count,days,1-count/np.maximum(total,1)]),index=pd.Index(ids,name='id'),columns=cols)
    assert out.shape==(len(ids),65) and np.allclose(hist.sum((1,2))[count>0],1)
    return out


def build(rd,view_specs=None,retain_assignments=False):
    threadpool_limits(limits=2);s=pd.read_csv(B/'fixed_split.csv',index_col='id');ids=s.index.to_numpy();fitids=s.index[s.split=='FIT'].to_numpy();chunks=[];sources={}
    for p in sorted((B/'new_row_inputs').glob('chunk_*.npz')):
        sources[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
        with np.load(p) as z:
            x=z['x'].copy();x[~np.isfinite(x[:,12])]=np.nan;a=pd.DataFrame(x,columns=NAMES);a['id']=z['id'];a['date']=z['date'];a['hour']=z['hour'];chunks.append(a)
    d=pd.concat(chunks,ignore_index=True);del chunks;gc.collect();d['day_rank']=d.groupby('id').date.rank(method='dense').astype('int16');aud=[]
    for vi,(v,k) in enumerate(view_specs if view_specs is not None else [('full',10000),('d1',1),('d3',3),('d7',7)]):
        a=d.loc[d.day_rank<=k].copy();valid=np.isfinite(a[['center_lon','center_lat','length_km']]).all(axis=1);train=a.loc[valid&a.id.isin(fitids)]
        rng=np.random.default_rng(20263000+vi);ix=np.concatenate([rng.choice(ix,size=32,replace=len(ix)<32) for ix in train.groupby('id').indices.values()]);sample=train.iloc[ix]
        assert sample.id.nunique()==len(fitids) and sample.groupby('id').size().eq(32).all() and set(sample.id)<=set(fitids)
        def shape_input(df):
            z=df[COLS].to_numpy(dtype=np.float64);z[:,:2]=np.log1p(np.maximum(z[:,:2],0));return z
        def geo(df):return np.column_stack([df.center_lon.to_numpy()*111.32*np.cos(np.deg2rad(35)),df.center_lat.to_numpy()*110.574])
        sx=shape_input(sample);med=np.nanmedian(sx,axis=0);sx=np.where(np.isfinite(sx),sx,med);low,high=np.quantile(sx,[.005,.995],axis=0)
        scaler=RobustScaler(quantile_range=(10,90));sx=scaler.fit_transform(np.clip(sx,low,high))
        shape=MiniBatchKMeans(n_clusters=6,random_state=20263100+vi,batch_size=4096,n_init=3).fit(sx)
        region=MiniBatchKMeans(n_clusters=8,random_state=20263200+vi,batch_size=4096,n_init=3).fit(geo(sample))
        sc=np.full(len(a),-1,dtype=int);rc=sc.copy();positions=np.flatnonzero(valid.to_numpy())
        for i in range(0,len(positions),100000):
            pos=positions[i:i+100000];part=a.iloc[pos];x=shape_input(part);x=np.where(np.isfinite(x),x,med)
            sc[pos]=shape.predict(scaler.transform(np.clip(x,low,high)));rc[pos]=region.predict(geo(part))
        a['shape_code']=sc;a['region_code']=rc;f=block(a,ids);f.to_csv(rd/f'fresh_relation_{v}.csv',float_format='%.9g')
        if retain_assignments:
            np.savez(rd/f'fresh_row_assignments_{v}.npz',id=a.id.to_numpy(),date=a.date.to_numpy(),shape_code=sc.astype(np.int8),region_code=rc.astype(np.int8))
        np.savez(rd/f'fresh_basis_{v}.npz',FIT_ids=fitids,sample_ids=sample.id.to_numpy(),sample_dates=sample.date.to_numpy(),sample_hours=sample.hour.to_numpy(),shape_centers=shape.cluster_centers_,region_centers=region.cluster_centers_,median=med,clip_low=low,clip_high=high,scale_center=scaler.center_,scale_scale=scaler.scale_)
        aud.append({'view':v,'FIT_basis_boats':len(fitids),'sample_rows':len(sample),'features':65,'fresh_shape_fit':True,'fresh_region_fit':True,'fresh_scaler_fit':True,'labels_read_for_basis':False})
        print('FRESH_RELATION_BASIS',json.dumps(aud[-1]),flush=True)
    (rd/'fresh_basis_audit.json').write_text(json.dumps({'views':aud,'source_cache_hashes':sources,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2),encoding='utf-8')
