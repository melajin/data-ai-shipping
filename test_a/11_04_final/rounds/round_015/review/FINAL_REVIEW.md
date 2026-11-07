# Round015 execution review

## Verdict

The saved smoke and standard-library mock receipts pass under the exact approval map. The synthetic Python child wrote a result with `status=completed`, exit code 0, completed progress, and bounded call counts. **The synthetic wrapper receipt is not a pass:** it records `completed=false`, `wait_finished=false` / `timed_out=true`, and a result-JSON parse error. No rerun or map, receipt, or source edit was made.

## Process and source integrity

The current approval-map SHA-256 is `2cede678cba53e4a92832c663bf4968b75ee63b5c1287ad25804aaf3dce59dd4`. Its hash matches each run's before/after receipt values and execution claim. Independent hashes of all three live sources match the map, each run's pre/post checks, and each run snapshot plus snapshot postcheck.

Smoke completed in 1.018 seconds with expected child exits 0 and 7; each recorded its stdout/stderr markers, drained streams, exited, and left an empty owned tree. Mock completed in 0.601 seconds with exit 0; captured stderr reports four mock cases passing. These are receipt observations; this reviewer did not run tests.

## Synthetic child result

The saved result JSON records `status=completed` for generated data only (seed `20261112`, 16 context rows by 8 features, 4 target rows by 8 features). It records target labels created after the sole `predict_proba`, and not passed to `fit` or `predict_proba`. Runtime recorded Python 3.12.14, TabICL 2.2.0, PyTorch 2.6.0+cpu, NumPy 2.3.5, CPU FP32, and 3 intra-op / 1 inter-op threads.

The saved result reports the `decoder[2]` source-head recalculation exact, with max logit difference 0; probability reconstruction max difference `5.960464477539063e-08` (within `1e-6`), finite values in [0,1], max row-sum error 0, and matching argmax. All six saved comparisons pass the `1e-5` logit and `1e-6` probability tolerances: five have zero logit/probability difference; public-probability reconstruction has logit difference 0 and probability difference `5.960464477539063e-08`. All preserve argmax. Call counts equal limits: checkpoint load 1, context fit 1, `predict_proba` 1, full forwards 4, head evaluations 12, backwards 4.

M4-a records finite/nonzero W gradients on both steps, exact-zero inactive six rows, fixed bias, and exact head-only reload. Diagnostic CE values are 1.4843811989 initially and [1.4843811989, 1.4840226173]. M4-b records A gradient zero at B=0, finite/nonzero B gradient on step 1, finite/nonzero A/B gradients on step 2, unchanged inactive rows and bias, one merge with duplicate rejected, and exact head-only reload. Its CE diagnostics are 1.4843811989 initially and [1.4843811989, 1.4843813181]. These values are diagnostics, not a selection or performance claim. The result records the upstream model unchanged and no project data, F1, performance selection, full-model reload, or hardware test.

Independent artifact-byte hashes (no `.pt` deserialization): `m4_a_head.pt`, 42,422 bytes, `c33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0`; `m4_b_merged_head.pt`, 42,464 bytes, `8127123b4e8109c1456914ac9c4f59284509116469d726bc2e9ac1df3b430a36`; result JSON, 64,851 bytes, `365535d9f117ae6d758909402413c3220eca4f0220a1b8b14d0ce6674dcc9105`.

## Wrapper gate failures and resources

The wrapper reports exit code 0, elapsed 16.764 seconds against a configured 170-second compute wait plus 10-second cleanup, but also `wait_finished=false` and `timed_out=true`; `exit_confirmed=true`, memory stop is false, the owned tree is clear, and streams were drained. The timeout flag conflicts with the elapsed time and confirmed exit; its precise cause is not established. In `run_m4.ps1`, the deadline loop starts at line 256; line 291 sets `wait_finished` from `WaitForExit(1)`, and line 292 derives `timed_out` from that flag. Do not treat the child result as restoring the wrapper gate.

Separately, `Read-Receipt` uses `ConvertFrom-Json` at line 383 and the synthetic branch reads the child artifact at line 587. The saved result has an empty property name under `upstream_model.module_training_before_after` (root module name, recorded at `m4_synthetic.py` line 860), consistent with the manager-reported PowerShell 5.1 invalid-name parse error. Thus wrapper `synthetic_result_status` is null although child stdout, progress, and result JSON say completed.

The wrapper recorded 11 resource samples: available RAM began at 5.7635 GiB and sampled minimum was 5.2198 GiB; sampled owned-tree peak was 585,891,840 bytes. The 1,536 MiB expected peak is a planning assumption, not a measurement. Samples are intermittent. No memory stop was recorded.

## Limits and bounded follow-up

I parsed saved receipts and result JSON using base Python `-B -S` standard-library JSON, and independently hashed sources, snapshots, and artifact bytes. I did not import Torch, deserialize `.pt` files, reload or re-hash the checkpoint, recalculate tensors from head files, replay model code, access project data, or recompute F1. Numeric comparisons above are recorded output, not an independent replay.

A finite next model-free probe is one sequential process-control run of at most 15 seconds covering exits 0/7, a monitored short success, and a genuine deadline-limited child, plus strict JSON projection/mock/saved-audit handling for the empty-name key. Keep process-wait classification and receipt parsing as separate gates; require an audit before any later model run.