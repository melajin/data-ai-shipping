# Conditional S2 preparation ticket — draft only

**Status:** dormant. This draft is not an S2 authorization. The manager must first complete and independently verify the single Round024 run. A resource interruption, incomplete fit count, or failed verification is not an S1 numeric-gate miss. Only the manager's verified numeric-gate result decides whether this ticket is opened. This ticket authorizes **zero training fits**.

## Purpose

If Round024 completes and its verified S1 numeric gate misses, prepare a bounded source/readiness review for an S2 daily-F156 feature route. First establish the recorded source location, schema, and FIT-only source connection. Then, only if the manager confirms the data boundary, specify an exact 3,144-FIT, one-month/one-chunk extraction contract. Do not build a model or calculate S2 features in this ticket.

**Technical goal:** establish a traceable, FIT-only daily source and a low-memory extraction specification before any feature generation.

**Learning goal:** explain how `(vessel, day)` segments are grouped, why vessel identity defines folds, and how chunking limits memory without allowing a vessel's labels into its own generated training features.

## Recorded sources to resolve, not yet revalidated

The prior `round_023/code_author/S2_READINESS.md` records these paths and source claims. It explicitly says it did not open the daily data or establish current existence/schema; this ticket preserves that limitation.

- Raw development source recorded in the plan: `F:\문제 데이터_수정_1027\vpass_26년(1월_6월) 데이터\vpass_1월_6월 데이터\`.
- Daily shards recorded by the S1 precheck: `outputs\remeasure_20261031\rows_train_1..6.parquet`. The static Round024 cache builder points to `D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\분석 결과\outputs\remeasure_20261031`; this path connection and shard existence have not been confirmed against the filesystem or data.
- Previously documented raw fields include `part_dt`, `rfid_id`, `rfid_time`, `geom`, and `fishing_code`. Actual Parquet schema, units, partition semantics, row counts, and whether the recorded shards contain the needed daily F156 representation are unknown.
- FIT roster source recorded by the prior plan: approved fold0 feature NPZ, using `roles == FIT` and its ordered `rfid_ids`; expected contract is exactly 3,144 unique IDs. The gate's existing roster hash should be carried forward if S2 preparation is opened.
- Prior code lineage records `run_005_main_20261101.py` → `run_005_F156_merge_20261101.py` → `run_cycle4_3_featAC_20261101.py` / `run_remeasure_20261031.py`. This is a lead for static inspection, not proof that files exist or that the present source has the same schema.

## Preparation sequence

1. **Resolve metadata without opening rows.** Inspect only the recorded project notes, source code lineage, path existence, manifests, and directory/file metadata needed to resolve the full shard root. Do not read Parquet row data in this step. Record exact paths, hashes/manifests if available, and whether each source claim is confirmed or still unknown.
2. **Confirm authorization and schema scope.** Before any schema/data read, manager checks the current data boundary. If authorized, inspect schema only for the recorded Train2026 daily shards and approved FIT roster. Do not open holdout/Test shards or labels, predictions, individual holdout/Test features, or OUTER evaluation rows. Do not use a combined file unless the scan can filter the exact FIT IDs before row materialization and the manager confirms that predicate behavior.
3. **Write the extraction contract before reading rows.** For each month 1–6, process one shard/month at a time and one bounded record batch at a time. Project only fields necessary for the approved daily-segment features. Apply the 2026/month predicate and exact ordered FIT ID membership before Python materialization; verify every returned row has an authorized FIT ID and matching month. Group only as `(rfid_id, part_dt)`; record source hash, row counts, dropped-row reasons, schema, and FIT roster hash. Write intermediate outputs only inside the authorized round directory and release each chunk/month's arrays/maps before proceeding.
4. **Recheck resources immediately before any authorized large read.** Continue to use single-process, `threads=1`/`n_jobs=1`, OMP/OpenBLAS/MKL/NumExpr set to one, and Windows `BELOW_NORMAL_PRIORITY_CLASS`. Require at least 1.5 GiB available RAM before entry and 1.0 GiB before each stage; use 0.5 GiB as the expected owned peak, enforce a 0.75 GiB owned RSS cap, and stop if system free RAM falls below 0.5 GiB. These are resource constraints, not a claim that S2's peak fits them; measure owned RSS during any later authorized bounded pilot. Do not poll for RAM or terminate user processes.
5. **Stop at source readiness.** Deliver a source/schema/connectivity note, exact extraction pseudocode/contract, hashes, boundary evidence, memory estimate basis, and unknowns. Do not generate labels, join non-FIT rows, calculate F156 features, fit models, tune, score OUTER/holdout/Test, or extend to full 3-fold/S2 training.

## Required evidence and pass condition

The preparation ticket is complete only if the exact source path, monthly schema, source-to-FIT join, date/month parsing, authorized row filter, and output schema are backed by source metadata or manager-approved schema inspection. The 3,144 ordered FIT roster hash must be recorded. Any mismatch, mixed/ambiguous path, unavailable schema, inability to filter FIT before materialization, or insufficient RAM leaves preparation blocked for manager decision; do not substitute a guessed source or label.

Expected artifacts, if the manager opens the ticket, are a source/readiness report and an extraction contract under the authorized round directory. They contain no trained model and no performance result.

## Scope and unknowns

- This ticket has not checked file existence, schema, hashes, row counts, coordinates, dates, or memory requirements from the actual source data.
- The existing S1/legacy cache is not evidence that fold-local S2 daily features can be reconstructed without leakage.
- Prior S2 readiness estimated 32 fits for a different nested procedure; that is not a current budget or approval. This ticket authorizes 0 fits. Any later S2 training needs a separate manager plan with finite fit/time budgets and verified memory requirements.
- No conclusion about S2 feasibility or model performance is made here.
