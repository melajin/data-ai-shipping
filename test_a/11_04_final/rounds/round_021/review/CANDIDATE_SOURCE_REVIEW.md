# Round021 candidate source review

**Decision: GO for the three-fold candidate fit/save/reload stage only.** This approval does not authorize OUTER feature/probability reads, historical prediction rows, or performance evaluation.

Reviewed 2026-11-05 00:26 UTC. Hash-bound sources are in `candidate_approved_sources.json`.

## Checks

- Runner SHA256: `E1660DF8D858BA34F36BDF267D25E92EFF900370D80E9703A14FB18584B9214E`.
- Worker SHA256: `EACBB986FA8C11FA710C4BB31E0520308B6BC95D1A54A87945CC0BFB4CA52ED6`.
- Spatial feature helper SHA256: `24265ECDD609B53AE3DE1574678A3E87C42A5977A2DBF11495F49C5BF9D4F2DC`.
- Profile extractor SHA256: `1E3EF3E47CECCF15721D324665B4436410522C6E79A9AC62163784A714B3E8BD`.
- Config SHA256: `07F4B526D6EFDCF6E2E0CECF80B9D27C7AAC09BF3F56147951A48322685A5245`.
- Launcher SHA256: `4A221F280C07641BADF4BCC1E03FBCAFC2DEB59C10BE9A0F4A80E925C33D6171`.
- Plan SHA256: `F52F64A5CB616F7E07EBD9060D8643E066FA78A9E3D04EF1B6146D6EDC1F070D`.
- Candidate SELECT features are read as CSV with exact key/column checks and joined to the canonical SELECT roster by fold and vessel ID. Missing feature values remain NaN and are handled by the worker's fixed constant-zero imputer with no missingness indicators.
- Before candidate fitting, the runner validates the saved baseline's 12-feature variant, model hashes, classes, and reload probabilities; it also checks row-keyed raw SELECT source probabilities against the current fold-local SELECT inputs.
- Candidate features are the same 12 clipped-log-probability columns plus the fixed eight spatial columns. The candidate uses the same StandardScaler and LogisticRegression settings. It runs three sequential 20-feature fits; the child worker has a 120-second hard timeout and promotes `ConvergenceWarning` to an error. No retry path is enabled.
- The candidate stage writes row-keyed SELECT meta probabilities and a fit record, then exits. It does not call the OUTER probability loader, spatial OUTER builder, historical prediction-row loader, or evaluation function. The legacy `--run` path remains disabled in this snapshot.
- Runner, worker, both spatial helpers, and launcher ASTs parsed; config JSON parsed. No candidate fit or OUTER/historical-row read was performed by this reviewer.

## Boundary for later evaluation

The file still contains an older evaluator function, but it is unreachable from the staged candidate command while `--run` is disabled. That evaluator has not been approved for Round021 because it does not yet implement the fixed 12-vs-20 OUTER comparison and both historical/seed42 integer protection reports. A separate exact-source review is required before OUTER authorization.
