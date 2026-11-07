# Round 008 — Source and mock gate review

**Decision:** source and saved mock review pass. The mock02 artifact matches the approved source snapshot and completed successfully. This review authorizes one bounded pilot attempt under the amended 420-second limit; no retry is authorized.

## Scope and evidence

Reviewed the frozen source set at 2026-11-04 18:52–18:56 UTC and the saved mock02 receipt/streams at 18:56 UTC: `replay_inner_pilot.py`, `column_chunk.py`, `test_configure_before_install.py`, and `manager/run_bounded.py`. Read the round plan, next-session instructions, round006 pilot source, round007 adapter and review record, pinned TabICL source files, and manager input-copy receipt. The reviewer did not load the NPZ arrays, raw data, holdout, OUTER data, or `y_inner`; did not import the model environment; and did not execute the mock or pilot. The author reports that AST syntax parsing passed; that result was not independently executed by this review.

Requested reviewer setting: `gpt-6-luna` / `xhigh` / `fork_turns=none`. Host turn-context metadata is recorded separately by the manager in `rounds/round_008/manager/assistant_host_evidence.json`; it is metadata evidence, not internal model authentication.

## Source findings

- The round008 pilot hard-pins the copied context and query-freeze SHA-256 values, the ordered IDs `["36001915", "31703435"]`, and their ordered digest. It also checks the checkpoint size/hash, TabICL 2.2.0, fixed estimator settings, data shapes/dtypes, four-class order, and frozen history rows. The manager copy receipt reports byte-equal copies: context 1,916,394 bytes and freeze 748 bytes.
- The history reader consumes the CSV header and first two data lines only, verifies their IDs in the frozen order, and parses only `rfid_id` and `p0..p3`. It does not access `y_inner`, later probability rows, or labels. Model output gates keep finite/range, row-sum error `<=1e-5`, absolute probability difference `<=1e-4`, and argmax equality separate from exact numeric equality.
- After `fit`, the pilot calls `original_col_manager.configure(**estimator.inference_config_.COL_CONFIG)` before installation. The same resolved config object is passed by pinned `TabICL`/`ColEmbedding` at prediction time. It checks resolved CPU/FP32/offload state before installation. The adapter delegates configure, wraps only `model_.col_embedder.inference_mgr`, chunks the independent column/group axis by 16, preserves sequence and FIT target axes, `train_size`, `output_repeat`, and unknown shared values, and rejects unsupported tensor inputs. It uses the pinned manager's `_prepare_inputs` and `_run_forward` methods. ROW/ICL managers are identity-checked and left unpatched.
- The pilot allows one `predict_proba` call and restores the original column manager in a `finally` block that begins immediately after installation. Restoration runs before any final diagnostic write.
- The wrapper binds each run kind to one fixed script. Mock bounds are 30 seconds with 2 seconds reserved for cleanup. After the manager's budget amendment, pilot bounds are 420 seconds with 410 seconds compute and 10 seconds cleanup, a 3 GiB launch gate, and a 1.5 GiB in-run stop threshold. It claims a single pilot attempt and records PID creation ticks immediately after `Popen`, checks process liveness with `WaitForSingleObject`, and limits termination to owned identities.

Pinned sources were reviewed as text. Their hashes are listed with the implementation, input-copy, and provenance hashes in `manager/approved_sources.json`. The local checkpoint is checked by the pilot with streaming SHA-256 and its fixed byte count; it is not added to the wrapper manifest, avoiding an unnecessary 110 MB preflight read.

## Mock01 outcome and authorized correction

The saved `mock_01` receipt records exit code 1 after 0.282 seconds, no timeout/RAM stop, and no remaining owned processes. Its stderr identifies a mock-protocol defect: `FakeManager` was not callable, so adapter construction rejected the fake before chunk execution. No model code ran. The author added the manager `__call__` protocol to the fake, delegating through `_prepare_inputs` and `_run_forward`.

The saved `mock_02` receipt records status `completed`, exit code 0, 0.266 seconds elapsed, no stop reason, and no remaining owned processes. Standard output is `configure-before-install pure mock passed`; stderr is empty. Receipt hashes match the approved test source `470563dc44be46970f49c9142b393f5fd587dd96d3e57494e3b25e0d57a193b6`, adapter `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded`, and wrapper `6962c94fa07a36cd7b3429eaeb27ac851aee3104e9b77758d7a99c0fc1a48e1d`; all three source-snapshot hashes agree. The receipt reports no resource stop. This verifies the bounded pure mock lifecycle only.

## Gate and limits

The approved next command is exactly one bounded pilot attempt. The wrapper claim prevents a second pilot attempt, and the 420-second total bound reserves 10 seconds for cleanup:

```powershell
$expectedPilot = '112ca09e7abba9c194421c22bd38771563636e2852c867c089cb27e985c39b0d'
$expectedAdapter = 'bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded'
$expectedMock = '470563dc44be46970f49c9142b393f5fd587dd96d3e57494e3b25e0d57a193b6'
$expectedWrapper = '6962c94fa07a36cd7b3429eaeb27ac851aee3104e9b77758d7a99c0fc1a48e1d'
if ((Get-FileHash './rounds/round_008/code/replay_inner_pilot.py' -Algorithm SHA256).Hash.ToLower() -ne $expectedPilot) { throw 'Frozen pilot source changed' }
if ((Get-FileHash './rounds/round_008/code/column_chunk.py' -Algorithm SHA256).Hash.ToLower() -ne $expectedAdapter) { throw 'Frozen adapter source changed' }
if ((Get-FileHash './rounds/round_008/manager/run_bounded.py' -Algorithm SHA256).Hash.ToLower() -ne $expectedWrapper) { throw 'Frozen wrapper source changed' }
& './environments/round_004_tabicl_cpu/Scripts/python.exe' -B './rounds/round_008/manager/run_bounded.py' --kind pilot --run-id pilot_01 --script './rounds/round_008/code/replay_inner_pilot.py'
```

This review did not execute mock or model code. Actual-context peak RAM, pilot completion, probability reproduction, and hardware behavior remain unknown. The manager must perform a fresh RAM check and record the contemporaneous resource evidence before launching the pilot. The mock's resource use does not establish pilot resource safety.
