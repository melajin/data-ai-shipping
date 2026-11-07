# Round 006 code author notes

## Scope and ownership

Authored only `rounds/round_006/code/replay_inner_pilot.py`, `rounds/round_006/code/test_validate_resolved_inference_state.py`, and this note. The manager owns runtime execution and shared status/report files; the independent reviewer owns `review/`. No round005 file was modified. No protected or holdout data was read.

The task requested `gpt-6-luna` with `xhigh` effort and `fork_turns=none`. The manager host-evidence record confirms requested and host values both `gpt-6-luna`/`xhigh` for author thread `01a1a7b1-b022-7fb1-8b54-8c0cfb3c3d43`. I inspected `rounds/round_006/manager/assistant_host_evidence.json` (SHA-256 `94050301c95d6deccd88893d05fe4433ab8150cd7d456ddd826f2a8bedf1c0cc`); its recorded source is the author session JSONL under the Codex sessions directory. This evidence concerns the author thread and does not establish a change to the parent session setting.

## Source evidence and hashes

Hashes below are SHA-256 of the files read from the stated project root (`D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`).

| Source | SHA-256 | Use |
|---|---|---|
| `AGENTS.md` | `7669fde3225cbdf926164f72f2114b2fc38920ee8190cd98983ae287cf20f918` | Root constraints and role/source rules |
| `NEXT_SESSION.md` | `1dfb2d2549eb145decbd74501b5e0d80caf9c7492161469571edfec6d93f5d0c` | Round006 authorization, exact correction, mock scope and limits |
| `rounds/round_006/ROUND_PLAN.md` | `e7f4cea58267b1d3b6688b9c0dffc4328551d15436061e1804a9e53de3284152` | Frozen round scope and acceptance conditions |
| `rounds/round_005/author_notes.md` | `3d90944cb0fc9be85c45304c085a82f040b1ab1d0c34733368549cdcd9992a1e` | Prior pilot diagnosis and source-only evidence |
| `rounds/round_005/review/FINAL_REVIEW.md` | `a627214f3205ccf1e53ae08e6d32626c54087d6f8f04b9fb0ff05721a564de2f` | Independent prior failure findings |
| `rounds/round_005/logs/pilot_01/source/replay_inner_pilot.py` | `b57f6c764d4b833451714d4dfcfa328ed3facecaf6f9a0198da8b17c4b860` | Exact B57 source copied before the narrow patch |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_sklearn/classifier.py` | `64f5ef7ef88a920a3f7a5f6e2d9d8dc08769ec343e931f910acc2d9c4eaa5534` | Pinned TabICL 2.2.0 fit attribute lifecycle |
| `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_model/inference_config.py` | `852abb9cf97e9c82ae42a92b034581f6e9131f3bec70efbd3ce068ac92a77a37` | Pinned stage config contract and `.items()` representation |

Pinned-source observation: `fit` creates `model_kv_cache_ = None` unconditionally, then creates `cache_mode_` only inside `if self.kv_cache`. Device, inference configuration, model, class encoder/order, input dimensions and ensemble generator are created in the normal successful fit path. Therefore cache-mode absence is valid for the fixed `kv_cache=False` contract, while absent `model_kv_cache_` after fit is treated as a lifecycle/contract error.

## Changes

- Copied B57 byte-for-byte as the starting source and changed its `ROUND` path to `round_006`; the round containment error text follows it. The output record schema is named `round006_inner_pilot_result.v1`. The historical input freeze schema check remains exactly `round005_frozen_inner_queries.v1`; frozen IDs, inputs, checkpoint, estimator settings, shuffles, probability calculation and comparison tolerances were not changed.
- Replaced direct/ambiguous cache-mode access with `hasattr` plus `getattr`. The resulting telemetry records `cache_mode_present` and `cache_mode` separately, so absent and explicit `None` both pass while remaining distinguishable. It also records presence and None-state for `model_kv_cache_`; the pinned fit source guarantees this diagnostic exists.
- Immediately after `estimator.fit` returns, the source persists stage `fit_returned` with `fit_returned=true` and fit-row count, before device, dtype, resolved-config or shuffle diagnostics run. The later `checkpoint_fit_context_bind_complete` stage still means those checks passed.
- Added a pure mock check which parses the pilot AST and extracts only `resolved_inference_state` and `validate_resolved_inference_state`. It defines lightweight stand-in stage/model objects and covers cache-mode absent, explicit None, and rejected CPU, AMP, FA3, column/row/estimator offload, enabled KV, allocated KV state, missing required model cache state, and non-None cache mode. It has no TabICL, Torch, checkpoint, project-data, or model import path.

## Validation state and limits

The source-copy input hash was `b57f6c764d4b833451714d4dfcfa328ed3facecaf6f9a0198da8b17c4b860`. Current authored hashes before independent review are:

- `replay_inner_pilot.py`: `a4d10bba93f3fe07ea7188aba216c1211e13eba24cec334fc19d7b985d681505`
- `test_validate_resolved_inference_state.py`: `237edc8867af5e1684d8ba99bd3cfd7c8d8aa1404e3956ecabaa10ef32a010b5`

Both authored Python files were parsed with `ast.parse` only; this checked syntax without importing the pilot, test, model package or checkpoint. No mock test, package import, checkpoint load, pilot, model forward, probability replay, F1 computation or performance evaluation was run by this author. Syntax parsing is not a functional test. Model output, inference success, RAM/time cost and host model/effort remain unverified by this author.
