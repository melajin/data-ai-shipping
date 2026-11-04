# Round 007 — Independent source precheck

## Decision

**Approve one pure mock invocation only**, after the manager freezes and verifies the exact manifest containing the three hashes below. This is pre-execution approval; the mock result is still pending. Synthetic model comparison remains unapproved until I review its frozen source and manager wrapper inputs separately.

| File | SHA-256 |
|---|---|
| `rounds/round_007/code/column_chunk.py` | `BF263BA75BEF5ED9AAB04364459E426F3A82BE92DA2CE642E89B06558FD9CDED` |
| `rounds/round_007/code/test_column_chunk.py` | `44B3AE7F56560EFD05268D8A0D253128CF1BE78178BCE4D0DCB75F1E3D602A32` |
| `rounds/round_007/manager/run_bounded.py` | `90654941F881979A72006ADF8620527D87F791AF33A96C5FBE7CA0F72E50BEFA` |

## Source contract established

I read the pinned TabICL 2.2.0 source as text and matched the hashes in `rounds/round_004/runtime_author/replay_contract.json`; I did not import TabICL/Torch or load a checkpoint.

- `InferenceManager.__call__` takes one `_run_forward(_prepare_inputs(...))` CPU path before accelerator batching. `_prepare_inputs` keeps non-tensors such as `train_size` and `embed_with_test`; `_run_forward` preserves no-grad and optional AMP/FA3 context. The CPU branch therefore does not implement the accelerator split that the adapter is adding.
- `ColEmbedding` owns the `tf_col` manager. Grouped and ungrouped calls both expose the last leading dimension as the per-column/group batch axis, with target-aware `y_train` expanded over that same axis. Shuffle-optimized inference exposes a single feature axis, then duplicates and permutes embeddings after the manager call.
- The set transformer and attention operate over each column/group's full sequence. `train_size` limits keys/values used for the training context while the full sequence remains query/output positions. Row interaction and ICL consume the reconstructed full column result after this manager returns.
- `output_repeat` only multiplies output-size estimation on the later accelerator/offload path; the shuffle optimization uses `output_repeat=B`. The adapter retains it without changing the CPU forward calculation.
- The adapter slices features and their aligned target tensor on the column/group axis, preserves sequence and grouping-internal dimensions, rejects unsupported tensors or target shapes, preallocates one output, and copies each chunk back into its original position. It forwards `configure`, keeps the original manager's preparation/forward methods, and exposes a restore handle.

The checkpoint was not inspected, so I cannot say which grouped or ungrouped shape it selects. The approved synthetic run should record the actual chunk shapes. That does not block this pure mock because the mock covers both rank-3 and rank-4 leading-axis layouts.

## Mock and manager review

The mock imports only the standard library and `column_chunk.py`, which is also torch-free. It reads no data files and performs no checkpoint/model access. Static checks cover 19 columns split as 16+3, original output order, target alignment, preserved shared arguments and `output_repeat`, a second leading table axis, bad shape rejection, unsupported tensor rejection, fixed chunk size, and install/configure/call/restore of only the column manager.

The bounded wrapper uses the exact approved hashes and snapshots, checks the round-local script allowlist, gates the mock at 1.5 GiB available RAM and 30 seconds, samples its owned process tree using PID creation times, and preserves stdout, stderr, resource samples, and termination/exit receipts. No blocking issue was found for the mock-only call.

## Known constraint for later actual replay

`TabICLClassifier.fit()` constructs the resolved inference config and loads the model; the column manager sets `exe_device` when `configure()` runs during forward. The current install helper requires a configured CPU manager. This is not a blocker for the planned synthetic baseline-first sequence, where the original prediction configures the manager before the adapter is installed. Before a future low-memory replay that installs the adapter before the first prediction, configure the original manager from the resolved CPU `COL_CONFIG`, confirm its settings are unchanged, then install; add a `fit → configure → install → predict` mock.

