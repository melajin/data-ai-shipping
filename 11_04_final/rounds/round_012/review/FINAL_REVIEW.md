# Round012 final independent review

## Verdict

**Static source review approved; no dynamic execution gate was reached.** The manager's guard stopped before `smoke_01` at the 20:42 UTC experiment cutoff. No process or execution claim was created. Do not describe the smoke, mock, or saved-evidence audit as run or passed.

## Evidence checked

- Author freeze ACK was declared at 2026-11-04 20:38:41 UTC and stored in `manager/candidate_freeze_ack.json`. Independent source review approved the exact three-file candidate at 20:41 UTC.
- `review/approved_sources.json` was created from direct disk SHA-256 calculations and independently rehashed after creation. Its SHA-256 is `b8e4e72b2cce5ee17535042a1fcd88e5c594a1cd9325f3a3dae81648e6def5ca`. The three code-file hashes still match that map at final read-only check.
- The approved source review found no blocker for the bounded process-control smoke, standard-library mock, and one saved-evidence audit. It covers static code only and is documented in `SOURCE_REVIEW.md`.
- A read-only filesystem check found no run directory, receipt, or `execution.claim` for `smoke_01`, `mock_01`, `mock_02`, or `audit_01`. The manager reports its cutoff guard blocked before launch. No unit test, Python process, model, checkpoint, protected data, or numeric audit was executed by this reviewer.
- `M4_NEXT_CHECKLIST.md` prepares the later tiny synthetic gate from round011's source-reviewed contract. It does not authorize or record a round012 model run.

## Outcome and limits

The source files and approval map are reviewable and frozen, but the required process exit-0/exit-7 evidence is missing. Therefore there is no successful process smoke, no completed exact-map mock, and no audit output. The audit must not be described as passing because source approval alone does not demonstrate that PowerShell preserved child exit codes, drained both streams, or cleaned up the owned process.

Round010's historical overall gate remains false. No new numeric replay was performed. Development baseline remains micro-F1 `0.5930133966423605`, macro-F1 `0.5252719738966167`; the prior unadopted search mean remains `0.5933525521451586`. Independent and official scores remain unknown, and the 0.7 goal is not reached. These are carried-forward values, not round012 results.

The requested reviewer setting is Luna/xhigh/fork-none. Host-reported session/settings evidence is recorded separately and does not constitute internal model attestation. The manager's initial resource record showed 4.1446 GiB available at 20:26:06 UTC, but this is not a current pre-run RAM measurement or a measured peak.

## Handoff

Continue in round013 with a version copy of the approved implementation and only the path/round substitutions needed to keep all new claims, receipts, logs, temp files, and audit output inside round013. Freeze and hash the new candidate independently; do not reuse the round012 approval map for modified files. After fresh review, run one process-control smoke first (exit 0 and 7, at most two sequential children, ≤10 seconds, no retry), then the exact-map mock (≤30 seconds), then at most one saved-evidence audit (≤30 seconds) only after a completed mock with integer exit 0 under the same map. Each failure stops the remaining sequence. Do not run M4 in round013 unless a separate fresh execution contract and source freeze explicitly include it; the existing M4 checklist is preparation only.
