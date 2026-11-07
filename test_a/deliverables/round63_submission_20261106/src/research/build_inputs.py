from pathlib import Path
import sys,json,time,hashlib
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'vendor'))
import numpy as np
import pandas as pd
import shapely
from sklearn.model_selection import train_test_split,StratifiedKFold

CLASSES=['연안복합','자망','통발','채낚기연승낚시']
NAMES=['length_km','extent_km','linearity','n_points','n_parts','zero_step_fraction','axis_strength','direction_strength','turn_abs','turn_reversal','short_step_fraction','long_step_fraction','center_lon','center_lat','width_km','height_km']
def write_json(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def clean(df):
    ok=df.part_dt.str.fullmatch(r'2026\d{4}',na=False)&df.rfid_id.str.fullmatch(r'\d{8}',na=False)&df.rfid_time.str.fullmatch(r'\d{1,2}',na=False)&df.fishing_code.isin(CLASSES)
    h=pd.to_numeric(df.rfid_time,errors='coerce');ok &= h.between(0,23)
    return ok
def row_features(wkts):
    wkts=np.where(pd.isna(wkts),None,wkts)
    g=shapely.from_wkt(wkts,on_invalid='ignore');n=len(g)
    parts,gi=shapely.get_parts(g,return_index=True)
    xy,pi=shapely.get_coordinates(parts,return_index=True)
    out=np.zeros((n,len(NAMES)),dtype=np.float32)
    bounds=shapely.bounds(g)
    out[:,12:14]=np.column_stack(((bounds[:,0]+bounds[:,2])/2,(bounds[:,1]+bounds[:,3])/2))
    out[:,14]=(bounds[:,2]-bounds[:,0])*111.32*np.cos(np.deg2rad(out[:,13]))
    out[:,15]=(bounds[:,3]-bounds[:,1])*110.574
    out[:,1]=np.hypot(out[:,14],out[:,15])
    out[:,3]=shapely.get_num_coordinates(g);out[:,4]=shapely.get_num_geometries(g)
    if len(xy)<2:
        missing=~np.isfinite(out[:,12]);out[missing]=np.nan
        return out,int(np.sum(missing))
    valid=pi[:-1]==pi[1:];src=np.flatnonzero(valid);rr=gi[pi[src]]
    dx=(xy[src+1,0]-xy[src,0])*111.32*np.cos(np.deg2rad((xy[src+1,1]+xy[src,1])/2))
    dy=(xy[src+1,1]-xy[src,1])*110.574; dist=np.hypot(dx,dy)
    def bc(v): return np.bincount(rr,weights=v,minlength=n)
    cnt=np.bincount(rr,minlength=n);den=np.maximum(cnt,1)
    length=bc(dist);out[:,0]=length
    out[:,5]=bc(dist<.001)/den;out[:,10]=bc(dist<.01)/den;out[:,11]=bc(dist>1)/den
    theta=np.arctan2(dy,dx);moving=dist>.001
    out[:,6]=np.hypot(bc(np.cos(2*theta)*dist),bc(np.sin(2*theta)*dist))/np.maximum(length,1e-6)
    out[:,7]=np.hypot(bc(dx),bc(dy))/np.maximum(length,1e-6)
    # Net distance of each actual LineString; never bridge disconnected parts.
    cp=shapely.get_num_coordinates(parts);end=np.cumsum(cp)-1;start=np.r_[0,end[:-1]+1];nz=cp>0
    vx=(xy[end[nz],0]-xy[start[nz],0])*111.32*np.cos(np.deg2rad((xy[end[nz],1]+xy[start[nz],1])/2))
    vy=(xy[end[nz],1]-xy[start[nz],1])*110.574
    out[:,2]=np.bincount(gi[nz],weights=np.hypot(vx,vy),minlength=n)/np.maximum(length,1e-6)
    adj=(src[1:]==src[:-1]+1)&(rr[1:]==rr[:-1])&(pi[src[1:]]==pi[src[:-1]])&moving[:-1]&moving[1:]
    a=np.flatnonzero(adj);dt=np.abs(np.arctan2(np.sin(theta[a+1]-theta[a]),np.cos(theta[a+1]-theta[a])))
    tc=np.maximum(np.bincount(rr[a],minlength=n),1)
    out[:,8]=np.bincount(rr[a],weights=dt,minlength=n)/tc
    out[:,9]=np.bincount(rr[a],weights=dt>2.3,minlength=n)/tc
    missing=shapely.is_missing(g);out[missing]=np.nan
    return out,int(np.sum(missing))

def build():
    cache=BASE/'new_row_inputs';cache.mkdir(exist_ok=True)
    audit=[];k=0
    for p in sorted((BASE.parent/'공식데이터_최신버전'/'vpass_26년(1월_6월) 데이터').rglob('*.csv')):
        t=time.time();r=0
        for df in pd.read_csv(p,usecols=['part_dt','rfid_id','rfid_time','geom','fishing_code'],dtype=str,chunksize=20000,encoding='utf-8-sig'):
            ok=clean(df)
            if (~ok).any():
                audit.append({'file':str(p),'parsed_row_offset_0based':r,'rejected_count':int((~ok).sum()),'invalid_rows':df.loc[~ok,['part_dt','rfid_id','rfid_time','fishing_code']].to_dict('records')})
            r+=len(df);df=df.loc[ok]
            x,bad=row_features(df.geom.to_numpy());
            if bad: audit.append({'file':str(p),'parsed_row_offset_0based':r-len(df),'invalid_geometry_count':bad})
            np.savez(cache/f'chunk_{k:04d}.npz',x=x,id=df.rfid_id.astype(np.int64).to_numpy(),date=df.part_dt.astype(np.int32).to_numpy(),hour=df.rfid_time.astype(np.int8).to_numpy(),y=pd.Categorical(df.fishing_code,categories=CLASSES).codes.astype(np.int8))
            k+=1
            if k%10==0: print(f'GEOMETRY chunks={k} current_file_rows={r} elapsed_file={time.time()-t:.1f}',flush=True)
        print(f'FILE COMPLETE {p.name} rows={r} seconds={time.time()-t:.1f}',flush=True)
    write_json(BASE/'input_quality_audit.json',audit)
    aggregate()

def aggregate():
    chunks=list((BASE/'new_row_inputs').glob('chunk_*.npz'))
    xs=[];ids=[];dates=[];hours=[];ys=[]
    for p in chunks:
        with np.load(p) as z:
            xs.append(z['x']);ids.append(z['id']);dates.append(z['date']);hours.append(z['hour']);ys.append(z['y'])
    x=np.concatenate(xs);del xs
    # Missing/empty geometries have no measured shape, rather than a stationary path.
    x[~np.isfinite(x[:,12])]=np.nan
    df=pd.DataFrame(x,columns=NAMES);del x
    df['id']=np.concatenate(ids);df['date']=np.concatenate(dates);df['hour']=np.concatenate(hours);df['y']=np.concatenate(ys)
    del ids,dates,hours,ys
    labels=df.groupby('id').y.agg(['first','nunique']);assert (labels['nunique']==1).all(),labels[labels['nunique']!=1]
    labels['split']='';allids=labels.index.to_numpy();y=labels['first'].to_numpy()
    fi,rest=train_test_split(allids,test_size=.4,stratify=y,random_state=20261105)
    tu,re=train_test_split(rest,test_size=.5,stratify=labels.loc[rest,'first'],random_state=20261105)
    labels.loc[fi,'split']='FIT';labels.loc[tu,'split']='TUNE';labels.loc[re,'split']='REPORT'
    labels['fold']=-1
    for fold,(_,b) in enumerate(StratifiedKFold(2,shuffle=True,random_state=20261105).split(fi,labels.loc[fi,'first'])):labels.loc[fi[b],'fold']=fold
    labels.rename(columns={'first':'y'}).drop(columns='nunique').to_csv(BASE/'fixed_split.csv')
    df['day_rank']=df.groupby('id').date.rank(method='dense').astype('int16')
    feats=[]
    for view,days in [('d1',1),('d3',3),('d7',7),('full',10000)]:
        d=df.loc[df.day_rank<=days];g=d.groupby('id',sort=True)
        agg=g[NAMES].agg(['mean','std','median','max']);agg.columns=['%s__%s'%c for c in agg.columns]
        extra=g.agg(n_rows=('date','size'),n_days=('date','nunique'),length_sum_km=('length_km','sum'),lon_min=('center_lon','min'),lon_max=('center_lon','max'),lat_min=('center_lat','min'),lat_max=('center_lat','max'))
        d=d.assign(night=((d.hour<6)|(d.hour>=18)).astype(float),h_sin=np.sin(d.hour*2*np.pi/24),h_cos=np.cos(d.hour*2*np.pi/24))
        hs=d.groupby('id')[['night','h_sin','h_cos']].mean()
        active=d.loc[d.length_km>.05].groupby('id')[['length_km','extent_km','linearity','axis_strength','direction_strength','turn_abs','turn_reversal','short_step_fraction']].agg(['mean','std','median'])
        active.columns=['active_%s__%s'%c for c in active.columns]
        result=agg.join(extra).join(hs).join(active).reindex(allids)
        result.to_csv(BASE/f'features_{view}.csv',float_format='%.8g')
        feats.append({'view':view,'vessels':len(result),'features':len(result.columns),'n_rows_total':int(result.n_rows.sum()),'days_quantiles':result.n_days.quantile([0,.1,.5,.9,1]).to_dict()})
        print('AGGREGATED',view,len(result),len(result.columns),flush=True)
    write_json(BASE/'input_spec.json',{'classes':CLASSES,'row_features':NAMES,'feature_sets':feats,'split_counts':labels.groupby(['split','first']).size().to_dict() if False else labels.groupby(['split','first']).size().reset_index(name='n').to_dict('records'),'seed':20261105,'raw_sha_source':'source_manifest.json','created_input_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'geometric_units':'kilometers, local equirectangular approximation per edge, no synthetic timestamps or speed','heldout_use':'REPORT is repeated development evaluation, TUNE chooses thresholds only'})
if __name__=='__main__':
    if '--aggregate' in sys.argv:aggregate()
    else:build()
