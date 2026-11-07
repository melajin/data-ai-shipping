# Round 028 worker source and provenance audit

Filesystem metadata audit: 2026-11-05 16:34 KST. Implementation and pilot status updated 2026-11-05 16:49 KST. This worker did not open or process source CSV contents. A manager-run 100-physical-line pilot later produced a small real-data contract check, recorded below; it is not a full-dataset extraction or model evaluation. No model was trained.

## Requested execution configuration

- Requested by task: GPT-6 Luna, effort ultra.
- Host limit reported in the task: Luna max; the work was assigned at max because ultra is unsupported.
- This report records the request and host limit; it does not claim that a project configuration file changed the parent session model.
- Resource policy for any later source read: one process, thread environment set to 1, Windows BelowNormal, entry RAM at least 1.5 GiB, month-step RAM at least 1.0 GiB, process RSS at most 0.75 GiB. The extractor records those gates to `resource_checks.json`; this worker did not run a source scan.

## Existing feature schema and duplication check

The fold 0 archive `D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\fold_0_features.npz` is 8,187,401 bytes. Only its compressed `feature_names` entry was read for this audit; it contained 304 ordered unique names. The 304 schema comprises 156 F156 columns, 68 behavior columns, 70 local-relative columns, and 10 T5 columns.

The 84 geometry-summary columns are 21 measures (`length_m`, `bbox_diagonal_m`, `endpoint_distance_m`, `straightness`, `turn_mean_rad`, `turn_p90_rad`, `turn_gt_pi2_fraction`, `linearity`, `area_m2`, `centroid_radius_m`, `max_step_m`, `point_count`, `component_count`, `compressed_point_count`, `repeat_fraction`, `mean_step_m`, `observed_turn_count`, `bbox_width_m`, `bbox_height_m`, `span_to_length`, `component_chord_sum_m`) each summarized across day `p10`, median, `p90`, and IQR. The remaining F156 groups include spatial occupancy, temporal-bin summaries, vocabulary statistics, and observation counts. The 68 behavior fields include coarse-grid revisitation and movement summaries; the 70 local-relative fields repeat that family under local reference context.

| New candidate | Existing nearby fields | Why the calculation is distinct |
|---|---|---|
| `turn_sign_reversal_fraction` | `turn_mean_rad__day_*`, `turn_p90_rad__day_*`, `turn_gt_pi2_fraction__day_*`, `observed_turn_count__day_*` | Existing fields summarize turn magnitudes/counts. The candidate counts direction-sign switches in the ordered within-part turn sequence after the fixed 15° filter. It does not connect turns across parts, rows, or days. |
| `nonlocal_return_vertex_fraction` | `rev_*`, `lr_rev_*`, `spatial_daily_grid_cells__*`, `grid_transition_rate` in Track2 | Existing revisitation/transition fields use grid cells and hourly/day centroid or aggregate sequences. The candidate asks whether a vertex returns within 100 m of a same-part prior vertex at least 500 m earlier along that part. The row-level vertex order is unavailable to those aggregates. |

The independent `fishing_demo/real_geometry_20261028.py` shape9 block also has turn-magnitude and global turn-direction concentration summaries, but that block is not in the 304 schema and global concentration does not encode consecutive sign reversals. It has no path-lagged within-part return fraction. This distinction is formula-level, not a claim that either candidate improves classification.

## Geometry source availability

The ordered coordinates are carried in each source CSV row's `geom` WKT `MULTILINESTRING`. The source description identifies `part_dt`, `rfid_id`, `rfid_time`, `geom`, and Train label `fishing_code`; X is longitude and Y is latitude. `rfid_time` is an hour band, not a timestamp for each WKT vertex. Exact EPSG/datum and point-level measurement times remain unconfirmed.

By contrast, the existing `s3_hourly.parquet` Track2 extractor (`11_04_final/rounds/round_026/track2_s2_segments/extract_segments.py`) selects `id`, `date`, `hour`, `cen_lon`, `cen_lat`, `stationary`, `gap_hours`, and `n_points`. It computes hourly/day centroid and cell summaries. That schema cannot reconstruct ordered within-part vertices or WKT and is not a source for these two features.

