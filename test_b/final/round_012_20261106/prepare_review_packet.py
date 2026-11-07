"""Verify stored baseline only, copy unchanged reference artifacts into a review packet."""
from pathlib import Path, PurePosixPath
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
import shutil
import time
import xml.etree.ElementTree as ET
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ARCHIVE=ROOT/'testB'/'과거'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):
            h.update(b)
    return h.hexdigest()


def read_template_ids(path):
    ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    relns='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(s.itertext()) for s in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('x:si',ns)]
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        sheet=next(s for s in wb.findall('x:sheets/x:sheet',ns) if s.get('name')=='테스트B')
        targets={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        target=targets[sheet.get(relns)]
        target=target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl')/target)
        xml=ET.fromstring(z.read(target))
        def value(cell):
            if cell is None:return ''
            if cell.get('t')=='inlineStr':return ''.join(cell.find('x:is',ns).itertext())
            node=cell.find('x:v',ns)
            text=node.text if node is not None else ''
            return shared[int(text)] if cell.get('t')=='s' else text
        rows=xml.findall('x:sheetData/x:row',ns)
        header_row=next(r for r in rows if r.get('r')=='1')
        headers={c.get('r'):value(c) for c in header_row}
        ids=[]
        for row in rows:
            number=int(row.get('r'))
            if number<=1:continue
            cell=next((c for c in row if c.get('r')==f'A{number}'),None)
            val=value(cell)
            if val:ids.append(str(val))
        return ids,[headers.get(f'{col}1','') for col in 'ABCDEFGHI']


def label(hour):
    stamp=datetime(1970,1,1)+timedelta(hours=int(hour))
    return f"{stamp.strftime('%Y%m%d')} {stamp.hour}"


def main():
    import psutil
    available=psutil.virtual_memory().available
    preflight={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'available_mib':available/1048576,
               'expected_extra_mib':512,'reserve_mib':640,'allowed':available>=1152*1048576,
               'basis':'Read-only4column46705row baseline projection and tinyCSV/zipXML; no model inference'}
    if not preflight['allowed']:raise MemoryError('Review packet memory deferred')
    import pyarrow.parquet as pq
    source=ARCHIVE/'first_results'
    template=ARCHIVE/'intake/1103_v2/inspection_001/reference_02_제출샘플.xlsx'
    paths=[source/'testB_submission_candidate.csv',source/'candidate_A.csv',source/'hourly_scores.parquet',source/'run.py',source/'results.json',template]
    before={str(p):sha(p) for p in paths}
    packet=HERE/'review_packet_001'
    if packet.exists():raise FileExistsError('Fresh packet directory required')
    packet.mkdir()
    with (source/'testB_submission_candidate.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f); submission=list(reader); fields=reader.fieldnames
    with (source/'candidate_A.csv').open(encoding='utf-8-sig',newline='') as f:
        candidate=list(csv.DictReader(f))
    template_ids,headers=read_template_ids(template)
    table=pq.read_table(source/'hourly_scores.parquet',columns=['rfid_id','ts','source_ordinal','score'])
    rows=table.to_pylist()
    grouped={}
    for row in rows:grouped.setdefault(str(row['rfid_id']),[]).append(row)
    sub_ids=[r['rfid_id'] for r in submission]
    if len(submission)!=100 or len(set(sub_ids))!=100 or len(rows)!=46705 or set(sub_ids)!=set(grouped):
        raise ValueError('Stored baseline roster/row count mismatch')
    candidate_by_id={r['rfid_id']:r for r in candidate}
    if len(candidate_by_id)!=100 or set(candidate_by_id)!=set(sub_ids):raise ValueError('Candidate source roster mismatch')
    expected_columns=['rfid_id','사고시각','이상항적 점수','시각1','시각1 이상항적 점수','시각2','시각2 이상항적 점수','시각3','시각3 이상항적 점수']
    if fields!=expected_columns:raise ValueError('Stored baseline CSV schema changed')
    checks=[]; nonmissing={f'시각{k}':0 for k in range(1,4)}
    for rec in submission:
        rid=rec['rfid_id']; vessel=grouped[rid]
        if not all(math.isfinite(float(r['score'])) and 0<=float(r['score'])<=1 for r in vessel):raise ValueError('Stored score invalid')
        best=max(float(r['score']) for r in vessel)
        peak=min((r for r in vessel if float(r['score'])==best),key=lambda r:int(r['source_ordinal']))
        if rec['사고시각']!=label(peak['ts']) or abs(float(rec['이상항적 점수'])-round(best,6))>1e-12:
            raise ValueError(f'Stored lead candidate mismatch:{rid}')
        saved=candidate_by_id[rid]
        if int(saved['source_ordinal'])!=int(peak['source_ordinal']) or saved['A']!=label(peak['ts']):
            raise ValueError('Candidate_A lineage mismatch')
        by_time={int(r['ts']):float(r['score']) for r in sorted(vessel,key=lambda r:(int(r['ts']),int(r['source_ordinal'])))}
        for k,offset in enumerate([3,2,1],1):
            col=f'시각{k}'; score_col=f'시각{k} 이상항적 점수'; hour=int(peak['ts'])-offset
            if hour in by_time and math.isfinite(by_time[hour]):
                if rec[col]!=label(hour) or not rec[score_col] or abs(float(rec[score_col])-round(by_time[hour],6))>1e-12:
                    raise ValueError(f'Stored preceding-hour mismatch:{rid}/{col}')
                nonmissing[col]+=1
            elif rec[col] or rec[score_col]:raise ValueError('Unexpected filled missing-hour slot')
        checks.append({'rfid_id':rid,'lead_matches_stored_peak':True,'source_ordinal':int(peak['source_ordinal']),
                       'lead_ts':int(peak['ts']),'stored_reference_hours_match':True})
    copies={source/'testB_submission_candidate.csv':'testB_existing_baseline_UNVERIFIED.csv',
            source/'candidate_A.csv':'testB_existing_candidate_lineage.csv',
            source/'hourly_scores.parquet':'testB_existing_hourly_scores.parquet',
            template:'submission_template_UNCHANGED_REFERENCE.xlsx'}
    copied=[]
    for original,name in copies.items():
        target=packet/name;shutil.copyfile(original,target)
        if sha(target)!=before[str(original)]:raise ValueError('Reference copy changed bytes')
        copied.append({'source':str(original),'copy':str(target),'sha256':sha(target),'bytes':target.stat().st_size})
    # Development outputs are a different cohort from the100-ID Test B reference.
    dev=ROOT/'testB/final/round_011_20261106/execution_001'
    with (dev/'predictions.csv').open(encoding='utf-8-sig',newline='') as f:
        devreader=csv.DictReader(f); devfields=devreader.fieldnames; devpred=[r for r in devreader if r['method']=='B0']
    with (packet/'development_B0_predictions_82RFIDs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=devfields);writer.writeheader();writer.writerows(devpred)
    with (dev/'event_results.csv').open(encoding='utf-8-sig',newline='') as f:
        devreader=csv.DictReader(f); eventfields=devreader.fieldnames; devevents=[r for r in devreader if r['method']=='B0']
    with (packet/'development_B0_event_results_100events.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=eventfields);writer.writeheader();writer.writerows(devevents)
    with (packet/'baseline_storage_checks.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(checks[0]));writer.writeheader();writer.writerows(checks)
    if any(sha(Path(p))!=digest for p,digest in before.items()):raise ValueError('Original artifact changed')
    receipt={'status':'complete','purpose':'Review packet ONLY; not a validated/improved competition submission',
        'no_new_inference':True,'no_workbook_edits':True,'no_upload':True,'original_files_unchanged':True,
        'ram_preflight':preflight,'source_sha256':sha(Path(__file__)),'input_sha256':before,'unchanged_reference_copies':copied,
        'testB_stored_rows':46705,'testB_stored_rfids':100,'lead_peak_checks':100,'reference_hour_checks':100,
        'nonmissing_preceding_time_slots':nonmissing,'template_ids_n':len(template_ids),
        'template_unique_ids_n':len(set(template_ids)),'template_id_set_matches':set(template_ids)==set(sub_ids),
        'template_id_order_matches':template_ids==sub_ids,'template_headers_A1_I1':headers,
        'baseline_csv_header_matches_template_verbatim':fields==headers,
        'observed_stored_first_hour':label(min(int(r['ts']) for r in rows)),
        'observed_stored_last_hour':label(max(int(r['ts']) for r in rows)),
        'official_rule_conformance':None,'confirmed_testB_accident_performance':None,
        'development_cohort_separate':{'rfids':82,'events':100,'tier01_events':60,'B0_all_top1':3,'B0_tier01_top1':2},
        'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in packet.iterdir() if p.is_file()}}
    (packet/'VERIFICATION.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ['status','testB_stored_rows','testB_stored_rfids','lead_peak_checks','nonmissing_preceding_time_slots','template_id_set_matches','template_id_order_matches','baseline_csv_header_matches_template_verbatim','observed_stored_first_hour','observed_stored_last_hour']},ensure_ascii=False))


if __name__=='__main__':main()
