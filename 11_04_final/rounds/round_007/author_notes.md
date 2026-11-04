# Round 007 code author notes

## Ownership, request, and execution boundary

Authored only `rounds/round_007/code/column_chunk.py`, `rounds/round_007/code/test_column_chunk.py`, `rounds/round_007/code/synthetic_pair.py`, and this note. The manager owns wrapper, bounded execution, logs, artifacts, reports, shared round state, and handoff files. The independent reviewer owns `review/`. I did not change the venv, checkpoint, prior round, original data, protected arrays, or holdout. The requested author setting is `gpt-6-luna` / `xhigh` / `fork_turns=none`; this note does not claim the parent host model changed. The manager records host-turn evidence separately.

The pinned source reads and code authoring were lightweight. At 2026-11-04 18:18:34 UTC, Windows reported 4.67 GiB available of 13.81 GiB visible RAM. No process was stopped. I did not import the model package, load the checkpoint, run the pure mock, fit an estimator, or run predictions. No model-comparison result is claimed here.

## Source evidence and hashes

Hashes are SHA-256 of files under `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`, except where the source path itself is a pinned installed package file. The installed package source was read as text only.

| Read-only source | SHA-256 | Relevant evidence used |
|---|---|---|
| `AGENTS.md` | `08FA7DD4EDF239910B8F000DB2176589F87178AA9E911D31E1B627AB535A7DFC` | Round scope, data restrictions, RAM and verification rules |
| `NEXT_SESSION.md` | `3D3E5A5ED6A6D522F17496A1F966890D8F38FB2EBE748959D234FA91AF30B53F` | Round007 fixed input, estimator, chunk, gate, and no-real-data contract |
| `rounds/round_007/ROUND_PLAN.md` | `811BC9385274B36FE6D17385A72A142F1DB98B20BA64B1ACCD7D7FA0A2873E4B` | Frozen responsibility, limits, gates, and manager execution budget |
| `rounds/round_004/runtime_author/replay_contract.json` | `819E60FD2F05A655A86DC1CDAA5E52F5A4FD0486E78FDD5DC5A4AB140AD7E2F5` | Historical estimator settings and limits of prior source-only claims |
| `rounds/round_006/code/replay_inner_pilot.py` | `A4D10BBA93F3FE07EA7188ABA216C1211E13EBA24CEC334FC19D7B985D681505` | Frozen estimator constructor, inference validation, and shuffle-state recording |
| `rounds/round_006/author_notes.md` | `53F33B9FCE12D8459E96A073BBD8F61A85DD117F6E3C78EFF0C7F58F63BD523A` | Prior round source/evidence context |
| `.../tabicl-2.2.0.dist-info/METADATA` | `E429EDBE64F243241E6425854643B0D4128DE550121B9FEB1598EF710B9941A2` | Installed package version metadata |
| `.../tabicl/_sklearn/classifier.py` | `64F5EF7EF88A920A3F7A5F6E2D9D8DC08769EC343E931F910ACC2D9C4EAA5534` | Fit-time checkpoint/model binding and prediction path |
| `.../tabicl/_sklearn/base.py` | `7F8F284CA91BF1F5A016179834E508890B3F5368C4A48A7DCB6CB4B83A30051A` | Estimator inference config construction and resolved runtime fields |
| `.../tabicl/_model/inference.py` | `F9E3CF0D83047E06DF7D6763BB8D8EE7A00FF1BA6708299A14635831F60BA4FC` | `_prepare_inputs`, `_run_forward`, CPU early return, and batched output assembly |
| `.../tabicl/_model/embedding.py` | `A0C562600FE22944F91B1B71B706198CB9A4C3D9D8AABA67A86F35A85493D322` | Feature/group tensor layouts, y expansion, feature shuffle path, output_repeat |
| `.../tabicl/_model/encoders.py` | `A3E0E9BDE47E7F587C4A196D124EA631E25755D4F5AC5D6A8568618A4E299A4E` | Encoder accepts arbitrary leading batch axes and applies blocks to the sequence axis |
| `.../tabicl/_model/layers.py` | `96CCE2E84DB33E176D872C7BB7C0DF8C305DE3EB7A02FCAD9F1128F33D319D95` | Attention preserves arbitrary leading batch axes; `train_size` restricts sequence K/V positions |
| `.../tabicl/_model/tabicl.py` | `583786E5FFD70B9EB425BCA8E52AED415DADCDF4254C908B3B6FA52026A56491` | `TabICL` constructs a dedicated `col_embedder`; row interaction is separate |
| `.../tabicl/_model/inference_config.py` | `852ABB9CF97E9C82AE42A92B034581F6E9131F3BEC70EFBD3CE068AC92A77A37` | Resolved COL/ROW/ICL defaults and config fields |

Pinned package paths above expand to `environments/round_004_tabicl_cpu/Lib/site-packages/`.

## Adapter contract from source

