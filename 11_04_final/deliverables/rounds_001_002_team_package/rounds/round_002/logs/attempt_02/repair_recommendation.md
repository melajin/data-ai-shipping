# Round 002 recovery note

Execution stopped after the second CatBoost API error, before any OUTER prediction or score. Attempt 1's CatBoost constructor rejected `feature_names`; no CatBoost `.fit()` call occurred there. Attempt 2 passed names through `Pool`, reused the verified fold 0 LightGBM baseline, then CatBoost `.fit()` rejected the explicit `Accuracy:use_weights=false` option before iteration. Do not resume under this configuration.

Minimal API correction for a future reviewed run: use `eval_metric="Accuracy"` and omit all sample/evaluation weights. With default unit object weights, this is the unweighted Accuracy target requested. Update and re-hash the config/code, review before training, and do not refit the already completed fold 0 baseline. No candidate/OUTER score exists from this round.
