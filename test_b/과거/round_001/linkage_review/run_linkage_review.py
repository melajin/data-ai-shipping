from __future__ import annotations
import csv, hashlib, json, os, platform, sys, time
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(r'D:\obsidian\claude\obsidian_export\DATA AI SHIPPING')
OUT = ROOT / 'testB' / 'round_001' / 'linkage_review'
OUT.mkdir(parents=True, exist_ok=True)
BASE = ROOT / '26_11_5' / 'accident_linkage_audit_20261105'
CACHE_DIR = ROOT / '29-30일 모델 심층 분석' / '분석 결과' / 'outputs' / 'remeasure_20261031'
ACCIDENT_XLSX = Path(r'F:\문제 데이터_수정_1027\26년 1~6월 어선 사고현황(테스트 데이터).xlsx')
INPUTS = [
    BASE / 'run_001' / 'event_audit.csv',
    BASE / 'run_001' / 'candidate_vessels.csv',
    BASE / 'run_001' / 'summary.json',
    BASE / 'derived_001' / 'baseline_single_review.csv',
    BASE / 'derived_001' / 'review_queue.csv',
    BASE / 'derived_001' / 'review_summary.json',
    BASE / 'run_001' / 'manifest.json',
    ACCIDENT_XLSX,
    ROOT / '26_11_5' / '20261105_TestB_감독세션_위임.md',
    ROOT / '26_11_5' / '20261105_사고연결_실행결과_상세보고서.md',
    ROOT / '26_11_5' / '20261105_분석종합과_TestB_실행계획.md',
    ROOT / '26_11_5' / 'accident_linkage_audit_20261105' / 'PROTOCOL.md',
    ROOT / '26_11_5' / 'testb_next_experiment_20261105' / 'contract' / 'preparation_contract.md',
    ROOT / 'testB' / 'round_001' / 'contract' / 'path_transition.md',
    ROOT / 'testB' / 'round_001' / 'integration' / 'runtime_receipts' / 'W1_path_transition_send.json',
    ROOT / '26_11_5' / 'testb_next_experiment_20261105' / 'integration' / 'runtime_receipts' / 'W1_start.json',
]
INPUTS.extend([ROOT/'docs'/'real_support_evidence_20261028.md', ROOT/'docs'/'competition_20261019'/'04_파일목록과_검증기록.md', ROOT/'docs'/'fishing_integration'/'04_평가와_후속실험.md'])
INPUTS.extend([CACHE_DIR/f'rows_train_{m}.parquet' for m in range(1,7)])
DOC_SEARCH_SCOPE = [
    '26_11_5/20261105_TestB_감독세션_위임.md',
    '26_11_5/20261105_분석종합과_TestB_실행계획.md',
    '26_11_5/20261105_사고연결_실행결과_상세보고서.md',
    '26_11_5/20261105_팀원자료_검토보고서.md',
    '26_11_5/20261105_Gemini대화_검토반박.md',
    '26_11_5/accident_linkage_audit_20261105/PROTOCOL.md',
    'docs/competition_20261019/** (local provided-material inventory and analysis notes)',
    'data/reference/competition_20261019/** (local provided-material inventory and project notes)',
    'docs/real_support_evidence_20261028.md',
    'docs/project_review_20261104.md',
    '11_04_final/docs/report_review_20261105/pdf_text.txt',
    'F:/문제 데이터_수정_1027/ (top-level/file-name inventory; contents not mass-searched)',
]

def sha(path: Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()
def stamp(): return datetime.now(timezone.utc).astimezone().isoformat()
def rows(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))
def finite_num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

started=stamp(); script_path=Path(__file__).resolve(); code_sha_pre=sha(script_path)
pre={str(p): {'size_bytes':p.stat().st_size,'sha256':sha(p)} for p in INPUTS if p.is_file()}

# All 30 single-candidate event records are read; priority union is represented explicitly.
base_rows=rows(BASE/'derived_001'/'baseline_single_review.csv')
review_rows=rows(BASE/'derived_001'/'review_queue.csv')
candidate_rows=rows(BASE/'run_001'/'candidate_vessels.csv')
event_rows={x['event_id']:x for x in rows(BASE/'run_001'/'event_audit.csv')}
by_review={x['event_id']:x for x in review_rows}
by_candidate=defaultdict(list)
for x in candidate_rows: by_candidate[x['event_id']].append(x)