The file names and byte sizes below were read from filesystem metadata only on 2026-11-05. They do not establish that file contents, headers, or coordinate ranges were revalidated in this round.

| Source group | Relative monthly CSV | Size (bytes) | Round 028 status |
|---|---|---:|---|
| Train2026 | `vpass_1월 데이터.csv` | 669,416,109 | Metadata only; approved input group |
| Train2026 | `vpass_2월 데이터.csv` | 635,512,252 | Metadata only; approved input group |
| Train2026 | `vpass_3월 데이터.csv` | 987,693,693 | Metadata only; approved input group |
| Train2026 | `vpass_4월 데이터.csv` | 1,113,299,125 | Metadata only; approved input group |
| Train2026 | `vpass_5월 데이터.csv` | 1,201,889,964 | Metadata only; approved input group |
| Train2026 | `vpass_6월 데이터.csv` | 1,255,966,524 | Metadata only; approved input group |
| **Train2026 total** | **6 files** | **5,863,777,667** | **Approx. 5.46 GiB; no source data read** |
| 2025 serving/Test | `vpass_1월 데이터.csv` | 1,032,427,516 | Metadata only; excluded from this round |
| 2025 serving/Test | `vpass_2월 데이터.csv` | 795,028,305 | Metadata only; excluded from this round |
| 2025 serving/Test | `vpass_3월 데이터.csv` | 1,115,652,054 | Metadata only; excluded from this round |
| 2025 serving/Test | `vpass_4월 데이터.csv` | 1,339,299,305 | Metadata only; excluded from this round |
| 2025 serving/Test | `vpass_5월 데이터.csv` | 1,581,199,983 | Metadata only; excluded from this round |
| 2025 serving/Test | `vpass_6월 데이터.csv` | 1,621,873,318 | Metadata only; excluded from this round |
| **2025 serving/Test total** | **6 files** | **7,485,480,481** | **Approx. 6.97 GiB; no source data read** |

Full paths observed:

