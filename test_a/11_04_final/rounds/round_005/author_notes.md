# Round 005 code author notes

## Scope and ownership

Authored only `rounds/round_005/code/build_context.py`, `rounds/round_005/code/replay_inner_pilot.py`, and this note. The bounded launcher is owned by the manager. No shared status, ledger, or report file was edited here.

The task requested GPT-6 Luna with xhigh effort. The delegated task specified that model and effort; this author has no separate host-turn metadata to verify beyond that request and does not claim that a parent session setting changed.

## Source and data evidence used

- Read the root `AGENTS.md`, `CYCLE_PROTOCOL.md`, `NEXT_SESSION.md`, round004 context recovery candidate/readiness/result, `review/context_precheck.json`, and `runtime_author/replay_contract.json`.
- Read only approved source code, runtime package source/metadata, ID-only split metadata, and allowed development-only manifests. Used `rounds/round_003/verification_20261105/v4_idhash.json` as the already-produced hash evidence; did not rerun its search or open prediction data during context export development.
- The exporter binds exact P and exp01 roots, pinned hashes from reviewed evidence, the split manifest and parent/frozen-rule linkage, the fold0 role partition, development NPZ membership, canonical labels, and the independently established vocabulary hash convention.
- Frozen-rule FIT/INNER membership uses numeric-sorted normalized integer IDs joined by LF with no final LF. Ordered source-list JSON digests are stored separately. Vocabulary FIT membership uses the sorted-string `BASE.digest_json` contract confirmed in `vocabulary_features.py`.
- The pilot verifies `query_freeze.json` and the context binding before reading only the first two ordered INNER probability rows. It uses FIT features/labels for pretrained context binding, does not access INNER labels, and makes one `predict_proba` call for two queries. The reference reader parses only the ID and p0–p3 fields; selected source lines may contain unparsed trailing columns, and labels are not used. It reports probability validity, per-query differences, argmax agreement, and the fixed 1e-4 gate; it does not compute F1.

## Changes and checks

- `build_context.py` preserves FIT/INNER source order, checks FIT/INNER/OUTER uniqueness, disjointness and exact development-set union, checks holdout ID metadata count/type/uniqueness and disjointness, transforms saved FIT medians plus raw missing flags to 312-column float32, and atomically writes an attempt-scoped context NPZ, a two-ID freeze file, and a manifest. It captures source/settings/input/output hashes and sample imputation/missingness evidence.
- The reviewer first approved exporter hash `DAB03947C274179C247EB74EB13B3AE3180E3879D3A985CB10EE3B3915AEDC73`. The subsequent recorded source edit renamed the stdout summary from a hard-coded `inner_order_match` field to `ordered_inner_ids_preserved` plus a computed frozen-membership match. The manager then executed the immutable source snapshot `08F4808238C3D613FD616C7D7B4D07A30CF20B806F8361828F3C7ACAAACE550D` once. The manager reported exit success in 2.672 seconds; outputs are in `artifacts/context_export_attempt_001/`. The independent context verifier passed according to the manager. This author did not run the exporter, and no second run is planned.
- A patch was initially applied one directory above `11_04_final`; the authored file was moved into the intended root. The manager verified and removed the resulting empty outside-root directories. No authored file remains outside `11_04_final`.
- Both owned Python files were parsed with the pinned environment's Python 3.12 using `ast.parse` only. This was a syntax check, not a test. No package/model import, checkpoint load, pilot, F1, or training was performed by this author.

## Current hashes and remaining checks

- `build_context.py`: `08f4808238c3d613fd616c7d7b4d07a30cf20b806f8361828f3c7acaaace550d`.
- `replay_inner_pilot.py`: final reviewed source `b57f6c764d4b833451714d4dfcfa328ed3facecaf6f9a93a0198da8b17c4b860`.
- The manager launched an immutable B57 source snapshot at 2026-11-04 17:44:18 UTC after the reviewer-requested runtime gates were added. The manager reported 3.57 GiB available RAM at launch and later reported the child ended with the validator `AttributeError` described below. This author did not launch or import the model.
- The independently verified context exporter result does not establish model performance, CPU/CUDA equivalence, independent validation, official score, hardware behavior, or learner understanding.

## Pilot failure diagnosis (source-only)

The manager later reported that the B57 child exited with code 1 after 24.125 seconds. The resource monitor saw at least 3.077 GiB available RAM during the child; no timeout or RAM kill occurred. The child result records the two fixed reference rows as verified, package import complete, and stage `checkpoint_fit_context_bind_start`. Its traceback is at `validate_resolved_inference_state` after `estimator.fit(...)` returned. It reports `predict_proba_attempted_count=0`, `predict_proba_completed_count=0`, no model probability output, and no F1. The child-local elapsed value is 21.812 seconds; the manager's 24.125 seconds is the wrapper's process-level elapsed measure.

The failure is a validator lifecycle assumption, not evidence of a TabICL inference or resource failure. Installed TabICL 2.2.0 `classifier.py` sets `model_kv_cache_ = None` during `fit`, and assigns `cache_mode_` only inside `if self.kv_cache:`. With the contract's `kv_cache=False`, the estimator has no `cache_mode_` attribute. The pilot had already passed its device, parameter/buffer dtype, and resolved stage checks; it then directly read `model.cache_mode_` while building the recorded estimator-scope dictionary, raising `AttributeError` before `predict_proba`.

Round 005's one-pilot allowance is consumed. Do not rerun it or modify the frozen B57 source/attempt. For a later round, the narrow code correction is to use `cache_mode_present = hasattr(model, "cache_mode_")` and `cache_mode = getattr(model, "cache_mode_", None)`, while accepting an absent/None mode when `model.kv_cache is False` and `model.model_kv_cache_ is None`. Record both presence and value. Rename `settings.predict_proba_calls` to `max_predict_proba_calls` so the allowed-call cap is clearly distinct from the actual attempted/completed counters.

Before a later fixed-query pilot, exercise only the validator with a pure mock estimator that has no `cache_mode_`, has `kv_cache=False`, `model_kv_cache_=None`, and the reviewed CPU/AMP/FA3/offload `MgrConfig` stage values. Assert it passes and records absent cache mode. A second pure mock with cache enabled should fail the no-cache guard. This requires no package/model import or checkpoint load. If that passes, the manager may propose a new bounded round using the existing frozen context and same two query IDs; do not select new queries or reuse the round005 attempt directory.