## Scope and limits

This is a static source review. It does not show that the mock passed or that the split model matches the unsplit model. I did not import a model, load a checkpoint, open feature arrays or probabilities, inspect labels, raw data, holdout, Test2025, or the full 7,372-row source; I did not compute F1.

Requested reviewer configuration is GPT-6 Luna/xhigh/fork_turns=none. `manager/assistant_host_evidence.json` records matching requested and host turn-context values; this is host evidence, not internal model authentication. See [`precheck.json`](precheck.json) for machine-readable source hashes, contract evidence, unknowns, and scope.

## Mock 01 result and mock 02 corrective approval

The first bounded mock ran the six pure mock functions successfully: stdout was `pure mock checks passed`, child exit was 0, and runtime was 0.281 seconds. The manager's raw receipt was `failed_or_stopped` because the old alive check counted the exited root process object while its `Popen` handle remained open. A follow-up OS process snapshot found neither recorded PID; no process was terminated. Preserve that raw receipt and correction record.

I reviewed the wrapper change in `run_bounded.py` SHA `2820871E8884A0FD642E550301154C16039D6C85C6168BDA32CBF67340F3BEE4`. It adds `SYNCHRONIZE` and `WaitForSingleObject(handle, 0)`, treating only `WAIT_TIMEOUT` plus the same creation ticks as a live process. The new static review found no blocker for one corrective second/final pure mock invocation. Frozen adapter and test hashes are unchanged. The exact approval is [mock02_precheck.json](mock02_precheck.json); synthetic comparison remains unapproved.

The original [precheck.json](precheck.json) remains the pre-mock01 approval record (SHA-256 `A657D5DC0A4F85D62611D504B08F11D7B4F308DDB3065622A9686AE67B957DED`). This addendum records the first invocation and the single corrective allowance without rewriting the original approval.

## Synthetic pair source gate

I independently reviewed the frozen synthetic pair at SHA-256 `67F74942B38C4C2EE42C6A0509C39997828C0E98658BC04ADB2CA96850F445B3` with the exact adapter, mock, and bounded wrapper hashes recorded in [synthetic_precheck.json](synthetic_precheck.json). **Approve one bounded synthetic pair invocation only**, after the manager verifies the source manifest and rechecks available RAM immediately before launch (minimum 3 GiB). This approval is not a model result; no synthetic execution has occurred at the time of review.

The final version fixes the input-fingerprint object to compare hash/shape/dtype consistently, serializes `torch.device('cpu')` as `cpu`, requires exact Torch `2.6.0+cpu` with CUDA unavailable and no CUDA build, and checks actual configured COL/ROW/ICL manager state after the baseline and adapted calls. Pinned source confirms expected offload enums: `AUTO` for COL and `GPU` for ROW/ICL (`InferenceManager._normalize_offload(False)` maps to GPU); CPU inference returns before accelerator offloading.

The pair is bounded to one checkpoint bind/fit and two `predict_proba` calls using the same estimator and fixed synthetic arrays. It records per-call input and shuffle fingerprints, shape events, runtime settings, outputs, finite/range/row-sum gates, exact equality, maximum absolute difference, and argmax agreement under fixed `1e-5` gates. It installs the adapter only on the fitted estimator's column manager and restores it in `finally`.

Source approval does not predict whether the pair will pass. If the process starts and fails, the one-attempt allowance is consumed. The result will establish only a small synthetic numerical comparison; actual-data replay and full-context memory impact remain unknown.

## Final pair result and artifact verification

The single approved pair completed under its frozen hashes. The final independent review and artifact-only verification are in [FINAL_REVIEW.md](FINAL_REVIEW.md), [final_review.json](final_review.json), and [synthetic_artifact_verification.json](synthetic_artifact_verification.json). The NumPy-only checker verified the NPZ against the result JSON and regenerated inputs; all 50 checks passed. Exact equality applies only to the two synthetic query rows in this run.
