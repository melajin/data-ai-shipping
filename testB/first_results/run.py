"""Original loader/builders/scorer, new Test B roster, local outputs only."""
from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = Path('D:/repos/fishing-track-classification/code/tools/run_008_testB_20261101.py')
SELECTED = ROOT / 'testB/round_002/execution/selected_rows'
IDS = ROOT / 'testB/round_002/preparation/new_testB_ids_100.csv'


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def metrics():
    mi = psutil.Process().memory_info()
    return {k: round(getattr(mi, k, 0) / 2**20, 2)
            for k in ('rss', 'peak_wset', 'pagefile', 'peak_pagefile')}


def preflight(stage, planned_mib):
    free = psutil.virtual_memory().available / 2**20
    record = {'at': datetime.now().astimezone().isoformat(), 'stage': stage,
              'available_mib': round(free, 1), 'planned_process_peak_mib': planned_mib,
              'reserve_mib': 640, 'basis': 'Sequential original implementation; estimate, not measured upper bound',
              'other_large_processes': []}
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            if p.info['memory_info'].rss > 200 * 2**20:
                record['other_large_processes'].append({'pid': p.pid, 'name': p.info['name'],
                    'rss_mib': round(p.info['memory_info'].rss / 2**20, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    save(f'{stage}_preflight.json', record)
    if free < planned_mib + 640:
        raise MemoryError(f'{stage}: available {free:.0f} MiB < plan {planned_mib}+640')


def module():
    spec = importlib.util.spec_from_file_location('testb_original_008', SOURCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(stage):
    plans = {'measure': 2600, 'domain': 400, 'harbor': 2200, 'density': 2800, 'gap': 2500, 'score': 650}
    preflight(stage, plans[stage])
    start = time.monotonic()
    s = module()
    if stage == 'measure':
        cols = ['row_index', 'part_dt', 'rfid_id', 'rfid_time', 'fishing_code', 'key_valid',
                'wkt_valid', 'n_coords', 'len_m', 'bbox_m', 'cen_lon', 'cen_lat']
        df = s.remeasure.load_rows('train', cols)
        result = {'rows': len(df), 'columns': list(df.columns),
                  'dataframe_deep_mib': round(df.memory_usage(deep=True).sum()/2**20, 2),
                  'dtypes': df.dtypes.astype(str).to_dict(), 'process_memory_mib': metrics(),
                  'original_loader': str(Path(s.remeasure.__file__).resolve())}
        save('original_loader_measurement.json', result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    elif stage == 'domain':
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
        result = {}
        for dataset in ('train', 'test'):
            counts = {'rows': 0, 'rfid_id_noninteger': 0, 'part_dt_noninteger': 0,
                      'admitted_rfid_id_noninteger': 0, 'admitted_part_dt_noninteger': 0,
                      'rfid_id_max_length': 0, 'part_dt_max_length': 0}
            for month in s.remeasure.MONTHS:
                pf = pq.ParquetFile(s.remeasure.parquet_path(dataset, month))
                for b in pf.iter_batches(batch_size=65536, columns=['rfid_id','part_dt','key_valid']):
                    counts['rows'] += b.num_rows
                    kv = b.column('key_valid')
                    for col in ('rfid_id', 'part_dt'):
                        a = b.column(col)
                        ok = pc.fill_null(pc.match_substring_regex(a, '^[+-]?[0-9]+$'), False)
                        bad = pc.invert(ok)
                        counts[col+'_noninteger'] += pc.sum(pc.cast(bad, 'int64')).as_py() or 0
                        counts['admitted_'+col+'_noninteger'] += pc.sum(pc.cast(pc.and_(bad,kv), 'int64')).as_py() or 0
                        counts[col+'_max_length'] = max(counts[col+'_max_length'], pc.max(pc.utf8_length(a)).as_py() or 0)
            result[dataset] = counts
        save('key_distribution.json', result)
        print(json.dumps(result), flush=True)
    elif stage == 'harbor':
        nearest, meta, points = s.build_train_harbors()
        save('harbors.json', {'meta': meta, 'points': points})
        print(json.dumps(meta), flush=True)
    elif stage == 'density':
        fine, coarse, unused_density, meta = s.build_train_fishing_density_dicts()
        with (HERE/'density.pkl').open('wb') as f:
            pickle.dump((fine,coarse), f, protocol=pickle.HIGHEST_PROTOCOL)
        save('density_meta.json', meta)
        print(json.dumps(meta), flush=True)
    elif stage == 'gap':
        gaps, jumps = s.build_gap_jump_reference()
        np.save(HERE/'gap_reference.npy', gaps)
        np.save(HERE/'jump_reference.npy', jumps)
        save('gap_meta.json', {'pairs':len(gaps),'gap_median_h':float(np.median(gaps)),
                               'jump_median_m':float(np.median(jumps))})
    elif stage == 'score':
        from scipy.spatial import cKDTree
        import pyarrow.parquet as pq
        target = pd.read_csv(IDS, dtype=str)['raw_value'].tolist()
        df = pd.concat([pq.read_table(p).to_pandas() for p in sorted(SELECTED.glob('month_*.parquet'))], ignore_index=True)
        df['rfid_id'] = df['rfid_id'].astype(str)
        df['part_dt'] = pd.to_numeric(df['part_dt']).astype(np.int32)
        df = df[df['key_valid'] & df['wkt_valid']].copy()
        df['ts'] = s.remeasure._ts_hours(df['part_dt'].to_numpy(),df['rfid_time'].to_numpy())
        if 'source_ordinal' not in df:
            raise RuntimeError('source_ordinal absent')
        harbors = json.loads((HERE/'harbors.json').read_text(encoding='utf-8'))
        pts = np.asarray(harbors['points'], dtype=float)
        mx = 111320.0 * np.cos(np.radians(harbors['meta']['ref_lat']))
        my = 110540.0
        tree = cKDTree(pts*np.array([mx,my])) if len(pts) else None
        def nearest(lons,lats):
            lons,lats = np.asarray(lons,dtype=float),np.asarray(lats,dtype=float)
            if tree is None or not len(lons):
                return np.full(len(lons),np.inf)
            _,idx = tree.query(np.column_stack([lons*mx,lats*my]), k=1)
            hp = pts[idx]
            return s.haversine_vec(lons,lats,hp[:,0],hp[:,1])
        with (HERE/'density.pkl').open('rb') as f:
            fine,coarse = pickle.load(f)
        norm_gap,_ = s.build_quantile_normalizer(np.load(HERE/'gap_reference.npy'))
        norm_jump,_ = s.build_quantile_normalizer(np.load(HERE/'jump_reference.npy'))
        all_scored, candidates, submission = [],[],[]
        for i,rid in enumerate(target):
            sub = df[df['rfid_id']==rid].sort_values(['ts','rfid_time','source_ordinal'],kind='stable').reset_index(drop=True)
            scored = s.score_vessel(sub,nearest,None,fine,coarse,norm_gap,norm_jump)
            all_scored.append(scored)
            valid = scored[np.isfinite(scored['score'])]
            rec = {'rfid_id':rid,'status':'no_valid_score','n_rows':len(scored)}
            draft = {'rfid_id':rid}
            if len(valid):
                peak = valid[valid['score']==valid['score'].max()].sort_values('source_ordinal').iloc[0]
                t,score = int(peak['ts']),float(peak['score'])
                rec.update(status='exploratory_A',A=s.hours_to_label(t),score=score,
                           s_zone=float(peak['s_zone']),s_change=float(peak['s_change']),s_gap=float(peak['s_gap']),
                           source_ordinal=int(peak['source_ordinal']))
                draft.update({'사고시각':s.hours_to_label(t),'이상항적 점수':round(score,6)})
                tmap = dict(zip(scored['ts'].tolist(),scored['score'].tolist()))
                for k,off in enumerate((3,2,1),1):
                    v = tmap.get(t-off)
                    if v is not None and np.isfinite(v):
                        draft[f'시각{k}'] = s.hours_to_label(t-off)
                        draft[f'시각{k} 이상항적 점수'] = round(float(v),6)
            candidates.append(rec)
            submission.append(draft)
            print(f'scored {i+1}/100 rows={len(scored)}', flush=True)
        scores = pd.concat(all_scored,ignore_index=True)
        a = pd.DataFrame(candidates)
        scores.to_parquet(HERE/'hourly_scores.parquet',index=False)
        scores.to_csv(HERE/'hourly_scores.csv',index=False,encoding='utf-8-sig')
        a.to_csv(HERE/'candidate_A.csv',index=False,encoding='utf-8-sig')
        cols = ['rfid_id','사고시각','이상항적 점수','시각1','시각1 이상항적 점수','시각2','시각2 이상항적 점수','시각3','시각3 이상항적 점수']
        draft = pd.DataFrame(submission).reindex(columns=cols)
        draft.to_csv(HERE/'testB_submission_candidate.csv',index=False,encoding='utf-8-sig')
        assert len(draft)==100 and draft['rfid_id'].tolist()==target
        assert len(scores)==46705
        assert scores['score'].between(1e-6,1).all()
        summary = {'target_vessels':len(target),'scored_rows':len(scores),'A_vessels':int((a.status=='exploratory_A').sum()),
                   'all_hourly_scores':scores['score'].describe().to_dict(),
                   'vessel_peak_scores':a['score'].describe().to_dict(),
                   'meaning':'Unsupervised anomaly score and A time candidate; not accident probability or measured competition performance.',
                   'submission':'Local A-only baseline in submission format; all finite A candidates filled; no calibrated accident threshold; not uploaded.',
                   'tie_rule':'First maximum in original source ordinal; causal scoring in timestamp/source order.',
                   'missing_ground_truth':'No confirmed 2025 Test B accident labels; precision/recall/time error not computed.'}
        save('results.json',summary)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    save(f'{stage}_receipt.json',{'stage':stage,'elapsed_seconds':round(time.monotonic()-start,3),
                                 'process_memory_mib':metrics(),'completed_at':datetime.now().astimezone().isoformat()})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['measure','domain','harbor','density','gap','score'])
    args=parser.parse_args()
    main(args.stage)
