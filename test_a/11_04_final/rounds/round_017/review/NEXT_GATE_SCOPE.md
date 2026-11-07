# Conditional Round018 scope: M4-a full-estimator integration and saved reload

This note is a source-grounded proposal, not an approval or execution authorization. It becomes eligible only after Round017 receives independent approval and the manager records a successful same-map smoke → mock → saved-audit sequence with completed receipts. Round016 remains frozen with an unapproved source set and no dynamic runs; do not make a later Round016 pass a prerequisite. Preserve the historical Round015 wrapper gate as false and Round010 gate as false regardless of any new Round017 saved-audit result. This future gate would test synthetic integration behavior only, not FIT, F1, generalization, independent validation, or hardware.

## Fixed candidate and input boundary

Use only the preselected Round015 M4-a head artifact `rounds/round_015/artifacts/m4_a_head.pt`, with expected size 42,422 bytes and SHA-256 `c33e0185a537bce0bfd0e583dcd1f9aaa0d2c0e141847a2e3ab0d9a3621ff0c0`. A future Round018 manager must verify the approved artifact's size and streaming SHA-256 at the gate. This note did not open, hash, or deserialize it. Do not substitute M4-b, select by observed CE or any score, or add a training or merge path. This is a preselected implementation scope, not a performance ranking.

Generate the fixed synthetic context `X_context[16,8]`, `y_context[16]`, and target `X_target[4,8]` using the Round014 sequence. Call `fit` once using only context labels. Do not create target labels or pass any target labels into classifier state, hooks, callbacks, the saved estimator, or comparisons. `predict_proba` receives only the four target feature rows. The target overlaps earlier synthetic mechanics work, so every comparison is implementation parity, not held-out evaluation.

## Fixed call budget and configuration

| Operation | Fixed count / maximum |
|---|---:|
| Synthetic context `fit` | 1 |
| Original checkpoint load, inside `fit` | 1 |
| `predict_proba`: baseline, modified, reloaded | 3 |
| Native model forward calls | 4 per prediction; 12 total maximum |
| Full estimator save / reload | 1 / 1 |
| External head evaluation on target-only `H` | 1 |
| Backward / optimizer / extra training / merge | 0 |
| Target labels / real data / NPZ / reference / OUTER / holdout / F1 | 0 |

Use the pinned local checkpoint with `allow_auto_download=False`, CPU FP32, three Torch threads, `n_estimators=4`, `batch_size=1`, one `none` normalization, no feature shuffle, class-shift permutations, temperature `0.9`, `average_logits=True`, AMP/FA3/KV cache off. Assert the observed view count is four; do not infer it from requested configuration. Round014 source notes say `fit` loads/prepares the model while KV-cache-disabled inference forwards during prediction. The future plan must reconfirm this against the exact frozen code and installed source before execution.

## Preconditions for any future model run

1. Create a new Round018 plan with the exact source set, independent approval map, commands, environment, finite total wall-clock cap and conservative peak-memory estimate. Complete its same-map smoke and stdlib mock before the model gate.
2. Immediately before model launch, record free RAM and concurrent work. Require at least **3 GiB available** and state the peak-memory basis; if conditions differ from the plan, stop and replan before launch. Round015 recorded a sampled owned-tree maximum of 558.75 MiB. That is historical and sampling-limited; it is not a guarantee of future peak usage or evidence of current availability.
3. Use one owned base-Python model process with the approved environment. No venv redirector or second model process. Keep all outputs in Round018. Do not access project data, OUTER, holdout, F1, or hardware.

## Integration and saved-estimator checks

1. Generate only the fixed synthetic context and target features. Fit once on `X_context` and `y_context`. Verify the loaded final layer is `model_.icl_predictor.decoder[2]`, with weight shape `[10,1024]` and bias shape `[10]`.
2. Before editing, record complete model parameter/buffer hashes, `requires_grad`, and mode. Attach read-only hooks to the final Linear for the three predictions; remove hooks in `finally`. On baseline, capture target-only `H[4,4,1024]` and logits `[4,4,10]` after excluding the 16 context rows. Confirm actual member-to-permutation order. Reconstruct baseline probabilities from each member's first four logits gathered with `out[..., p]`, then logit-average, temperature-scale at `0.9`, softmax, and row-normalize.
3. Copy the frozen M4-a weight into `decoder[2].weight` exactly once. Check equality to the approved M4-a artifact, unchanged inactive rows `[4:,:]`, unchanged bias, and unchanged upstream model state. Keep the fitted model in eval mode and frozen. On the second public prediction, require `H` to match baseline; compare hooked raw outputs with one external evaluation `H @ W_a.T + b` within `1e-5`. Reconstruct probabilities and require the existing `1e-6` tolerance, finite values, `[0,1]` range, row sums, and argmax equality. Do not compute CE or any score.
4. Save and reload the **whole fitted estimator** with these fixed flags:

   ```python
   clf.save(path, save_model_weights=True,
            save_training_data=True, save_kv_cache=False)
   reloaded = TabICLClassifier.load(path, device="cpu")
   ```

   Do not omit or change flags. `save_model_weights=True` retains the modified model; `save_training_data=True` retains context needed when KV cache is disabled; `save_kv_cache=False` is the fixed scope. Explicitly freeze reloaded model parameters and confirm eval mode.
5. Compare complete pre-save/post-load model-state hashes, head weights/bias, classes/permutation, preprocessing state, and prediction outputs. The third `predict_proba` is the reloaded estimator and must remain within its four-forward allowance. No refit, checkpoint reload, extra run, or tolerance widening. Confirm hooks are gone and no owned child remains.

## Claims and unknowns

Passing would establish synthetic full-estimator integration and save/reload behavior under the tested configuration only. It would not establish model quality, F1, independent performance, checkpoint correctness beyond the single recorded pinned load, or hardware behavior. The M4-a artifact identity is fixed above, but the current Round018 environment, free RAM, peak estimate, execution cap, and result are unknown until a separate plan and approved gate. The historical baseline remains micro-F1 `0.5930133966423605`, macro-F1 `0.5252719738966167`; the exploratory `0.5933525521451586` remains unadopted. Independent and official scores remain null, and the 0.7 goal remains unmet absent a distinct qualifying evaluation.
