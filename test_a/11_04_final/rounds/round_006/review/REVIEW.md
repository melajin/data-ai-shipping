# Round 006 — Independent Precheck

## Decision

Static review approves one bounded mock invocation using the exact pilot source SHA `a4d10bba93f3fe07ea7188aba216c1211e13eba24cec334fc19d7b985d681505` and test SHA `237edc8867af5e1684d8ba99bd3cfd7c8d8aa1404e3956ecabaa10ef32a010b5`.

The pilot is conditionally approved only if that mock passes and the manager confirms the pilot source still has the approved SHA before launch. Any source change requires another exact-hash review. The reviewer did not run the mock, import TabICL/Torch, or load the checkpoint.

## Evidence reviewed

- Round005 final review, receipt, actual executed source snapshot, stderr traceback, and staged result.
- Pinned TabICL 2.2.0 classifier source in the existing round004 environment. Its `fit` assigns `model_kv_cache_ = None` and only assigns `cache_mode_` inside the enabled-KV-cache branch, explaining the round005 `AttributeError` when `kv_cache=False`.
- Round006 pilot source and exact diff from the round005 source.
- Round006 mock test, bounded wrapper, and bounded mock runner. No model imports or checkpoint reads are part of the mock test; the runner checks hashes and snapshots the exact files before its one 30-second call.

## Review findings

- The diagnostic records `cache_mode_` presence separately from its value. It accepts both absence and explicit `None`, while the other fixed CPU, AMP, FA3, offload, and KV-cache conditions remain enforced.
- `fit_returned` is saved immediately after `estimator.fit` returns and before post-fit validation, so a later diagnostic failure cannot erase evidence that fit returned.
- The initial recovery record and subsequent pilot records consistently use the round006 result schema. The frozen historical query schema remains round005 as required by the unchanged input.
- The source diff preserves the estimator constructor/settings, fixed context and two frozen query IDs, and probability/tolerance/argmax comparison logic.

## Scope and limits

This is a static source review. It does not establish that the mock passed, that the model pilot ran, that probabilities reproduced, or that inference meets any performance or F1 target. No protected data, holdout, Test2025, or full 7,372-row source was read.

Requested reviewer configuration was GPT-6 Luna xhigh. Host-turn evidence in `manager/assistant_host_evidence.json` also reports GPT-6 Luna xhigh; this is host configuration evidence, not internal model authentication.

See [precheck.json](precheck.json) for hashes and machine-readable disposition.
