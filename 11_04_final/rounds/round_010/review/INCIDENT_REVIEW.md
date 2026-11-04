# Round010 post-freeze wrapper mutation incident

**Verdict: the pilot's overall source-freeze/provenance gate is expected to fail.** Keep any child numerical replay result separate from the wrapper completion status. Do not edit the approved map, replace snapshots, or rerun the model this round.

## Evidence and exact change

The approved manifest and successful `mock_01` bind `rounds/round_010/manager/run_bounded.py` SHA-256 `c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210`. The mock receipt started at `2026-11-04T19:56:17.987501Z`, exited 0 in 0.281 s, and records that wrapper hash for both the live source and copied snapshot. Its source and wrapper checks passed before the edit.

The pilot receipt started at `2026-11-04T19:56:30.748973Z`; it copied `logs/pilot_01/source/run_bounded.py` with SHA-256 `c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210`. The live wrapper file was modified at `2026-11-04T19:57:09.1491992Z`; its current SHA-256 is `c1d595c94641e81c1e930a216a448013709fd58050cc32d5e31d84251df38867` (25,428 bytes). The pilot snapshot still matches the mock snapshot and is still SHA `c0bb06…`; the live file differs.

A line diff between the mock snapshot and live wrapper shows one change only: two lines were added to the early `root_identity_capture_failed` return path, computing `wrapper_unchanged` from the live wrapper and copied snapshot. The approved map was not changed. The current manifest therefore intentionally still points to the launch-time wrapper SHA, and the mock receipt remains valid for that exact frozen map.

## Branch reachability and consequence

The changed lines are in the branch used only if the Popen process starts but identity cannot be captured from process counters or the exact Popen handle. The pilot stdout already contains normal child stages (`column_forward_complete`, `row_forward_complete`, `icl_forward_enter/complete`); at the recorded point it had progressed through the fourth estimator call. That proves the early identity-capture-failure branch was not taken by this pilot.

The running manager process uses the old, copied wrapper source. Its normal post-run path in that frozen source still compares the live wrapper SHA with the approved SHA and compares the snapshot SHA. Since the live file changed after launch, the post-run `wrapper_unchanged` check should be false and the wrapper's `completed` predicate should fail, even if the child later reaches `PILOT_COMPLETE` and its two-query probability checks pass. This is a provenance failure caused by post-launch source drift; it does not establish whether the child numerical replay matches the fixed reference.

## Review and handling

I read the mock and pilot receipts, source snapshots, live wrapper diff/hash, and current child stdout/stderr progress only. I did not rerun code, access the NPZ as an array, read reference rows, or inspect holdout/raw data. The source hash in `approved_sources.json` remains unchanged. No source file was restored or rewritten by this reviewer.

For the final round010 result, record separate fields for child numerical gates and wrapper/source-freeze gates. If the child checks pass, report only the two fixed INNER probability comparisons and clearly state that wrapper provenance failed; do not call the entire pilot a clean completion. Record the live and snapshot hashes and preserve all receipts. Do not repeat the pilot in round010.

Next-round provenance acceptance should require: a frozen wrapper whose approved, copied, and post-run hashes all agree; an exact-map successful mock; no source edits after launch; and a collector that reports child numerical equivalence separately from wrapper/process-tree/resource completion. Any later model rerun should follow a new explicit execution gate and must not be presented as repetition of a clean round010 result.
