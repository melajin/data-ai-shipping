# Round018 independent final review

## Outcome

**Smoke failed; mock and saved-audit were not run.** The failure is confined to the final timeout probe's classification/provenance record. The three ordinary process probes passed. This does not invalidate the static source approval, but it fails the smoke gate, so the planned sequence stopped before mock and audit.

## Saved execution evidence

The manager launched `smoke_01` with approved map SHA-256 `bc586a48880da1e7942db80e2f2b58b2d236bd62fce9580508abadc81328f587`; the launch record says the map stayed stable. The outer PowerShell process exited `1` after `8.6628274` seconds, inside its 15-second cap. The wrapper receipt is `state=failed` after `6.3332115` seconds; the probe batch is `completed=false` after `5.6016298` seconds.

| Probe | Saved outcome |
|---|---|
| Immediate exit 0 | `completed`, expected exit 0, output markers drained, owned tree clear |
| Immediate exit 7 | `nonzero_exit`, expected exit 7, output markers drained, owned tree clear |
| 1.2-second monitored success | `completed`, expected exit 0, output markers drained, owned tree clear |
| 5-second timeout probe, 0.5-second wait deadline | `indeterminate`, `timed_out=false`, `completed=false`; this fails the smoke gate |

For the timeout probe, `WaitForExit` returned false at `0.4959699s`, just before the `0.5s` deadline. The monotonic loop recorded deadline reached at `0.9381056s`, then attempted a kill. Exit was observed at `0.9397325s`, after cleanup began. The process tree was reported clear and stdout/stderr drained. The record says `exit_confirmed=true` but also `exit_code=-1` and `process_exit_utc=1601-01-01T00:00:00.0000000Z`; the exit timestamp is not usable provenance, and the code value is not independently established as the expected natural or kill result. This review does not relabel the run as a valid timeout or a successful probe.

`Get-ProcessClassification` at `run_saved_m4_audit.ps1:39` requires both an exit observation later than the deadline and a false-wait elapsed time at or after the deadline. Here the false-wait time is earlier than the deadline, so the classifier returns `indeterminate` even though the later monotonic loop crossed the deadline and killed the process. The artifacts do not record a positive observation that the process was still running strictly after the deadline and before the kill. A likely race/measurement gap is that `WaitForExit(timeout)` returned false just before the Stopwatch deadline and the next loop did not observe the process until later; the exact cause is not proven by this run. Removing the elapsed-time condition alone would risk misclassifying a natural late exit.

The closeout records no mock or audit claim/files, matching source hashes, 83 prior selected files unchanged, zero model calls, zero checkpoint access/deserialization, zero actual-data access, and `new_f1=null`. Historical Round015 wrapper and Round010 gate flags remain false. No model, data, F1, or hardware result was produced.

## Review limits

I inspected the saved `probe_receipt.json`, `wrapper_receipt.json`, `smoke_launch.json`, `smoke_preflight.json`, and `execution_closeout.json`, plus the frozen classifier and process-control source lines. I did not rerun a mode, alter frozen code, import model libraries, access a checkpoint or project data, calculate F1, or test hardware. Process-tree clearance and stream-drain fields are saved observations, not independent OS tracing.