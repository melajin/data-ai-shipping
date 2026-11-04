import csv, hashlib, json, os, platform, sys, time, traceback, zipfile
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
import openpyxl

ROOT = Path.cwd()
OUT = ROOT / 'testB/round_001/input_compatibility'
MANIFEST_PATH = ROOT / 'testB/intake/1103_v2/inspection_001/archive_manifest.json'
ZIP_PATH = next(Path(r'C:\Users\dlehs\Downloads').glob('*_1103_v2.zip'))


def utcnow(): return datetime.now(timezone.utc).isoformat()
def sha_stream(stream, chunk=4*1024*1024):
    h=hashlib.sha256(); n=0
    while True:
        b=stream.read(chunk)
        if not b: break
        n += len(b); h.update(b)
    return h.hexdigest(), n

def file_meta(p):
    s=p.stat()
    return {'path':str(p),'exists':True,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'mtime_utc':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat()}

def file_hash(p):
    with p.open('rb') as f: return sha_stream(f)

def effective_style(cell):
    s=cell._style
    def color(c):
        return None if c is None else {'type':c.type,'rgb':c.rgb,'indexed':c.indexed,'theme':c.theme,'tint':c.tint,'auto':c.auto}
    return {
      'font': {'name':cell.font.name,'sz':cell.font.sz,'b':cell.font.b,'i':cell.font.i,'u':cell.font.u,'strike':cell.font.strike,'vertAlign':cell.font.vertAlign,'charset':cell.font.charset,'family':cell.font.family,'scheme':cell.font.scheme,'color':color(cell.font.color), 'outline':cell.font.outline, 'shadow':cell.font.shadow, 'condense':cell.font.condense, 'extend':cell.font.extend},
      'alignment': {'horizontal':cell.alignment.horizontal,'vertical':cell.alignment.vertical,'text_rotation':cell.alignment.textRotation,'wrap_text':cell.alignment.wrapText,'shrink_to_fit':cell.alignment.shrinkToFit,'indent':cell.alignment.indent,'relativeIndent':cell.alignment.relativeIndent,'justifyLastLine':cell.alignment.justifyLastLine,'readingOrder':cell.alignment.readingOrder},
      'fill': {'fill_type':cell.fill.fill_type,'patternType':cell.fill.patternType,'fgColor':color(cell.fill.fgColor),'bgColor':color(cell.fill.bgColor), 'gradientType':getattr(cell.fill,'type',None)},
      'border': {side:({'style':getattr(cell.border,side).style,'color':color(getattr(cell.border,side).color)} if getattr(cell.border,side) is not None else None) for side in ['left','right','top','bottom','diagonal','vertical','horizontal'] } | {'diagonalUp':cell.border.diagonalUp,'diagonalDown':cell.border.diagonalDown,'outline':cell.border.outline},
      'protection': {'locked':cell.protection.locked,'hidden':cell.protection.hidden},
      'number_format':cell.number_format,
    }

def val_serial(v):
    if isinstance(v, (datetime,)): return {'datetime':v.isoformat()}
    if isinstance(v, bytes): return {'bytes_hex':v.hex()}
    return v

def cell_obj(c):
    return {'coordinate':c.coordinate,'value':val_serial(c.value),'data_type':c.data_type,'formula':c.value if isinstance(c.value,str) and c.value.startswith('=') else None,
      'number_format':c.number_format,'style':effective_style(c)}

def dimension_map(ws):
    rows={str(k):{'height':v.height,'hidden':v.hidden,'outlineLevel':v.outlineLevel,'collapsed':v.collapsed,'style':v.style,'thickTop':v.thickTop,'thickBot':v.thickBot} for k,v in ws.row_dimensions.items()}
    cols={str(k):{'width':v.width,'hidden':v.hidden,'bestFit':v.bestFit,'outlineLevel':v.outlineLevel,'collapsed':v.collapsed,'min':v.min,'max':v.max,'style':v.style} for k,v in ws.column_dimensions.items()}
    return rows,cols