priority_stable={'E0023'}
priority_multi={'E0042','E0108','E0123'}
priority_widened={x['event_id'] for x in base_rows if x['baseline_single_becomes_multiple_when_time_widened']=='True'}
priority=priority_stable | priority_multi | priority_widened

# Verify the exact accident spreadsheet columns and selected original rows only.
from openpyxl import load_workbook
wb=load_workbook(ACCIDENT_XLSX, read_only=True, data_only=True)
ws=wb['Sheet1']
headers=[c.value for c in ws[1]]
header_text=[str(x) if x is not None else '' for x in headers]
header_id_gaps=[h for h in header_text if any(t in h.lower() for t in ('rfid','선명','선박id','선박 ID','등록번호','선박번호'))]
raw_selected={}
for b in base_rows:
    eid=b['event_id']; excel_row=int(b['source_excel_row_number'])
    values=[c.value for c in ws[excel_row]]
    raw={header_text[i]: (values[i].isoformat() if hasattr(values[i], 'isoformat') else values[i]) for i in range(min(len(headers),len(values)))}
    raw_selected[eid]={'excel_row':excel_row,'time':str(raw.get('발생일시')),'reported_vessel_count':str(raw.get('사고선박수')),
                       'type':str(raw.get('선 종')),'tonnage':str(raw.get('톤수')),
                       'row_matches_derived_time':str(raw.get('발생일시'))==b['accident_original__발생일시'],
                       'has_direct_vessel_key_in_workbook':False}
wb.close()

# Cache-priority raw-row-shape summary for the existing minimum-distance row of each of the 30 cases.
import pyarrow.parquet as pq
shape_rows={}
for b in base_rows:
    eid=b['event_id']; fn=b['minimum_distance_row__source_filename']; ix=int(b['minimum_distance_row__source_cache_row_index'])
    p=CACHE_DIR/fn
    table=pq.read_table(p, columns=['row_index','part_dt','rfid_id','rfid_time','wkt_valid','n_coords','len_m','bbox_m','cen_lon','cen_lat'], filters=[('row_index','==',ix)])
    candidates=table.to_pylist()
    want_id=b['rfid_id']
    match=next((r for r in candidates if str(r.get('rfid_id'))==want_id), None)
    shape_rows[eid]={'cache_file':fn,'cache_row_index':ix,'source_row_index':b['minimum_distance_row__source_row_index'],
                     'row_found':match is not None,
                     'row_identity_matches':bool(match and str(match.get('rfid_id'))==want_id),
                     'part_dt':match.get('part_dt') if match else None,'rfid_time_hour':match.get('rfid_time') if match else None,
                     'wkt_valid':match.get('wkt_valid') if match else None,'n_coords':match.get('n_coords') if match else None,
                     'len_m':match.get('len_m') if match else None,'bbox_m':match.get('bbox_m') if match else None,
                     'cen_lon':match.get('cen_lon') if match else None,'cen_lat':match.get('cen_lat') if match else None,
                     'source_geometry_shape_available_in_cache':False}

condition_keys=[(h,r) for h in (0,1,2) for r in (1000,3000,5000)]
condition_maps={}
for b in base_rows:
    eid=b['event_id']; conds={}
    for h,r in condition_keys:
        key=f'h{h}_r{r}m'
        links=[]
        for c in by_candidate[eid]:
            if int(c['hour_bucket_radius'])==h and int(c['spatial_radius_m'])==r:
                links.append({'rfid_id':c['rfid_id'],'nearby_row_count':int(c['nearby_row_count']),
                              'unique_hour_count':int(c['unique_hour_count']),
                              'minimum_distance_row':{'source_filename':c['minimum_distance_row__source_filename'],
                                  'source_row_index':int(c['minimum_distance_row__source_row_index']),
                                  'cache_row_index':int(c['minimum_distance_row__source_cache_row_index']),
                                  'centroid_distance_m':finite_num(c['minimum_distance_row__centroid_distance_m']),
                                  'hour_bucket_offset':int(c['minimum_distance_row__bucket_offset_hours']),
                                  'track_hour_start_minus_accident_minutes':int(c['minimum_distance_row__track_hour_start_minus_accident_minutes']),
                                  'interval_gap_minutes':int(c['minimum_distance_row__interval_gap_minutes']),
                                  'accident_within_interval':c['minimum_distance_row__accident_within_track_hour_interval']=='True',
                                  'track_hour_start':c['minimum_distance_row__track_hour_start'],
                                  'track_hour_end_exclusive':c['minimum_distance_row__track_hour_end_exclusive']}})
        conds[key]=links
    condition_maps[eid]=conds

