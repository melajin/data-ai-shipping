"""Pure per-target features: equal weight per observed date, no fitted basis."""
from pathlib import Path
import json,hashlib,gc
import numpy as np,pandas as pd
from build_inputs import NAMES
from build_state_inputs import state_codes
B=Path(__file__).resolve().parent


def equal_days(a,ids):
    z=a.loc[a.state>=0].copy()
    day=z.groupby(['id','date','state']).size().unstack(fill_value=0).reindex(columns=range(8),fill_value=0)
    mix=day.div(day.sum(axis=1),axis=0)
    f=mix.groupby(level='id').agg(['mean','median'])
    f.columns=[f'equalday_state_{i}_{stat}' for i,stat in f.columns]
    assert np.allclose(f[[f'equalday_state_{i}_mean' for i in range(8)]].sum(1),1)
    # Hour x state proportions normalized within each actually observed date.
    z['hs']=z.hour//4*8+z.state
    hs=z.groupby(['id','date','hs']).size().unstack(fill_value=0).reindex(columns=range(48),fill_value=0)
    hs=hs.div(hs.sum(axis=1),axis=0).groupby(level='id').mean();hs.columns=[f'equalday_hourstate_{i}' for i in range(48)]
    cols=['length_km','extent_km','linearity','axis_strength','direction_strength','turn_abs','turn_reversal','zero_step_fraction']
    daily=z.groupby(['id','date'])[cols].mean().groupby(level='id').agg(['mean','std'])
    daily.columns=[f'equalday_{c}_{stat}' for c,stat in daily.columns]
    counts=day.sum(1);support=counts.groupby(level='id').agg(['mean','std','min','max'])
    support.columns=[f'daily_observation_count_{c}' for c in support.columns]
    result=f.join(hs).join(daily).join(support).reindex(ids)
    assert result.shape==(len(ids),84) and not np.isinf(result.to_numpy()).any()
    return result


def build(rd):
    chunks=[];hashes={}
    for p in sorted((B/'new_row_inputs').glob('chunk_*.npz')):
        hashes[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
        with np.load(p) as a:
            x=pd.DataFrame(a['x'],columns=NAMES);x['id']=a['id'];x['date']=a['date'];x['hour']=a['hour'];chunks.append(x)
    a=pd.concat(chunks,ignore_index=True);del chunks;gc.collect()
    a['day_rank']=a.groupby('id').date.rank(method='dense').astype('int16')
    a['state']=state_codes(a.length_km.to_numpy(),a.linearity.to_numpy(),np.isfinite(a[['length_km','linearity','center_lon','center_lat']]).all(axis=1).to_numpy())
    ids=pd.read_csv(B/'fixed_split.csv').id.to_numpy();audit=[]
    for v,k in [('full',10000),('d1',1),('d3',3),('d7',7)]:
        z=a.loc[a.day_rank<=k];f=equal_days(z,ids);f.to_csv(rd/f'day_features_{v}.csv',float_format='%.9g')
        audit.append({'view':v,'n_rows':len(z),'n_vessels':len(f),'columns':len(f.columns),'fitted_transform':False})
        print('FRESH_DAY_INPUT',json.dumps(audit[-1]),flush=True)
    (rd/'day_input_audit.json').write_text(json.dumps({'views':audit,'raw_derived_cache_hashes':hashes,'basis':'Fixed physical thresholds, pure target-local aggregation; no prior fitted artifacts','code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2),encoding='utf-8')
