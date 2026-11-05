# Bounded S2 readiness note

## Current gate state and recommendation

Manager reports Round023 stopped before the first model fit: available RAM was 2.465 GiB against the 2.5 GiB pre-fit guard; progress is 0/8 and no prediction artifacts exist. This is not an S1 performance result and does not trigger the plan's S1-failure branch. Keep model/feature variants and S2 execution paused while the manager prepares a resource-aware S1 recovery round. The manager's `next_resource_contract.json` sets the Round024 admission threshold at 4.5 GiB (= unchanged 2.5 GiB per-stage free guard + 1.5 GiB owned-job peak limit + 0.5 GiB reserve); the per-stage guard remains 2.5 GiB. The admission threshold is not a guarantee of future availability, and the contract is pending independent review. S2 remains a bounded alternative if a completed S1 gate meets the plan's failure condition. This note makes no claim that 0.7 is impossible.

## Recorded F156 and daily-source locations

Paths below come from `docs/20261105_CODEX_인계_0.7_실행계획.md` and `rounds/round_022/review/S1_PRECHECK_REVIEW.md`; this author did not open those data files or check their current existence.

- Read-only raw development source recorded by the plan: `F:\문제 데이터_수정_1027\vpass_26년(1월_6월) 데이터\vpass_1월_6월 데이터\`. Documented fields include `part_dt`, `rfid_id`, `rfid_time`, `geom`, and `fishing_code`. Any future scan needs a separate scope check so only authorized FIT vessels are materialized; do not read the adjacent Test2025 directory or non-FIT/holdout rows.
- Existing 304-column fold artifacts: `D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\fold_{0,1,2}_features.npz`. The plan lists `X(5897,304)`, `y`, `rfid_ids`, `roles`, `feature_names`, and `obs_days`; these are vessel-level summaries, not daily F156 sequences.
- Existing daily row-shard path recorded by the S1 precheck relative to the reviewed result root: `outputs\remeasure_20261031\rows_train_1..6.parquet`, produced through `run_remeasure_20261031.py`. The review warns that these shards include Train2026 vessels beyond development FIT; do not scan them wholesale. The exact full root and current file state were not verified here.
- Existing legacy F156/T5 cache pattern: `...\outputs\f156_merge\for_teammate\fold_{0,1,2}_t5.csv`. The S1 precheck says this cache cannot replace fold-local recomputation of label-based posterior features; it is not evidence that daily F156 rows are available in a CV-safe form.
- Recorded implementation chain: `D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과\tools\run_005_main_20261101.py` → `run_005_F156_merge_20261101.py` → `run_cycle4_3_featAC_20261101.py` / `run_remeasure_20261031.py`.

## Leakage controls and fit budget

The plan defines a segment as `(rfid_id, part_dt)`, with daily F156 values before percentile aggregation, that day's hour histogram, and S1 spatial posterior features. Vessel identity must define the split: all days from one vessel stay in one role. For FIT vessels, create segment probabilities by grouped five-fold out-of-fold prediction, so each vessel's labels are absent from the model generating its own aggregated features. INNER/OUTER segment probabilities use a segment model fitted on FIT only. During an internal four-fold FIT gate, rebuild all label-dependent S1 and S2 features inside each fold; features precomputed from all FIT labels would leak validation labels.

Assuming four gate folds, five grouped OOF segment models plus one fold-training segment model per fold, and one baseline plus one candidate vessel model per fold, the planned S2-only budget is `4 × (5 + 1 + 2) = 32` model fits. This count excludes feature construction/prediction passes and does not establish that 32 fits fit a given wall-clock budget. The plan sets segment-model threads to at most three and prohibits hyperparameter search.

## Preparation-first ticket

1. Before reading daily rows, inventory only the recorded source paths, hashes/manifests if available, schema, and FIT-only join contract. Resolve the full root of the relative `rows_train_1..6.parquet` path without opening the shards. Confirm the current manager's permitted data scope; the legacy cache path is not a substitute for that check.
2. If the manager explicitly authorizes the input, process one month/chunk at a time, filter to the exact authorized FIT vessel roster before materialization, and write fold-local intermediates. The plan estimates about 500,000 vessel-days and 120 MB for 500,000 × 60 float32 segment features; this is a planning estimate, not a measured peak for the full pipeline. LightGBM and intermediate peak RAM remain unknown.
3. Recheck available RAM immediately before any large read or fit. Use the reviewer-approved Round024 resource contract (4.5 GiB admission threshold; 2.5 GiB per-stage free guard), one job at a time, no polling loop, and no user-process termination. If the guard fails, defer while doing independent documentation/source-contract work.
4. Establish wall-clock cost from the approved resource contract or a separately authorized bounded pilot before committing to 32 fits. Keep the 30-minute Round023 compute ceiling from being silently assumed for a new round; no S2 training is authorized by this note.

## Unknowns

- Current existence, hashes, and usable daily F156 columns of the listed external sources were not checked.
- Whether the recorded `remeasure` shards can safely provide only FIT vessel-days under the current data boundary remains unresolved.
- Actual peak RAM and fit time for the nested 32-fit S2 procedure are unmeasured. No S2 code, raw data, holdout/Test material, or model output was read or produced here.
