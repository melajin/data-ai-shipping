# Round 003 independent review

## Decision

**Artifact and calculation review: PASS. Development progress gate: FAIL.** The authorized score run completed successfully, and independent replay from the saved development OOF probabilities reproduces the policy, predictions, reported metrics, transition counts, and paired bootstrap artifacts. This does not establish independent validation or production readiness.

## Bound run and scope

- Frozen runner SHA256: `9f333f7f4be7ed81ef8296f36b4474f8a6730f99f306c8e4f586c9d031bea6a2`
- Launcher SHA256: `0346fb307a015289c4686cc186aedcaf9854f6f5702a0808d66217cde35b0760`
- Experiment config SHA256: `29202080ea8f2a33120f2f6471679acc1f7afe702848f28ed8a741e3f4ccbbb6`
- Frozen plan SHA256: `54cef183b6845d6cecfca64314fc0d801c8d1b8c7c826da76f9a42b665ea2ce0`
- Reviewer precheck receipt: PASS, bound to the hashes above. Score receipt reports exit 0 in 15.127 s, with no timeout.
- Reviewer read only the allowlisted saved OOF/INNER predictions and development-role, class, rule, run and source metadata needed for the audit. It read zero individual holdout rows, full-7,372/F156/label rows, Test2025 rows, raw rows, or feature rows. No model/checkpoint was loaded, no fit or new inference was run.

## Pre-score source and input audit

- Both development OOF files contain 5,897 unique vessels (fold counts 1,966 / 1,966 / 1,965). Each of the six seed/fold INNER prediction files contains 787 vessels. Labels, folds, observed-day values, roles and IDs align to the development roster. OOF probabilities are finite, in range and sum to one within tolerance `1e-12` (maximum observed sum error `1.11e-16`).
- The archived `comparison_models.py` source (SHA256 `f818c0f2c3bb79cd80781a4df22c3d6cca425528fc3e3df4a08e55324d914251`) shows TabICL `fit_estimator` calls `model.fit(fit_x, fit_y)`; INNER is passed for prediction, not fitting or early stopping. Six fold training records report zero trained parameters, no selection metric, and INNER unused for training/early stopping. This verifies the documented saved-run lineage only; it does not replay the original inference or validate its checkpoint on this host.
- Allowlisted package/source manifest hashes matched, including the fixed-rule INNER prediction file hashes and role membership. The historical ID digest computed using the current INNER CSV row order does not match the frozen ID digest. The producer's original ID-list serialization/order was unavailable. Treat this as **unverified original ordering**, not as evidence of a corrupt file or split mismatch. The package-manifest self-entry is not self-listed and is recorded as not applicable, not a mismatch.
- The archived helper returns unnormalized trap-adjusted decision scores, while saved `oof_decisions.csv` scores are normalized after scaling. The argmax is invariant; this review recomputed `A_old` from original `p0..p3` and the frozen `2/3/2` factors. Neither scaled representation is a calibrated probability.
- Input width remains ambiguous: `run_settings.json` says no missing flags, while the hash-verified generation code appends missing indicators after imputation. The 156 raw-feature metadata could therefore yield 312 model inputs. No feature rows were read to resolve this.

## Independent output recomputation

The six chosen factors exactly match the frozen policy; no support fallback was used:

| Seed | Fold 0 | Fold 1 | Fold 2 |
|---|---:|---:|---:|
| 42 | 1.0 | 1.5 | 1.0 |
| 2026 | 1.0 | 1.0 | 1.0 |

Overall OOF results (5,897 vessels per seed; reported means are arithmetic means of per-seed metrics):

| Policy | Seed 42 correct / micro F1 / macro F1 | Seed 2026 correct / micro F1 / macro F1 | Mean micro F1 | Mean macro F1 |
|---|---:|---:|---:|---:|
| `A_raw` | 3491 / 0.591996 / 0.515399 | 3503 / 0.594031 / 0.515717 | 0.593013 | 0.515558 |
| `A_old` | 3391 / 0.575038 / 0.537904 | 3389 / 0.574699 / 0.536550 | 0.574869 | 0.537227 |
| `A_micro_select` | 3495 / 0.592674 / 0.525409 | 3503 / 0.594031 / 0.515717 | 0.593353 | 0.520563 |

The saved `predictions.csv` has 11,794 rows and exact coverage of all seed/vessel pairs. Every saved row's source probabilities, label, fold, day value, and three decisions matched the independent replay. All 960 checked metric fields across seeds, overall, fold and observed-day scopes matched, including empty scopes. Paired prediction transitions and original-probability diagnostics also matched.

I independently reproduced the paired vessel bootstrap draws using 5,000 resamples and the frozen seed; all six saved 5,000-by-2 arrays (micro and macro deltas for three comparisons) matched **cell for cell**. For selected vs raw, the mean micro delta is `+0.0003392` with 95% CI `[-0.0009327, +0.0016110]`; mean macro delta is `+0.0050048` with CI `[+0.0026074, +0.0075626]`.

The progress gate correctly fails: mean micro improvement is below `+0.005`, seed 2026 has no micro improvement, and the paired micro CI includes zero. The macro, class-F1-drop, and natural 1?7-day macro-drop checks pass. These are previously exposed development OUTER results; resampling does not remove adaptive selection bias or geographic dependence.

## Evidence files

- `precheck.json` ? reviewer pre-score decision and bound hashes.
- `preflight_audit.json` ? independent input/lineage audit; no metric computation.
- `independent_recompute.py` / `independent_recompute.json` ? independent factor selection, OOF metric and paired-bootstrap recomputation.
- `compare_saved_artifacts.py` / `artifact_comparison.json` ? artifact-by-artifact comparison, including exact numeric bootstrap draw equality.
- Score outputs are in the sibling `artifacts/` and `logs/` directories; no files outside `review/` were changed by this reviewer.
