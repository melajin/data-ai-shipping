"""Round010 critical review: rebuild window metrics and cache control pools.

Reuses the Round009 reviewed source for pct_rank/ctrl_mask so the baseline
reproduction is byte-comparable with Round010's promoted cell.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import importlib.util, json, pickle
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent              # testB
R8 = BASE / 'round_008_linkage_audit_20261105'
R9 = BASE / 'round 9'
spec = importlib.util.spec_from_file_location('r009_readonly', R9 / 'verify_round9_review.py')
review = importlib.util.module_from_spec(spec); spec.loader.exec_module(review)
build_vessel, ctrl_mask, pct_rank = review.build_vessel, review.ctrl_mask, review.pct_rank

METRICS = ['lin_raw','straight_win','speed_mean','step_mean','bearing_consistency','turn_rate','still_frac']
COLS = ['rfid_id_int','ts','len_m','bbox_m','cen_lon','cen_lat','state','score']

def bearing(lat1,lon1,lat2,lon2):
    p1,p2=np.radians(lat1),np.radians(lat2); dl=np.radians(lon2-lon1)
    return np.arctan2(np.sin(dl)*np.cos(p2),np.cos(p1)*np.sin(p2)-np.sin(p1)*np.cos(p2)*np.cos(dl))

def make_windows(g,half,lo,hi):
    span=hi-lo+1
    g=g.copy(); g['s_gap']=np.nan
    original=build_vessel(g,span,lo) if half==3 else None
    centers=np.arange(half,span-half)
    W={'center':centers,'n_rows':np.zeros(len(centers),int)}
    for m in METRICS: W[m]=np.full(len(centers),np.nan)
    ts=g.ts.to_numpy(dtype=int)-lo; lm=g.len_m.to_numpy(float); bb=g.bbox_m.to_numpy(float)
    lat=g.cen_lat.to_numpy(float); lon=g.cen_lon.to_numpy(float)
    q10=float(np.nanquantile(lm,.1))
    steps=review.haversine_m(lat[:-1],lon[:-1],lat[1:],lon[1:])
    dt=np.diff(ts)
    bearings=bearing(lat[:-1],lon[:-1],lat[1:],lon[1:])
    bearings[(steps<=1e-9) | ~np.isfinite(steps)]=np.nan
    turns=np.abs(np.angle(np.exp(1j*np.diff(bearings))))
    left=np.searchsorted(ts,centers-half,'left'); right=np.searchsorted(ts,centers+half,'right')
    W['n_rows']=right-left
    for j,(a,b) in enumerate(zip(left,right)):
        if b<=a: continue
        lens=lm[a:b]; valid=np.isfinite(lens)
        if valid.any():
            W['speed_mean'][j]=float(np.mean(lens[valid]))
            W['still_frac'][j]=float(np.mean(lens[valid]<q10))
        v=(lens>=1)&np.isfinite(lens)&np.isfinite(bb[a:b])
        if v.any(): W['lin_raw'][j]=float(np.mean(bb[a:b][v]/lens[v]))
        den=np.sum(lens) if valid.all() else np.nan
        if b-a>=2:
            if den>0: W['straight_win'][j]=float(review.haversine_m(lat[a],lon[a],lat[b-1],lon[b-1])/den)
            ss=steps[a:b-1]/dt[a:b-1]
            if np.isfinite(ss).any(): W['step_mean'][j]=float(np.nanmean(ss))
            ang=bearings[a:b-1]; ang=ang[np.isfinite(ang)]
            if len(ang): W['bearing_consistency'][j]=float(abs(np.mean(np.exp(1j*ang))))
        if b-a>=3 and np.isfinite(turns[a:b-2]).any(): W['turn_rate'][j]=float(np.nanmean(turns[a:b-2]))
    if original is not None:
        assert np.array_equal(W['center'],original['center'])
        assert np.array_equal(W['n_rows'],original['n_rows'])
    return W

def load():
    pos=pd.read_csv(R8/'devset_positives.csv')
    audit=pd.read_csv(R9/'task1_linkage_audit_167.csv')
    linked=audit.set_index('acc_id').loc[pos.acc_id]
    assert np.array_equal(pos.rfid_id.to_numpy(),linked.rfid_id.to_numpy())
    assert np.array_equal(pos.tier.to_numpy(),linked.tier.to_numpy())
    ids=set(pos.rfid_id.astype(int))
    pf=pq.ParquetFile(R8/'dev_hourly_scores.parquet')
    frames=[]
    for batch in pf.iter_batches(batch_size=65536,columns=COLS,use_threads=False):
        df=batch.to_pandas(); sub=df.loc[df.rfid_id_int.isin(ids)]
        if len(sub): frames.append(sub.copy())
    sc=pd.concat(frames,ignore_index=True).sort_values(['rfid_id_int','ts'],kind='stable')
    assert not sc.duplicated(['rfid_id_int','ts']).any()
    assert pd.to_datetime(sc.ts,unit='h').dt.year.eq(2026).all()
    return pos,sc

def main():
    pos,sc=load()
    lo,hi=int(sc.ts.min()),int(sc.ts.max())
    out={}
    for half in (3,6,12):
        pools=[]
        for rid,g in sc.groupby('rfid_id_int',sort=True):
            W=make_windows(g,half,lo,hi)
            events=pos.loc[pos.rfid_id==int(rid)]
            all_acc=events.acc_ts.to_numpy(int)-lo
            for e in events.to_dict('records'):
                ai=int(e['acc_ts'])-lo
                found=np.flatnonzero(W['center']==ai)
                if not len(found):
                    continue
                ci=int(found[0])
                rec={'acc_id':int(e['acc_id']),'rfid_id':int(rid),'tier':int(e['tier']),
                     'cause':str(e['발생유형']),'acc_ts':int(e['acc_ts']),'half':half,
                     'n_acc_rows':int(W['n_rows'][ci])}
                for hod in (0,1,2,3,None):
                    for match in (True,False):
                        ok=ctrl_mask(W,hi-lo+1,all_acc,72,W['n_rows'][ci],exact=match)
                        if hod is not None:
                            dd=np.abs((W['center']+lo)%24-int(e['acc_ts'])%24)
                            ok &= np.minimum(dd,24-dd)<=hod
                        idx=np.flatnonzero(ok)
                        key=f'hod_{"none" if hod is None else hod}/nrows_{"matched" if match else "unmatched"}'
                        rec[key]={'idx':idx.astype(np.int32),
                                  'acc':np.array([W[m][ci] for m in METRICS],dtype=np.float64),
                                  'mat':np.column_stack([W[m][idx] for m in METRICS]).astype(np.float64)}
                # full-track rank for deployability (no guard, no match, no hod)
                rec['full_track']={'centers':W['center'].astype(np.int32),'acc_pos':ci,
                                   'mat':np.column_stack([W[m] for m in METRICS]).astype(np.float64),
                                   'n_rows':W['n_rows'].astype(np.int32)}
                pools.append(rec)
        out[half]=pools
        print('half',half,'events with complete window:',len(pools),flush=True)
    with open(HERE/'pools.pkl','wb') as f: pickle.dump({'lo':lo,'hi':hi,'pools':out},f,protocol=4)
    print('saved pools.pkl')

if __name__=='__main__':
    main()
