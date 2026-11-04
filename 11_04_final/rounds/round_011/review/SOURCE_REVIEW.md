# Round011 independent source review

**Verdict: approved for the bounded pure mock and saved-evidence audit in `rounds/round_011/manager/run_audit.ps1`.** Approval is tied to the exact SHA-256 map in `approved_sources.json`. The author acknowledged the freeze before approval; no code changed after that ACK during review.

## Reviewed scope and method

Static source review only. I read `verify_frozen_run.py`, its synthetic fixture tests, `run_audit.ps1`, round010's approved-source map, receipts, saved result/probability JSON, incident/postcheck metadata, and the current M4 source contract. I did not execute the mock or auditor, import Python packages, load a checkpoint, read NPZ/reference/raw/holdout files, or compute F1. The audit source imports only Python standard-library modules and streams file hashes with a 1 MiB buffer.

The approved map freezes only the two round011 Python files and the round011 PowerShell runner. Independent live hashes matched the map at approval:

- `verify_frozen_run.py`: `e183e7e323ddc9bc0754fd0bd66489d7d6596bacad806756c54776686f1e3e45`
- `test_verify_frozen_run.py`: `80493e3e0ded68db2aa0c1bee7594f5c400d28744c31c87fcbb03c7520d64995`
- `run_audit.ps1`: `713e8839aa50cc0bb464f4430d9ac7c6140c90835105f663ab14f881bbc54ae7`

The requested reviewer setting was `gpt-6-luna`, `xhigh`, `fork_turns=none`. `manager/host_turn_evidence.json` records the host-reported reviewer session and settings; this is host metadata, not internal model attestation.

## Source and fixture findings

- The auditor separates saved launch snapshots, current live-source checks, saved numeric replay, audit-integrity status, and the historical overall gate. `historical_overall_gate` is fixed false, so a clean current-source fixture cannot erase round010's source-freeze failure.
- The round010 map walk excludes array/table extensions, checkpoint assets, and raw/reference/holdout paths before opening or hashing them. Its only numeric comparison inputs are the already-saved two-row probability and selected-reference JSON records. It separately records excluded NPZ/checkpoint metadata as unverified.
- Snapshot verification checks the exact approved map, source-file set, copied code hashes, wrapper snapshot hash, and executed script path/hash. The wrapper diff is read from saved source text; the early-return inference uses the saved pilot child result and progress stages. The numeric check independently recomputes row sums, finite/range checks, max absolute difference, argmax, and float64 exact equality, then compares those with the recorded fields. It preserves the distinction between tolerance pass and exact inequality.
- `current_source_gate` is true only when saved launch snapshots and currently rehashed eligible sources match. It can be false while `audit_integrity_passed` and the saved numeric result are true; the historical gate remains false in both cases.
- The fixture source supplies clean-live and live-wrapper-drift cases under a temporary directory inside round011. Both preserve the old incident; the drift case keeps approved launch snapshots and numeric evidence valid while making the current-source gate false. These are code-reviewed assertions, not executed results.
- The runner checks live approved hashes before and after, uses a one-run claim, snapshots all three approved files, invokes the base Python from `pyvenv.cfg` with `-B -S`, caps the process at 28 seconds plus 2 seconds cleanup, and records exit confirmation. The auditor contains no subprocess calls; timeout cleanup targets only the launched process. The runner's RAM gate is 0.5 GiB with a 100 MiB planning estimate, not a measured peak.

## Limits and pending results

Static review found no blocker for the defined audit scope. The planned mock and saved-evidence audit have not run yet, so their actual exit status, receipt values, and generated audit JSON remain unknown. This approval does not reverify round010's protected NPZ/checkpoint bytes, validate hardware behavior, establish M4 integration, or change the historical round010 outcome. The separate `M4_REVIEW.md` approves only the source-grounded synthetic head-mechanics contract, not a performance claim.

## Prelaunch map correction

The launch precheck rejected the first `approved_sources.json` because its test-file hash had one extra `b`. No process was launched and no run claim was created. The rejected map is preserved as `approved_sources_prelaunch_typo.json`; the active map was corrected to the independently measured file hash. The three code files remain at the same frozen contents, and all active-map hashes were rechecked against disk before launch.
