# Round018 minimal next repair scope

## Hypothesis and boundary

The timeout probe reached its monotonic deadline, but its earlier `WaitForExit` false return (`0.4959699s` versus a `0.5s` deadline) did not prove the child was still alive at the deadline. The later loop recorded the deadline at `0.9381056s`, killed the process, and observed it exited at `0.9397325s`. The classifier's wait-time predicate then returned `indeterminate`. A minimal repair should add a separate, explicit `still_running_observed_after_deadline` fact, recorded by a nonblocking `HasExited` / `WaitForExit(0)` observation strictly after the monotonic deadline and before kill. Keep wait-return time, monotonic deadline, exit observation, and termination confirmation as separate facts. Do not classify timeout from `WaitReturned=false` alone.

Do not modify Round017/018 history or overwrite `smoke_01`. Any new source set needs a new author write-freeze, manifest, direct hash review, approval map, and a fresh one-use claim/run ID (for example `smoke_02`). This note authorizes no code edit or run. Remain MODEL-ZERO: no Torch/NumPy/TabICL import, checkpoint read/hash/load, `.pt` deserialization, project data/OUTER/holdout, F1, installation, or hardware.

## Required termination provenance

After a deadline kill, perform a bounded OS termination wait unconditionally, even when a cached `HasExited` check already says true. Record the wait result and timeout separately from `HasExited`. Record `ExitCode` read success/value and `ExitTime` read success/validity independently; treat `1601-01-01T00:00:00Z` as invalid timestamp evidence. Preserve a returned `-1` as a reported value, but do not claim it is a verified natural exit code or infer timeout from it. Missing or invalid termination provenance remains unknown.

## Regression cases and expected classification

| Case | Evidence supplied to the classifier | Expected |
|---|---|---|
| Normal exit 0 before deadline | Exit observed strictly before deadline; exit code 0 | `completed` |
| Normal exit 7 before deadline | Exit observed strictly before deadline; exit code 7 | `nonzero_exit` |
| False wait just before deadline, process still alive after it | Wait false at `0.4959699s`; deadline `0.5s`; explicit post-deadline live observation at `0.9381056s`, before kill; exit later at `0.9397325s` | `deadline_timeout`; record `still_running_observed_after_deadline=true` and `timed_out=true` |
| Natural exit first observed late, with no post-deadline live observation and no validated monotonic exit-time evidence | Wait false before deadline; first observed exited after deadline | `indeterminate`; never `completed` or timeout solely from false wait/late discovery |
| Exact-boundary observation | Exit or live-state observation exactly at `0.5s` for a `0.5s` deadline | `indeterminate`; preserve boundary semantics |
| Memory stop | `memory_stop=true`, regardless of a concurrent deadline signal | `memory_stop`; do not report timeout or normal completion |

The existing recorded normal cases should remain passing. The repair must also prove that a post-deadline live observation is required before assigning `deadline_timeout`; otherwise the late-natural-exit case can become a false timeout.

## Acceptance for any separately authorized attempt

First freeze and independently approve the minimal source/map change. Run one fresh smoke attempt only. Accept smoke only if the wrapper receipt is `completed`, the outer OS exit is `0`, all four probe classifications and expected exits match, the timeout case records post-deadline live evidence before kill, bounded termination confirmation and exit metadata validity are explicit, stdout/stderr drain and owned-tree cleanup pass, source/map hashes stay stable, and both wrapper and outer wall time stay within their caps. Do not launch mock or audit if any smoke assertion is unknown or fails; do not rerun a consumed claim. If the fresh smoke passes, mock and saved-audit remain separate once-only gates under that same approved map. This would establish process-control and saved-evidence gate results only, not model behavior or performance.