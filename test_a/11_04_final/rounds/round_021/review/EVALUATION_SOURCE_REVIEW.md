# Round021 final evaluation source review

**Decision: GO for the single, hash-bound development OUTER evaluation.** This approval is limited to the fixed 12-feature baseline versus 20-feature candidate comparison after all six model fits have been saved and reloaded. It does not claim independent performance, official score, or adoption.

Reviewed 2026-11-05 00:33 UTC. Exact hashes are in `evaluation_approved_sources.json`.

## Checks

- Evaluator SHA256: `60C1B85FE5124A3F18D4BAAEB3440E687D42231EE6C9D426907F77E5DF18EB30`.
- Round runner SHA256: `E1660DF8D858BA34F36BDF267D25E92EFF900370D80E9703A14FB18584B9214E`.
- Worker SHA256: `EACBB986FA8C11FA710C4BB31E0520308B6BC95D1A54A87945CC0BFB4CA52ED6`.
- Spatial feature helper SHA256: `24265ECDD609B53AE3DE1574678A3E87C42A5977A2DBF11495F49C5BF9D4F2DC`.
- Profile extractor SHA256: `1E3EF3E47CECCF15721D324665B4436410522C6E79A9AC62163784A714B3E8BD`.
- Config SHA256: `07F4B526D6EFDCF6E2E0CECF80B9D27C7AAC09BF3F56147951A48322685A5245`.
- Launcher SHA256: `4A221F280C07641BADF4BCC1E03FBCAFC2DEB59C10BE9A0F4A80E925C33D6171`.
- Frozen plan SHA256: `F52F64A5CB616F7E07EBD9060D8643E066FA78A9E3D04EF1B6146D6EDC1F070D`.
- Before OUTER loads, the evaluator checks manager approval for this evaluator SHA and `allowed_stage=evaluation`, exact OUTER feature CSV/manifest hashes, fit-stage result/model hashes, six saved/reloaded models, SELECT probability reproduction, and current source/config/input hashes.
- The baseline and candidate use the fixed 12 and 20 feature matrices with the frozen scaler/logistic settings. There is one candidate argmax evaluation with no extra fit or threshold change. The runner writes keyed OUTER probabilities and core baseline/candidate metrics before it reads historical per-vessel rows.
- Historical source SHA, reference TP/support vectors, same-condition seed42 TP vector, and raw LightGBM expected metrics are checked. Historical IDs, labels, and folds are aligned to the current 5,897 OUTER rows before protected gain/loss/net calculations.
- Metrics include full class precision/recall/F1/TP, target-class FP sources, fold and observed-day strata, class transition matrices, vessel bootstrap (5,000 draws, seed 20261105), hard TP0≥2389 / TP3≥92, protected recall nondecrease versus baseline12, and nondecrease versus both references. The reference F1 calculation uses global class metrics, including false positives from other true classes.
- The output records development-only status, `.7` reach separately, no adoption, independent/official result `null`, and a one-run claim. It does not read 2025/Test2025 or holdout rows.
- Evaluator, runner, worker, spatial helpers, and launcher ASTs parsed; config JSON parsed. No OUTER probabilities, historical rows, model fits, or evaluation outputs were read by this reviewer.

## Scope and reporting note

The 2026 year field is cohort provenance, not row-wise measured year. The OUTER set is repeatedly exposed development data; the paired interval does not establish independent performance. A successful source review authorizes the one planned evaluation only; it does not itself constitute an executed result.
