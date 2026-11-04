# Independent M4 source review

**Verdict: approved for the bounded synthetic head-only mechanics gate in `rounds/round_011/m4_contract/M4_CONTRACT.md`.** This approval covers implementation design and source-grounded checks only. It is not evidence of M4 training, actual FIT integration, F1 improvement, or runtime performance.

## Evidence and method

I read the contract, its `source_evidence.json`, the pinned TabICL 2.2.0 source files listed there, and the saved round004 smoke metadata. I did not import Python packages, execute tests or code, load the checkpoint, read NPZ/reference/raw/holdout data, or compute F1. I independently hashed the inspected `learning.py`, `classifier.py`, `preprocessing.py`, and `inference.py`; each matched its recorded SHA-256. The smoke JSON records the prior observed final layer as `icl_predictor.decoder.2`, with input width 1024, output width 10, weight shape `[10, 1024]`, and bias.

## Source-grounded findings

- `learning.py` defines the ICL decoder as `Linear(d_model, 2*d_model) → GELU → Linear(2*d_model, out_dim)`. The saved smoke metadata establishes the concrete 512→1024→10 configuration for the prior loaded checkpoint. The contract correctly treats this as a prior observation and requires a shape assertion on a future load.
- `_icl_predictions` adds encoded `y_train` only to the first `train_size` rows, then runs the full ICL encoder and decoder. Its inference path returns only rows after `train_size`; standard classification also restricts output columns to the number of unique context classes. For four classes, columns `:4` are live and the final six rows of the 10-output head are inactive.
- The classifier label-encodes classes and the ensemble generator applies each class pattern as `p[y]`. The aggregation code restores canonical class order by gathering each member output with `out[..., p]`, then averages logits when `average_logits=True`, applies temperature 0.9, and normalizes row probabilities. The contract's warning against gathering with `argsort(p)` is correct.
- With `average_logits=False`, the classifier asks the model for probabilities per member and averages those probabilities. The contract correctly fixes `average_logits=True` and keeps temperature out of the cross-entropy training loss, applying it only during probability reconstruction.
- The classifier inference path uses `torch.no_grad()` and converts model outputs to NumPy; `InferenceManager._run_forward` also uses `torch.no_grad()`. A loss attached to `predict_proba` cannot update the readout. The proposed detached hidden-state cache and external copied head give a valid, narrow way to test readout math without changing checkpoint parameters.
- The synthetic design keeps the 16 support/context labels in `fit` and the four target labels out of `fit` and `predict_proba`; it uses target labels only for the external head loss. Slicing hidden states and logits to target positions prevents label-bearing context rows from becoming supervised target examples. Per-view loss labels `p[y_target]` are consistent with the source's class-shuffled training labels.
- M4-a's copied weight has 10,240 entries, with only 4,096 directly active under four-class output slicing. M4-b's `A[2,1024]`, `B[10,2]`, and `W_eff = W0 + B@A` yield 2,068 trainable entries, of which 2,056 are directly active. With `B=0`, the first gradient for A is zero while B may update; checking A after step two is appropriate. The fixed-bias and inactive-row invariants are consistent with the loss slice.
- The call limits, target-only head evaluation, merge-once guard, head-only save/reload scope, and explicit exclusion of real-data/performance conclusions keep the proposed gate bounded. The contract also preserves the unresolved real-input/preprocessing lineage and does not use this synthetic check to claim it is resolved.

## Limits

The final-layer dimensions are grounded in the pinned source plus a prior smoke record, not a fresh checkpoint load in this review. The future synthetic gate can establish output ordering, gradient routing, merge, and head-state reload mechanics. It cannot establish that a real-data M4 candidate improves performance, that the original data pipeline is fully resolved, or that the entire modified classifier integrates correctly after save/reload.
