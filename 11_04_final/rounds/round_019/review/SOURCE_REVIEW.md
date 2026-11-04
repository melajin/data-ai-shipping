# Round019 independent source review

## Verdict

**Not approved for execution.** The frozen source set has a blocking saved-receipt validation gap: the Python smoke validator does not verify that the raw `ExitTime` agrees with its validity flag. No `approved_sources.json` was created.

The author acknowledged a write freeze at `2026-11-04T23:09:52.1205810Z`, with `write_freeze=true` and `no_author_runs=true`. Direct hashes taken after that acknowledgement match both the candidate manifest and freeze acknowledgement.

| Frozen file | Bytes | Direct SHA-256 |
|---|---:|---|
| `rounds/round_019/code/saved_m4_audit.py` | 53,708 | `551176887ab273f3a92f30642143e4a3760f15bf41274c61d4aedf5ec024f751` |
| `rounds/round_019/code/run_saved_m4_audit.ps1` | 41,382 | `36854d10d0a050753f2d77ebc0119cf94669ee8e2906b011023f7e30afc0cbc2` |
| `rounds/round_019/code/candidate_sources.json` | 4,199 | `fc0402503454ad68431adcffd9399a9286b52b95e2a12872f141a3be6c69482c` |
| `rounds/round_019/code/author_freeze_ack.json` | 1,880 | `33349b56992837f93e49f891b86327160f236bde4f57f41258ff2261ce0e7eb6` |

The ACK and manifest contain the same two source hashes; the ACK's candidate-manifest hash matches the direct manifest hash. The manifest requests `gpt-6-luna`, `xhigh`, `fork_turns=none`; execution identity is explicitly not attested, and host evidence is separate.

## Static review

- The PowerShell Parser API reported zero parse errors. A token scan found no bareword `true`, `false`, or `null` identifiers.
- Base Python `-B -S -X utf8` `ast.parse` passed. The module was not imported.
- The PowerShell control path records each wait's monotonic begin, requested milliseconds, end, result, and error. It explicitly observes `HasExited` after the deadline before kill; the classifier requires that post-deadline live evidence and a later kill attempt before returning `deadline_timeout`. Late exit without that evidence, kill without pre-kill live evidence, and exact-boundary cases are classified `indeterminate`; `memory_stop` has priority.
- The frozen PowerShell source performs a bounded `WaitForExit` unconditionally, then records its result, `HasExited`, `ExitCode`, and `ExitTime` reads separately. The 1601 timestamp is marked invalid. The `exit_code_verified_natural` field now requires a pre-deadline exit observation and no kill or memory stop. A wait timeout is left unknown when the wait throws.
- The timeout smoke gate requires explicit post-deadline liveness, kill attempt, bounded termination confirmation, `ExitCode` read success, an `ExitTime` read, and owned-tree clearance. The Python validator requires those timeout fields and preserves the inherited size caps: 64 KiB for approval/manifests/ACKs/claims and Python mode receipts, 128 KiB for the process probe receipt, and 32 KiB for classifier cases. The existing Round015 input paths, hashes, and numeric tolerances are retained in the manifest and source constants.

## Blocking finding

In `saved_m4_audit.py` `process_smoke`, the validator requires `exit_time_read_succeeded` and `exit_time_valid` to be booleans and checks that a raw value is a string when the read succeeded. It does not parse or cross-check that raw value. Consequently it accepts contradictory evidence such as `exit_time_read_succeeded=true`, `raw_exit_time="1601-01-01T00:00:00.0000000Z"`, `exit_time_valid=true`; it also permits `exit_time_read_succeeded=false` with `exit_time_valid=true` if an error string is present. This can promote invalid timestamp evidence to valid in the saved receipt audit, contrary to the required unknown treatment for 1601 or unavailable `ExitTime`.

This is a static source finding; no receipt was generated or executed to demonstrate it at runtime. The author was asked to make a minimal validator correction and, if changed, produce a new manifest and freeze ACK for another direct-hash review. The frozen source set remains unapproved pending that correction.

## Scope and limits

I read the Round018 source review, repair scope, final review and saved receipts; the Round017 manager handoff contract; and the Round019 plan, candidate manifest and ACK. I directly hashed the four frozen files, inspected the control and receipt-validation paths, parsed PowerShell, and parsed Python syntax only. I did not run smoke, mock, saved-audit, or any process probe; import the target module; read or hash a checkpoint; open project data; compute F1; or test hardware. Process timing, termination behavior and saved-audit runtime behavior remain unverified. This review makes no performance claim.
