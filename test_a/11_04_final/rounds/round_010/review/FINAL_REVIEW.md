# Round010 final independent review

## Verdict

**The saved two-query INNER probability replay passes its stated numeric gates, but round010 does not pass the complete approved-run gate.** A post-freeze edit changed the live wrapper after the approved mock and pilot launch. The child completed and its saved probabilities agree with the frozen reference within tolerance; the wrapper/source-freeze checks correctly fail. Keep these conclusions separate.

## Evidence reviewed

Read-only review of `artifacts/result.json`, `artifacts/pilot_01/pilot_result.json`, `artifacts/pilot_01/progress.jsonl`, the mock and pilot receipts/snapshots, `review/approved_sources.json`, and `review/INCIDENT_REVIEW.md`. The saved JSON records are the source for the result facts below. I independently recomputed row-wise maximum absolute differences and probability row-sum errors from the two saved probability/reference rows using PowerShell. I did not run code, tests, a mock, or a model; import PyTorch; read raw input arrays, holdout data, or the original reference file; or inspect labels.

## Child execution and numeric replay

- Child result is `PILOT_COMPLETE`; checkpoint/context fit returned, `predict_proba` completed once, and the three temporary managers were restored. Saved input and shuffle-state fingerprints match before and after prediction.
- Scope is exactly frozen INNER IDs `36001915` and `31703435`, comparing their four `p0..p3` values. Both rows have matching argmax (classes 0 and 1 respectively). Independently recomputed maximum absolute differences are `2.6026283017621665e-7` and `1.8446231598301388e-6`; overall `1.8446231598301388e-6` is below the `1e-4` tolerance. The maximum float64 probability row-sum error is `5.541369318962097e-8`, below `1e-5`. **Exact numeric equality is false.**
- The saved input contract is 3,144 fit rows x 312 features plus two query rows; ICL receives all 3,146 rows and 3,144 training labels. Instrumentation records 8 COL calls / 112 completed column chunks, 8 ROW calls / 3,152 completed row chunks, and 8 completed ICL forwards. The final row chunk contains the two query rows; no truncation is recorded.
- These are two fixed-row replay checks, not F1, generalization, production performance, or a claim that the model goal was achieved. The saved result reports no inner-label use, F1 calculation, training, holdout read, or outer inference.

## Run limits and provenance failure

- Manager result: 215.485 seconds against the 480-second cap; pilot resource sampling completed; owned process tree is clear. Preflight available RAM was 4.5623 GiB and minimum observed available RAM was 3.3008 GiB (above the 1.5 GiB stop floor); sampled process-tree peak working set was 1,265,553,408 bytes. These are measurements from this run, not a future resource guarantee.
- The exact-map mock passed in 0.281 seconds with exit 0 before pilot launch. Its wrapper snapshot matched approved SHA-256 `c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210`.
- After freeze/launch, the live wrapper changed to SHA-256 `c1d595c94641e81c1e930a216a448013709fd58050cc32d5e31d84251df38867`. The pilot used its approved `c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210` snapshot, but the live post-run wrapper no longer matched. The run receipt therefore reports `wrapper_unchanged=false`; manager checks report `wrapper_completed=false`, `sources_unchanged=false`, and `all_execution_gates_passed=false`. The child exit was 0, while the bounded wrapper command exited 4 with status `failed_or_stopped` because of the wrapper drift; no stop reason or remaining owned process was reported.
- The edited branch was the early root-identity-capture-failure return path. Normal COL/ROW/ICL events and child completion show that branch was not reached. This limits its effect on the observed child output but does not cure the violated source-freeze/provenance gate.

## Disposition

Preserve the approved map and both wrapper versions/snapshots as evidence; do not rewrite hashes to make the run green and do not rerun the model as a continuation of round010. Record the result as `completed_numeric_replay_pass_source_freeze_violation`, not as a clean approved-run completion. For the next round, recover provenance first: audit the frozen contract and sources, enforce no edits after freeze, and require approved, mock-snapshot, prelaunch, and post-run hashes to agree before accepting a run. Any later model execution requires its own explicit gate.
