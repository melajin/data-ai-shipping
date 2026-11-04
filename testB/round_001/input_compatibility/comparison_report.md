# Input compatibility comparison (W0)

Run status: **succeeded**; captured runner exit code: **0**.
Run interval UTC: 2026-11-04T17:50:34.0045175Z to 2026-11-04T17:52:03.5621088Z; elapsed 88.079 seconds.

## Scope and limits

Read-only comparison of both v2 XLSX workbooks against the exact old paths mapped in the archive manifest, and SHA-256 streaming comparison of all 12 ZIP CSV members against paired old files. No workbook authoring/export, full archive extraction, or incident rematch was performed. These checks establish byte and workbook compatibility only; they do not establish cache lineage, code correctness, or detection performance.

The raw archive SHA-256 was measured before and after the runner and is identical; archive size and modification metadata are unchanged. Every CSV and XLSX ZIP member was read to EOF; ZipExtFile CRC verification completed with no errors. A full `testzip()` pass was avoided because all regular file members were already consumed to EOF during the authorized comparisons. Old exact-path file hashes were re-read after comparison and checked against the comparison hashes; see `summary.json`.

## Workbook findings

- **26년 1~6월 어선 사고현황(테스트 데이터).xlsx**: 0 logical cell/structure differences; byte-identical per intake manifest: True; differing package parts: 0.
- **테스트셋 및 결과제출 샘플/제출샘플.xlsx**: 202 logical cell/structure differences; byte-identical per intake manifest: False; differing package parts: 5.

The incident workbook SHA evidence in intake reports byte identity with the old exact-path file. Its extracted v2 reference and old workbook also have identical logical snapshots. The 167-incident matching was not rerun.

### Submission sample

Sheets remain ordered `테스트A`, `테스트B` and visible. Dimensions remain `A1:C101` and `A1:I101`, with 100 data records on each sheet. All 100 IDs changed in column A rows 2–101 on each sheet; ID sequence and list differences are summarized in `summary.json`, and each changed cell is in `workbook_cell_differences.csv`. IDs remain text values with number format `@`.

Test B header values by column (H1 is blank): A1='rfid_id', B1='사고시각', C1='이상항적 점수', D1='시각1', E1='시각1 이상항적 점수', F1='시각2', G1='시각2 이상항적 점수', H1=None, I1='시각3 이상항적 점수'.
Example time cells: B2='20251027 10' (number format '@'), D2='20251027 07' (number format '@'), F2='20251027 08' (number format '@'), H2='20251027 09' (number format '@'). These time examples are stored as text; time columns B/D/F/H and score/result columns C/E/G/I have unchanged content, types, and cell formats.

No per-cell effective style differences were found: font, alignment, fill, border, protection, and number format are unchanged. The old workbook has explicit column widths in Test A column B and Test B columns B–I; v2 has no explicit column dimensions on these sheets, so effective widths may differ because defaults apply. This is a layout difference, not a cell style-ID difference.

Five package XML parts differ: `docProps/core.xml`, `xl/sharedStrings.xml`, `xl/workbook.xml`, `xl/worksheets/sheet1.xml`, and `xl/worksheets/sheet2.xml`. Core properties have changed created/modified timestamps; shared strings reflect changed IDs; worksheet XML contains ID and column-dimension changes. Workbook XML also changes absolute source path, document UUID, and window state. Thus package differences are not only save metadata: IDs and explicit widths changed, while time/result fields and logical workbook structure remain stable.

The comparison covered sheet order/visibility, dimensions, instantiated or styled cells, formulas/types, effective cell styles, merged ranges, row/column dimensions and hidden flags, freeze panes, data validation, conditional formatting, defined names, print settings/areas/titles/margins, and print options. Except for the explicit column widths and ID cell values, no such structural or style differences were found.

## CSV content identity

| # | ZIP member | new/old bytes | SHA-256 identical | CRC through EOF | seconds |
|---:|---|---:|:---:|:---:|---:|
| 1 | `vpass_26년(1월_6월) 데이터/vpass_1월_6월 데이터/vpass_1월 데이터.csv` | 669416109/669416109 | True | True | 4.598 |
| 2 | `vpass_26년(1월_6월) 데이터/vpass_1월_6월 데이터/vpass_2월 데이터.csv` | 635512252/635512252 | True | True | 4.094 |
| 3 | `vpass_26년(1월_6월) 데이터/vpass_1월_6월 데이터/vpass_3월 데이터.csv` | 987693693/987693693 | True | True | 5.129 |
| 4 | `vpass_26년(1월_6월) 데이터/vpass_1월_6월 데이터/vpass_4월 데이터.csv` | 1113299125/1113299125 | True | True | 5.889 |
| 5 | `vpass_26년(1월_6월) 데이터/vpass_1월_6월 데이터/vpass_5월 데이터.csv` | 1201889964/1201889964 | True | True | 7.346 |
| 6 | `vpass_26년(1월_6월) 데이터/vpass_1월_6월 데이터/vpass_6월 데이터.csv` | 1255966524/1255966524 | True | True | 7.662 |
| 7 | `테스트셋 및 결과제출 샘플/테스트셋/vpass_1월 데이터.csv` | 1032427516/1032427516 | True | True | 6.472 |
| 8 | `테스트셋 및 결과제출 샘플/테스트셋/vpass_2월 데이터.csv` | 795028305/795028305 | True | True | 4.865 |
| 9 | `테스트셋 및 결과제출 샘플/테스트셋/vpass_3월 데이터.csv` | 1115652054/1115652054 | True | True | 7.05 |
| 10 | `테스트셋 및 결과제출 샘플/테스트셋/vpass_4월 데이터.csv` | 1339299305/1339299305 | True | True | 8.706 |
| 11 | `테스트셋 및 결과제출 샘플/테스트셋/vpass_5월 데이터.csv` | 1581199983/1581199983 | True | True | 10.05 |
| 12 | `테스트셋 및 결과제출 샘플/테스트셋/vpass_6월 데이터.csv` | 1621873318/1621873318 | True | True | 10.242 |

All 12 pairs were byte-identical by SHA-256; total uncompressed bytes on each side: 13,349,258,148. Old-file posthashes matched comparison hashes: True.

## Reproducibility and artifacts

- Python 3.13.3 (tags/v3.13.3:6280bb5, Apr  8 2025, 14:47:33) [MSC v.1943 64 bit (AMD64)] on Windows-11-10.0.26300-SP0; openpyxl 3.1.5; chunk size 4 MiB.
- Runner SHA-256: `5a5dce6e36a267b02f1779813ff30d82e33544a409ecfdcc7a9b4d2c62c8459a`.
- Finalizer SHA-256: `7d39eb7ad6fdcdd744f70dd9d6cc3f8fedb1284bdfd717ae967438c090f1b5ee`.
- Runner stdout, stderr, actual exit code, and start/finish times are retained in this folder.
- This is input compatibility evidence only; it does not verify cache lineage, application correctness, model performance, or hardware behavior.
