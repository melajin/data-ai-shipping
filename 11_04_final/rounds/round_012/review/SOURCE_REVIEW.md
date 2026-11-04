# Round012 independent source review

## Verdict

**Approved for the bounded round012 process-control smoke, pure standard-library fixture mock, and one saved-evidence audit.** Approval is tied to `approved_sources.json` SHA-256 `b8e4e72b2cce5ee17535042a1fcd88e5c594a1cd9325f3a3dae81648e6def5ca`. This is static source approval only. No smoke, mock, audit, Python test, model run, or saved-number recalculation was performed by this reviewer.

## Scope and evidence

Reviewed the author-frozen files after the 2026-11-04 20:38:41 UTC candidate ACK:

| File | SHA-256 |
|---|---|
| `rounds/round_012/code/verify_frozen_run.py` | `832b4d0627ea508dbcf40a970c9e5daffd2b93b822d19db968ac37f9fc99331b` |
| `rounds/round_012/code/test_verify_frozen_run.py` | `72d3d43ad677e739b52a128702921c27d2559a9f1d52e818ac4f1a64b312641a` |
| `rounds/round_012/code/run_audit.ps1` | `c446991ab85167693057afcde11417bba7ebe2360577358ee050c2d9692177d3` |

The author candidate manifest was independently rehashed as `6e283fef3a6c1fb93597f24f244e17565b3dc896dc2f0c124151cd77527972b1`; its executable-source hashes matched the frozen files. I created `approved_sources.json` by calculating the three hashes directly from disk. A second direct disk hash after map creation matched all three values above. The manifest is documented as evidence but is not an executable entry in the approved map. The requested reviewer configuration is Luna/xhigh/fork-none; the host session record is host-reported evidence, not internal model attestation.

## Findings

- `run_audit.ps1` uses `ProcessStartInfo` and retains the launched `Process` handle. It records PID and process creation time, starts both `ReadToEndAsync` drains before waiting, bounds mock/audit child wait to 28 seconds plus up to 2 seconds cleanup, and records the raw `ExitCode` only when it is an `Int32`. A missing or non-Int32 exit value cannot become zero. Timeout cleanup targets the owned process; residual identity requires PID plus creation time and fails closed when identity is unknown.
- The smoke branch launches explicit exit-0 and exit-7 Python children sequentially, checks integer child codes and stdout/stderr markers, and rejects timeout, undrained output, failed termination confirmation, or a residual process. The runner returns its own wrapper result separately from each child exit. The smoke receipt is source-code-approved but not yet observed.
- The runner validates the approved map schema and exact three-file path set; rehashes live sources before and after; snapshots all three approved files; checks snapshot hashes; preserves the approval-map hash before/after; creates a new claim with `CreateNew`; and gates audit launch on a completed mock whose exit is integer zero under the same map. `Get-MapChecks` returns the individual check entries and the caller captures them as an array, avoiding the nested-array ambiguity identified before freeze.
- The runner uses Windows PowerShell 5.1/.NET Framework-compatible `ProcessStartInfo.Arguments`, CRT-style argument quoting, and `EnvironmentVariables`; it does not rely on `ArgumentList`, `.Environment`, or `Kill(entireProcessTree)` overloads. The smoke/mock/audit receipt and stdout/stderr logs, source snapshots, claims, and temporary files are rooted under round012. Audit output is fixed to `rounds/round_012/artifacts/provenance_audit.json`.
- `verify_frozen_run.py` imports only the Python standard library and streams SHA-256 in 1 MiB blocks. It is restricted to source round010; excludes array/table, checkpoint, raw/reference/holdout assets before hash/open; reads saved receipts, incident/postcheck metadata, saved results/probabilities, and selected reference JSON rows; and does not import model packages or launch subprocesses.
- Snapshot integrity, live/current source status, saved numeric replay, audit integrity, and historical overall outcome are separate. The historical round010 overall gate is fixed to `false`; a clean current tree cannot repair that historical failure. Numeric tolerance and float64 exact equality remain separate results. NPZ/checkpoint bytes are declared unverified.
- The copied fixture tests synthesize a temporary round010 tree under `rounds/round_012/temp`. The clean-live fixture preserves historical failure; the live-wrapper-drift fixture keeps launch snapshot and numeric integrity true while current-source status becomes false. The assertions were read statically and have not been executed.

## Limits and pending evidence

No source-level blocker was found for the bounded scope. The approved map establishes only which code bytes may be run. Actual PowerShell API behavior, process exit values, output draining, cleanup/residual state, mock assertions, and generated audit fields remain unverified until the authorized sequential runs produce receipts. The configured base Python runtime was not launched or version-queried during this review; the auditor uses `str | None` and `Path.is_relative_to`, so the mock must confirm that the configured runtime supports these APIs. Initial host resource evidence records 4.1446 GiB available at 20:26:06 UTC and an estimated 100 MiB stdlib hashing peak plus 200 MiB worker-document overhead; this is not a measured peak or a fresh pre-run reading.

This review does not load a checkpoint, open NPZ/reference CSV/raw/OUTER/holdout data, run inference, calculate F1, verify hardware, or change round010's historical result. If the exit-0/exit-7 smoke fails, stop before mock and audit. If the exact-map mock fails, stop before audit. The saved-evidence audit is one attempt with no retry. A successful saved audit establishes bounded provenance checks only, not model performance or M4 integration.

## Post-approval execution status

Source approval was recorded at 2026-11-04 20:41 UTC. The manager's execution guard reached the 20:42 UTC experiment cutoff before starting `smoke_01`; the manager reports process/claim count zero. A read-only check found no directories, receipts, or claims for `smoke_01`, `mock_01`, `mock_02`, or `audit_01`. Rehashing the three frozen code files and the approved map still matched the recorded hashes. Dynamic process-control, mock, and audit evidence is therefore absent; the source approval did not pass any run gate.