def workbook_snapshot(path):
    wb=openpyxl.load_workbook(path, data_only=False, read_only=False)
    out={'path':str(path),'sheet_order':wb.sheetnames,'defined_names':{},'sheets':[]}
    for k,v in wb.defined_names.items():
        out['defined_names'][str(k)]={'attr_text':v.attr_text,'hidden':v.hidden,'function':v.function,'vbProcedure':v.vbProcedure,'xlm':v.xlm,'localSheetId':v.localSheetId,'functionGroupId':v.functionGroupId,'shortcutKey':v.shortcutKey,'publishToServer':v.publishToServer,'workbookParameter':v.workbookParameter}
    for ws in wb.worksheets:
        rows,cols=dimension_map(ws)
        cells={c.coordinate:cell_obj(c) for row in ws.iter_rows() for c in row if c.value is not None or c.has_style}
        dvs=[]
        for dv in ws.data_validations.dataValidation:
            dvs.append({'type':dv.type,'operator':dv.operator,'formula1':dv.formula1,'formula2':dv.formula2,'allow_blank':dv.allow_blank,'showDropDown':dv.showDropDown,'showInputMessage':dv.showInputMessage,'showErrorMessage':dv.showErrorMessage,'errorTitle':dv.errorTitle,'error':dv.error,'promptTitle':dv.promptTitle,'prompt':dv.prompt,'sqref':str(dv.sqref)})
        cfs=[]
        for cf in ws.conditional_formatting:
            rules=[]
            for rule in ws.conditional_formatting[cf]:
                rules.append({'type':rule.type,'priority':rule.priority,'stopIfTrue':rule.stopIfTrue,'operator':rule.operator,'formula':rule.formula,'dxf':str(rule.dxf) if rule.dxf else None})
            cfs.append({'sqref':str(cf.sqref),'rules':rules})
        ps=ws.page_setup
        page_setup={k:getattr(ps,k) for k in ['orientation','paperSize','scale','fitToWidth','fitToHeight','firstPageNumber','useFirstPageNumber','blackAndWhite','draft','horizontalDpi','verticalDpi','copies','pageOrder','usePrinterDefaults','errors']}
        margins={k:getattr(ws.page_margins,k) for k in ['left','right','top','bottom','header','footer']}
        print_options={k:getattr(ws.print_options,k) for k in ['horizontalCentered','verticalCentered','headings','gridLines']}
        sheet={'title':ws.title,'state':ws.sheet_state,'max_row':ws.max_row,'max_column':ws.max_column,'calculate_dimension':ws.calculate_dimension(),
          'cells':cells,'merged_ranges':sorted(str(x) for x in ws.merged_cells.ranges),'row_dimensions':rows,'column_dimensions':cols,
          'freeze_panes':str(ws.freeze_panes) if ws.freeze_panes else None,'sheet_view':{'showGridLines':ws.sheet_view.showGridLines,'zoomScale':ws.sheet_view.zoomScale,'zoomScaleNormal':ws.sheet_view.zoomScaleNormal,'rightToLeft':ws.sheet_view.rightToLeft},
          'data_validations':dvs,'conditional_formatting':cfs,'auto_filter':ws.auto_filter.ref,'print_area':str(ws.print_area) if ws.print_area else None,'print_title_rows':ws.print_title_rows,'print_title_cols':ws.print_title_cols,
          'page_setup':page_setup,'page_margins':margins,'print_options':print_options,'sheet_format':{'defaultRowHeight':ws.sheet_format.defaultRowHeight,'defaultColWidth':ws.sheet_format.defaultColWidth,'baseColWidth':ws.sheet_format.baseColWidth}}
        out['sheets'].append(sheet)
    return out

