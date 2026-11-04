from __future__ import annotations
import csv, hashlib, json, math, os, platform, re, statistics, sys, time, zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import psutil
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT=Path.cwd()
AUDIT=ROOT/'testB/round_002/audit/preparation_001'
ROUND=ROOT/'testB/round_002'
PREP=ROUND/'preparation'
EXEC=ROUND/'execution'
BATCH=16384
IDS=PREP/'new_testB_ids_100.csv'
PROJECTION=['row_index','part_dt','rfid_id','rfid_time','key_valid','wkt_valid','n_coords','len_m','bbox_m','cen_lon','cen_lat']
NUMERIC=['rfid_time','cen_lon','cen_lat','len_m','bbox_m']
SELECTION_FIELDS=['row_index','part_dt','rfid_id','rfid_time','key_valid','wkt_valid','n_coords','len_m','bbox_m','cen_lon','cen_lat']

def sha_file(path:Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def jsonread(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def as_tuple(row): return tuple(row.get(k) for k in SELECTION_FIELDS)
def finite(v): return v is not None and (not isinstance(v,float) or math.isfinite(v))
def dateok(v):
    if v is None: return False
    s=str(v)
    if not re.fullmatch(r'\d{8}',s): return False
    try: datetime.strptime(s,'%Y%m%d'); return True
    except ValueError: return False

def rows_csv(path):
    with path.open('r',encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def env_snapshot(label):
    vm=psutil.virtual_memory()
    procs=[]
    for p in psutil.process_iter(['name','memory_info']):
        try:
            n=p.info['name'] or ''
            if any(x in n.lower() for x in ('python','codex','orca','node')):
                procs.append({'name':n,'pid':p.pid,'rss_mib':round(p.info['memory_info'].rss/2**20,1)})
        except (psutil.NoSuchProcess,psutil.AccessDenied,TypeError): pass
    procs.sort(key=lambda x:x['rss_mib'],reverse=True)
    return {'phase':label,'local_time':datetime.now().astimezone().isoformat(),'available_mib':round(vm.available/2**20,1),'total_mib':round(vm.total/2**20,1),'process_count':len(psutil.pids()),'python_count':sum(x['name'].lower().startswith('python') for x in procs),'top_relevant_processes':procs[:12]}

def ids_direct_from_xlsx(raw_bytes, sheet_name='테스트B'):
    import io, openpyxl
    wb=openpyxl.load_workbook(io.BytesIO(raw_bytes),read_only=True,data_only=True)
    try:
        ws=wb[sheet_name]
        vals=[]
        for (v,) in ws.iter_rows(min_row=2,max_row=101,min_col=1,max_col=1,values_only=True):
            if not isinstance(v,str): raise AssertionError(f'workbook ID not string: {v!r}')
            vals.append(v)
        if ws['A1'].value!='rfid_id': raise AssertionError('workbook header mismatch')
        return vals, {'sheetnames':wb.sheetnames,'max_row':ws.max_row,'max_column':ws.max_column,'header':ws['A1'].value}
    finally: wb.close()

def run():
    before=env_snapshot('immediately_before_independent_scan')
    process=psutil.Process(); rss_start=process.memory_info().rss; rss_peak=rss_start
    if before['available_mib'] < 1024: raise RuntimeError(f'RAM gate: {before["available_mib"]} MiB < 1024MiB (512 work + 512 reserve)')
    prep=jsonread(PREP/'manifest.json'); em=jsonread(EXEC/'execution_manifest.json')
    current_ids=rows_csv(IDS)
    id_col='rfid_id' if current_ids and 'rfid_id' in current_ids[0] else 'raw_value'
    ids=[r[id_col] for r in current_ids]
    expected_hash=prep['new_submission']['ordered_ids_csv_sha256']
    ids_hash=sha_file(IDS)
    if len(ids)!=100 or len(set(ids))!=100 or any(not isinstance(x,str) or not x for x in ids): raise AssertionError('current ID list not exact 100 unique strings')
    if ids_hash!=expected_hash: raise AssertionError(f'current ID file hash mismatch: {ids_hash} != {expected_hash}')
    prior_path=ROOT/'testB/round_001/audit/v2_id_recheck_001/source_id_rows.csv'
    prior_sha=sha_file(prior_path)
    if prior_sha!=prep['new_submission']['direct_recheck_source_rows_sha256']: raise AssertionError('prior direct-source rows hash mismatch')
    prior=rows_csv(prior_path)
    # The prior direct check stores workbook rows for several sheets; select new ZIP member Test B rows only.
    prior_fields=list(prior[0]) if prior else []
    prior_groups=defaultdict(list)
    for r in prior:
        cell=r.get('cell','')
        if r.get('source')=='new_zip_member' and cell.startswith('A') and cell[1:].isdigit() and 2<=int(cell[1:])<=101:
            prior_groups[r.get('sheet','')].append((int(cell[1:]),r.get('raw_value') or r.get('raw') or r.get('value')))
    prior_matches=[]
    for sheet, pairs in prior_groups.items():
        seq=[v for _,v in sorted(pairs)]
        if len(seq)==100 and seq==ids: prior_matches.append({'sheet_field':sheet,'ids':seq})
    prior_newb=prior_matches[0]['ids'] if len(prior_matches)==1 else []
    if len(prior_matches)!=1: raise AssertionError(f'prior direct workbook rows did not uniquely match ordered IDs; matching groups={len(prior_matches)}; groups={[(k,len(v)) for k,v in prior_groups.items()]}')

    prior_summary=jsonread(ROOT/'testB/round_001/audit/v2_id_recheck_001/summary.json')
    zmeta=prior_summary['zip_member']
    zip_path=Path(zmeta['archive_path'])
    member_name=zmeta['member']
    intake_path=ROOT/'testB/intake/1103_v2/inspection_001/reference_02_제출샘플.xlsx'
    zip_stat_before=zip_path.stat(); intake_stat_before=intake_path.stat()
    with zipfile.ZipFile(zip_path,'r') as zf:
        zi=zf.getinfo(member_name)
        if zi.file_size!=zmeta['member_uncompressed_bytes'] or f'{zi.CRC:08x}'!=zmeta['member_crc32']:
            raise AssertionError('ZIP central-directory member size/CRC differs from prior direct record')
        workbook_bytes=zf.read(member_name)
    member_sha=hashlib.sha256(workbook_bytes).hexdigest()
    intake_sha=sha_file(intake_path)
    if member_sha!=prep['new_submission']['member_sha256'] or member_sha!=intake_sha or member_sha!=prep['new_submission']['intake_copy_sha256']:
        raise AssertionError('ZIP member/intake/current preparation hashes disagree')
    workbook_ids,wbmeta=ids_direct_from_xlsx(workbook_bytes)
    if workbook_ids!=ids: raise AssertionError('direct ZIP workbook Test B A2:A101 differs from ordered ID CSV')
    if zip_stat_before.st_size!=zip_path.stat().st_size or zip_stat_before.st_mtime_ns!=zip_path.stat().st_mtime_ns: raise AssertionError('ZIP metadata changed during member read')
    if intake_stat_before.st_size!=intake_path.stat().st_size or intake_stat_before.st_mtime_ns!=intake_path.stat().st_mtime_ns: raise AssertionError('intake workbook metadata changed during check')

    # Capture source/production code stats and exact current hashes where their small files permit.
    source_paths=[Path(r['parquet_path']) for r in prep['v2_csv_to_cache_lineage']['months']]
    prod_paths=[EXEC/'isolated_runner.py', EXEC/'preflight_report.md', EXEC/'execution_manifest.json', EXEC/'scan_result.json', EXEC/'target_row_summary.csv', *(EXEC/'selected_rows'/f'month_{m:02d}.parquet' for m in range(1,7)), ROUND/'preparation'/'manifest.json']
    watched={str(p):{'size_bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns,'sha256':sha_file(p)} for p in prod_paths}
    source_before={str(p):{'size_bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in source_paths}
    base_ordinal=0; month_results=[]; by_id={rid:{'raw':0,'valid':0,'scorable_contract':0,'scorable_producer':0,'month':Counter(),'dates':[],'bad':Counter(),'ranges':{n:[None,None] for n in NUMERIC},'ordinals':[],'duplicates':0} for rid in ids}
    duplicate_keys=set(); seen_rows_total=0; selected_total=0; invalid_dates=0; invalid_hours=0; key_invalid=0; finite_bad=0; selected_mismatch=[]; selected_missing=[]; selected_extra=[]; rowindex_bad=[]; source_stats=[]

    for src in prep['v2_csv_to_cache_lineage']['months']:
        month=int(src['month']); source=Path(src['parquet_path']); selected=EXEC/'selected_rows'/f'month_{month:02d}.parquet'
        expected_rows=int(src['raw_rows']); file_name=Path(src['source_path']).name
        pf=pq.ParquetFile(source); sf=pq.ParquetFile(selected)
        if not set(PROJECTION).issubset(pf.schema_arrow.names): raise AssertionError(f'source missing projection {month}')
        selected_map={}
        for b in sf.iter_batches(batch_size=BATCH,use_threads=False):
            cols={n:b.column(b.schema.get_field_index(n)).to_pylist() for n in b.schema.names}
            for i,rid in enumerate(cols['rfid_id']):
                key=(int(cols['row_index'][i]),rid)
                if key in selected_map: selected_extra.append((month,key,'duplicate selected key'))
                selected_map[key]=({n:cols[n][i] for n in SELECTION_FIELDS},cols['source_month'][i],cols['source_file'][i],cols['source_ordinal'][i])
        src_rows=0; picked_rows=0; local_last=-1; source_file_selected=Counter(); index_issues=0
        for batch in pf.iter_batches(batch_size=BATCH,columns=PROJECTION,use_threads=False):
            rss_peak=max(rss_peak,process.memory_info().rss)
            n=batch.num_rows; src_rows+=n; seen_rows_total+=n
            ix=batch.column(batch.schema.get_field_index('row_index')).to_pylist()
            for val in ix:
                if val is None or int(val)!=local_last+1:
                    index_issues+=1; rowindex_bad.append((month,local_last,val))
                local_last=int(val) if val is not None else local_last
            ids_col=batch.column(batch.schema.get_field_index('rfid_id')).to_pylist()
            mask=[rid in by_id for rid in ids_col]
            if not any(mask): continue
            picked=batch.filter(pa.array(mask,type=pa.bool_())); picked_rows+=picked.num_rows; selected_total+=picked.num_rows
            vals={n:picked.column(picked.schema.get_field_index(n)).to_pylist() for n in PROJECTION}
            for j,rid in enumerate(vals['rfid_id']):
                row={n:vals[n][j] for n in PROJECTION}; rowidx=row['row_index']
                key=(int(rowidx),rid)
                got=selected_map.pop(key,None)
                if got is None: selected_missing.append((month,key))
                else:
                    selrow,selmonth,selfile,ordinal=got
                    if as_tuple(selrow)!=as_tuple(row): selected_mismatch.append((month,key,as_tuple(row),as_tuple(selrow)))
                    if selmonth!=month or selfile!=file_name or ordinal!=base_ordinal+int(rowidx): selected_mismatch.append((month,key,'lineage',selmonth,selfile,ordinal))
                source_file_selected[selfile if got else 'missing']+=1
                st=by_id[rid]; st['raw']+=1; st['month'][month]+=1; st['ordinals'].append(base_ordinal+int(rowidx))
                for field in ['part_dt','key_valid','wkt_valid','n_coords','row_index']:
                    if row[field] is None: st['bad']['missing_'+field]+=1
                d=row['part_dt']; h=row['rfid_time']; valid=row['wkt_valid'] is True; st['valid']+=int(valid)
                if d is not None: st['dates'].append(str(d))
                doc=dateok(d)
                if not doc: st['bad']['invalid_part_dt']+=1; invalid_dates+=1
                hourok=isinstance(h,int) and not isinstance(h,bool) and 0<=h<=23
                if not hourok: st['bad']['rfid_time']+=1; invalid_hours+=1
                if row['key_valid'] is not True: st['bad']['key_valid']+=1; key_invalid+=1
                nums_ok=True
                for name in NUMERIC:
                    v=row[name]
                    if not finite(v): st['bad'][name]+=1; nums_ok=False; finite_bad+=1
                    else:
                        lo,hi=st['ranges'][name]; st['ranges'][name]=[v if lo is None else min(lo,v),v if hi is None else max(hi,v)]
                producer_scoreable=valid and nums_ok and d is not None and len(str(d))==8 and str(d).isdigit()
                strict_scoreable=valid and nums_ok and doc and hourok and row['key_valid'] is True
                st['scorable_producer']+=int(producer_scoreable)
                st['scorable_contract']+=int(strict_scoreable)
                if d is not None and hourok:
                    dupkey=(rid,str(d),int(h))
                    if dupkey in duplicate_keys: st['duplicates']+=1
                    else: duplicate_keys.add(dupkey)
        if src_rows!=expected_rows or local_last!=expected_rows-1: raise AssertionError(f'month {month} source row count/index mismatch: rows={src_rows},last={local_last},expected={expected_rows}')
        if selected_map: selected_extra.extend((month,k,'selected row not in source scan') for k in list(selected_map)[:10])
        if index_issues: raise AssertionError(f'month {month}: {index_issues} nonsequential row_index values')
        if picked_rows!=sf.metadata.num_rows: raise AssertionError(f'month {month}: independent selected count {picked_rows} != selected parquet {sf.metadata.num_rows}')
        month_results.append({'month':month,'source_rows_scanned':src_rows,'selected_in_source':picked_rows,'selected_parquet_rows':sf.metadata.num_rows,'row_index_sequential':True,'source_selected_values_exact':not any(x[0]==month for x in selected_mismatch),'selected_ordinals_exact':not any(x[0]==month for x in selected_mismatch),'source_file_exact':not any(x[0]==month for x in selected_mismatch),'source_file_values':dict(source_file_selected),'source_path':str(source)})
        base_ordinal+=expected_rows

    summary_rows=rows_csv(EXEC/'target_row_summary.csv')
    if len(summary_rows)!=100: raise AssertionError(f'target summary row count {len(summary_rows)} != 100')
    summary_by_id={r['rfid_id']:r for r in summary_rows}
    if list(summary_by_id)!=ids: raise AssertionError('summary ID order not equal selected ID order')
    summary_mismatches=[]; summary_comparisons=[]
    for order,rid in enumerate(ids,1):
        s=by_id[rid]; prod=summary_by_id[rid]
        values={'target_order':str(order),'raw_rows':s['raw'],'valid_wkt_rows':s['valid'],'invalid_wkt_rows':s['raw']-s['valid'],'scorable_finite_rows':s['scorable_producer'],'excluded_nonfinite_or_bad_date_rows':s['valid']-s['scorable_producer'],'month_row_counts':json.dumps({str(m):s['month'][m] for m in range(1,7)},separators=(',',':')),'date_min':min(s['dates']) if s['dates'] else '', 'date_max':max(s['dates']) if s['dates'] else '', 'duplicate_timestamp_rows_in_checked_keys':s['duplicates'],'missing_part_dt':s['bad']['missing_part_dt'],'missing_key_valid':s['bad']['missing_key_valid'],'missing_wkt_valid':s['bad']['missing_wkt_valid'],'missing_n_coords':s['bad']['missing_n_coords'],'missing_row_index':s['bad']['missing_row_index'],'missing_or_nonfinite_rfid_time':s['bad']['rfid_time'],'missing_or_nonfinite_cen_lon':s['bad']['cen_lon'],'missing_or_nonfinite_cen_lat':s['bad']['cen_lat'],'missing_or_nonfinite_len_m':s['bad']['len_m'],'missing_or_nonfinite_bbox_m':s['bad']['bbox_m'],'invalid_part_dt':s['bad']['invalid_part_dt']}
        for name in NUMERIC:
            values[name+'_min']=s['ranges'][name][0]; values[name+'_max']=s['ranges'][name][1]
        # Need null counts exactly from selected row data; derive in a second selected-only bounded pass.
        for k,v in values.items():
            if v is None: continue
            got=prod.get(k,'')
            if isinstance(v,float):
                try: match=(got=='' and v is None) or math.isclose(float(got),v,rel_tol=1e-12,abs_tol=1e-12)
                except Exception: match=False
            elif isinstance(v,(int,)): match=got!='' and int(got)==v
            else: match=str(got)==str(v)
            if not match: summary_mismatches.append({'rfid_id':rid,'field':k,'independent':v,'production':got})
        summary_comparisons.append({'rfid_id':rid,'raw_rows':s['raw'],'valid_wkt_rows':s['valid'],'production_scorable':s['scorable_producer'],'contract_scorable':s['scorable_contract'],'strict_vs_production_delta':s['scorable_contract']-s['scorable_producer'],'month_counts':{str(m):s['month'][m] for m in range(1,7)},'min_ordinal':min(s['ordinals']) if s['ordinals'] else None,'max_ordinal':max(s['ordinals']) if s['ordinals'] else None})

    # Focused static/runtime review of production code and evidence; independent fixtures below are authored here.
    runner_path=EXEC/'isolated_runner.py'; runner_text=runner_path.read_text(encoding='utf-8-sig')
    runner_ast=__import__('ast').parse(runner_text)
    topdefs={n.name:n for n in runner_ast.body if isinstance(n,(__import__('ast').FunctionDef,__import__('ast').AsyncFunctionDef))}
    static={'runner_sha256':sha_file(runner_path),'uses_explicit_source_hash_guard':'verify_source_bytes' in runner_text and 'EXPECTED_SOURCE_HASHES' in runner_text,'shim_is_simple_namespace':'SimpleNamespace(**rm_ns)' in runner_text,'AST_extracts_only_allowlisted_defs':'ast.Module(body=nodes' in runner_text,'build_gate_default_denies':'allow_reference_rebuild: bool = False' in runner_text and 'if not allow_reference_rebuild' in runner_text,'test_fit_partition_fenced':'partition != "train"' in runner_text,'load_inputs_manifest_unpack_fixed':'_id_manifest,target_ids,_id_sha=load_inputs()' in runner_text,'scoring_order_includes_source_ordinal':'sort_values(["ts", "rfid_time", "source_ordinal"]' in runner_text,'A_source_order_selection':'sort_values("source_ordinal"' in runner_text,'output_path_validation_present':'validate_output_path' in runner_text,'main_entrypoint_guard':'if __name__=="__main__"' in runner_text}
    # Verify full source bytes against fixed hashes recorded in execution manifest; do not import production code.
    expected_hashes=em['lineage_hashes']; source_code_paths={'run008':Path(r'D:\repos\fishing-track-classification\code\tools\run_008_testB_20261101.py'),'remeasure':Path(r'D:\repos\fishing-track-classification\code\tools\run_remeasure_20261031.py'),'run005':Path(r'D:\repos\fishing-track-classification\code\tools\run_005_F156_merge_20261101.py'),'featAC':Path(r'D:\repos\fishing-track-classification\code\tools\run_cycle4_3_featAC_20261101.py')}
    code_hashes={}
    for k,p in source_code_paths.items():
        if p.exists(): code_hashes[k]={'current_sha256':sha_file(p),'expected_execution_sha256':expected_hashes.get(k),'matches':sha_file(p)==expected_hashes.get(k)}
        else: code_hashes[k]={'path_exists':False,'current_sha256':None,'expected_execution_sha256':expected_hashes.get(k),'matches':None}

    # Independent scalar score contribution checks; no real reference/data. Haversine formula against two coordinates.
    def haversine_scalar(lon1,lat1,lon2,lat2,R=6371000.0):
        p1=math.radians(lat1); p2=math.radians(lat2); dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
        a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*R*math.asin(min(1.0,math.sqrt(a)))
    distance=haversine_scalar(127.0,36.0,127.1,36.0)
    scalar={'synthetic_haversine_m_127_0_36_to_127_1_36':distance,'formula':'2*R*asin(sqrt(sin²(dlat/2)+cos(lat1)cos(lat2)sin²(dlon/2)))','earth_radius_m':6371000.0,'synthetic_only':True}
    # Independently implement A policy fixtures incl equal maxima, same-time conflicts, missing, floor.
    def a_policy(rows):
        for key in {(x['ts'],x['rfid_time']) for x in rows}:
            group=[x for x in rows if (x['ts'],x['rfid_time'])==key]
            finite_scores=[x['score'] for x in group if x['score'] is not None and math.isfinite(x['score'])]
            if finite_scores and (len(finite_scores)!=len(group) or len(set(finite_scores))>1): return 'data_conflict',None
        finite_rows=[x for x in rows if x['score'] is not None and math.isfinite(x['score'])]
        if not finite_rows: return 'no_valid_score',None
        mx=max(x['score'] for x in finite_rows)
        return 'candidate',min((x for x in finite_rows if x['score']==mx),key=lambda x:x['source_ordinal'])
    fixtures={
      'two_rows_equal_max_input_order':a_policy([{'ts':1,'rfid_time':1,'score':0.7,'source_ordinal':8},{'ts':2,'rfid_time':2,'score':0.7,'source_ordinal':3}]),
      'same_timestamp_conflicting':a_policy([{'ts':1,'rfid_time':2,'score':0.7,'source_ordinal':8},{'ts':1,'rfid_time':2,'score':0.8,'source_ordinal':3}]),
      'same_timestamp_valid_missing':a_policy([{'ts':1,'rfid_time':2,'score':0.7,'source_ordinal':8},{'ts':1,'rfid_time':2,'score':None,'source_ordinal':3}]),
      'all_missing':a_policy([{'ts':1,'rfid_time':2,'score':None,'source_ordinal':8}]),
      'floor_preserved':1e-6
    }
    # Compare execution evidence; provider launch is not proof of provider-internal runtime.
    log_codes={}
    for p in sorted((EXEC/'logs').glob('*.exit_code.txt')):
        try: log_codes[p.name]=p.read_text(encoding='utf-8-sig').strip()
        except Exception: log_codes[p.name]='unreadable'
    current_stat_after={str(p):{'size_bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns,'sha256':sha_file(p)} for p in prod_paths}
    source_after={str(p):{'size_bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in source_paths}
    if watched!=current_stat_after: raise AssertionError('production/execution files changed during independent audit')
    if source_before!=source_after: raise AssertionError('source parquet stat changed during independent scan')
    if selected_mismatch or selected_missing or selected_extra: raise AssertionError('selected parquet values/lineage mismatch to independent source scan')
    if summary_mismatches: raise AssertionError(f'summary mismatches: {len(summary_mismatches)}')
    return {'status':'scan_complete','ram_start':before,'ram_expected_peak_increment_mib':256,'ram_peak_basis':'conservative bound: bounded 16,384-row projected batches plus at most 10,429 selected-row map entries for one month; session reserve 512MiB retained; no other worker launched by this auditor','ram_measured_process_rss_start_mib':round(rss_start/2**20,1),'ram_peak_rss_sampled_mib':round(rss_peak/2**20,1),'ram_peak_rss_sampled_delta_mib':round((rss_peak-rss_start)/2**20,1),'ram_peak_sampling':'sampled once per processed source batch, may miss within-batch transient peak','requested_model':'gpt-6-luna','requested_effort':'xhigh','provider_internal_model_effort':'unknown','ids':{'count':len(ids),'unique':len(set(ids)),'sha256':ids_hash,'ordered_match_prior_direct_rows':bool(prior_newb and prior_newb[:100]==ids),'prior_direct_rows_matched_count':len(prior_newb[:100]),'direct_zip_member_sha256':member_sha,'intake_copy_sha256':intake_sha,'workbook_metadata':wbmeta,'zip_member':member_name,'archive_read':'selected member only; no full archive hash/extraction'},'full_source_scan':{'batch_size':BATCH,'projection':PROJECTION,'rows_scanned':seen_rows_total,'selected_rows':selected_total,'per_month':month_results,'row_index_errors':len(rowindex_bad),'source_selected_exact':not selected_mismatch and not selected_missing and not selected_extra,'selected_values_mismatch_count':len(selected_mismatch),'selected_missing_count':len(selected_missing),'selected_extra_count':len(selected_extra),'scorable_producer_total':sum(x['scorable_producer'] for x in by_id.values()),'scorable_contract_total':sum(x['scorable_contract'] for x in by_id.values()),'invalid_calendar_date_rows':invalid_dates,'invalid_hour_rows':invalid_hours,'key_valid_not_true_rows':key_invalid,'nonfinite_or_missing_numeric_cells':finite_bad,'summary_field_mismatch_count':len(summary_mismatches),'summary_mismatches':summary_mismatches[:100]},'summary_rows':summary_comparisons,'static_review':static,'source_code_hashes':code_hashes,'synthetic_independent_fixtures':{'scalar':scalar,'A_policy':fixtures,'reference/test_fit_gate_static_only':True,'actual_score_or_reference_executed':False},'execution_evidence':{'manifest_execution':em.get('execution'),'logged_exit_codes':log_codes,'repair_history_preserved':all((EXEC/'logs'/x).exists() for x in ['preflight_report_mojibake_legacy.md','execution_manifest_mojibake_legacy.json']),'latest_manifest_hashes_recorded':True,'legacy_hashes_distinguished':'legacy mojibake backups have independent artifact hashes; current UTF-8 report/manifest hashes differ'},'read_only_integrity':{'production_files_before_after':watched,'source_parquet_stats_before_after':source_before,'unchanged':watched==current_stat_after and source_before==source_after},'environment':{'python':sys.version,'platform':platform.platform(),'pyarrow':pa.__version__,'pandas':__import__('pandas').__version__,'numpy':__import__('numpy').__version__,'psutil':psutil.__version__},'audit_exit':0}

if __name__=='__main__':
    started=time.time()
    try:
        result=run(); result['elapsed_seconds']=round(time.time()-started,2)
        (AUDIT/'independent_scan_result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'rows_scanned':result['full_source_scan']['rows_scanned'],'selected_rows':result['full_source_scan']['selected_rows'],'mismatches':result['full_source_scan']['summary_field_mismatch_count'],'elapsed_seconds':result['elapsed_seconds']},ensure_ascii=False))
    except Exception as e:
        err={'status':'fail','error_type':type(e).__name__,'error':str(e),'elapsed_seconds':round(time.time()-started,2)}
        (AUDIT/'independent_scan_result.json').write_text(json.dumps(err,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps(err,ensure_ascii=False),file=sys.stderr); sys.exit(1)

