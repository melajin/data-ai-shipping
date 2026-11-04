import csv, hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import openpyxl
ROOT=Path.cwd(); OUT=ROOT/'testB/round_001/input_compatibility'; started=time.perf_counter()
def meta(p):
 s=p.stat();return {'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}
def sha(p):
 h=hashlib.sha256();n=0
 with p.open('rb') as f:
  while True:
   b=f.read(4*1024*1024)
   if not b:break
   h.update(b);n+=len(b)
 return h.hexdigest(),n
summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
if summary.get('status')!='succeeded': raise SystemExit('comparison run summary is not succeeded')
with (OUT/'csv_identity.csv').open(encoding='utf-8-sig',newline='') as f: csvrows=list(csv.DictReader(f))
wbdata=json.loads((OUT/'workbook_comparison.json').read_text(encoding='utf-8'))
# Verify every old exact-path file after comparison. The identity hash is the hash observed during the matching stream comparison.
verify=[]
for row in csvrows:
 p=Path(row['old_exact_path']); before=row['old_meta_before']; after_compare=row['old_meta_after']; final_before=meta(p); digest,n=sha(p); final_after=meta(p)
 verify.append({'path':str(p),'comparison_sha256':row['old_sha256'],'post_sha256':digest,'comparison_bytes':int(row['old_stream_bytes']),'post_bytes':n,'comparison_hash_matches_post':row['old_sha256']==digest,'metadata_before_comparison':before,'metadata_after_comparison':after_compare,'metadata_before_posthash':final_before,'metadata_after_posthash':final_after,'metadata_unchanged_through_posthash':before==after_compare==final_before==final_after})
for wb in summary['xlsx_results']:
 p=Path(wb['old_path']); expected=next((x['old_sha256'] for x in summary['xlsx_member_stream_results'] if x['member']==wb['member']),None)
 d,n=sha(p); m=meta(p)
 verify.append({'path':str(p),'comparison_sha256':expected,'post_sha256':d,'comparison_hash_matches_post':expected==d,'post_bytes':n,'post_metadata':m})
summary['old_input_posthash_verification']=verify
summary['old_inputs_posthash_all_match']=all(x['comparison_hash_matches_post'] for x in verify)
summary['finalizer_started_utc']=datetime.now(timezone.utc).isoformat()
# Test B details for report
sample=next(x for x in wbdata['workbooks'] if '????.xlsx' in x['member'])
old_s={x['title']:x for x in sample['old_snapshot']['sheets']}; new_s={x['title']:x for x in sample['new_snapshot']['sheets']}
def id_list(sheet): return [str(sheet['cells'].get(f'A{r}',{}).get('value')) for r in range(2,102)]
ids={}
for title in old_s:
 oi=id_list(old_s[title]);ni=id_list(new_s[title]);
 ids[title]={'old_count':len(oi),'new_count':len(ni),'sequence_equal':oi==ni,'common_unique_count':len(set(oi)&set(ni)),'old_unique_count':len(set(oi)),'new_unique_count':len(set(ni)),'old_unique_not_new':sorted(set(oi)-set(ni)),'new_unique_not_old':sorted(set(ni)-set(oi)),'old_first_10':oi[:10],'new_first_10':ni[:10]}
summary['test_id_sequence_summary']=ids
summary['finalizer_elapsed_seconds']=round(time.perf_counter()-started,3)
summary['actual_exit_code']=int((OUT/'exit_status.txt').read_text().strip())
summary['runner_started_utc']=(OUT/'started_utc.txt').read_text(encoding='utf-8-sig').strip()
summary['runner_finished_utc']=(OUT/'finished_utc.txt').read_text(encoding='utf-8-sig').strip()
summary['runner_code_sha256']=sha(OUT/'run_comparison.py')[0]
summary['finalizer_code_sha256']=sha(OUT/'finalize_outputs.py')[0]
# report
lines=['# Input compatibility comparison (W0)','',f"Run status: **{summary['status']}**; captured runner exit code: **{summary['actual_exit_code']}**.",f"Run interval (UTC): {summary['runner_started_utc']} to {summary['runner_finished_utc']}; runner elapsed {summary['elapsed_seconds']} s.",'','## Scope and limits','', 'Read-only comparison of the two v2 XLSX workbooks against manifest-mapped old files, and SHA-256 streaming comparison of all 12 v2 ZIP CSV members against their exact old paths. No workbook authoring/export, extraction of the full archive, or 167-case incident rematch was performed. These checks establish workbook/CSV input compatibility only; they do not establish cache lineage, code correctness, or detection performance.','', 'The archive-level SHA-256 was measured before and after the run; the SHA-256 is identical and archive metadata is unchanged. Each CSV member was streamed to EOF and compared bytewise by SHA-256 with its paired old file; its old-file metadata was sampled before and after the comparison. Old-file hashes were then re-read after the comparison and compared with the matching stream hashes. ZIP member CRC checks complete only when ZipExtFile reaches EOF; all 12 CSV plus two workbook members reached EOF without CRC errors. A whole-archive `testzip()` pass was intentionally not run because every regular file member was already read to EOF during the authorized comparisons.','', '## Workbook findings','']
for w in summary['xlsx_results']:
 lines.append(f"- **{w['member']}**: {w['cell_or_structure_difference_count']} logical cell/structure differences; byte-identical to old per intake manifest: {w['manifest_byte_identical_to_old']}; differing ZIP package members: {w['package_member_difference_count']}.")
acc=next(x for x in summary['xlsx_results'] if '?? ????' in x['member'])
lines += ['',f"The incident workbook was reported byte-identical to its old exact-path file by intake manifest SHA-256 ({acc['manifest_byte_identical_to_old']}); this task did not rerun the 167-incident matching. The extracted v2 reference and old workbook also have identical logical snapshots.",'', '### Submission sample: logical, semantic, and package differences','', 'Sheets remain ordered `???A`, `???B`, both visible. Dimensions remain `A1:C101` and `A1:I101`; 100 data records per sheet. Each sheet has 100 changed ID values in column A (rows 2?101), so ID list membership/order changed; see `workbook_cell_differences.csv` for every changed cell and `workbook_comparison.json` for full snapshots. The IDs are stored as text with number format `@`; first-ten old/new lists and set differences are in `summary.json`.','', 'The Test B header is unchanged: A1 `rfid_id`, B1 `????`, C1 `???? ??`, D1 `??1`, E1 `??1 ???? ??`, F1 `??2`, G1 `??2 ???? ??`, H1 blank, and I1 `??3 ???? ??`. The H1 blank is intentionally captured as blank; H2 contains the third time example. Example times B2/D2/F2/H2 are text (`20251027 10`, `20251027 07`, `20251027 08`, `20251027 09`) with `@` number format, unchanged. The score-result columns C/E/G/I and the B/D/F/H time columns retain the same values, types, and cell formatting; only the IDs changed in cell contents.','', 'Valid per-cell style components (font, alignment, fill, border, protection, number format) are unchanged for the compared sample cells. No cell-level style/format changes were found. The old file has explicit column widths on B for Test A and B?I for Test B; the v2 workbook has no explicit column-dimension entries on those sheets, so displayed widths can differ through defaults. This is a layout difference, not a difference in cell style IDs.','', 'At package level, five XLSX ZIP parts differ: `docProps/core.xml`, `xl/sharedStrings.xml`, `xl/workbook.xml`, `xl/worksheets/sheet1.xml`, and `xl/worksheets/sheet2.xml`. Core properties differ in created/modified timestamps; shared strings reflect changed IDs; worksheet XML contains ID and column-dimension changes. `workbook.xml` includes a changed absolute path/document UUID/window state metadata. Thus the package delta is not merely save metadata: the ID list and explicit column widths changed, while result/time fields and logical workbook structure described above remained stable.','', 'The requested structural audit also compared sheet visibility/order, dimensions, all instantiated or styled cells, formulas and value types, effective style components, merges, row/column dimensions and hidden flags, freeze panes, data validation, conditional formatting, defined names, page setup/margins, print areas/titles, and print options. No differences were found in the listed features except the explicit column dimensions; no defined-name, validation, conditional-format, merge, freeze, print-setting, row-height, hidden-state, or per-cell style differences were present.','', '## CSV content identity','', '| # | ZIP member | bytes (new/old) | SHA-256 equal | CRC through EOF | seconds |','|---:|---|---:|:---:|:---:|---:|']
for r in csvrows: lines.append(f"| {r['index']} | `{r['zip_member']}` | {r['new_stream_bytes']}/{r['old_stream_bytes']} | {r['content_identical']} | {r['zip_crc_checked_to_eof']} | {r['elapsed_seconds']} |")
lines += ['',f"All {summary['csv_summary']['count']} CSV pairs were byte-identical by SHA-256 ({summary['csv_summary']['total_new_bytes']:,} bytes each side in aggregate). Post-comparison old-file hashes matched their comparison hashes: {summary['old_inputs_posthash_all_match']}. Per-file old/new digests, sizes, paths, and metadata checks are in `csv_identity.csv` and `summary.json`.",'','## Reproducibility and artifacts','',f"- Python {summary['python']} on {summary['platform']}; openpyxl {summary['openpyxl']}; chunk size 4 MiB.",f"- Runner SHA-256: `{summary['runner_code_sha256']}`; finalizer SHA-256: `{summary['finalizer_code_sha256']}`.",'- Actual runner stdout/stderr and exit capture are `stdout.log`, `stderr.log`, and `exit_status.txt`; `stderr.log` is empty for the successful final run.','- This report is generated after successful comparison; the hashes and execution times are summarized in `summary.json` and `manifest.json`.','']
(OUT/'comparison_report.md').write_text('\n'.join(lines),encoding='utf-8')
# Refresh final hashes including report, stdout/stderr/status and all result files.
artifacts=[]
for p in sorted(OUT.iterdir()):
 if p.is_file() and p.name!='manifest.json': artifacts.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)[0]})
manifest={'run_started_utc':summary['runner_started_utc'],'run_finished_utc':summary['runner_finished_utc'],'actual_exit_code':summary['actual_exit_code'],'status':summary['status'],'runner_code_sha256':summary['runner_code_sha256'],'finalizer_code_sha256':summary['finalizer_code_sha256'],'inputs':{'archive':summary['archive_path'],'archive_sha256_before':summary['archive_sha256_before'],'archive_sha256_after':summary['archive_sha256_after'],'archive_unchanged':summary['archive_unchanged_by_hash'],'intake_manifest_sha256':summary['input_manifest_sha256'],'old_input_posthash_all_match':summary['old_inputs_posthash_all_match'],'old_inputs':verify},'artifacts':artifacts}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'status':summary['status'],'actual_exit_code':summary['actual_exit_code'],'csv_identical':summary['csv_summary'],'old_inputs_posthash_all_match':summary['old_inputs_posthash_all_match'],'report':str(OUT/'comparison_report.md')},ensure_ascii=False))