def norm(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def zip_member_diff(new,old):
    z1=zipfile.ZipFile(new); z2=zipfile.ZipFile(old)
    a={i.filename:i for i in z1.infolist()}; b={i.filename:i for i in z2.infolist()}
    results=[]
    for n in sorted(set(a)|set(b)):
        if n not in a or n not in b: results.append({'member':n,'status':'only_new' if n in a else 'only_old'}); continue
        with z1.open(n) as f1,z2.open(n) as f2:
            h1,s1=sha_stream(f1); h2,s2=sha_stream(f2)
        if h1!=h2 or s1!=s2: results.append({'member':n,'status':'content_diff','new_bytes':s1,'old_bytes':s2,'new_sha256':h1,'old_sha256':h2})
    z1.close();z2.close();return results

start_utc=utcnow(); t0=time.perf_counter(); run={'started_utc':start_utc,'script_path':str(OUT/'run_comparison.py'),'python':sys.version,'platform':platform.platform(),'openpyxl':openpyxl.__version__,'zipfile_crc_checked_on_eof':True,'status':'running','errors':[]}
try:
    manifest=json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    csv_entries=[e for e in manifest['entries'] if not e.get('is_directory') and str(e.get('name','')).lower().endswith('.csv')]
    xlsx_entries=[e for e in manifest['entries'] if not e.get('is_directory') and str(e.get('name','')).lower().endswith('.xlsx')]
    run['input_manifest_sha256']=hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    run['archive_path']=str(ZIP_PATH)
    run['archive_meta_before']=file_meta(ZIP_PATH)
    run['archive_sha256_before'],run['archive_hash_bytes_before']=file_hash(ZIP_PATH)
    run['old_files_meta_before']={e['old_exact_path']:file_meta(Path(e['old_exact_path'])) for e in csv_entries+xlsx_entries}
    with zipfile.ZipFile(ZIP_PATH,'r') as z:
        bad=None
        run['zip_testzip_result']='not_run_full_archive_scan_avoided'
        run['zip_testzip_note']='Each of the 12 CSV and 2 XLSX members is explicitly streamed to EOF; ZipExtFile verifies its CRC at EOF.'
        xlsx_stream_results=[]
        for e in xlsx_entries:
            t=time.perf_counter(); h=hashlib.sha256(); n=0
            with z.open(e['name'],'r') as zf:
                while True:
                    b=zf.read(4*1024*1024)
                    if not b: break
                    h.update(b); n+=len(b)
            old_path=Path(e['old_exact_path'])
            old_digest,old_n=file_hash(old_path)
            xlsx_stream_results.append({'member':e['name'],'new_stream_bytes':n,'old_stream_bytes':old_n,'new_sha256':h.hexdigest(),'old_sha256':old_digest,'content_identical':n==old_n and h.hexdigest()==old_digest,'zip_crc_checked_to_eof':True,'elapsed_seconds':round(time.perf_counter()-t,3)})
        # Workbooks: compare extracted new reference to manifest-mapped old exact workbook.
        wb_results=[]
        for e in xlsx_entries:
            new_path=Path(e['extracted_reference_path']); old_path=Path(e['old_exact_path'])
            # ZIP archive's original sample path can differ from extracted alias; use member stream bytes via temp-free in-memory? load from extracted manifest reference established at intake.
            ns=workbook_snapshot(new_path); osnap=workbook_snapshot(old_path)
            differences=[]
            if ns['sheet_order']!=osnap['sheet_order']:
                differences.append({'kind':'sheet_order','new':ns['sheet_order'],'old':osnap['sheet_order']})
            if ns['defined_names']!=osnap['defined_names']:
                differences.append({'kind':'defined_names','new':ns['defined_names'],'old':osnap['defined_names']})
            nsm={x['title']:x for x in ns['sheets']}; osm={x['title']:x for x in osnap['sheets']}
            all_diff=[]
            for title in sorted(set(nsm)|set(osm)):
                if title not in nsm or title not in osm:
                    all_diff.append({'sheet':title,'cell':'','difference':'sheet_presence','new':title in nsm,'old':title in osm});continue
                a=nsm[title];b=osm[title]
                for attr in ['state','max_row','max_column','calculate_dimension','merged_ranges','row_dimensions','column_dimensions','freeze_panes','sheet_view','data_validations','conditional_formatting','auto_filter','print_area','print_title_rows','print_title_cols','page_setup','page_margins','print_options','sheet_format']:
                    if norm(a[attr])!=norm(b[attr]): all_diff.append({'sheet':title,'cell':'','difference':attr,'new':a[attr],'old':b[attr]})
                for coord in sorted(set(a['cells'])|set(b['cells'])):
                    av=a['cells'].get(coord);bv=b['cells'].get(coord)
                    if norm(av)!=norm(bv):
                        all_diff.append({'sheet':title,'cell':coord,'difference':'cell','new':av,'old':bv})
            # convenient structure details emphasis via cell addresses and labels
            wb_results.append({'member':e['name'],'new_path':str(new_path),'old_path':str(old_path),'new_snapshot':ns,'old_snapshot':osnap,'differences':all_diff,'new_sha256':e.get('new_sha256'),'old_sha256':e.get('old_sha256'),'manifest_byte_identical_to_old':e.get('byte_identical_to_old')})
        # XLSX package member-level differences show bytes/package metadata vs logical workbook differences.
        xlsx_pkg=[]
        for e in xlsx_entries:
            xlsx_pkg.append({'member':e['name'],'package_member_differences':zip_member_diff(Path(e['extracted_reference_path']),Path(e['old_exact_path']))})
        # sequential CSV byte content compare: per member stream hashes in chunks; reaches EOF so zipfile performs CRC.
        csv_rows=[]
        for i,e in enumerate(csv_entries,1):
            t=time.perf_counter(); old=Path(e['old_exact_path']); old_before=file_meta(old)
            with z.open(e['name'],'r') as zf, old.open('rb') as of:
                hnew=hashlib.sha256(); hold=hashlib.sha256(); nnew=nold=0
                while True:
                    bn=zf.read(4*1024*1024)
                    bo=of.read(4*1024*1024)
                    if bn: hnew.update(bn);nnew+=len(bn)
                    if bo: hold.update(bo);nold+=len(bo)
                    if not bn and not bo: break
                # zf EOF consumed fully; ZipExtFile checks CRC before returning EOF / on close.
                crc_checked=True
            old_after=file_meta(old)
            row={'index':i,'zip_member':e['name'],'old_exact_path':str(old),'zip_uncompressed_bytes_manifest':e.get('uncompressed_bytes'),'zip_compressed_bytes_manifest':e.get('compressed_bytes'),'old_bytes_manifest':e.get('old_bytes'),'new_stream_bytes':nnew,'old_stream_bytes':nold,'new_sha256':hnew.hexdigest(),'old_sha256':hold.hexdigest(),'size_equal':nnew==nold,'sha256_equal':hnew.digest()==hold.digest(),'content_identical':nnew==nold and hnew.digest()==hold.digest(),'zip_crc_checked_to_eof':crc_checked,'old_meta_before':old_before,'old_meta_after':old_after,'old_metadata_unchanged':old_before==old_after,'elapsed_seconds':round(time.perf_counter()-t,3)}
            csv_rows.append(row)
            print(f"CSV {i}/{len(csv_entries)} {row['content_identical']} {nnew} bytes {row['elapsed_seconds']}s {e['name']}",flush=True)
    run['xlsx_member_stream_results']=xlsx_stream_results
    run['xlsx_results']=[]
    for wr in wb_results:
        run['xlsx_results'].append({'member':wr['member'],'new_path':wr['new_path'],'old_path':wr['old_path'],'cell_or_structure_difference_count':len(wr['differences']),'manifest_byte_identical_to_old':wr['manifest_byte_identical_to_old'],'zip_package_difference_count':next((len(x['package_member_differences']) for x in xlsx_pkg if x['member']==wr['member']),None)})
    run['archive_meta_after']=file_meta(ZIP_PATH)
    run['archive_sha256_after'],run['archive_hash_bytes_after']=file_hash(ZIP_PATH)
    run['archive_unchanged_by_hash']=run['archive_sha256_before']==run['archive_sha256_after']
    run['archive_metadata_unchanged']=run['archive_meta_before']==run['archive_meta_after']
    run['old_files_meta_after']={e['old_exact_path']:file_meta(Path(e['old_exact_path'])) for e in csv_entries+xlsx_entries}
    run['all_old_file_metadata_unchanged']=run['old_files_meta_before']==run['old_files_meta_after']
    run['csv_summary']={'count':len(csv_rows),'identical_count':sum(r['content_identical'] for r in csv_rows),'different_count':sum(not r['content_identical'] for r in csv_rows),'total_new_bytes':sum(r['new_stream_bytes'] for r in csv_rows),'total_old_bytes':sum(r['old_stream_bytes'] for r in csv_rows)}
    run['zip_crc_verified_all_csv_eof']=all(r['zip_crc_checked_to_eof'] for r in csv_rows)
    run['zip_crc_verified_all_file_members_eof']=run['zip_crc_verified_all_csv_eof'] and all(r['zip_crc_checked_to_eof'] for r in xlsx_stream_results)
    run['zip_testzip_result']='not_run_full_archive_scan_avoided'
    run['status']='succeeded' if not run['errors'] and bad is None else 'failed'
    # Write workbook difference CSV, retain header even empty.
    fields=['workbook_member','sheet','cell','difference','new','old']
    with (OUT/'workbook_cell_differences.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for wr in wb_results:
            for d in wr['differences']:
                w.writerow({'workbook_member':wr['member'],'sheet':d.get('sheet',''),'cell':d.get('cell',''),'difference':d.get('difference',d.get('kind','')),'new':json.dumps(d.get('new'),ensure_ascii=False,default=str),'old':json.dumps(d.get('old'),ensure_ascii=False,default=str)})
    with (OUT/'csv_identity.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(csv_rows[0].keys()) if csv_rows else ['zip_member','old_exact_path','new_sha256','old_sha256','content_identical','elapsed_seconds']);w.writeheader();w.writerows(csv_rows)
    (OUT/'workbook_comparison.json').write_text(json.dumps({'workbooks':wb_results,'package_comparisons':xlsx_pkg},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    run['csv_results_file']=str(OUT/'csv_identity.csv');run['workbook_differences_file']=str(OUT/'workbook_cell_differences.csv');run['workbook_detail_file']=str(OUT/'workbook_comparison.json')
    run['finished_utc']=utcnow();run['elapsed_seconds']=round(time.perf_counter()-t0,3)
    (OUT/'summary.json').write_text(json.dumps(run,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    # detailed lineage manifest includes each artifact hash, excluding itself and mutable stdout/exit files
    artifacts=[]
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name not in ('manifest.json','stdout.log','stderr.log','exit_status.txt'):
            artifacts.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':file_hash(p)[0]})
    out_manifest={'run_started_utc':start_utc,'run_finished_utc':run['finished_utc'],'exit_code_intended':0 if run['status']=='succeeded' else 1,'status':run['status'],'artifacts':artifacts,'inputs':{'zip':run.get('archive_path'),'manifest':str(MANIFEST_PATH),'old_exact_paths':[e['old_exact_path'] for e in csv_entries+xlsx_entries]}}
    (OUT/'manifest.json').write_text(json.dumps(out_manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':run['status'],'summary':run['csv_summary'],'xlsx':run['xlsx_results'],'elapsed_seconds':run['elapsed_seconds'],'archive_unchanged':run['archive_unchanged_by_hash'],'old_metadata_unchanged':run['all_old_file_metadata_unchanged']},ensure_ascii=False),flush=True)
    sys.exit(0 if run['status']=='succeeded' else 1)
except Exception as ex:
    run['status']='failed';run['errors'].append({'exception':repr(ex),'traceback':traceback.format_exc()})
    run['finished_utc']=utcnow();run['elapsed_seconds']=round(time.perf_counter()-t0,3)
    (OUT/'summary.json').write_text(json.dumps(run,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(traceback.format_exc(),file=sys.stderr,flush=True)
    sys.exit(1)

