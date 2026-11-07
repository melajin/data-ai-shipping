# Deferred M4-a integration scope (not the immediate Round017 gate)

This is a source-document scope note only. Round016 did **not** receive independent source approval and ran no dynamic gates, so the M4-a integration described below is not eligible for the immediate Round017 work. The immediate follow-up remains model-zero source repair and independent review of the process deadline classifier. Consider this M4-a gate only after a later Round016 pass is recorded. This note does not authorize a run, approve uncreated code, or establish current checkpoint/runtime state. It is based on `rounds/round_014/review/NEXT_INTEGRATION_CHECKLIST.md` and Round016's incoming plan.

## Fixed candidate and input boundary

- Use only the Round015 M4-a head artifact `rounds/round_015/artifacts/m4_a_head.pt`, fixed at 42,422 bytes and SHA-256 `c33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0`. Verify size and streaming SHA-256 at the later gate; do not deserialize it in this document review.
- M4-a is a one-weight-matrix copy into `decoder[2].weight`. Do not substitute the M4-b merged artifact, make a candidate choice from observed CE or any score, or introduce another training/merge path. This is a preselected integration scope, not a performance ranking.
- Generate the fixed synthetic context `X_context[16,8]`, `y_context[16]`, and target `X_target[4,8]` using the referenced Round014 sequence. Call `fit` once on context only. Never create target labels or pass target labels into classifier state, hooks, callbacks, saved estimator, or comparisons.
- `predict_proba` receives only the four target feature rows. Treat results as synthetic implementation parity, not held-out evaluation, F1, generalization, or hardware evidence.

## Finite call budget

| Operation | Fixed count / maximum |
|---|---:|
| Synthetic context fit | 1 |
| Original checkpoint load, inside fit | 1 |
| `predict_proba`: baseline, modified, reloaded | 3 |
| Native model forward calls | 4 per prediction; 12 total maximum |
| Full estimator save / reload | 1 / 1 |
| External head evaluation on captured target-only H | 1 |
| Backward / optimizer / extra training / merge | 0 |
| Target labels / real data / NPZ / reference / OUTER / holdout / F1 | 0 |

Use the reference config: local pinned checkpoint, `allow_auto_download=False`, CPU FP32, three Torch threads, `n_estimators=4`, `batch_size=1`, one `none` normalization, no feature shuffle, class-shift permutations, temperature `0.9`, `average_logits=True`, AMP/FA3/KV cache off. Assert the actual view count is four and verify exactly four forwards per prediction and 12 total; do not infer counts from requested configuration alone.

## Integration and saved-estimator requirements

1. In a future authorized Round017, independently freeze and approve the exact code/map first, then require same-map smoke and stdlib mock before the model gate. The manager must record current available RAM, other running work, a conservative peak basis, and a finite wall-clock cap immediately before launch. Require at least **3 GiB available RAM** before model execution. Re-evaluate if the actual conditions differ; do not reuse Round015's measured peak as a current estimate.
2. Fit once using context labels only. Confirm final layer `model_.icl_predictor.decoder[2]`, weight shape `[10,1024]`, and bias shape `[10]`. Record full model parameter/buffer state, `requires_grad`, and mode before editing; install read-only hooks and remove them in `finally`.
3. Capture baseline target-only H `[4,4,1024]` and logits `[4,4,10]` after excluding the 16 context rows. Verify actual permutation order and reconstruct baseline probabilities from each member's first four logits using `out[..., p]`, then logit averaging, temperature `0.9`, softmax, and row normalization.
4. Copy the approved M4-a weight exactly once. Verify the artifact-to-layer equality, unchanged inactive rows `[4:,:]`, unchanged bias, and unchanged upstream parameters/buffers. Keep the fitted model in eval mode and frozen. On the second `predict_proba`, confirm H matches baseline and the single external head evaluation `H @ W_a.T + b` matches hooked logits within the already fixed `1e-5` tolerance. Reconstructed probabilities must meet the existing `1e-6` tolerance, finite/range/row-sum checks and argmax equality. Do not compute CE or any score.
5. Save and reload the **whole fitted estimator** with these exact flags:

   ```python
   clf.save(path, save_model_weights=True,
            save_training_data=True, save_kv_cache=False)
   reloaded = TabICLClassifier.load(path, device="cpu")
   ```

   Do not omit or change flags: `save_model_weights=True` preserves the modified model, `save_training_data=True` preserves context required when KV cache is disabled, and `save_kv_cache=False` is the fixed scope. Explicitly freeze reloaded model parameters and confirm eval mode.
6. Compare complete pre-save/post-load model-state hashes, final head weights/bias, classes/permutation, preprocessing state, H and the two post-baseline public predictions under the existing tolerances. The third prediction uses the reloaded estimator and must fit within its four-forward allowance. No refit, checkpoint reload, extra run, or widened tolerance. Confirm hooks are gone and no owned child remains.

## Claims and unknowns

Passing this gate would establish synthetic full-estimator integration/save-reload behavior under the tested config only. It would not establish model quality, F1, independent evaluation, checkpoint correctness beyond the one recorded pinned load, or hardware behavior. The current note records no installed-package import, checkpoint access, artifact deserialization, model output, or experiment. Round015's saved M4-a artifact identity is known; future environment condition, RAM, cap, and execution outcome remain unknown until a separately approved Round017 plan.

