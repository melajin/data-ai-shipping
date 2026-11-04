# Lineage audit diagnostic history

## Purpose

This note reconciles the audit's actual execution history with the final result metadata. It records only outcomes and edits visible in the working-session tool transcript. It does not reconstruct hashes, commands, timestamps, logs, or exit receipts that were not saved at launch.

**Eight successful executions of `audit_input_lineage.py` are visible in the transcript.** An intermediate result labeled the final execution as iteration 7 with six previous diagnostics. A later rerun happened after that counter was hard-coded, so the current `result.json` still says iteration 7 even though the transcript shows an eighth execution. The computation outputs stayed the same. Do not treat `audit_iteration` or `prior_diagnostic_run_count` as an accurate launch counter.

## Observed invocations

| Invocation | Change made before launch | Outcome visible in the session | Durable per-run evidence now present |
|---:|---|---|---|
| 1 | Initial bounded NPZ/name/role/label and saved-median audit. | `PASS_WITH_LIMITATIONS`; no mismatch reported. The summary counter reported three median comparisons because its count expression was wrong; the script had iterated seeds and folds. No transformed tensor hashes yet. | No per-run result snapshot, launch hash, stdout file, or explicit exit receipt retained. |
| 2 | Added P metadata, parent/training/preprocessor context and fold vocabulary checks. The first path-patching attempt hit a Windows/Korean-path encoding error; the subsequent script used directory globs and completed. | Successful output: 3/3 NPZ hashes, first-156 order, and roster/label checks; six median comparisons; no mismatch. Vocabulary FIT-ID hash checks were included. | No per-run result snapshot, launch hash, stdout file, or explicit exit receipt retained. |
| 3 | Added transformed 312-column float32 FIT and INNER-query hashes and wrote `run.log`. | `PASS_WITH_LIMITATIONS`; 12 transformed arrays hashed; explicit shell output showed exit code 0. Hashes used the NPZ/development-roster order. | The run log was later overwritten. Only the final log remains. |
| 4 | Added the audit script hash to the result's source hash inventory. | Same checks passed; explicit shell output showed exit code 0. | Earlier script hash/result/log snapshot was not retained. |
| 5 | Tightened the median gate to require metadata-name order, complete definitions, source/generator contracts, class order, NPZ hash, and vocabulary FIT-ID match. | Same checks passed; explicit shell output showed exit code 0. | Earlier source hashes/result/log snapshot was not retained. |
| 6 | Added the source-based limitation that P selects ordered `fit_ids` / `inner_ids`, and recorded the split-manifest path as the missing order evidence. Did not read that manifest. | Same checks passed; explicit shell output showed exit code 0. Original model context/query order remained unresolved. | Earlier result/log snapshot was not retained. |
| 7 | Added an explicit mismatch mapping for 304-vs-312 width, missing-flag settings conflict, original ID order, and unverified per-row F156 values. | Same checks passed; explicit shell output showed exit code 0. | The result still encoded the previous hard-coded run counter. Earlier result/log snapshot was not retained. |
| 8 | Updated the hard-coded run label to “final extended rerun 7” and reran the unchanged checks. | `PASS_WITH_LIMITATIONS`; explicit shell output showed exit code 0; final elapsed time recorded as 0.517 s. | Current `result.json` and `run.log` are from this last execution. The counter remains mislabeled as 7. |

## What the final files prove

- `result.json` contains the final observed check results, source/input hashes, transformed candidate tensor hashes, final command, script-recorded time, exit code, and final `run.log` hash.
- `run.log` contains only the last execution's stdout. Earlier stdout was overwritten, not archived.
- The final `audit_script` hash and source/input hashes were computed by the script during its last execution. They are **post-launch hashes**, not an independent pre-launch snapshot or manager launch receipt. They do not provide hashes for the seven earlier code states.
- Explicit shell output recorded exit code 0 for invocations 3 through 8. The first two displayed successful audit output, but no separate native exit-code receipt was saved. No per-invocation launch-time hash, command receipt, or log was retained for any run.
- No claim is made that earlier commands used byte-identical code or inputs. Their exact launch-time hashes are unavailable.

## Remaining limitation and safe continuation

For the original TabICL row sequence, the source uses `fold['fit_ids']` and `fold['inner_ids']`. The current candidate tensor hashes use roster order and cannot establish the original ordering. A later scoped audit may inspect only those ID arrays in `P/splits/splits_original.json`, after reviewing its schema; it must not load feature or protected label rows. No audit was rerun for this history correction.
