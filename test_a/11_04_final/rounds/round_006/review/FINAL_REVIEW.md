# Round 006 — Independent Final Review

## Result

The diagnostic mock passed, and the single approved pilot reached and completed FIT/context binding with the corrected optional-attribute telemetry. The manager stopped the process during the one `predict_proba` call when available RAM fell below the 1.5 GiB guard. No probabilities returned, so the two-query replay comparison remains unresolved. The pilot attempt limit is exhausted; no retry is permitted or recommended.

This is a **resource-guard stop**, not evidence that TabICL raised an OOM error or failed a completed inference. The application stderr is empty. The result record stays at `predict_proba_start`, with one attempted call and zero completed calls.

## Execution evidence

- The mock receipt reports PASS, exit code 0, and 0.656 seconds. Three tests covered absent `cache_mode_`, present-but-`None`, and ten invalid setting subcases. The mock imported no model package and loaded no checkpoint.
- The executed pilot snapshot SHA matches the approved source SHA `a4d10bba93f3fe07ea7188aba216c1211e13eba24cec334fc19d7b985d681505`; the bounded wrapper SHA also matches the reviewed wrapper.
- The pilot started with 4.2835 GiB available RAM, below the 600-second timeout, and lasted 27.594 seconds. The minimum observed available RAM was 1.3921 GiB and sampled owned-tree working set peaked at 3,160,498,176 bytes.
- It validated the fixed context and two frozen development INNER queries, imported TabICL 2.2.0/Torch 2.6.0+cpu, and fit the pretrained estimator on the 3,144-row FIT context. Post-fit checks recorded CPU FP32, canonical class order, and the expected resolved settings. They recorded `cache_mode_` absent and `model_kv_cache_` present-but-`None`, then persisted `predict_proba_start`.
- One `predict_proba` call was attempted. It did not complete. There are no output probabilities, row-sum/tolerance/argmax results, or replay-gate decision. No INNER labels, OUTER data, F1/accuracy, or protected rows were used.
- The immediate receipt saw two owned process identities during taskkill cleanup. A later identity and process-snapshot check found none; no additional termination was needed.
- At the user-requested 18:00:31 UTC RAM recheck, available memory had recovered to 4.2017 GiB and no new pilot was launched. Recovery supports independent source/documentation work; it does not establish full-context inference fits or reset round006’s one-pilot limit.

## Source-only observation and next scope

The pinned TabICL source routes CPU inference through one `_run_forward` call when `auto_batch=True`; its accelerator batch sizing path is bypassed. That gives a plausible direction for a fresh feasibility audit, but the pilot evidence does not prove which internal stage caused the memory growth.

Recommended next work is a separate, source-only audit of CPU prediction batching and possible safe slice boundaries. Preserve FIT rows, sequence axes, feature order, shuffle state, and ensemble semantics. If source inspection proves a safe independent batch boundary, design one small synthetic equivalence check under bounded resources before any actual-data replay. Stop if equivalence cannot be established. Do not repeat round006 or treat this run as an F1/performance result.

The seasonal hypothesis in [SEASONAL_HYPOTHESIS.md](../SEASONAL_HYPOTHESIS.md) is separate. It was not validated by this pilot and does not alter this replay result.

## Scope and limits

This review used round006 manager logs, the staged pilot result, the exact executed source snapshot, the prior round005 review evidence, the approved round plan, and pinned TabICL source. It did not rerun computation, import the model, load a checkpoint, or inspect holdout, Test2025, the full 7,372-row source, or raw protected data.

The requested reviewer configuration was GPT-6 Luna xhigh. `manager/assistant_host_evidence.json` reports the same host configuration; this is host configuration evidence, not internal model authentication. Machine-readable hashes, stages, limits, and unknowns are in [final_review.json](final_review.json).
