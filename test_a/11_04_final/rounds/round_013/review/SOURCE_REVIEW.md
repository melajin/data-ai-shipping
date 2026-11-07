# Round013 independent source review

## Verdict

**Approved for the bounded round013 process-control smoke, standard-library fixture mock, and one saved-evidence audit under the frozen approval map.** Approval is tied to `approved_sources.json` SHA-256 `ccb8ada4a66760bfd1a6ae970f395f47f779b9a1829d8011034a7964f624de26`. This is static source approval only. No smoke, mock, audit, Python test, model run, or saved-number recalculation was performed by this reviewer.

## Scope and evidence

The previous round012 approval was checked first. Its map SHA-256 is `b8e4e72b2cce5ee17535042a1fcd88e5c594a1cd9325f3a3dae81648e6def5ca`; the three source files still match its recorded hashes. The round012 candidate manifest direct hash is `6e283fef3a6c1fb93597f24f244e17565b3dc896dc2f0c124151cd77527972b1`.

The author freeze ACK is timestamped `2026-11-04T20:47:28.7293154Z`; it declares write-stop and no author runs. The round013 candidate manifest SHA-256 is `c5e9d2cf5b615447b06977dadbcd3a02c60848c57d826d2e59d2f79f2897e3d6`. I independently calculated the following final source hashes from disk and confirmed they match both the candidate manifest and freeze ACK:

| File | SHA-256 |
|---|---|
| `rounds/round_013/code/verify_frozen_run.py` | `6a10eee36bad5921e7a856eafc74f99b800970f82991eddaa218688f61f4c41e` |
| `rounds/round_013/code/test_verify_frozen_run.py` | `85ca95b500a2024801284aaf1c7a8d12aebfa5161ee5d2c20d4bb19e3e7b5f72` |
| `rounds/round_013/code/run_audit.ps1` | `be6614b1b523550ff9b16a7fc2db61db88504a088ff17e4b2b7396186200a782` |

I compared each frozen file to its round012 approved counterpart. Replacing only `round_013` with `round_012`, `round013` with `round012`, and `Invoke-Round013` with `Invoke-Round012` makes each file byte-for-byte text-equal to the approved source. The changes therefore only relocate fixture/temp/output/approval paths, update the round-specific schema and messages, and rename the runner function. The auditor remains bounded to source round010, keeps its approved-map checks and 1 MiB streaming hashes, excludes prohibited data assets, and preserves the fixed historical round010 overall gate as false. No round010 source, historical gate, audit calculation, or model logic was changed.

The new approval map contains exactly the three round013 executable source paths. It was created from independent direct disk hashes and rehashed after creation; its hash is recorded above. The candidate manifest is retained as freeze evidence, not added as executable approval-map content.

## Execution boundary and limitation

The runner retains the round012 ProcessStartInfo design, owned-process identity/cleanup, concurrent stdout/stderr draining, integer exit-code handling, bounded waits, and before/after source and approval-map checks. It snapshots the approved sources and gates audit on a completed mock with integer exit zero under the same map. The smoke-before-mock prerequisite is enforced by the manager-controlled exact sequence, not by the runner itself; the manager must preserve that external gate and stop after any failed stage.

Static approval does not demonstrate PowerShell runtime behavior, child exit values, stream draining, cleanup, fixture assertions, audit output, or saved-number integrity. On a failed smoke, do not launch mock or audit. Only after a successful smoke may the exact-map mock be attempted; only after its completed integer exit zero may the one audit attempt run. Do not change the approval map after execution begins.

No tests, Python process, runner mode, model, checkpoint, protected dataset, or numeric audit was executed by this reviewer. This review does not establish F1, independent/official performance, or hardware behavior. The historical round010 source-freeze failure remains false and cannot be repaired by current-source cleanliness.
