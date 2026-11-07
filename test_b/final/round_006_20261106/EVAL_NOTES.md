# Round 6 Evaluation and Runner Notes — Gemini Owner

## 1. System Architecture and Ownership Boundaries

- **Gemini scope**: `evaluate_duration.py`, `run_duration.py`, `check_duration_eval.py`, `eval_checks.json`, `EVAL_NOTES.md`.
- **Luna scope**: `duration_rules.py`, `check_duration_rules.py`, `rule_checks.json`, `RULE_NOTES.md`.
- **Coordinator / Root scope**: Final execution of integrated pipeline on full dev dataset once both worker implementations are settled.
- **Strict boundary**: No dev parquets or TestB test sets are loaded during worker verification. Verification is performed strictly on small deterministic synthetic fixtures.

## 2. Integration Addendum 01 & Implementation Fixes

Per `INTEGRATION_ADDENDUM_01.md` and `FIX_GEMINI_INTEGRATION.md`:
1. **Preserved Byte-Exact Originals**:
   - `implementation_fixes/evaluate_duration_before.py` (SHA256: `792832fb11c75b36d33c1e4cd5821746919b1792fba2b9cc0c83af05dc45a9de`)
   - `implementation_fixes/run_duration_before.py` (SHA256: `ff940cad03410ef5af592561eb9fbc0ab5b94b7cfaef3653bec850e214bb9661`)
   - Preserved in `implementation_fixes/gemini_before.sha256.json`.
2. **Strict Epoch-Hour Conversion (`to_epoch_hour`)**:
   - Removed the heuristic treating `Timestamp.value < 1e9` as raw hour count.
   - Numeric inputs convert directly as integer hours; non-integer fractional hours raise `ValueError`.
   - `pd.Timestamp` values must be strictly hour-aligned (`ns % 3_600_000_000_000 == 0`). Wrongly interpreted nanosecond timestamps (such as `pd.Timestamp(24)`) and non-aligned timestamps raise `ValueError`.
   - Selected prediction timestamps with `pd.NaT` raise `ValueError`.
   - Censored `close_ts` in `run_registry` permits `pd.NaT` with `allow_nat=True`, preserving right-censored semantics.
   - Standard 2026 timestamps map directly and cleanly to integer epoch hours (e.g. `2026-06-27 15:00:00` $\to$ `495159`).
3. **Pre-Label Frozen Predictions Persistence**:
   - `run_duration.py` enforces code-level ordering:
     Immediately after `build_duration_rules`, the four rule artifacts (`predictions.csv`, `pool_manifest.csv`, `run_registry.csv`, `candidate_ledger.parquet`) are written to disk.
     The SHA-256 hash of `predictions.csv` and timestamp are recorded in `execution["frozen_predictions"]`.
     `devset_positives.csv` is read and parsed strictly **after** this persistence stage.

## 3. Generic Stage Specification and Status Tracking

- `evaluate_duration.py` consumes the generic `stage_spec` list of dictionaries rather than hardcoding stage names:
  - `stage_id`: `d0` through `d4`.
  - `mask_column`: `d0_ok` .. `d4_ok`.
  - `status_column`: `d0_status` .. `d4_status` (`keep`, `reject`, `defer`, `not_applicable`).
  - `reason_column`: `d0_reason` .. `d4_reason`.
- Missing and broken observation keys strictly record `defer` (`missing_previous_hour`, `invalid_geometry_ts_or_legacy_score`).
- Observations outside small criteria record `reject` (`observed_not_small`).
- Upstream ineligible records record `not_applicable` with reason `upstream_ineligible`, avoiding double-counting in downstream transitions.
- `_build_stage_counts(ledger, pool_manifest, stage_spec)` generates `stage_counts.csv` dynamically according to this schema.

## 4. Strict Cohort Separation and Operational Gate

To eliminate previous cohort mixing bugs:
- Random expectation pools are calculated and recorded separately for both:
  1. `all` scope (100 retrospective positive events).
  2. `tier01` scope (60 high-confidence retrospective positive events).
- Each scope maintains its own method-specific event probabilities and means for `B0`, `S`, and `G`.
- Combinatorial formula used:
  - `top1 = h / n` (if $n > 0$, else $0.0$).
  - `top4 = 1 - comb(n - h, kcap) / comb(n, kcap)` (if $n - h \ge kcap$, else $1.0$; $0.0$ if $n=0$ or $h=0$).
- **Four Operational Gate Conditions**:
  1. `tier01_top1_diff_g_vs_b0 >= 0.05` (+5.0 percentage points improvement).
  2. `tier01_top1_paired_bootstrap_ci95_lower > 0.0` (cluster bootstrap over RFIDs, $B=4000$, seed=20261105).
  3. `whole100_top1_non_worsening`: $G - B_0 \ge 0.0$ on all 100 events.
  4. `tier01_top1_exceeds_random`: Tier01 $G$ observed hit rate strictly exceeds **Tier01** $G$ actual-pool random expectation (never compared across cohorts).

## 5. Explanatory Run-Level Characteristics (No Ground-Truth Claims)

- **Label decoupling**: Predictions (`predictions.csv`), pool allocations (`pool_manifest.csv`), completed-run registry (`run_registry.csv`), and `candidate_ledger.parquet` are persisted to disk strictly before positive incident labels are parsed or joined.
- **Run length lower bounds**: Ongoing small sequences whose left boundary is not observed as valid non-small are explicitly marked with `current_L_is_lower_bound = True`. The fraction of such lower bounds is reported in `metrics.json` and `diagnostics.json`.
- **Reference run censoring**: The completed run registry records censor reasons (`left_censor_reason`, `right_censor_reason`) for runs cut off by data boundaries or observation gaps. Only runs with both observed non-small boundaries qualify as references.
- **Top-4 diversity**: Distinct run counts and temporal span (hours) across the selected top 4 predictions are reported per vessel and summarized per method as descriptive context.
- **No normal-truth claims**: Duration lengths, continuation filters, and peer CDF scores are candidate-ranking statistics only; they do not represent ground truth of normal vessel waiting or incident probabilities.

## 6. Memory Preflight, Overwrite Guard, and Execution Receipts

- `run_duration.py` enforces RAM preflight verification before heavy imports or parquet reads:
  - Estimated peak: 768 MiB.
  - System reserve: 640 MiB.
  - Total requirement: 1408 MiB.
  - Native OS query via `GlobalMemoryStatusEx` (Windows) / `/proc/meminfo` (Linux).
  - Top 15 process working set inventory recorded.
  - If available memory is below threshold, the runner safely exits with code 75 (`status: "memory_deferred"`).
- Overwrite protection: If `EXECUTION.json` exists in `execution_001` with `status: "complete"`, the runner immediately refuses overwrite and exits cleanly with code 0.
- Source and input tracking: Hashes (SHA-256) of input parquets, gear registries, positive labels, numerical helpers (`round_002_20261105/data_eval.py`), and all script sources are recorded in the atomic execution receipt.

## 7. Verification Results

All 8 independent contract checks pass deterministically:
- `python testB/final/round_006_20261106/check_duration_eval.py`
- Output: `testB/final/round_006_20261106/eval_checks.json` (`overall_status: "succeeded"`, 8/8 checks passed in 4.90s).
