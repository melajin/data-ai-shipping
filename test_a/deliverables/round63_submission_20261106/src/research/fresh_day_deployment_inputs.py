"""Expose pure equal-observed-day features to primary inference, not only training."""
from fresh_day_geometry_inputs import pure_daily_geometry,aggregate_days,COLS
from fresh_rounds import *


def reference_day_extension(rd,s,base,persist=True):
    data,meta=pure_daily_geometry()
    frame=pd.DataFrame(data['values'],columns=COLS)
    for key in ['id','date','valid_rows','actual_rows']:frame[key]=data[key]
    extra=aggregate_days(frame,s.index).astype(np.float32)
    state=base['full'].join(pd.read_csv(B/'layout_features_full.csv',index_col='id')).join(pd.read_csv(B/'state_features_full.csv',index_col='id')).reindex(s.index)
    assert state.shape==(7372,337) and extra.shape==(7372,20)
    assert np.array_equal(frame.groupby('id').actual_rows.sum().reindex(s.index),state.n_rows)
    assert np.array_equal(frame.groupby('id').date.nunique().reindex(s.index),state.n_days)
    if persist:
        path=rd/'reference_pure_day_extension.npz'
        np.savez(path,ids=s.index.to_numpy(),columns=extra.columns.to_numpy(dtype=str),values=extra.to_numpy())
        dump(rd/'reference_day_extension_audit.json',{
            'pure_raw_derived_only':True,'learned_transforms_models_or_labels_used':False,
            'all_boats':len(s),'features':20,'all_actual_observed_dates_and_rows_matched':True,
            'same20features_as_neural_full_inputs':True,
            'compact_features':150,'state_features':357,'relation_features':422,
            'source_sha256':sha(B/'fresh_day_deployment_inputs.py'),
            'extension_sha256':sha(path),'pure_daily_cache_metadata':meta})
    return extra


def load_reference_day_extension(rd,ids):
    with np.load(rd/'reference_pure_day_extension.npz') as z:
        assert np.array_equal(z['ids'],np.asarray(ids))
        return pd.DataFrame(z['values'],index=ids,columns=z['columns'])