fields=['event_id','source_filename','source_sheet','source_row_index','source_excel_row_number','accident_time','accident_lon','accident_lat',
        'reported_accident_vessel_count','accident_original__선 종','accident_original__어업면허','accident_original__톤수',
        'rfid_id','baseline_candidate_ids','baseline_status','review_category','same_single_candidate_all_nine_conditions',
        'baseline_single_becomes_multiple_when_time_widened','baseline_single_present_in_narrowest_condition',
        'reported_count_mismatch_flag','min_distance_m','minrow_track_hour_start_minus_accident_minutes','minrow_interval_gap_minutes',
        'min_distance_row_source_file','min_distance_row_source_index','best_time_row_source_file','best_time_row_source_index',
        'baseline_h1_r5000_ids','widest_h2_r5000_ids','all_9_condition_relations_json','selected_cache_shape_json',
        'identity_confirmed','identity_evidence_level','direct_rfid_shipname_crosswalk_found','registry_available_in_prior_audit',
        'type_tonnage_filter_applied','development_use_allowed','normal_label_evidence_available','scope_priority_union','xlsx_source_row_time','xlsx_source_row_vessel_count','xlsx_row_matches_derived']
with (OUT/'evidence_table.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for b in base_rows:
        eid=b['event_id']; rv=by_review[eid]; ev=event_rows[eid]; cm=condition_maps[eid]
        h0=[z['rfid_id'] for z in cm['h1_r5000m']]
        h2=[z['rfid_id'] for z in cm['h2_r5000m']]
        case={'E0023':'stable_single','E0042':'reported_2_vessels','E0108':'reported_2_vessels','E0123':'reported_2_vessels','E0046':'widens_to_multiple','E0052':'widens_to_multiple','E0096':'widens_to_multiple','E0109':'widens_to_multiple','E0134':'widens_to_multiple','E0136':'widens_to_multiple'}.get(eid,'remaining_single_candidate_review')
        w.writerow({'event_id':eid,'xlsx_source_row_time':raw_selected[eid]['time'],'xlsx_source_row_vessel_count':raw_selected[eid]['reported_vessel_count'],'xlsx_row_matches_derived':str(raw_selected[eid]['row_matches_derived_time']).lower(),'event_id':eid,'source_filename':b['source_filename'],'source_sheet':b['source_sheet'],'source_row_index':b['source_row_index'],'source_excel_row_number':b['source_excel_row_number'],
           'accident_time':b['accident_time'],'accident_lon':b['accident_lon'],'accident_lat':b['accident_lat'],'reported_accident_vessel_count':b['reported_accident_vessel_count'],
           'accident_original__선 종':b['accident_original__선 종'],'accident_original__어업면허':b['accident_original__어업면허'],'accident_original__톤수':b['accident_original__톤수'],
           'rfid_id':b['rfid_id'],'baseline_candidate_ids':b['baseline_candidate_ids'],'baseline_status':b['baseline_status'],'review_category':b['review_category'],
           'same_single_candidate_all_nine_conditions':b['same_single_candidate_all_nine_conditions'],
           'baseline_single_becomes_multiple_when_time_widened':b['baseline_single_becomes_multiple_when_time_widened'],
           'baseline_single_present_in_narrowest_condition':b['baseline_single_present_in_narrowest_condition'],
           'reported_count_mismatch_flag':b['single_candidate_does_not_cover_reported_multi_vessel_event'],
           'min_distance_m':b['minimum_distance_row__centroid_distance_m'],'minrow_track_hour_start_minus_accident_minutes':b['minimum_distance_row__track_hour_start_minus_accident_minutes'],
           'minrow_interval_gap_minutes':b['minimum_distance_row__interval_gap_minutes'],'min_distance_row_source_file':b['minimum_distance_row__source_filename'],
           'min_distance_row_source_index':b['minimum_distance_row__source_row_index'],'best_time_row_source_file':b['best_time_row__source_filename'],'best_time_row_source_index':b['best_time_row__source_row_index'],
           'baseline_h1_r5000_ids':';'.join(sorted(z['rfid_id'] for z in cm['h1_r5000m'])),'widest_h2_r5000_ids':';'.join(sorted(h2)),
           'all_9_condition_relations_json':json.dumps(cm,ensure_ascii=False,separators=(',',':')),
           'selected_cache_shape_json':json.dumps(shape_rows[eid],ensure_ascii=False,separators=(',',':')),
           'identity_confirmed':'false','identity_evidence_level':'spatiotemporal_candidate_only; no direct identifying key',
           'direct_rfid_shipname_crosswalk_found':'false in inspected supplied local inventory','registry_available_in_prior_audit':ev.get('track_registry_available','False'),
           'type_tonnage_filter_applied':'false','development_use_allowed':'unknown; no primary archived use-rule source located in inspected local files',
           'normal_label_evidence_available':'false in inspected local material; missing record is not a normal label',
           'scope_priority_union':case})

# Local supplied data inventory: names/metadata only, no bulk CSV reads.
provided_dir=Path(r'F:\문제 데이터_수정_1027')
provided_files=[]
if provided_dir.exists():
    for p in sorted(provided_dir.rglob('*')):
        if p.is_file() and (p.suffix.lower() in ('.xlsx','.pdf','.hwp','.txt','.md') or p.parent==provided_dir):
            provided_files.append({'path':str(p),'size_bytes':p.stat().st_size,'content_read':p==ACCIDENT_XLSX})

# Search tracked local documentation, but retain explicit scope limits; no internet or outside contact.
search_terms=['RFID','선명','선박 ID','선박ID','제원','테스트 데이터','학습 금지','전체 항적','이후 항적','사고시각','6시간','정상 정답']
report={
 'title':'W1 연결근거 검토', 'date_local':datetime.now().astimezone().date().isoformat(), 'input_version':'legacy provided inputs; no 1103_v2 archive used or validated',
 'finding':{'priority_union_event_count':len(priority),'priority_union_event_ids':sorted(priority),
   'all_existing_single_candidate_events_reviewed':len(base_rows),'identity_confirmed_count':0,
   'direct_crosswalk_found':False,'registry_found_in_audit':False,'type_tonnage_filter_applied':False,
   'development_use_allowed':'unknown','normal_label_evidence_available':False,
   'recommended_gate':'아직 시각 비교 준비만 가능',
   'recommendation_reason':'후보표는 항적 유사성을 보일 뿐 직접 신원 키가 없고, 사고 자료의 개발용 사용 허용에 대한 원문이 로컬에서 확인되지 않았으며, 독립적인 확인 정상 라벨/분모도 없다.'},
 'case_counts':{'base_single_candidates':len(base_rows),'stable_same_candidate_all_nine_conditions':sum(b['same_single_candidate_all_nine_conditions']=='True' for b in base_rows),
   'time_widened_to_multiple':sum(b['baseline_single_becomes_multiple_when_time_widened']=='True' for b in base_rows),
   'reported_multiple_accident_vessel_count':sum(b['single_candidate_does_not_cover_reported_multi_vessel_event']=='True' for b in base_rows),
   'selected_cache_rows_checked':sum(r['row_found'] for r in shape_rows.values()),
   'xlsx_headers_count':len(headers),'xlsx_selected_source_row_match_count':sum(x['row_matches_derived_time'] for x in raw_selected.values()),'direct_id_headers':header_id_gaps},
 'local_search':{'terms':search_terms,'scope':DOC_SEARCH_SCOPE,'conclusion':'In the inspected local source inventory, accident workbook identifies time/location/type/count/tonnage but no RFID, vessel name, registration number, or vessel registry crosswalk. No primary original competition announcement/Q&A file was located; rule statements are repeated in local handoff/planning documents that attribute them to user-provided organizer replies. No universal absence claim.'},
 'input_inventory':provided_files,
 'limits':['The full 30-case table is existing single-candidate subset only, not all 167 events; no relabeling of the other 137 events.','The existing candidate conditions are inherited, not recalculated.','Cache rows provide summarized geometry (n_coords, length, bbox, centroid) but not original WKT/part boundaries; no raw CSV geometry was read.','No point-level timestamps; no speed or acceleration calculated.','Candidate distance/time residuals are linkage evidence only, never detection error or performance.','No test-set training, label fitting, outside search, external contact, or new classifier/threshold fitting.','The 1103_v2 ZIP was not opened; this is explicitly legacy-input analysis.']
}
(OUT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Inputs used / observed manifests with pre/post hashes; output files listed except manifest itself.
post={str(p): {'size_bytes':p.stat().st_size,'sha256':sha(p)} for p in INPUTS if p.is_file()}
code_sha_post=sha(script_path)
manifest={
 'task':'W1 linkage evidence review','output_version':'testB/round_001/linkage_review','input_version':'legacy existing audit data and local legacy provided files','started_local':started,'finished_local':stamp(),
 'model_evidence':{'requested_by_orca':'gpt-6-luna','effort_requested':'xhigh','evidence_path':str(ROOT/'26_11_5'/'testb_next_experiment_20261105'/'integration'/'runtime_receipts'/'W1_start.json'),
   'receipt':json.loads((ROOT/'26_11_5'/'testb_next_experiment_20261105'/'integration'/'runtime_receipts'/'W1_start.json').read_text(encoding='utf-8-sig')),'server_internal_runtime_model':'unknown'},
 'environment':{'python':sys.version,'python_executable':sys.executable,'platform':platform.platform(),'pyarrow':__import__('pyarrow').__version__,'openpyxl':__import__('openpyxl').__version__},
 'inputs_pre':pre,'inputs_post':post,'input_hashes_unchanged':pre==post,
 'code':{'path':str(script_path),'sha256_pre':code_sha_pre,'sha256_post':code_sha_post,'unchanged':code_sha_pre==code_sha_post},
 'scope':{'event_ids_reviewed':sorted(b['event_id'] for b in base_rows),'priority_union_event_ids':sorted(priority),
   'candidate_conditions_inherited':[f'h{h}_r{r}m' for h,r in condition_keys],'raw_accident_rows_read':len(raw_selected),'cache_rows_selected':len(shape_rows),
   'source_wkt_geometry_read':False,'external_internet_or_contact':False,'v2_zip_read':False},
 'local_document_search':{'terms':search_terms,'scope':DOC_SEARCH_SCOPE,'not_exhaustive_paths':['other user/cloud accounts','unindexed files outside listed local source folders','original organizer email/chat not saved as a local file']},
 'outputs':['evidence_table.csv','review_report.md','summary.json','manifest.json','run_linkage_review.py','stdout.log','stderr.log','process_result.json','stdout_attempt1.log','stderr_attempt1.log','process_result_attempt1.json','process_result_attempt2.json','stdout_attempt3.log','stderr_attempt3.log','process_result_attempt3.json','stdout_attempt4.log','stderr_attempt4.log','process_result_attempt4.json','stdout_attempt5.log','stderr_attempt5.log','process_result_attempt5.json','process_result_attempt6_pre_source_hashes.json','stdout_attempt7.log','stderr_attempt7.log','process_result_attempt7.json'],
 'output_sha256_after_run':{p.name:sha(p) for p in [OUT/'evidence_table.csv',OUT/'summary.json',script_path]},
 'attempt_history':[{'attempt':1,'exit_code':1,'reason':'UTF-8 BOM in Orca runtime receipt was not handled','artifacts':['stdout_attempt1.log','stderr_attempt1.log','process_result_attempt1.json']},{'attempt':2,'exit_code':0,'note':'preliminary successful artifact generation before CSV field label correction','artifact':'process_result_attempt2.json'},{'attempt':3,'exit_code':1,'reason':'attempt-history metadata syntax error','artifacts':['stdout_attempt3.log','stderr_attempt3.log','process_result_attempt3.json','stdout_attempt4.log','stderr_attempt4.log','process_result_attempt4.json','stdout_attempt5.log','stderr_attempt5.log','process_result_attempt5.json','process_result_attempt6_pre_source_hashes.json','stdout_attempt7.log','stderr_attempt7.log','process_result_attempt7.json']}],
 'process_result_recorded_by_wrapper':'process_result.json (actual Python exit code captured by PowerShell wrapper)'
}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'events_reviewed':len(base_rows),'priority_union_count':len(priority),'priority_union_ids':sorted(priority),'cache_rows_found':sum(x['row_found'] for x in shape_rows.values()),'identity_confirmed':0,'input_hashes_unchanged':pre==post,'code_hash_unchanged':code_sha_pre==code_sha_post},ensure_ascii=False))







