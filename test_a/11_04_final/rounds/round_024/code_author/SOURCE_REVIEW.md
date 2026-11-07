# Round024 source review — Luna xhigh

## Scope and limits

Static review of `code/run_gate.py`, `code/s1_features.py`, `code/t5_rebuild.py`, `code/prepare_t5_cache.py`, and `code_author/supplement_metrics.py`, against `ROUND_PLAN.md`, `manager/runtime_contract.json`, `manager/copied_inputs.json`, `configs/experiment.json`, and `manager/launch.py`. Also read the round handoff, project instructions, and prior `round_023/code_author/S2_READINESS.md` for the conditional ticket draft.

No Python code, tests, preparation, data scan, model fit, freeze, verifier, or metric calculation was run. No raw source, fold NPZ, holdout/Test rows, or prepared cache was opened. This is source inspection only; actual memory use, model output, runtime, and gate result remain unknown.

## Findings and edits

- The paired gate remains one `StratifiedKFold(4, shuffle=True, random_state=42)` pass over 3,144 FIT rows, with one baseline and one candidate fit per fold. The config fixes `threads=1`, `n_jobs=1`, 300 estimators, and the 8-fit/0-retry budget. The candidate gate is the conjunction `candidate >= 1833` and `candidate - matched baseline >= 16`; the 1,817 fixed reference is recorded separately.
- T5 is rebuilt once per CV fold from that fold's training indices and labels. Its manifest checks bind the cache to the 2026 FIT roster and assert no labels used in cache creation. The callback is deleted after the four small T5 fold matrices are built. In `t5_rebuild.py`, train-query self contributions are removed from both cell counts and the train-only prior; validation rows are absent from the fold label mapping.
- S1 receives only `train_idx` and `y[train_idx]`; the builder does not accept validation labels. For FIT queries present in the fold training set, it subtracts that vessel from cell counts and global prior. It builds the full period and each of six months sequentially, with one period's sparse profiles and count maps released before the next.
- Static memory-contract gap fixed in `code/run_gate.py`: the previous tuple loop held references to both `X_base` and `X_candidate` through the baseline fit. The gate now fits/saves baseline using `X_base` first; only on entering the candidate branch does it construct `X_candidate`, check its frozen 328-column shape, then delete `X_base` and collect before candidate fitting. The candidate's 304 base columns and appended 24 S1 columns retain the same order and values. Estimator parameters and the saved `feature_evidence` contract are unchanged. The loop still runs the same two variants for each of four folds.
- Static memory-contract gap fixed in `code/s1_features.py`: the last resolution's temporary `month_values` dictionary is now deleted before loading the next month. Its values have already been copied into `month_min`/`month_max`, so the resulting 24 features are unchanged.
- The launch wrapper statically sets OMP/OpenBLAS/MKL/NumExpr threads to one, uses `BELOW_NORMAL_PRIORITY_CLASS`, rejects concurrent Python jobs, checks 1.5 GiB entry RAM, and stops its owned process family above 0.75 GiB RSS or below 0.5 GiB available system RAM. The gate records 1.0 GiB stage checks. These are configured guards, not measured results from this review.
- `prepare_t5_cache.py` remains unchanged and was not run. Its source describes a bounded shared-harbor aggregate that reads unlabeled Test2025 geometry for that aggregate; this review did not access those rows or caches. Any new preparation/data access remains outside this task.
- `supplement_metrics.py` remains unchanged and is read-only by design after a completed eight-fit gate; it reads saved predictions and the approved fold0 NPZ roster/observation-day arrays. It was not run. Its stated prerequisite for independent verification is a manager workflow condition, not enforced by a verifier token in this script.

The fold0 NPZ loader reads the approved development artifact's arrays before selecting the FIT mask. The manager confirms that this artifact contains 5,897 development rows and no holdout/Test rows. The non-FIT development arrays are not passed to feature builders or model fitting; this full-array NPZ materialization is a known memory/data-access limitation. This review did not open the artifact.

## Changed files and hashes

Only the two source changes above were made by this reviewer. No other worker edits were reverted.

| File | SHA-256 after review |
|---|---|
| `code/run_gate.py` | `1179e95cf81314be9d686a894c633c1f26592013c79970614597b36811848737` |
| `code/s1_features.py` | `6ea7177382a2151508364f8fa14bbe0c087483e42373b98fc362065b0dd14c0a` |
| `code/t5_rebuild.py` | `6b1e252928d4174f569b4225299fa7a62094f1f0f1ac6a9d92708d2fae418a16` |
| `code/prepare_t5_cache.py` | `98c4c52a36dd9bb6f289aac0705e9f031d12ff4463e193153b98844a8ab3876e` |
| `code_author/supplement_metrics.py` | `f107c4929463502aa56dec4008b37ffcaec7ab1e099f3153b01df10884ed8ff1` |

The unchanged `code/t5_rebuild.py` hash matches the recorded low-memory patch hash. The unchanged `code/prepare_t5_cache.py` and `code_author/supplement_metrics.py` hashes match their copied-input hashes. The edited files' copied pre-review low-memory hashes recorded in `manager/copied_inputs.json` are `code/run_gate.py`: `ebf3d2c35aad300c8a0c34ad0e6cc36b7488926714fc76969d6114c0d45c516b` and `code/s1_features.py`: `b357123d2d859b0852fda535453392346a0aee4b4978e58ee9098f7748951b54`. Their current hashes differ only due to the documented edits. No approval/freeze hash was created here.

## Unknowns and handoff

- No source execution or tests were requested or performed. Syntax/runtime behavior and semantic equivalence are not dynamically verified.
- The expected 0.5 GiB owned peak is a manager estimate, not a measured peak. Only the manager's bounded launch can establish actual RSS/free-RAM evidence.
- The existing profile cache's contents and provenance were not reopened; only the code's manifest checks were reviewed.
- Independent review must recalculate final hashes for all approval-listed files, inspect this two-file diff, and decide whether to approve. Do not freeze or launch based on this author review alone.
- Round024 result, gate outcome, `STATUS.json`, ledger, and final report remain untouched.
