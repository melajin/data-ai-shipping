"""Pure daily geometry cache and coherent20day-balanced NN input features."""
from fresh_rounds import *
from build_inputs import NAMES
from build_state_inputs import state_codes

COLS=['length_km','extent_km','linearity','axis_strength','direction_strength','turn_abs','turn_reversal','zero_step_fraction']

def pure_daily_geometry():
    cache=B/'pure_daily_geometry_cache';cache.mkdir(exist_ok=True);mp=cache/'metadata.json';data_path=cache/'daily_data.npz'
    paths=sorted((B/'new_row_inputs').glob('chunk_*.npz'));hashes={p.name:sha(p) for p in paths}
    if mp.exists() and data_path.exists():
        meta=json.loads(mp.read_text(encoding='utf-8'))
        if meta['raw_derived_cache_hashes']==hashes and meta['state_code_sha256']==sha(B/'build_state_inputs.py') and meta['columns']==COLS:
            assert meta['pure_data_only'] and meta['no_labels_fitted_transforms_prototypes_or_predictions'] and meta['data_sha256']==sha(data_path)
            with np.load(data_path) as z:return {k:z[k] for k in z.files},meta
    parts=[]
    for p in paths:
        with np.load(p) as z:
            x=z['x'];a=pd.DataFrame(x,columns=NAMES)
            valid=state_codes(a.length_km.to_numpy(),a.linearity.to_numpy(),np.isfinite(a[['length_km','linearity','center_lon','center_lat']]).all(axis=1).to_numpy())>=0
            f=a[COLS].copy();f.loc[~valid,COLS]=np.nan;f['id']=z['id'];f['date']=z['date'];f['valid']=valid.astype(np.int16);parts.append(f)
    rows=pd.concat(parts,ignore_index=True);del parts;gc.collect();g=rows.groupby(['id','date'],sort=True);means=g[COLS].mean();valid=g.valid.sum();actual=g.size()
    data={'id':means.index.get_level_values('id').to_numpy(),'date':means.index.get_level_values('date').to_numpy(),
        'values':means.to_numpy(dtype=np.float32),'valid_rows':valid.to_numpy(dtype=np.int32),'actual_rows':actual.to_numpy(dtype=np.int32),'columns':np.asarray(COLS,dtype=str)}
    assert (data['actual_rows']>0).all() and (data['valid_rows']<=data['actual_rows']).all() and int(actual.sum())==len(rows)
    np.savez(data_path,**data)
    meta={'pure_data_only':True,'no_labels_fitted_transforms_prototypes_or_predictions':True,'columns':COLS,'actual_source_rows':len(rows),'all_actual_dates_retained_including_invalid_only_dates':True,
        'raw_derived_cache_hashes':hashes,'state_code_sha256':sha(B/'build_state_inputs.py'),'data_sha256':sha(data_path)}
    dump(mp,meta);print('PURE_DAILY_GEOMETRY_CACHE_READY',json.dumps({'actual_rows':len(rows),'actual_dates':len(means),'model_fits':0}),flush=True)
    return data,meta

def aggregate_days(frame,ids):
    valid=frame.loc[frame.valid_rows>0]
    f=valid.groupby('id')[COLS].agg(['mean','std']);f.columns=[f'daygeom_valid_equal_{c}_{stat}' for c,stat in f.columns]
    support=valid.groupby('id').valid_rows.agg(['mean','std','min','max']);support.columns=[f'daygeom_valid_record_count_{x}' for x in support.columns]
    out=f.join(support).reindex(ids);assert out.shape==(len(ids),20) and not np.isinf(out.to_numpy()).any();return out

def extend_input_encoder_features(rd,s,data402,persist=True):
    data,meta=pure_daily_geometry();a=pd.DataFrame(data['values'],columns=COLS);a['id']=data['id'];a['date']=data['date'];a['valid_rows']=data['valid_rows'];a['actual_rows']=data['actual_rows']
    a['day_rank']=a.groupby('id').date.rank(method='dense').astype(np.int16);fit=s.split.eq('FIT').to_numpy();ids=s.index.to_numpy();sub=s.index[~fit];out=dict(data402);audit={}
    row_column=list(data402['columns']).index('n_rows');day_column=list(data402['columns']).index('n_days');new_columns=None
    for v,k in [('full',10000),('d1',1),('d3',3),('d7',7)]:
        selected=a.loc[a.day_rank<=k];extra=aggregate_days(selected,ids);new_columns=extra.columns.to_numpy(dtype=str)
        q=extra.loc[sub].to_numpy(dtype=np.float32);out[f'raw_query_{v}']=np.column_stack([data402[f'raw_query_{v}'],q])
        assert np.array_equal(selected.groupby('id').actual_rows.sum().reindex(sub),data402[f'raw_query_{v}'][:,row_column])
        assert np.array_equal(selected.groupby('id').date.nunique().reindex(sub),data402[f'raw_query_{v}'][:,day_column])
        if v=='full':out['raw_train']=np.column_stack([data402['raw_train'],extra.loc[s.index[fit]].to_numpy(dtype=np.float32)])
        audit[v]={'query_boats':len(sub),'actual_selected_dates':int(selected.id.isin(sub).sum()),'uses_only_own_selected_dates':True}
    dates=pd.read_csv(rd/'crop_actual_dates.csv');selected=a.loc[pd.MultiIndex.from_frame(a[['id','date']]).isin(pd.MultiIndex.from_frame(dates[['id','date']]))]
    extra=aggregate_days(selected,s.index[fit]);out['raw_crop']=np.column_stack([data402['raw_crop'],extra.to_numpy(dtype=np.float32)])
    assert np.array_equal(selected.groupby('id').actual_rows.sum().reindex(s.index[fit]),data402['raw_crop'][:,row_column])
    assert np.array_equal(selected.groupby('id').date.nunique().reindex(s.index[fit]),data402['raw_crop'][:,day_column])
    out['columns']=np.r_[data402['columns'],new_columns]
    assert len(out['columns'])==422 and out['raw_train'].shape==(4423,422) and out['raw_crop'].shape==(4423,422)
    if persist:
        np.savez(rd/'input_encoder_raw_inputs.npz',**out)
        dump(rd/'input_encoder_input_audit.json',{'features':422,'base_summary_and_current_FIT_relation_features':402,'pure_equal_observed_day_geometry_and_support_features':20,
            'all_features_same_actual_selected_observations':True,'all_boats_and_classes_retained':True,'invalid_only_actual_dates_retained_for_scope_ranking':True,
            'geometry_aggregation':'Mean of valid actual records within each selected observed date,then equal date mean/std. Support describes valid provided records,not fishing-action ground truth.',
            'pure_daily_cache_metadata':meta,'view_scope':audit,'current_basis_sha256':sha(rd/'fresh_basis_full.npz'),'actual_crop_dates_sha256':sha(rd/'crop_actual_dates.csv')})
        print('INPUT_ENCODER_COHERENT422_READY',json.dumps({'features':422,'FIT_boats':4423,'query_boats':2949}),flush=True)
    return out
