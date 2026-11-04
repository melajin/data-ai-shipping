# Round 008 code author notes

## Role, scope, and execution boundary

Authored only the round008 code and bounded wrapper assigned to this Luna author: `code/replay_inner_pilot.py`, `code/column_chunk.py`, `code/test_configure_before_install.py`, `manager/run_bounded.py`, and this note. The column adapter was copied byte-for-byte from round007. The manager owns the frozen input copies, execution, state, logs, and final report. The independent reviewer owns review artifacts and `manager/approved_sources.json`. I did not alter those files or prior-round sources.

Requested author setting: `gpt-6-luna` / `xhigh` / `fork_turns=none`, as assigned by the manager. This note does not claim the parent host model or effort changed, and I do not have separate host turn-context evidence for this subtask. The project manager records its own host evidence.

No mock or model program was executed. I did not import torch, load the checkpoint, read round008 input arrays or historical probability rows, fit an estimator, call `predict_proba`, or train model parameters. I performed only read-only source inspection, SHA-256 reads, and an AST syntax parse of the four authored Python files with system Python 3.13.3150.1013. All four parsed successfully. This is a syntax check, not a mock, model, data, or hardware validation result.

## Read-only source evidence

SHA-256 values below are from the work root unless an installed package path is shown.

| Source | SHA-256 | Evidence used |
|---|---|---|
| `AGENTS.md` | `08fa7dd4edf239910b8f000db2176589f87178aa9e911d31e1b627ab535a7dfc` | File ownership, data restrictions, bounded execution and RAM rules |
| `NEXT_SESSION.md` | `13d442b4afb7898d97b6dead4a8fe0aeec61ac5e7a037596911257b026eb85c9` | Frozen round008 input, model, limits, gates, and source requirements |
| `rounds/round_008/ROUND_PLAN.md` | `355d7a60003b851fdf3d3b485d82227d7f9088c597a29dc621dff47703beef60` | Scope, thresholds, ownership, execution limits, and learner questions |
| `rounds/round_006/code/replay_inner_pilot.py` | `a4d10bba93f3fe07ea7188aba216c1211e13eba24cec334fc19d7b985d681505` | Frozen settings, input handling, reference-row reader, model-state checks, comparison calculation |
| `rounds/round_007/code/column_chunk.py` | `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded` | Fixed 16-column adapter, target alignment, original manager forwarding, reversible install |
| `rounds/round_007/manager/run_bounded.py` | `2820871e8884a0fd642e550301154c16039d6c85c6168bda32cbf67340f3bee4` | Corrected process-identity and root-process completion checks used as wrapper starting point |
| `rounds/round_004/runtime_author/replay_contract.json` | `819e60fd2f05a655a86dc1cdaa5e52f5a4fd0486e78fdd5dc5a4ab140ad7e2f5` | Historical model/runtime contract |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/embedding.py` | `a0c562600fe22944f91b1b71b706198cb9a4c3d9d8aaba67a86f35a85493d322` | `ColEmbedding` configures its inference manager at the start of inference (`configure(**mgr_config)`, lines 565–568) |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/inference.py` | `f9e3cf0d83047e06df7d6763bb8d8ee7a00ff1ba6708299a14635831f60ba4fc` | Manager configuration resolves device, AMP, FA3, offload enum, and configured state |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/inference_config.py` | `852abb9cf97e9c82ae42a92b034581f6e9131f3bec70efbd3ce068ac92a77a37` | `MgrConfig` exposes mapping-style items/keys for the pinned `configure(**COL_CONFIG)` call |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_sklearn/classifier.py` | `64f5ef7ef88a920a3f7a5f6e2d9d8dc08769ec343e931f910acc2d9c4eaa5534` | Estimator fit and prediction call path |

The manager verified the byte-copied context and query-freeze inputs against the frozen hashes before this author turn. The pilot source independently pins those hashes plus the ordered IDs and digest so a different copied input or query order hard-fails. Only the existing first-two-row historical probability reader is retained; it does not search or reorder. No input values were read during implementation.

## Implemented behavior

| Authored file | SHA-256 | Behavior |
|---|---|---|
| `rounds/round_008/code/column_chunk.py` | `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded` | Exact byte copy of the reviewed round007 chunk-16 adapter |
| `rounds/round_008/code/replay_inner_pilot.py` | `112ca09e7abba9c194421c22bd38771563636e2852c867c089cb27e985c39b0d` | Round008 paths and schema; hard-pinned context/freeze/query values; preserves round006 estimator, two-query, and probability checks; configures the original column manager from the estimator's unchanged resolved `COL_CONFIG`, checks CPU/FP32/offload state, then installs only the column adapter and performs one prediction call; `finally` restores before persistence |
| `rounds/round_008/code/test_configure_before_install.py` | `470563dc44be46970f49c9142b393f5fd587dd96d3e57494e3b25e0d57a193b6` | Standard-library fake estimator/tensor/manager flow asserting fit-state → original configure → adapter install → configured chunked call → `finally` restoration; callable fake-manager protocol delegates through preparation and forward; no model imports |
| `rounds/round_008/manager/run_bounded.py` | `6962c94fa07a36cd7b3429eaeb27ac851aee3104e9b77758d7a99c0fc1a48e1d` | Round008 wrapper with `mock`/`pilot` kinds, default script selection, 30s/420s total limits, pilot cleanup reserve of 10s (410s compute bound), one-pilot claim, min-start-RAM gate, thread cap, source verification/snapshotting, adapter co-snapshot requirement, and process-tree tracking by PID plus creation time and running state; root creation identity is captured before the first receipt write |

The pilot writes an atomic result record before loading the checkpoint, then records stages for manager configuration, adapter install, prediction, and restoration. The adapter event callback persists each call/chunk start and completion. `current_chunk` records the active column interval before a forward; `last_completed_column_chunk` survives later interruption. The prediction path also records pre/post array hashes, ensemble shuffle state, runtime manager states, and ROW/ICL manager identity checks. Restoration runs in `finally` around the only `predict_proba` call. Source snapshotting requires the adapter alongside the selected pilot or mock script so the adjacent-module import resolves from the snapshot directory.

## Expected result and unknowns

The code implements the fixed round008 gate: one 3,144-row context fit, one `predict_proba` call for the frozen two INNER queries, four output probabilities per query, row-sum tolerance `1e-5`, and historical maximum absolute probability difference `1e-4` with both argmax values matching. Exact numeric equality and tolerance acceptance remain separate recorded fields. No F1 or performance score is computed.

The pure mock result, independent source approval, actual pilot result, actual memory peak, chunk shapes, elapsed time, child process exit, and restoration outcome are unknown at author handoff because those manager/reviewer stages have not been executed. AST parsing passed. No actual-data equivalence, full-context memory reduction, learner understanding, hardware behavior, independent score, or official score is claimed. A passing two-query replay would only verify this fixed probability-reproduction gate and would not establish F1 or authorize M4 by itself.
