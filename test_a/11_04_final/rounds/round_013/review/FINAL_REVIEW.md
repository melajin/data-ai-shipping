# Round013 independent final review

## Verdict

**The bounded round013 smoke, fixture mock, and saved-evidence audit completed successfully under the approved source map.** This establishes the recorded process behavior and the bounded saved-number check. The round010 current-source and historical overall gates remain false; round013 did not repair that source-freeze incident or produce a new model/F1 result.

## Execution evidence reviewed

I read the three round013 receipts, claims, stdout/stderr logs, and `artifacts/provenance_audit.json` directly from disk. The order is smoke → mock → audit, with one attempt each. No rerun was performed by this reviewer.

| Run | Recorded result | Duration | Key checks |
|---|---|---:|---|
| `smoke_01` | Wrapper exit 0 | 0.2565873 s | Two sequential children returned integer 0 and 7; expected stdout/stderr markers were present; both exits confirmed; no timeout or residual process. |
| `mock_01` | Child and wrapper exit 0 | 0.4048464 s | Standard-library fixture suite reported `Ran 2 tests ... OK`; no timeout or residual process. |
| `audit_01` | Child and wrapper exit 0 | 0.3333715 s | Audit completed and wrote the expected round013 artifact; no timeout or residual process. |

All receipts report `completed=true`, approval-map SHA unchanged before/after, all three live source prechecks and postchecks matching, all source snapshots and snapshot postchecks matching, stdout/stderr drained, owned process exited, and no owned residual. The observed start times preserve the required order. All three pre-run RAM records exceed the 0.5 GiB floor; no unrelated Python process was recorded before or after each stage. No retry, timeout, or forced termination was recorded.

The smoke exercised normal exit-0 and exit-7 children. **The timeout/forced-cleanup branch was not dynamically exercised**, so its behavior remains supported by static review only.

## Saved-evidence audit

`provenance_audit.json` reports `source_round=round_010`, `executed_snapshot_matches_approved=true`, `saved_numeric_replay_passed=true`, `audit_integrity_passed=true`, and no issues. It also correctly reports `live_source_unchanged=false`, `current_source_gate=false`, and `historical_overall_gate=false`. The false live/current values refer to the already-recorded round010 wrapper drift; they do not conflict with the round013 source and approval-map hashes remaining unchanged during these runs.

The artifact describes a replay of the two saved 2×4 probability rows and selected saved reference values: max absolute difference `1.8446231598301388e-6` within the recorded `1e-4` tolerance, matching argmax, with exact float64 equality false. This is a saved-JSON check, not new inference, F1, or independent performance evidence. The audit records NPZ/checkpoint as not read or rehashed, raw/reference CSV as not read, and model runtime as not imported or run.

## Final hash check

Direct post-run hashes remain equal to the approved map and candidate freeze:

| File | SHA-256 |
|---|---|
| `rounds/round_013/code/verify_frozen_run.py` | `6a10eee36bad5921e7a856eafc74f99b800970f82991eddaa218688f61f4c41e` |
| `rounds/round_013/code/test_verify_frozen_run.py` | `85ca95b500a2024801284aaf1c7a8d12aebfa5161ee5d2c20d4bb19e3e7b5f72` |
| `rounds/round_013/code/run_audit.ps1` | `be6614b1b523550ff9b16a7fc2db61db88504a088ff17e4b2b7396186200a782` |
| `rounds/round_013/review/approved_sources.json` | `ccb8ada4a66760bfd1a6ae970f395f47f779b9a1829d8011034a7964f624de26` |

## Conditional Round014 draft

The `manager/NEXT_SUCCESS_DRAFT.md` remains explicitly conditional on round013 final review. Its round011 contract/evidence/review, round012 checklist, and referenced environment paths exist. It keeps new code, temporary files, logs, caches, and artifacts under round014; separates the synthetic head gate from real-data/F1 work; preserves the round010 historical failure; and requires a fresh source freeze and ordered smoke/mock before the bounded synthetic run. No scope or path correction is needed before promoting it after the manager completes the shared-state handoff. The draft is not approval to run M4 now; the future implementation still needs its own source review to resolve the exact Python child/runtime path and process-tree evidence.

No tests, runner, model, checkpoint, protected data, or numeric audit were executed by this reviewer. This review does not establish timeout-branch behavior, hardware behavior, F1, independent performance, or official score. The development baseline and 0.7 goal remain unchanged and unmet.