- Train2026: `F:\문제 데이터_수정_1027\vpass_26년(1월_6월) 데이터\vpass_1월_6월 데이터\`
- 2025 serving/Test: `F:\문제 데이터_수정_1027\테스트셋 및 결과제출 샘플\테스트셋\`

Prior project evidence describes the geometry row contract in `docs/real_support_evidence_20261028.md`, `docs/fishing_evaluation_cycle_results_20261028.md`, and `docs/real_model_cycle_protocol_20261028.md`. The workspace `26_11_4/README.md` confirms that `s3_hourly.parquet` is a vessel-day-hour aggregate. These documents are evidence about prior inspections; they are not new content reads of the source CSVs.

## Frozen formulas, units, and limits implemented

1. `turn_sign_reversal_fraction` = sign switches between adjacent retained within-part signed turns divided by adjacent retained-turn pairs. Retain turns with `abs(turn) >= 15°`. Collapse only exactly repeated adjacent coordinates; apply no distance simplification or epsilon. Angles are computed in local tangent coordinates from the declared longitude/latitude order. A zero denominator yields a blank feature and denominator 0.
2. `nonlocal_return_vertex_fraction` = same-part vertices that are within 100 m haversine distance of any earlier same-part vertex at least 500 m back along that part, divided by vertices with at least one eligible prior vertex. Distances use a spherical Earth-radius approximation. A zero denominator yields a blank feature and denominator 0.

Both metrics pool integer numerators and denominators across valid rows and parts for each vessel before division. They do not use fishing labels, predictions, vessel identity as a feature, dates, hour bins, or other vessels. They do not infer stop time, speed, acceleration, or operation. No pair crosses a part or row boundary.

Fail-closed input rules: strict 2D `MULTILINESTRING` only; explicit coordinate-order confirmation required by the API/CLI; WKT lon/lat range checks; empty/missing/malformed input recorded separately; any within-part adjacent segment above 10 km invalidates that row as a potential jump; more than 100,000 points or 16 MiB WKT characters rejects the whole row; more than 1,000,000 candidate haversine comparisons per source row rejects the whole row. No partial prefix from a limit-exceeded row is used. The point/character/comparison limits are computational guards, not tuned feature thresholds. The 10 km check is a data-quality guard and does not imply elapsed time or speed.

`coordinate_order_confirmed=True` is required to calculate. A later 100-line source-format pilot must precede full FIT extraction to check headers, numeric lon/lat range, row parsing, and part boundaries. This worker has not run that pilot. The 100 m/500 m thresholds remain design assumptions frozen by Round 028, not verified physical limits for either gear type.

## Extraction scope and output contract

The future `extract` mode resolves only the six fixed Train2026 month names under the recorded Train directory and filters WKT parsing to unique `roles == FIT` IDs from fold 0 (expected 3,144). It emits one row for every roster ID, including IDs with no matching source rows; missing features remain blank and counts are zero. Output columns include `rfid_id`, the two frozen feature names, integer numerators/denominators, rows seen, valid/missing/empty/invalid/truncated geometry counts, and a JSON reason-count field. The manifest records input sizes/modified times, selected columns, file row counts, limits, and scope flags without copying source WKT.

The `pilot` mode is restricted to the first Train CSV and at most 100 physical lines including the header. It writes `pilot_100_features.csv` plus its own manifest; it cannot overwrite `derived_features.csv` by default. `extract` writes `derived_features.csv` and `derived_features.manifest.json`, refuses existing outputs unless `--overwrite` is explicitly supplied, and writes only after all inputs are processed. Neither mode reads the 2025 serving/Test directory.

The first manager-side pilot command reached resource preflight but did not open a CSV. The recorded snapshot was 2.820 GiB available and 0.024 GiB process RSS; it stopped because the initial ctypes process-handle prototype failed to set BelowNormal. The handle/API prototypes were corrected to use a pointer-width Windows handle, and a synthetic regression test verifies the process priority call.

The manager then ran the source-format pilot at 2026-11-05 16:48:25 KST. It read exactly 100 physical lines from the first Train2026 file (one header plus 99 data rows), matched 50 rows to the 3,144-ID FIT roster, and skipped 49 non-roster rows before WKT parsing. The manager reported all 50 matched geometries valid. In those matched rows, 32 vessels had a positive turn denominator and 3 had a positive nonlocal-return denominator. The output contains 3,144 roster IDs, including absent IDs with blank features and zero counts. The manifest confirms only `rfid_id` and `geom` were used, no label values or predictions were read, no holdout/Test was read, and part boundaries were preserved. Numeric lon/lat range and geometry structure passed for this 50-row FIT subset; EPSG/datum remain unconfirmed. This pilot does not characterize the unscanned rows or the other five months.

Resource receipts for the successful pilot recorded entry availability 2.926 GiB / process RSS 0.025 GiB, before month 2.913 GiB / 0.035 GiB, and after month 2.904 GiB / 0.036 GiB; priority was BelowNormal, thread environment values were 1, and no other Python process was listed. Expected peak 0.50 GiB is an estimate, not a measured peak. The manager began the separate full FIT-only extraction after the pilot; this worker did not run that scan, and its final result belongs in the manager's execution record.

## Evidence status

| Work | Status |
|---|---|
| 304 names/size metadata review | Completed; feature-name entry only |
| Train/Test file name and size inventory | Completed; filesystem metadata only |
| Ordered geometry input contract | Located in prior project evidence; no source rows opened in this round |
| Synthetic parser/feature unit tests | 16/16 pass; synthetic fixtures only |
| Source-format pilot | Completed by manager on 99 data rows; 50 FIT matches, all valid; subset only |
| FIT feature extraction | Manager began a separate full scan after the pilot; this worker did not perform or independently verify it |
| Model training/evaluation | Not run |