- `InferenceManager.__call__` accepts `output_repeat` and general leading batch dimensions (`inference.py:1234-1285`). With `exe_device.type == "cpu"`, it returns from `_run_forward(forward_fn, _prepare_inputs(inputs))` before accelerator batching and before output-size/offload handling (`1291-1298`). The adapter therefore calls the same manager's `_prepare_inputs` and `_run_forward` on each chunk; those methods preserve the pinned CPU device preparation, `no_grad`, flash-attention toggle, and optional AMP context (`1210-1232`). Since the fixed path is CPU FP32, AMP remains disabled. CPU ignores `output_repeat` in the original path; the adapter accepts and records the unchanged value without changing original CPU behavior.
- `ColEmbedding` uses a dedicated `inference_mgr` with `enc_name="tf_col"` (`embedding.py:183`); `TabICL` separately constructs column and row components (`tabicl.py:240-261`). The adapter installer replaces only `estimator.model_.col_embedder.inference_mgr`; it does not patch a class/global manager or the ROW/ICL managers. The installation object restores the original manager and rejects an unexpected replacement at restore time.
- The grouped inference path builds `features=(B,G+C,T,group_size)` and, when target-aware, expands y to `(B,G+C,train_size)` before invoking the manager (`embedding.py:580-606`). Ungrouped inference uses `(B,H+C,T,1)` with matching y (`608-639`). The feature-shuffle optimization invokes the manager on `(H+C,T,1)` with y `(H+C,train_size)` and passes `output_repeat=B` (`641-665`). The variable-feature path also presents compact `(N,T,1)` features and matching `(N,train_size)` targets at the embedding boundary (`498-512`). The adapter selects `axis = ndim - 3`, the last leading feature/group batch axis immediately before sequence `T`; other leading table axes are retained. In a grouped configuration the chunk unit is a feature group; the internal `group_size` remains whole.
- `_compute_embeddings` applies per-feature input projection/target embedding and then the column set transformer over the sample sequence, with `train_size` retained as a scalar (`embedding.py:340-421`). Encoder and attention signatures retain arbitrary leading batch axes (`encoders.py:120-147`, `layers.py:406-438`). For the induced-attention route, `train_size` controls which sequence positions provide keys/values (`layers.py:625-652`). This supports independent leading feature/group computations for the fixed embedding path, while preserving the entire FIT/query sequence and attention context within each chunk.
- The wrapped manager is configured on each `ColEmbedding` inference call (`embedding.py:565-568`), so `ColumnChunkManager.configure` delegates to the original manager and checks that configuration remains CPU. The synthetic script validates the fitted estimator's resolved COL/ROW/ICL configuration, KV/offload state, parameter/buffer devices and floating dtypes, and canonical class order before prediction. After the baseline has configured the three runtime managers, it records and validates their configured flag, CPU device, AMP/FA3 flags, and offload enum names; it checks the same state after the adapted call. The pinned `InferenceManager.configure` normalizes auto to `OffloadMode.AUTO` and false to `OffloadMode.GPU` (`inference.py:656-680, 797-826`).

The source establishes the candidate slicing axis and forwarding contract, not tolerance-level numerical equivalence. That remains an execution question for the one bounded synthetic pair. The adapter rejects an unrecognized tensor input instead of guessing whether it is shared or sliced; it slices `y_train` only when its shape exactly matches the source-expanded feature axes and FIT sequence. It preallocates one output and copies each chunk into its original position, including the final short chunk.

## Authored files and intended behavior

| Authored file | SHA-256 | Behavior |
|---|---|---|
| `rounds/round_007/code/column_chunk.py` | `BF263BA75BEF5ED9AAB04364459E426F3A82BE92DA2CE642E89B06558FD9CDED` | Fixed chunk-16 column/group adapter, narrow target alignment, original manager preparation/forward, output preallocation, reversible column-only installation, configure forwarding |
| `rounds/round_007/code/test_column_chunk.py` | `44B3AE7F56560EFD05268D8A0D253128CF1BE78178BCE4D0DCB75F1E3D602A32` | Standard-library pure mock using a fake tensor/manager; no torch import; checks order, 16+remainder, target alignment, retained sequence/table axes, output_repeat, unsupported/malformed inputs, configure/install/call/restore |
| `rounds/round_007/code/synthetic_pair.py` | `67F74942B38C4C2EE42C6A0509C39997828C0E98658BC04ADB2CA96850F445B3` | Synthetic-only result process: atomic JSON at stages and per chunk event, pinned environment/checkpoint verification, fixed input hashes/settings/shuffles, one estimator fit, baseline then adapted predict on same estimator, finally restoration, input/shuffle pre/post checks, runtime manager validation, 1e-5/range/row-sum/argmax gates, NPZ of synthetic arrays and probabilities |

The script finds the project root by locating `STATUS.json` and `AGENTS.md` among the snapshot's ancestors, so it remains usable from the manager's source-copy directory. It refuses to overwrite the fixed result or NPZ artifact. It checks hashes for X_fit, y_fit, and X_query immediately before and after each prediction and compares the fitted shuffle state around each call; both calls must use the original recorded hashes/state. Result data is limited to the deterministic synthetic inputs, their hashes, and their two synthetic probability arrays.

## Current limitations and handoff

- This author did not execute the pure mock or the model pair. Their outcomes, measured RAM, chunk call shapes, probability differences, and gate status are unknown here. The reviewer/manager owns those authorized bounded steps. This source note must not be read as test approval or a model-equivalence result.
- The synthetic baseline is deliberately first. It configures the original manager before adapter installation; the adapted call then invokes the same manager's configure method through the wrapper. A future path that installs before any embedding configure must explicitly configure the original column manager from the fitted estimator's `inference_config_.COL_CONFIG` before install and verify CPU, or add and review a separately tested lazy-install contract. Do not use a full-context baseline prediction just to configure it.
- Chunk-16 is a hypothesis about intermediate memory, not proof of total-memory reduction. The synthetic pair cannot establish the full 3,144-row context's peak RAM, actual-data replay equivalence, official score, F1, or ship-classification performance. Exact equality and tolerance/argmax gates are recorded separately; the 1e-5 threshold is fixed and must not be widened after a failure.
