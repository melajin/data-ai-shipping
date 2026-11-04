import csv,json,time
from datetime import datetime,timezone
from pathlib import Path
OUT=Path.cwd()/'testB/round_001/input_compatibility'; began=time.perf_counter()
def stat(p):
 s=p.stat();return {'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}
def digest(p):
 import hashlib
 h=hashlib.sha256();n=0
 with p.open('rb') as f:
  while True:
   b=f.read(4*1024*1024)
   if not b:break
   h.update(b);n+=len(b)
 return h.hexdigest(),n
summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
if summary.get('status')!='succeeded':raise SystemExit('runner summary is not succeeded')
with (OUT/'csv_identity.csv').open(encoding='utf-8-sig',newline='') as f: csvrows=list(csv.DictReader(f))
wbdata=json.loads((OUT/'workbook_comparison.json').read_text(encoding='utf-8'))
verify=summary.get('old_input_posthash_verification') or []
if not verify:
 for row in csvrows:
  p=Path(row['old_exact_path']); b=row['old_meta_before']; a=row['old_meta_after']; mid=stat(p); dh,n=digest(p); end=stat(p)
  verify.append({'path':str(p),'comparison_sha256':row['old_sha256'],'post_sha256':dh,'comparison_bytes':int(row['old_stream_bytes']),'post_bytes':n,'comparison_hash_matches_post':row['old_sha256']==dh,'metadata_before_comparison':b,'metadata_after_comparison':a,'metadata_before_posthash':mid,'metadata_after_posthash':end,'metadata_unchanged_through_posthash':b==a==mid==end})
 for wb in summary['xlsx_results']:
  p=Path(wb['old_path']); expected=next((x['old_sha256'] for x in summary['xlsx_member_stream_results'] if x['member']==wb['member']),None); dh,n=digest(p); verify.append({'path':str(p),'comparison_sha256':expected,'post_sha256':dh,'comparison_hash_matches_post':expected==dh,'post_bytes':n,'post_metadata':stat(p)})
summary['old_input_posthash_verification']=verify;summary['old_inputs_posthash_all_match']=all(x['comparison_hash_matches_post'] for x in verify)
summary['finalizer_started_utc']=datetime.now(timezone.utc).isoformat()
sample=wbdata['workbooks'][1]; old_s={x['title']:x for x in sample['old_snapshot']['sheets']};new_s={x['title']:x for x in sample['new_snapshot']['sheets']}
def ids(sh):return [str(sh['cells'].get(f'A{r}',{}).get('value')) for r in range(2,102)]
idinfo={}
for title in old_s:
 oi=ids(old_s[title]);ni=ids(new_s[title]);idinfo[title]={'old_count':len(oi),'new_count':len(ni),'sequence_equal':oi==ni,'common_unique_count':len(set(oi)&set(ni)),'old_unique_count':len(set(oi)),'new_unique_count':len(set(ni)),'old_unique_not_new':sorted(set(oi)-set(ni)),'new_unique_not_old':sorted(set(ni)-set(oi)),'old_first_10':oi[:10],'new_first_10':ni[:10]}
summary['test_id_sequence_summary']=idinfo
summary['finalizer_elapsed_seconds']=round(time.perf_counter()-began,3)
summary['actual_exit_code']=int((OUT/'exit_status.txt').read_text().strip())
summary['runner_started_utc']=(OUT/'started_utc.txt').read_text(encoding='utf-8-sig').strip();summary['runner_finished_utc']=(OUT/'finished_utc.txt').read_text(encoding='utf-8-sig').strip()
summary['runner_code_sha256']=digest(OUT/'run_comparison.py')[0];summary['finalizer_code_sha256']=digest(OUT/'finalize_outputs.py')[0]
headers=[]
for c in 'ABCDEFGHI':
 x=old_s[list(old_s)[1]]['cells'].get(c+'1');headers.append((c, None if x is None else x['value']))
time_examples=[]
for c in ('B2','D2','F2','H2'):
 x=old_s[list(old_s)[1]]['cells'].get(c);time_examples.append((c,None if x is None else x['value'],None if x is None else x['number_format']))
lines=['# Input compatibility comparison (W0)','','Run status: **'+summary['status']+'**; captured runner exit code: **'+str(summary['actual_exit_code'])+'**.','Run interval UTC: '+summary['runner_started_utc']+' to '+summary['runner_finished_utc']+'; elapsed '+str(summary['elapsed_seconds'])+' seconds.','','## Scope and limits','','Read-only comparison of both v2 XLSX workbooks against the exact old paths mapped in the archive manifest, and SHA-256 streaming comparison of all 12 ZIP CSV members against paired old files. No workbook authoring/export, full archive extraction, or incident rematch was performed. These checks establish byte and workbook compatibility only; they do not establish cache lineage, code correctness, or detection performance.','','The raw archive SHA-256 was measured before and after the runner and is identical; archive size and modification metadata are unchanged. Every CSV and XLSX ZIP member was read to EOF; ZipExtFile CRC verification completed with no errors. A full `testzip()` pass was avoided because all regular file members were already consumed to EOF during the authorized comparisons. Old exact-path file hashes were re-read after comparison and checked against the comparison hashes; see `summary.json`.','','## Workbook findings','']
for w in summary['xlsx_results']:lines.append('- **'+w['member']+'**: '+str(w['cell_or_structure_difference_count'])+' logical cell/structure differences; byte-identical per intake manifest: '+str(w['manifest_byte_identical_to_old'])+'; differing package parts: '+str(w['zip_package_difference_count'])+'.')
acc=summary['xlsx_results'][0];lines += ['', 'The incident workbook SHA evidence in intake reports byte identity with the old exact-path file. Its extracted v2 reference and old workbook also have identical logical snapshots. The 167-incident matching was not rerun.','','### Submission sample','','Sheets remain ordered '+', '.join('`'+t+'`' for t in sample['new_snapshot']['sheet_order'])+' and visible. Dimensions remain `A1:C101` and `A1:I101`, with 100 data records on each sheet. All 100 IDs changed in column A rows 2–101 on each sheet; ID sequence and list differences are summarized in `summary.json`, and each changed cell is in `workbook_cell_differences.csv`. IDs remain text values with number format `@`.','','Test B header values by column (H1 is blank): '+', '.join(f'{c}1={v!r}' for c,v in headers)+'.','Example time cells: '+', '.join(f'{c}={v!r} (number format {fmt!r})' for c,v,fmt in time_examples)+'. These time examples are stored as text; time columns B/D/F/H and score/result columns C/E/G/I have unchanged content, types, and cell formats.','','No per-cell effective style differences were found: font, alignment, fill, border, protection, and number format are unchanged. The old workbook has explicit column widths in Test A column B and Test B columns B–I; v2 has no explicit column dimensions on these sheets, so effective widths may differ because defaults apply. This is a layout difference, not a cell style-ID difference.','','Five package XML parts differ: `docProps/core.xml`, `xl/sharedStrings.xml`, `xl/workbook.xml`, `xl/worksheets/sheet1.xml`, and `xl/worksheets/sheet2.xml`. Core properties have changed created/modified timestamps; shared strings reflect changed IDs; worksheet XML contains ID and column-dimension changes. Workbook XML also changes absolute source path, document UUID, and window state. Thus package differences are not only save metadata: IDs and explicit widths changed, while time/result fields and logical workbook structure remain stable.','','The comparison covered sheet order/visibility, dimensions, instantiated or styled cells, formulas/types, effective cell styles, merged ranges, row/column dimensions and hidden flags, freeze panes, data validation, conditional formatting, defined names, print settings/areas/titles/margins, and print options. Except for the explicit column widths and ID cell values, no such structural or style differences were found.','','## CSV content identity','','| # | ZIP member | new/old bytes | SHA-256 identical | CRC through EOF | seconds |','|---:|---|---:|:---:|:---:|---:|']
for r in csvrows:lines.append(f"| {r['index']} | `{r['zip_member']}` | {r['new_stream_bytes']}/{r['old_stream_bytes']} | {r['content_identical']} | {r['zip_crc_checked_to_eof']} | {r['elapsed_seconds']} |")
lines += ['',f"All {summary['csv_summary']['count']} pairs were byte-identical by SHA-256; total uncompressed bytes on each side: {summary['csv_summary']['total_new_bytes']:,}. Old-file posthashes matched comparison hashes: {summary['old_inputs_posthash_all_match']}.",'','## Reproducibility and artifacts','',f"- Python {summary['python']} on {summary['platform']}; openpyxl {summary['openpyxl']}; chunk size 4 MiB.",f"- Runner SHA-256: `{summary['runner_code_sha256']}`.",f"- Finalizer SHA-256: `{summary['finalizer_code_sha256']}`.",'- Runner stdout, stderr, actual exit code, and start/finish times are retained in this folder.','- This is input compatibility evidence only; it does not verify cache lineage, application correctness, model performance, or hardware behavior.','']
(OUT/'comparison_report.md').write_text('\n'.join(lines),encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
artifacts=[]
for p in sorted(OUT.iterdir()):
 if p.is_file() and p.name not in ('manifest.json','finalizer_stdout.log','finalizer_stderr.log','finalizer_exit_status.txt'):artifacts.append({'path':str(p.relative_to(Path.cwd())),'bytes':p.stat().st_size,'sha256':digest(p)[0]})
manifest={'run_started_utc':summary['runner_started_utc'],'run_finished_utc':summary['runner_finished_utc'],'actual_exit_code':summary['actual_exit_code'],'status':summary['status'],'runner_code_sha256':summary['runner_code_sha256'],'finalizer_code_sha256':summary['finalizer_code_sha256'],'inputs':{'archive':summary['archive_path'],'archive_sha256_before':summary['archive_sha256_before'],'archive_sha256_after':summary['archive_sha256_after'],'archive_unchanged':summary['archive_unchanged_by_hash'],'intake_manifest_sha256':summary['input_manifest_sha256'],'old_inputs_posthash_all_match':summary['old_inputs_posthash_all_match'],'old_inputs':verify},'artifacts':artifacts}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'status':summary['status'],'actual_exit_code':summary['actual_exit_code'],'csv':summary['csv_summary'],'old_inputs_posthash_all_match':summary['old_inputs_posthash_all_match'],'report':str(OUT/'comparison_report.md')},ensure_ascii=False))
