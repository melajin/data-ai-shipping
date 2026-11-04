# Round 009 — pinned ROW source gate

**Decision:** Source inspection supports a fixed chunk of ROW's leading row-batch axis `T`, while preserving each row's complete feature/register-token sequence. Keep the ICL sequence over all `T` rows whole. This approves implementation and pure-mock work only; it does not approve model execution until the author sources and wrapper are independently reviewed and hashed into `approved_sources.json`.

## Scope, method, and provenance

Static text and SHA-256 inspection of the pinned TabICL sources only. I did not import the package, PyTorch, or the estimator; run a model, mock, or test; open NPZ/input arrays; or inspect actual features, labels, OUTER, or holdout data. The round008 saved source audit and reviews, NEXT_SESSION, AGENTS, and current round plan were also read as planning evidence. Source review time: 2026-11-04 19:07 UTC. Available RAM at that static-review point was 3.9213 GiB of 13.8094 GiB (Windows OS report); only small source and metadata files were read.

Requested reviewer setting: `gpt-6-luna` / `xhigh` / `fork_turns=none`. The manager's `rounds/round_009/manager/assistant_host_evidence.json` records a Luna/xhigh turn context for this reviewer. Host metadata is evidence of reported session settings, not internal model attestation.

## Independent-axis reasoning

1. `tabicl.py:415–440` derives `train_size`, calls `col_embedder`, passes its completed result to `row_interactor`, and only then invokes `icl_predictor`. This gives the ordering; it does not itself prove the row-axis contract.
2. `interaction.py:111–168` declares row input `(B,T,H+C,E)`. Its transformer blocks run over this tensor; the last block queries the class-token prefix while keys/values cover the full final axis `H+C`. `out_ln` is either `LayerNorm(E)` or identity, applied only to each returned class-token embedding, then the class-token and embedding axes are flattened to `(B,T,C*E)`.
3. `interaction.py:215–253` configures `row_interactor.inference_mgr` and calls it with only `OrderedDict([("embeddings", embeddings)])`. It does not use `T` to build a mask or shared row statistic in this inference path. The preceding class-token replacement is indexed `embeddings[:, :, :num_cls]` and is local to each `(B,T)` row.
4. `encoders.py:120–147` accepts `(..., seq_len, d_model)`. `layers.py:345–353` uses batch-first attention blocks. Its pre-norm branch applies `LayerNorm(d_model)` to the last embedding axis; attention itself receives the full `(..., seq_len, d_model)` row. `attention.py:232–303` extracts all dimensions before the final `(tgt_len, embed_dim)` as batch shape, preserves them, and computes attention along `tgt_len`/`src_len`. `sdpa_with_flattened_batch` flattens those leading batch dimensions for the kernel, then restores them. Thus `B,T` identify independent batches of rows; `H+C` is the attention sequence and is not to be chunked.
5. The CPU runtime does not auto-split this ROW call: `inference.py:1210–1232` prepares tensors on the configured execution device and `_run_forward` preserves `no_grad`, Flash Attention toggle, and optional AMP; `inference.py:1288–1298` sends configured CPU work through one `_run_forward(_prepare_inputs(inputs))`. A local wrapper must call the original manager's `_prepare_inputs` and `_run_forward` for each row slice to preserve those semantics.
6. ICL has a different contract. `learning.py:241–282` encodes FIT labels, adds them to `R[:, :train_size]`, then runs `tf_icl(R, train_size=train_size)` across full `T`. `learning.py:326–339` slices away the FIT portion only after the manager returns. Chunking ICL along `T` would remove or alter each query's FIT context and is not covered by the ROW independence result.

Therefore a candidate adapter may split only the ROW manager's `embeddings` tensor on dimension 1, concatenate output slices in original order on dimension 1, preserve full dimensions 0 and 2 onward, and reject any unsupported key/value/shape. `rowchunk=8` and the short tail require pure-mock coverage. The adapter must remain attached only to the fitted instance's `row_interactor.inference_mgr`, delegate configuration to the original manager, and restore that instance's manager in `finally`.

## Limits and required follow-up

The source establishes structural independence of ROW examples, not bitwise equality under different kernel batch shapes. Batch-size-dependent floating-point execution remains possible, so the frozen synthetic pair must separately compare ROW output (if captured within the two existing predictions) and final probabilities using the already-fixed `1e-5` maximum absolute probability difference and equal argmax gates. No extra forward or `predict_proba` call is allowed. Tiny synthetic agreement does not establish memory safety or a memory reduction for `T=3146`; the full `(B,T,C*E)` ROW output and full-T ICL computation remain, and no actual-context run is authorized in this round.

The round008 pilot's last event is only a completed column-manager call. There is no ROW-start event, so this source result does not locate its RAM stop or prove ROW caused it. The round009 comparison remains the prescribed single small synthetic pair only after pure mock passes and exact source hashes match the approved manifest.

## Pinned source snapshot

All paths are relative to the worktree root. Hashes below were read from the local pinned environment; no package code was executed.

| Source | SHA-256 | Evidence lines |
|---|---|---|
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/tabicl.py` | `583786e5ffd70b9eb425bca8e52aed415dadcdf4254c908b3b6fa52026a56491` | 415–440: complete column → ROW → ICL order |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/interaction.py` | `6f35b5a70cd7b7ea44286faa8921b64c2cc83aca8ed49a4ad8b287abe54cbf27` | 111–168: ROW sequence/output; 215–253: configuration and single `embeddings` manager input |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/encoders.py` | `a3e0e9bde47e7f587c4a196d124ea631e25755d4f5ac5d6a8568618a4e299a4e` | 120–147: `(..., seq_len, d_model)` and block iteration |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/layers.py` | `96cce2e84db33e176d872c7bb7c0df8c305de3eb7a02fcad9f1128f33d319d95` | 345–353: batch-first block; 442–472: per-token embedding-dimension normalization and attention |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/attention.py` | `2406a52571ce33392b003aca185550bc33a8e55797de72bdbf8b4449b09e66f8` | 49–130: flatten/restore leading batch axes; 232–303: sequence and batch dimensions |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/inference.py` | `f9e3cf0d83047e06df7d6763bb8d8ee7a00ff1ba6708299a14635831f60ba4fc` | 1210–1232: preparation and forward context; 1288–1298: CPU single-call path |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/learning.py` | `7549dff09c3796a3cb0b55ea03e249342392fa601a681526f7b1efb6a6f1eef2` | 241–282: full-T ICL with FIT labels; 326–339: query slicing after forward |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/embedding.py` | `a0c562600fe22944f91b1b71b706198cb9a4c3d9d8aaba67a86f35a85493d322` | 580–638, 679–734: column inputs and completed embedding shape, consistent with round008 audit |

Requested model/effort and host turn-context evidence are recorded separately, following project policy. This source review does not claim model performance, resource savings, or hardware validation.
