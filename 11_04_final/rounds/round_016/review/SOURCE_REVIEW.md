# Round016 independent source review

## Verdict

**Not approved for execution.** The author froze the candidate sources at `2026-11-04T22:10:36.5027008Z`. Direct reviewer hashes at `2026-11-04T22:12:15.5609429Z` match the candidate manifest and write-stop ACK. The reviewed implementation contains a deadline-classification race in the process probe, which is the core Round016 control-layer gate. I did not create `approved_sources.json`; smoke, mock, and saved-audit modes were not run.

## Freeze evidence

Candidate manifest SHA-256: `43443b8628b6cb6ce831f01bbd5a823bccfadbc0b0a1525b8a2de6221f078b5a`.

Author ACK SHA-256: `45dc16fc164ae51869a2a8fcfd822d0f713296f38edd97a100e18c14c7971010`; `write_freeze=true`, no author runs, and the ACK binds the manifest hash and both source hashes.

| Frozen source | Bytes | Direct SHA-256 | Manifest/ACK match |
|---|---:|---|---|
| `rounds/round_016/code/saved_m4_audit.py` | 47,747 | `9d1ea2816a382b9c8134095543d504a1f21345b1decdbeff9692c13cf11edd18` | yes |
| `rounds/round_016/code/run_saved_m4_audit.ps1` | 18,841 | `f553e7aee06cd85acbc84cfc8a7c75a2e96f45b59c38c09837d383f5511752ac` | yes |

The exact two-source path set, schema identifiers, candidate-manifest hash, author-ACK hash, and source digests are consistent. The map was not created because source approval was withheld.

## Blocking source finding

In `Invoke-Probe`, after the wait loop the code checks `$p.HasExited` first and records `exitObservedBeforeCleanup=true`; it only records `deadlineReached=true` in the `elseif` path when the process is still running. A process that exits just after the configured deadline but before that final `HasExited` check can therefore be recorded as a normal exit with `actual_wait_deadline_reached=false`. That defeats the round's required separation of an actually elapsed deadline from an observed exit. Record whether the configured deadline elapsed independently, distinguish an exit observed before the deadline from one observed during cleanup, and retain the exit code without allowing a late exit to erase the timeout fact. The planned sleep-based probe does not cover this boundary race, and I did not execute it.

The owned-process identity helper also converts `CreationDate` through `ManagementDateTimeConverter` after stringifying it. If the CIM provider supplies a `DateTime` representation rather than a DMTF string, the catch path records `identity_check_failed` and fails closed. This is a portability risk that may cause a valid probe to fail; it was not dynamically checked.

## Static findings and limits

- The Python auditor uses bounded strict JSON handling with duplicate-key and non-finite rejection, preserves the empty root-module key, validates saved numeric assertions separately from provenance/history gates, and reads `.pt` inputs as opaque bytes. The static source contains no Torch/NumPy/TabICL imports or checkpoint load path.
- Round015 smoke/mock success and synthetic wrapper failure are distinct in the saved-audit logic. Round010 and Round015 historical false gates remain separate from new numeric/provenance outcomes.
- PowerShell uses `ProcessStartInfo`, finite wait arguments, stream tasks, RAM snapshots, before/after hashes and process-tree observation. The deadline race above remains a blocker even though these surrounding checks are present.
- I reviewed source and frozen metadata only. I did not rerun the author's PowerShell parser or Python AST checks, import the module, run candidate modes, load or hash any checkpoint, deserialize `.pt`, recalculate tensors, read actual project data, or evaluate F1/hardware. No runtime process/stream/tree behavior is established.
- Round016 execution is deferred. After an author fix, require a new freeze ACK, direct independent hashes and approved map, then manager-owned same-map smoke → mock → saved audit within the original finite budgets. Do not reuse this unapproved frozen set as an execution map.

