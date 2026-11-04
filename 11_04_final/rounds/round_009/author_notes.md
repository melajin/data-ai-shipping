# Round 009 code author notes

## Scope and execution boundary

Owned only `rounds/round_009/code/*`, `rounds/round_009/manager/run_bounded.py`, and this note. The column adapter was copied from round008 and verified byte-identical by SHA-256. No earlier round, installed package, source dataset, venv, checkpoint, or manager execution artifact was modified by the author.

Requested setting: `gpt-6-luna` / `xhigh` / `fork_turns=none`. The recorded host evidence in `rounds/round_009/manager/assistant_host_evidence.json` lists request model/effort `gpt-6-luna` / `xhigh` and turn-context model/effort `gpt-6-luna` / `xhigh` for this author session. This is session metadata, not internal model attestation.

I did not run the pure mock, load TabICL or PyTorch, load the checkpoint, generate the synthetic arrays, fit an estimator, call `predict_proba`, read project feature/label arrays, or run a model. I performed read-only source inspection and AST syntax parsing of the four authored Python files using system Python. All four AST parses succeeded. No mock, model, data-equivalence, memory, or hardware result is claimed.

## Sources and independence basis

Read `AGENTS.md`, `NEXT_SESSION.md`, round008 author notes, round008 `review/SOURCE_REVIEW.md`, round008 `POST_COLUMN_SOURCE_AUDIT.md`, round007 `code/synthetic_pair.py` and column adapter, and round008 `manager/run_bounded.py`. The independent round009 source review records the pinned source hashes and line evidence in `rounds/round_009/review/SOURCE_REVIEW.md`.

The source review establishes that ROW receives `(B,T,H+C,E)`, performs attention over the per-row `H+C` token sequence, and returns `(B,T,C*E)`. `B,T` are leading batch axes. ICL instead consumes full `T` with FIT labels in context; the script leaves ICL, the estimator head, precision, global classes, and the environment unchanged. Source independence supports slicing ROW's `T` axis for this local comparison; it does not prove bitwise equality, memory reduction at `T=3146`, or identify the allocation that stopped round008.

| Source | SHA-256 | Use |
|---|---|---|
| `rounds/round_008/code/column_chunk.py` and copied `rounds/round_009/code/column_chunk.py` | `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded` | Exact byte-copy of the reviewed fixed column-chunk-16 adapter |
| Pinned `interaction.py` | `6f35b5a70cd7b7ea44286faa8921b64c2c83aca8ed49a4ad8b287abe54cbf27` | ROW shape, sequence-axis behavior, manager input |
| Pinned `encoders.py` | `a3e0e9bde47e7f587c4a196d124ea631e25755d4f5ac5d6a8568618a4e299a4e` | Transformer sequence and leading batch axes |
| Pinned `attention.py` | `2406a52571ce33392b003aca185550bc33a8e55797de72bdbf8b4449b09e66f8` | Attention dimensions and leading-batch handling |
| Pinned `inference.py` | `f9e3cf0d83047e06df7d6763bb8d8ee7a00ff1ba6708299a14635831f60ba4fc` | CPU forwarding, input preparation, and forward wrapper |
| Pinned `learning.py` | `7549dff09c3796a3cb0b55ea03e249342392fa601a681526f7b1efb6a6f1eef2` | Full-T ICL and post-forward query slicing |

## Implemented behavior

- `code/row_chunk.py` wraps only the fitted estimator's `model_.row_interactor.inference_mgr`. It requires the already configured CPU `tf_row` manager, slices `embeddings` only on axis 1 in chunks of 8, keeps `B`, `H+C`, and `E` intact, and concatenates each output slice in original row order. It delegates `configure`, `_prepare_inputs`, and `_run_forward` to the original manager, preserves `auto_batch=False` delegation and `output_repeat`, logs shape/chunk events, rejects unknown shape-bearing inputs and unsupported output contracts, and exposes an instance-only restore handle.
- `code/test_row_chunk.py` is callable as a pure standard-library fake-manager script. Its cases cover incomplete tail chunk and order, B/T/sequence/width shapes, manager configuration, output-repeat reporting/forwarding, preservation of shared values and input data, invalid input/output contracts, dtype changes, error propagation, and restoration. It imports neither torch nor numpy. It has not been run by this author.
- `code/synthetic_pair.py` retains the round007 fixed synthetic contract: `default_rng(20261105)`, standard-normal float32 FIT `(32,312)`, query `(2,312)`, labels `tile(arange(4),8)`, the pinned checkpoint/runtime/settings. It configures the original column manager with the fitted estimator's unchanged `COL_CONFIG` before installing the byte-identical chunk-16 adapter. It performs exactly two `predict_proba` calls on the same fitted estimator and ordered arrays: baseline with COL-16/native ROW, then candidate with COL-16/ROW-8. The native baseline prediction configures the original ROW manager before the row adapter is installed. It compares finite/range/row-sum checks, exact equality separately from maximum absolute probability difference `<=1e-5`, and argmax equality. It records fingerprints, shuffle and manager state, adapter chunk events, and restores the local row then column managers in `finally` before persisting final restoration diagnostics. The ICL manager identity is checked and left unchanged.
- `manager/run_bounded.py` is round009-local. It reads `review/approved_sources.json` with schema `round009_approved_sources.v1`, checks the full SHA map, snapshots the approved round009 code, and binds `mock` to `test_row_chunk.py` and `synthetic_pair` to `synthetic_pair.py`. It limits mock attempts to `mock_01` and at most one ordered `mock_02` retry, each 30 seconds total with 2 seconds for cleanup. It requires a successful mock receipt for the exact same approved SHA map before the one `pair_01` run. The pair gets 300 seconds total (290 compute, 10 cleanup), a one-time claim, a 3 GiB launch gate, three threads, and a 1.5 GiB available-RAM stop threshold. Process ownership tracks PID plus creation ticks and Windows running state; the just-launched root identity is collected immediately after `Popen` before the running-receipt write, and cleanup targets only matching owned identities.

## Frozen source hashes and actual results

| Authored file | SHA-256 |
|---|---|
| `rounds/round_009/code/column_chunk.py` | `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded` |
| `rounds/round_009/code/row_chunk.py` | `d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b` |
| `rounds/round_009/code/test_row_chunk.py` | `1a134ff544b5c67efb813417322e3304317ccd4fc2136d85650ef36c72d86ee0` |
| `rounds/round_009/code/synthetic_pair.py` | `dcf056bb5772a1bd31b17194ed680655e427b9914ddef953eb7b291723213c19` |
| `rounds/round_009/manager/run_bounded.py` | `56a42a14b987da1c2f4afb077d640183265f2d2b8f2afc3730df66469d7a9dfe` |

The column adapter hash matched the round008 source hash exactly. The static AST parse passed for `row_chunk.py`, `test_row_chunk.py`, `synthetic_pair.py`, and `manager/run_bounded.py`. The independent reviewer has the frozen hashes and is preparing its source/mock review and approval manifest. At author handoff, mock execution, the synthetic pair, their receipts, observed memory/time, probability values, and restoration results remain unknown. The author did not run them.

Any passing synthetic pair will show only that this tiny fixed synthetic comparison met its frozen execution gates. It will not establish memory savings for full-context `T=3146`, F1, real-data equivalence, learner understanding, or hardware behavior.
