# Round 008 post-column source audit

## Scope and method

This is a static source audit of the pinned TabICL package plus the round008 pilot's progress metadata. No model or torch import, forward call, test, or input-array read was performed. The pilot metadata contains shapes and event records only; no probability values or raw input values were read here.

## Pinned execution flow

1. `ColEmbedding` sends feature tensors through the column inference manager. In the feature-group path, the manager receives `(B, G+C, T, group_size)`; its output is converted back to `(B,T,G+C,E)`. In the ungrouped path, the manager receives `(B,H+C,T,1)` and the embedding layer similarly returns `(B,T,H+C,E)`. The public `ColEmbedding.forward` returns `(B,T,G+C,E)`. See `embedding.py:580-638,679-734`.
2. `TabICL._inference_forward` passes the completed column embedding output directly to `row_interactor`, then passes the resulting row representations and the original `y_train` to `icl_predictor` (`tabicl.py:416-442`).
3. `RowInteraction` receives `(B,T,H+C,E)`, configures its `tf_row` manager, and sends the whole embedding tensor to that manager (`interaction.py:111-123,215-253`). It transforms across the per-row feature/class-token sequence `H+C`, retains `B,T` as leading batch axes, and returns `(B,T,C*E)`. The pinned `Encoder` accepts `(..., seq_len, d_model)` (`encoders.py:120-145`); here the row sequence is `H+C`, so different rows have no ROW attention path between them. Thus per-row independence is supported by the source contract for the ROW transform.
4. This configured runtime is CPU. `InferenceManager.__call__` takes its CPU path through one `_run_forward(_prepare_inputs(inputs))` and does not apply accelerator auto-batching (`inference.py:1288-1298`). Therefore the CPU ROW manager has **no active chunk axis**: it forwards the complete `(B,T,H+C,E)` input in one call. `T` is a leading, theoretically sliceable independent-row axis for ROW, but the current CPU manager does not slice it.
5. ICL is not per-row independent. `_icl_predictions` adds encoded `y_train` to the first `train_size` representations and calls `tf_icl(R, train_size=train_size)` over the full `T` row sequence (`learning.py:241-282`). The standard prediction path slices away the FIT portion only after the ICL forward (`learning.py:284-337`). Naively chunking ICL over `T` would change its FIT-context attention and is outside this audit's proposed row-only comparison.

## Pilot evidence and diagnostic limit

The pilot result record (`rounds/round_008/artifacts/pilot_attempt_001/pilot_result.json`, SHA-256 `bb4b2b4b1ae3fd1c741eb2c43f47a162f98a0bc1a8b47bf64f438f6f01348547`) remained `STARTED`, `current_stage=predict_proba_start`, with one prediction attempted, zero completed, no probabilities, 30 adapter events, and no restoration event. Its last persisted event was `column_chunk_call_completed` for call 0: input shape `[1,223,3146,3]`, output shape `[1,223,3146,128]`, 14 column chunks, `T=3146`, `train_size=3144`. The last chunk covered columns `[208,223)` with input `[1,15,3146,3]` and output `[1,15,3146,128]`.

The wrapper receipt (`rounds/round_008/logs/pilot_01/receipt.json`, SHA-256 `e5a1a8be6ffa8f9c52a9a099c147a211056228b10783577fc38f8fb979ae1c0a`) records a RAM-guard stop at 25.64 seconds, available RAM minimum `1.3799629211425781 GiB`, sampled process-tree peak working set `3,182,952,448` bytes, child exit code 1, and no remaining owned processes.

**Proven:** the first column-adapter manager call completed all 14 chunks and returned the recorded manager output shape before the resource guard stopped the process. `predict_proba` did not complete and produced no probabilities. The adapter remains marked installed and not restored because the wrapper stopped the process before Python could reach its `finally` block.

**Not proven:** no ROW-start or ICL-start event is recorded. The guard may have followed later ColEmbedding assembly or a ROW allocation; ROW is a plausible next pressure point from the source call order, but the recorded evidence does not identify the allocation that crossed the RAM threshold. The event is the completion of one column-manager call; it does not independently record the return from all of `ColEmbedding.forward` or entry into `RowInteraction`.

## Source files and hashes

All paths are relative to `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`.

| Pinned source | SHA-256 | Relevant lines |
|---|---|---|
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/embedding.py` | `a0c562600fe22944f91b1b71b706198cb9a4c3d9d8aaba67a86f35a85493d322` | 580–638: grouped/ungrouped column-manager inputs; 679–734: embedding output shape |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/tabicl.py` | `583786e5ffd70b9eb425bca8e52aed415dadcdf4254c908b3b6fa52026a56491` | 416–442: column → ROW → ICL call order and configuration |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/interaction.py` | `6f35b5a70cd7b7ea44286faa8921b64c2cc83aca8ed49a4ad8b287abe54cbf27` | 111–123: ROW tensor shape/intent; 215–253: config, manager invocation, return shape |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/encoders.py` | `a3e0e9bde47e7f587c4a196d124ea631e25755d4f5ac5d6a8568618a4e299a4e` | 120–145: encoder sequence axis and leading batch axes |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/inference.py` | `f9e3cf0d83047e06df7d6763bb8d8ee7a00ff1ba6708299a14635831f60ba4fc` | 1288–1298: configured-manager check and CPU single-forward path |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/learning.py` | `7549dff09c3796a3cb0b55ea03e249342392fa601a681526f7b1efb6a6f1eef2` | 241–282: full-sequence ICL with FIT labels as context; 284–337: standard inference and post-forward query slicing |

## Candidate tiny synthetic comparison (not implemented)

If the manager approves a new synthetic-only gate, compare two normal full `predict_proba` calls on the same small synthetic fitted estimator and inputs:

- Baseline: existing COL chunk-16 path followed by the native full-`T` ROW call and one full-sequence ICL call.
- Candidate: the same COL chunk-16 path, with only the ROW input sliced along its independent `T` axis into chunks of 8 and concatenated, followed by one unchanged full-sequence ICL call.

Capture the existing ROW return tensor during each call (for example through an output hook); do not add standalone ROW or ICL forwards. Compare ROW tensors and final synthetic probabilities under a gate fixed before execution. This would test source-supported ROW batching equivalence and the changed allocation path on tiny inputs. It would not establish memory safety or probability equivalence for `T=3146`, and it would not justify another actual-data replay without a separate bounded plan.
