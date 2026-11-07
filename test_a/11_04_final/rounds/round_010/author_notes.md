# Round 010 code author notes

## Scope and provenance

Owned only `rounds/round_010/code/*`, `rounds/round_010/manager/run_bounded.py`, and this note. The column and ROW adapters are byte copies of the reviewed round009 sources. New files and runtime outputs are round010-local. No prior round, installed environment, source dataset, checkpoint, copied input, review artifact, or manager-owned plan/execution document was modified.

Requested author setting: `gpt-6-luna` / `xhigh` / `fork_turns=none`. `rounds/round_010/manager/assistant_host_evidence.json` records the host-reported author turn context as Luna/xhigh; this is host metadata, not internal model attestation.

Read-only sources used: root `AGENTS.md` and `NEXT_SESSION.md`; round009 author notes, source review and approved sources; round008 author notes, source review and `code/replay_inner_pilot.py`; round009 `code/column_chunk.py`, `row_chunk.py`, `test_row_chunk.py`, `synthetic_pair.py`, and `manager/run_bounded.py`; and pinned TabICL source text for `learning.py` and `inference.py`. The round009 review pins `learning.py` at SHA-256 `7549dff09c3796a3cb0b55ea03e249342392fa601a681526f7b1efb6a6f1eef2` and `inference.py` at `f9e3cf0d83047e06df7d6763bb8d8ee7a00ff1ba6708299a14635831f60ba4fc`.

## Implemented contract

- `column_chunk.py` and `row_chunk.py` preserve the exact approved round009 bytes. Their SHA-256 values are respectively `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded` and `d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b`.
- `replay_inner_pilot.py` is rooted in round010 and pins the copied context and query-freeze hashes, ordered IDs `[36001915, 31703435]`, digest, checkpoint, runtime contract, and both adapter hashes. It keeps the round008 reference reader contract: read the CSV header plus only the first two data rows, verify ordered IDs, parse only `rfid_id` and `p0..p3`; it never accesses `y_inner`.
- The single fitted estimator uses the existing TabICL settings and exactly one checkpoint/context fit and one `predict_proba` call. Immediately after fit, the original COL and ROW managers receive the unchanged resolved `COL_CONFIG` and `ROW_CONFIG`, before either adapter is installed. Both adapters remain instance-local.
- `icl_observer.py` transparently forwards the existing ICL manager call, configuration and return value. It does not invoke another forward or change inputs. Static inspection of pinned `learning.py` established the call mapping is `R` plus `y_train`; `train_size` is inferred from `y_train.shape[1]`. The observer validates full `R` row count 3146 and FIT size 3144, and records entry/completion inside that existing call. ROW events record call entry/completion and per-chunk boundaries in append-only `progress.jsonl`; the result JSON stores bounded counters and the latest/last-completed boundary rather than rewriting an expanding event list on each chunk.
- All adapter and observer installation plus prediction diagnostics are inside a `try/finally`. Restoration attempts run in reverse installation order, continue after an individual restore error, and finish before the restoration diagnostic is written. The comparison separately reports exact equality and the fixed historical tolerance `1e-4`, and gates finite/range, `2x4`, class order, row sums `<=1e-5`, both argmax values, unchanged inputs/shuffle state, full ICL context, and restoration.
- `test_adapter_pair.py` is a callable standard-library fake-manager suite. It covers COL+ROW coexistence, config forwarding, short tails and order, unknown tensors, injected failures and restoration; it also verifies ICL call transparency and full-context acceptance/rejection using `R`/`y_train` shapes.
- `manager/run_bounded.py` binds only `mock` and `pilot`, applies 30 seconds total for each mock (2 seconds cleanup) with one ordered correction retry, and a 480-second pilot cap (470 seconds compute + 10 seconds cleanup). Pilot launch requires at least 4 GiB available RAM; runtime stops below 1.5 GiB. It requires the exact approved SHA map and a successful mock receipt before claiming the single `pilot_01`; it rejects a second pilot and blocks `mock_02` after a successful first mock. The bounded wrapper must itself be in the approved map; both its executed file and snapshot are hash-checked. PID+creation-time/running-state ownership, exact `Popen` handle fallback, and unverified descendants are retained from round009.

## Static checks and actual results

AST parsing with system Python succeeded for all six code/wrapper files. This is syntax-only evidence. I did not execute the pure mock or wrapper, import torch/NumPy/TabICL, open or read NPZ/reference arrays, load the checkpoint, fit an estimator, call `predict_proba`, read source-dataset rows, run OUTER/holdout/F1, or perform hardware experiments. The model probability result, real-context resource peak, manager process receipt, and restoration outcome remain unknown until independent source approval and the manager-authorized runs. The full-path peak requirement is not measured; the previous interrupted run's sampled peak near 2.96 GiB is not an upper bound.

The manager reported an available-RAM preflight of 4.5367 GiB at 2026-11-04 19:52 UTC; it was not a pilot measurement. The round010 paths and code hashes at handoff are:

| File | SHA-256 |
|---|---|
| `rounds/round_010/code/column_chunk.py` | `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded` |
| `rounds/round_010/code/row_chunk.py` | `d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b` |
| `rounds/round_010/code/icl_observer.py` | `73770185e12662b3c589a24736fc12af7c7673b09c296ea62c9eb12763a2659b` |
| `rounds/round_010/code/test_adapter_pair.py` | `460bf6aa7c42cdc089d897a162331a2dd2a630ed2e8212abe18e2f93e955dbf6` |
| `rounds/round_010/code/replay_inner_pilot.py` | `488b7e935188e803651ea018a57dbbeb69eb85843041df13a043300e58c28aa0` |
| `rounds/round_010/manager/run_bounded.py` | `c1d595c94641e81c1e930a216a448013709fd58050cc32d5e31d84251df38867` |

The reviewer is independently checking this candidate and owns the approved source manifest. No independent source approval or run receipt is claimed in this author note. A passing fixed two-query replay would only establish that this declared replay gate passed; it would not establish F1, general model performance, full-context memory reduction, learner understanding, or hardware behavior.
