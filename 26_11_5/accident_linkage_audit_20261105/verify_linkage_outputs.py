"""Independent read-only verification; writes only independent_review.json beside this file."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


HOUR_NS = 3_600_000_000_000


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def distance(lon1, lat1, lon2, lat2):
    a, b = np.radians(lat1), np.radians(lat2)
    v = np.sin((b-a)/2)**2 + np.cos(a)*np.cos(b)*np.sin(np.radians(lon2-lon1)/2)**2
    return 12_742_000 * np.arcsin(np.sqrt(np.clip(v, 0, 1)))


def verify(run):
    checks = []
    def check(name, result, detail=None):
        checks.append({'name': name, 'passed': bool(result), 'detail': detail})
    manifest = json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    summary = json.loads((run/'summary.json').read_text(encoding='utf-8'))
    ev = pd.read_csv(run/'event_audit.csv', dtype={'event_id': str})
    cand = pd.read_csv(run/'candidate_vessels.csv', dtype={'event_id': str, 'rfid_id': str})
    sens = pd.read_csv(run/'sensitivity_summary.csv')
    dup = pd.read_csv(run/'possible_duplicate_events.csv')
    check('successful_manifest_and_input_unchanged', manifest['status']=='completed' and manifest['input_and_script_unchanged'])
    hashed = []
    for record in manifest['input_pre'] + manifest['outputs']:
        path = Path(record['path'])
        ok = path.is_file() and path.stat().st_size == record['size_bytes'] and digest(path)==record['sha256']
        hashed.append({'filename': path.name, 'passed': ok})
    check('all_input_and_output_hashes', all(x['passed'] for x in hashed), hashed)
    pre = {x['path']:x for x in manifest['input_pre']}
    post = {x['path']:x for x in manifest['input_post']}
    check('pre_post_hash_records_equal', pre==post)
    check('script_hash_current', digest(manifest['script_pre']['path']) == manifest['script_pre']['sha256'] == manifest['script_post']['sha256'])
    forbidden = Path(r'D:\repos\fishing-track-classification').resolve()
    check('output_outside_canonical', forbidden!=run and forbidden not in run.parents)

    accident = next(Path(x['path']) for x in manifest['input_pre'] if x['filename'].lower().endswith('.xlsx'))
    schema = manifest['accident_schema']
    raw = pd.read_excel(accident, sheet_name=schema['sheet'], dtype=object)
    check('all_167_source_rows_preserved', len(raw)==len(ev)==167 and ev.event_id.is_unique
          and ev.source_row_index.tolist()==list(range(len(raw)))
          and ev.source_excel_row_number.tolist()==list(range(2,len(raw)+2)))
    # Original fields are preserved textually; allow CSV's numeric representation change.
    original_ok = True
    for col in raw.columns:
        out = ev['accident_original__'+col]
        for original, actual in zip(raw[col],out):
            if pd.isna(original) and pd.isna(actual):
                continue
            if isinstance(original,(pd.Timestamp,datetime)):
                same = pd.Timestamp(original)==pd.to_datetime(actual,errors='coerce')
            elif isinstance(original,(int,float,np.number)):
                same = np.isclose(float(original),pd.to_numeric(actual,errors='coerce'),rtol=1e-11,atol=1e-10)
            else:
                same = str(original)==str(actual)
            original_ok = original_ok and bool(same)
    check('original_event_fields_and_row_mapping', original_ok)
    check('invalid_events_preserved', int((~ev.metadata_valid).sum())==summary['metadata_invalid_event_count']
          and (ev.loc[~ev.metadata_valid,'baseline_status']=='invalid_metadata').all())
    check('candidate_keys_unique', not cand.duplicated(['event_id','hour_bucket_radius','spatial_radius_m','rfid_id']).any())
    check('candidate_event_ids_exist', set(cand.event_id)<=set(ev.event_id))
    check('no_confirmed_identity_claim', not cand.association_is_confirmed_identity.any() and not ev.association_is_confirmed_identity.any())
    check('nine_distinct_conditions', set(zip(sens.hour_bucket_radius,sens.spatial_radius_m))=={(h,r) for h in (0,1,2) for r in (1000,3000,5000)} and len(sens)==9)
    sets = {}
    for row in sens.itertuples(index=False):
        h,r = int(row.hour_bucket_radius),int(row.spatial_radius_m)
        selected = cand[(cand.hour_bucket_radius==h)&(cand.spatial_radius_m==r)]
        count = selected.groupby('event_id').rfid_id.nunique().reindex(ev.event_id,fill_value=0).to_numpy()
        prefix = f'h{h}_r{r}m'
        sets[(h,r)] = set(zip(selected.event_id,selected.rfid_id))
        check(f'{prefix}_counts', (count==ev[prefix+'__candidate_vessel_count']).all()
              and int((count>0).sum())==row.candidate_event_count
              and int((count==1).sum())==row.single_candidate_event_count
              and int((count>1).sum())==row.multiple_candidate_event_count
              and len(selected)==row.candidate_event_vessel_association_count
              and int(selected.nearby_row_count.sum())==row.nearby_event_row_association_count)
        for which in ('minimum_distance_row__','best_time_row__'):
            dist = selected[which+'centroid_distance_m'].to_numpy()
            offset = selected[which+'bucket_offset_hours'].to_numpy()
            check(f'{prefix}_{which}finite_boundaries', np.isfinite(dist).all() and (dist>=0).all()
                  and (dist<=r+1e-7).all() and (np.abs(offset)<=h).all())
    check('nested_candidate_sets_nondecreasing', all(a<=b for (h,r),a in sets.items()
          for (hh,rr),b in sets.items() if h<=hh and r<=rr), 'Single-candidate event counts are not required to be monotonic.')
    baseline = cand[(cand.hour_bucket_radius==1)&(cand.spatial_radius_m==5000)]
    counts = baseline.groupby('event_id').rfid_id.nunique()
    check('baseline_118_candidate_30_single_events', len(counts)==118 and int((counts==1).sum())==30)
    check('duplicate_pairs_unique_not_merged', not dup.duplicated(['event_id_a','event_id_b']).any()
          and not dup.merged.any() and set(dup.event_id_a)|set(dup.event_id_b)<=set(ev.event_id))

    # Independently scan selected columns once for a few event/vessel combinations.
    samples = baseline.iloc[sorted(set([0,len(baseline)//2,len(baseline)-1]))].copy() if len(baseline) else baseline.copy()
    different = baseline[baseline['minimum_distance_row__source_row_index']!=baseline['best_time_row__source_row_index']]
    if len(different): samples = pd.concat([samples,different.iloc[[0]]]).drop_duplicates(['event_id','rfid_id'])
    by_event = ev.set_index('event_id')
    refs = {(x.event_id,x.rfid_id):[] for x in samples.itertuples(index=False)}
    sample_ids = set(samples.rfid_id)
    cols = ['row_index','part_dt','rfid_id','rfid_time','cen_lon','cen_lat','key_valid','wkt_valid']
    for record in manifest['input_pre']:
        path=Path(record['path'])
        if path.suffix.lower()!='.parquet': continue
        offset=0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=131072,columns=cols):
            frame=batch.to_pandas()
            frame['_physical']=np.arange(offset,offset+len(frame))
            offset+=len(frame)
            frame=frame[frame.rfid_id.astype(str).isin(sample_ids)&frame.key_valid&frame.wkt_valid].copy()
            if frame.empty: continue
            dates=pd.to_datetime(frame.part_dt.astype(str),format='%Y%m%d',errors='coerce')
            frame['_hour']=dates.astype('int64')//HOUR_NS + frame.rfid_time.astype(int)
            for (event_id,rid), rows in refs.items():
                e=by_event.loc[event_id]; when=pd.Timestamp(e.accident_time)
                hour=when.value//HOUR_NS
                sub=frame[(frame.rfid_id.astype(str)==rid)&((frame._hour-hour).abs()<=1)]
                if sub.empty: continue
                dist=distance(float(e.accident_lon),float(e.accident_lat),sub.cen_lon.to_numpy(),sub.cen_lat.to_numpy())
                for (_,x),d in zip(sub.iterrows(),dist):
                    if not np.isfinite(d) or d>5000: continue
                    delta=(int(x._hour)*HOUR_NS-when.value)/60_000_000_000
                    rows.append({'file':path.name,'index':int(x.row_index),'physical':int(x._physical),
                                 'distance':float(d),'delta':delta,'gap':max(delta,-delta-60,0),
                                 'offset':int(x._hour)-hour,'lon':float(x.cen_lon),'lat':float(x.cen_lat)})
    sample_details=[]
    for x in samples.itertuples(index=False):
        key=(x.event_id,x.rfid_id); rows=refs[key]
        record=samples[(samples.event_id==x.event_id)&(samples.rfid_id==x.rfid_id)].iloc[0]
        ok=len(rows)==int(x.nearby_row_count)
        for label,sorter in [('minimum_distance_row__',lambda a:(a['distance'],a['gap'],a['file'],a['index'],a['physical'])),
                             ('best_time_row__',lambda a:(a['gap'],abs(a['delta']),a['distance'],a['file'],a['index'],a['physical']))]:
            if not rows: ok=False; continue
            best=min(rows,key=sorter)
            ok=ok and best['file']==record[label+'source_filename'] and best['index']==record[label+'source_row_index'] and best['physical']==record[label+'source_cache_row_index']
            for name,value in [('centroid_distance_m',best['distance']),('track_hour_start_minus_accident_minutes',best['delta']),('interval_gap_minutes',best['gap']),('cen_lon',best['lon']),('cen_lat',best['lat'])]:
                ok=ok and bool(np.isclose(record[label+name],value,rtol=1e-10,atol=1e-6))
        sample_details.append({'event_id':x.event_id,'rfid_id':x.rfid_id,'source_rows_recomputed':len(rows),'passed':bool(ok)})
    check('independent_selected_cache_provenance_and_argmin', len(samples)>0 and all(x['passed'] for x in sample_details),sample_details)
    return {'status':'passed' if all(x['passed'] for x in checks) else 'failed',
            'verification_type':'independent_real_data_output_audit','checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'run_directory':str(run),'checks':checks,'event_count':len(ev),'candidate_association_rows':len(cand),
            'limits':['Candidate linkage is not confirmed vessel identity or accident detection performance.',
                      'Direct raw-cache argmin verification covers selected event/vessel samples; table aggregation covers every output row.',
                      'No source data, canonical repository, or producer output is modified.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory',type=Path)
    args=parser.parse_args()
    destination=Path(__file__).resolve().parent/'independent_review.json'
    try: report=verify(args.run_directory.resolve(strict=True))
    except Exception as error:
        report={'status':'failed','error_type':type(error).__name__,'error':str(error),
                'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(destination)},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
