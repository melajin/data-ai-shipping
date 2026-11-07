# Conditional next gate: M4-a full-estimator integration and reload

This is a source-grounded proposal only. It is eligible only if Round014 independently approves the frozen source and M4-a passes its specified gradient, invariance, head-reload, and tolerance checks. M4-a has no low-rank merge step. This document does not approve uncreated Round014 code or authorize execution. The result would test synthetic inference mechanics only, not FIT, F1, generalization, or hardware behavior.

## Scope choice

Use exactly one candidate: the already-trained M4-a head weight from Round014. Choose it before inspecting CE or any output because it copies one weight matrix directly into `decoder[2]`; this keeps the integration change to one tensor and removes the separate low-rank merge path. This is an implementation-scope choice, not a performance ranking. If M4-a fails, do not substitute M4-b or choose a candidate from observed scores in this gate.

Replay Round014's exact synthetic context and target feature generation, context labels, model configuration, view order, and permutations. The follow-up need not generate or retain target labels at all. Fit only the 16 context rows with their four-class labels; call `predict_proba` with only the four target feature rows. No target label may enter classifier state, hooks, callbacks, saved estimator, or comparison code. The target features overlap the preceding synthetic mechanics gate, so every comparison is an implementation parity check and must not be described as held-out evaluation.

## Fixed call and process budget

| Operation | Maximum/count |
|---|---:|
| Synthetic context `fit` | 1 |
| Original checkpoint load | 1, inside `fit` |
| `predict_proba` calls | 3: baseline, modified, reloaded |
| Native full-model forwards | 4 per prediction; 12 total maximum |
| Full estimator save / reload | 1 / 1 |
| External head evaluation | 1, M4-a on the captured target-only H |
| Backward / optimizer / additional training / merge | 0 |
| Target labels / real data / NPZ / reference / OUTER / holdout / F1 | 0 |

Use the pinned local checkpoint with `allow_auto_download=False`, CPU FP32, three Torch threads, `n_estimators=4`, `batch_size=1`, one `none` normalization, no feature shuffle, class-shift permutations, temperature `0.9`, `average_logits=True`, AMP/FA3/KV cache off. The runner must use a single owned base-Python process with the approved environment's `site-packages`; do not launch a venv redirector or a second model process. `kv_cache=False` matters: source `fit()` loads and prepares the model but only forwards during fit when building a KV cache.

`fit` calls `_load_model` once and uses only context labels (`classifier.py:423–528`). Each `predict_proba` flattens the actual normalization/view/permutation order and calls `_batch_forward`; with the fixed four views and `batch_size=1`, it performs four model forwards (`classifier.py:594–621, 742–765`; `preprocessing.py:1122–1141`). Assert the actual view count is four rather than assuming that the requested count guarantees it.

## Integration and checks

1. Freeze and approve the exact new source/map and complete the same-map smoke and stdlib mock before this model gate. Recheck available RAM immediately before the model process; require at least 3 GiB and record other processes and a conservative peak estimate. Do not promote an execution time limit or memory estimate from a prior round without current evidence. The exact total wall-clock cap and expected peak remain manager decisions before execution.
2. Generate synthetic `X_context[16,8]`, `y_context[16]` and `X_target[4,8]` from the fixed Round014 generation sequence. Call `fit(X_context, y_context)` once; never create target labels. Confirm the loaded final layer is `model_.icl_predictor.decoder[2]`, with weight `[10,1024]` and bias `[10]`.
3. Before editing, record full model parameter/buffer hashes, `requires_grad`, and mode. Attach read-only hooks to the final Linear for the three predictions and remove them in `finally`. Baseline capture must be `[4,4,1024]` target H and `[4,4,10]` logits after slicing away the 16 context rows. Confirm the actual member-to-permutation mapping. The baseline `predict_proba` must agree with canonical reconstruction from each member's first four logits gathered with `out[...,p]`, then logit average, temperature 0.9, softmax and row normalization.
4. Copy the frozen M4-a weight into `decoder[2].weight` exactly once. Assert equality to the approved M4-a artifact, require its inactive rows `[4:,:]` to equal the baseline rows exactly, preserve the full baseline bias exactly, and confirm all other model parameters/buffers are unchanged. Keep the whole TabICL model in eval mode and frozen. Run the second public `predict_proba` on the same target features. H from the second prediction must match baseline H; its hooked raw outputs must match one external evaluation `H @ W_a.T + b` within the existing logit tolerance (`1e-5`). Reconstruct canonical probabilities by using each member's first four logits and actual `p` order; check probability tolerance (`1e-6`), finiteness, `[0,1]`, row sums and argmax. Do not compute CE or any score.
5. Save and reload the **whole fitted estimator**, including the modified full model and the synthetic context needed for prediction. Use the explicit source-supported flags:

   ```python
   clf.save(path, save_model_weights=True,
            save_training_data=True, save_kv_cache=False)
   reloaded = TabICLClassifier.load(path, device="cpu")
   ```

   The default `save_model_weights=False` omits model weights and reloads the original checkpoint, which would lose the M4 head (`_sklearn/base.py:247–264, 336–430`). With embedded model config/state, `__setstate__` reconstructs TabICL from the saved state without another checkpoint load (`base.py:295–328`). Saving context is required here because KV cache is disabled. In the future integration gate, write the self-created synthetic estimator only under a fresh Round015 tree; keep all Round014 sources, outputs and receipts read-only. Do not read external serialized objects. The load path calls `eval()` but does not preserve `requires_grad` flags, so explicitly set all reloaded model parameters frozen and recheck eval mode.
6. Compare the complete pre-save and post-load model state hashes, final head weights/bias, class/permutation and preprocessing state, and the two `predict_proba` outputs. They must match under the already fixed tolerances; no tolerance widening, refit, checkpoint reload, or rerun is allowed. Record the third prediction's four forwards and confirm hooks are removed and no owned process remains.

## Evidence and unresolved items

Source reviewed read-only: `rounds/round_011/m4_contract/M4_CONTRACT.md`, `rounds/round_011/review/M4_REVIEW.md`, `rounds/round_012/review/M4_NEXT_CHECKLIST.md`, and pinned `tabicl/_model/learning.py`, `tabicl/_model/tabicl.py`, `tabicl/_model/inference.py`, `tabicl/_sklearn/classifier.py`, `tabicl/_sklearn/preprocessing.py`, and `tabicl/_sklearn/base.py`. Directly hashed installed source: `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl/_sklearn/base.py` SHA-256 `7f8f284ca91bf1f5a016179834e508890b3f5368c4a48a7dcb6cb4b83a30051a`. The five M4 sources match Round011's `source_evidence.json`; installed files remain read-only.

The actual Round014 M4-a artifact name, candidate pass/fail, runtime, and peak memory are unknown here. The manager must verify the successful result and exact artifact path, choose a finite wall-clock cap and peak estimate with current RAM evidence, and place exact commands in a later fresh-round plan before any follow-up execution. This document records no run, model output, checkpoint access, or data evaluation.
