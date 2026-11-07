# Round8 extraction and rule implementation notes

## Scope and execution status

Requested execution configuration: **GPT-6 Luna, xhigh**. This work implements the geometry extractor and frozen B0/S/G rule API, plus synthetic checks and the coordinator-authorized geometry extraction. It read the R4 canonical ledger, R3 gear registry, month caches, and six raw CSVs for geometry extraction; it did not read event/accident labels or run score evaluation/training. No hardware or field measurement is involved.

The extraction CLI requires explicit paths for the R4 canonical ledger, R3 gear registry, six month-cache parquet files, six raw CSVs, and a new `--output-dir`. Existing output directories are refused. The runner integration should read `runtime_receipt.json` and `output_manifest.json`; it must require `status=complete`, zero errors/mismatches, 99,677 output rows, and `release_ready_for_scoring=true` before it loads the geometry ledger.

## Extraction behavior

- Reads only the canonical numeric fields `rfid_id,ts,source_ordinal,len_m,bbox_m,cen_lon,cen_lat,score`; requires exactly 99,677 rows, 82 RFIDs, and unique `(rfid_id,ts)` and `source_ordinal` keys.
- Uses monthly row counts from parquet metadata to compute offsets, then confirms the six values against `[497942,479290,657292,717294,761846,773405]`. A source ordinal maps to the corresponding month and zero-based data-record index after the CSV header.
- Scans each local CSV independently using `csv.reader(encoding='utf-8-sig', newline='')`, checks the first five header fields and full data-record count, and parses only `row[3]`. It checks file size/mtime before and after the read, hashes raw files in 1 MiB byte chunks, compares month 1/5/6 with the recorded R7 hashes, and reports newly observed month 2/3/4 hashes without implying an old-hash match.
- The raw `rfid_id`, `part_dt`, and `rfid_time` are checked against the canonical row. Per `TIME_INTERFACE_ADDENDUM.md`, the integer source clock is `naive YYYYMMDD hours since 1970-01-01 + rfid_time`; it is not converted to UTC or KST. The actual timezone is unknown.
- Each target cache row is looked up from projected columns by `row_index`. Raw/cache date and hour, cache/canonical numeric values, and reconstructed raw/cache point count, length, bbox, and center are compared. Tolerances are `1e-4 m` for length/bbox and `1e-7 degrees` for centers. Every target parse/key/cache mismatch is streamed to `mismatch_registry.jsonl`; the receipt retains an error count and the first 100 global error examples.
- Geometry parts remain independent. Each part uses original point order and records point count, exact distinct finite coordinate count, path length, first-to-last displacement, D/L, finite-coordinate validity, eligibility and reason. Eligibility requires finite points, at least three unique coordinates, positive path length, and finite D/L within `[-1e-9,1+1e-9]` before clamping. The longest eligible part wins; exact ties choose the smaller original index. No eligible part remains an explicit row state.
- A SQLite disk spool preserves canonical row order while bounds Python memory; Arrow output is written in 4,096-row batches with an explicit nullable schema. The spool avoids keeping a 99,677-row output dictionary list. Per-gear descriptive output includes counts, range, mean and D/L decile counts; it makes no normality or accident claim.
- `runtime_receipt.json` records current RAM preflight, observed jobs, row/error counts, process RSS/peak working set when the platform exposes it, timings, source-clock caveat, hashes and release status. `output_manifest.json` records code/input/output hashes and R7 source references.

Geometry source reference: `testB/final/round_007_20261106/run_round7.py`, SHA-256 `19ad0ff9d630bccdf3195971a4919817284da331e24ad41c67c485613a2f6282`. The copied haversine/geometry parser was itself attributed in R7 to `run_remeasure_20261031.py`, SHA-256 `5579c35ba5ca204ff54281515e0907db57edb31eeaa5b45aafacec0fc75b0d0c`. Haversine radius is 6,371,000 m. Coordinates are treated as the upstream longitude/latitude values; exact CRS remains unknown.

## Rule API

`shape_rules.build_shape_rules(frame, gear_registry) -> {ledger, predictions, pool_manifest, diagnostics, stage_spec}` consumes a canonical-plus-geometry pandas frame and R3 gear registry. It rejects event/label-like columns, null keys, non-integer source-clock hours, duplicate RFID/hour keys, and duplicate registry RFIDs; it preserves the input row order. It uses a per-vessel rolling `[t-720,t)` shape-history sweep with compressed-value Fenwick trees and daily counts, avoiding all-history rescans. History eligibility is at least 24 valid s2 rows and at least three `floor(ts/24)` source-clock dates.

Own rarity uses the exact midrank CDF and `1-2*min(p,1-p)` without rounding. Peer rarity is computed by applying that same statistic to the current candidate shape against each eligible same-single-code vessel's own prior history, then averaging equally across eligible vessels. Peers are based on history at the same query hour and do not require a peer's current row. B0/fallback legacy rank is descending; S/G rank rarity descending, legacy descending on ties, then timestamp and ordinal ascending. Stages, shared `min(4,G actual pool size)` cap, score kinds and peer tie-activation diagnostics follow the frozen Round8 contract.

## Synthetic evidence

`extract_checks.json` and `shape_checks.json` were generated only from synthetic values. The Arrow writer fixture verifies a one-row file and a null-first/valid-second two-row file: exactly-once row count, key order and preservation of the later numeric D/L. No production parquet/CSV or label source was opened.

RAM checks before the small Arrow and pandas fixtures are recorded in the corresponding result JSON. Before actual extraction, available RAM was 3,484.44 MiB with one external Python service; threshold was 2,176 MiB (768 MiB extraction + 768 MiB overlap allowance + 640 MiB reserve). The extractor's own preflight immediately before heavy imports recorded 3,418.68 MiB and the same active service. The extractor now adds a conservative 768 MiB allowance per active external Python process and runs before importing PyArrow. No user process was terminated.

## Actual extraction receipt

The single released command completed at `testB/final/round_008_20261106/geometry_execution_001`. `runtime_receipt.json` reports `status=complete`, `rows_written=canonical_rows_expected=99,677`, `mismatch_count=0`, `error_count=0`, and `release_ready_for_scoring=true`; canonical roster validation required 82 unique RFIDs and unique RFID/hour keys. All six raw files matched cache metadata record counts `[497942,479290,657292,717294,761846,773405]`, and all selected raw RFID/date/hour and raw/cache/canonical geometry validations completed with zero errors.

Raw hashes for months 1, 5 and 6 matched the R7 expected SHA-256 values. Months 2, 3 and 4 were recorded as newly observed full-file SHA-256 values, with no prior expected hash comparison. The ledger has 99,677 rows and SHA-256 `2af19410a858dbc36f7b816c00b93adc19b8b33d5042cfa5a7c81fc82f756c9f`; the actual extractor SHA-256 is `a7a6ffed1319b8c75155df2935e11e3ab1c9f1de73f384563d5c6e99f1d1ffdb`. Runtime was 123.408 seconds, end RSS 287.24 MiB, and peak working set 293.72 MiB. `FINAL_CHECK_BINDING.json` binds the final synthetic receipts to the unchanged extractor and rules hashes.

## Known limitations

- Extraction validated the actual configured paths and zero mismatches for this run, but it does not establish event/anomaly utility. Actual evaluation remains gated by coordinator integration and a separate release.
- No event labels, predictions, scoring evaluation or training were used in the extraction run. This receipt releases the geometry artifact for later integration review, not scoring execution.
- The time-of-day source clock timezone and coordinate reference system remain unconfirmed. No elapsed speed, acceleration, port meaning, normality or operational cause is inferred.
