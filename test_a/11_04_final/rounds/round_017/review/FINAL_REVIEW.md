# Round017 independent final review

## Outcome

The approved smoke wrapper was launched once and failed before launching any probe child or Python auditor. The outer PowerShell process exited `1` after `3.6515994` seconds, within the 15-second cap. `rounds/round_017/logs/smoke_01/execution.claim` remains; the smoke log directory contains no probe/auditor receipt. Mock and saved-audit modes were not launched. There is no dynamic gate result, saved audit, or new F1.

The failure is in the PowerShell wrapper's initial receipt construction, not in the deadline classifier or saved-evidence audit. In `Save-WrapperReceipt` at `run_saved_m4_audit.ps1:78`, the hashtable uses `claimed=true`; PowerShell interprets bare `true` as a command and raises `CommandNotFoundException`. The native-encoding `manager/smoke_stderr.txt` records the command error and source line. The manager's `smoke_launch.json` records mode `smoke`, approved map SHA `9d20b92bf696b7d6d2003c9bd34bb4105f8fd6ebc4113e357f94f5595e100fe9`, outer exit `1`, and elapsed `3.6515994` seconds. The manager-reported preflight was 5.5104904 GiB free with no other Python process; the 200 MiB peak is an estimate, not a measurement.

## Frozen source and preservation evidence

I re-hashed the frozen source, manifest, ACK, and approved map after the launch. They still match the source review and author ACK:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `rounds/round_017/code/saved_m4_audit.py` | 49,394 | `8ca9be725be25a6d4e80d43a17a82341ef78a94ea33115ff8d3bfef10ce4b227` |
| `rounds/round_017/code/run_saved_m4_audit.ps1` | 29,662 | `fba54fd84873430039348f8d15a6660655126df7bc19ed2bdde8f4c71c7de720` |
| `rounds/round_017/code/candidate_sources.json` | 1,870 | `aff522305a7a1d8b0215caa598eaecbe3fc4596060c7afa335ee8fb5c1a29449` |
| `rounds/round_017/code/author_freeze_ack.json` | 1,650 | `fbde4e6b3426ee3e399a82aa35e1108fc9ef388d73e4eab4c7c7f8ee4269652b` |
| `rounds/round_017/review/approved_sources.json` | 1,023 | `9d20b92bf696b7d6d2003c9bd34bb4105f8fd6ebc4113e357f94f5595e100fe9` |

The manager's `execution_closeout.json` reports the two frozen source hashes still match, only the smoke execution claim exists, mock/audit have no files or claims, and all 45 selected prior files remain unchanged. It records zero model calls, checkpoint access, `.pt` deserialization, actual-data access, saved audit, and new F1. Historical Round015 wrapper failure and Round010 gate failure remain false as before. No process was left running.

## Limits and next scope

No probe process ran, so actual timeout/exit observation, process ownership, stream draining, and cleanup remain untested. The auditor did not run, so the saved JSON, provenance, and numeric checks remain untested. The manager's parser check reported no parse errors, which did not catch this command-expression runtime error. This failure does not reverse the static source approval for the frozen hashes, but those sources are not eligible for another launch because the one smoke claim is consumed and the wrapper failed.

No model or checkpoint was loaded or hashed, no `.pt` content was deserialized, no project data or holdout was read, no F1 was computed, and no hardware behavior was tested. Round015's historical wrapper gate and Round010's historical gate remain false. Round018 full-estimator M4-a integration stays conditional and is not authorized by this failed smoke.
