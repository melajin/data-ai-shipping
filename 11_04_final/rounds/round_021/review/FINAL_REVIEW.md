# Round021 independent saved-output review

## Decision

The independent audit **passed**: saved keyed predictions reproduce the published metrics, fold/class support, paired comparison, protected-reference transitions, and recorded gate result. The candidate itself **failed the frozen protection gate** and should not be adopted from this round. `verification.json` records `passed: true` for audit consistency and `candidate_gate_pass: false` for the model decision; these are separate outcomes.

## Scope and sources

This review recomputed predictions by `argmax` over saved probability columns and calculated confusion matrices directly from the saved labels. It did not reload or run a model, refit, search parameters, or generate probabilities. The reviewed files were:

- `artifacts/outer_predictions_round021_long.csv` — 29,485 keyed rows, 5 methods × 5,897 unique IDs. SHA256: `9c69ca58f6ec9be0f60ae432ada589d0904c9ff2c0ce3324ead1c8759aedd244`.
- `artifacts/evaluation_round021.json` — report compared against the independent calculations.
- Historical reference predictions at `D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/artifacts/exp01/sqrt_macro/outer_predictions.csv`, SHA256: `dfdf805f5c60cff019400e3b16f57f5d03aa6d24277e31c3cdfb2c5b2f4992a4`.
- Frozen historical protection metadata: `rounds/round_020/manager/historical_protection_reference.json`.

The OUTER file contains 5,897 matching IDs per method and exactly one row per ID, fold, and method. Fold counts are 1,966 / 1,966 / 1,965 for folds 0 / 1 / 2; class support is 2,920 / 2,016 / 835 / 126. All probability values were finite and within [0,1], with maximum row-sum error below 1e-6. Labels, folds, and ID sets aligned with both protected references. All 50 saved-report consistency checks passed, including the report's paired bootstrap interval. This is a saved development-OUTER audit, not a new holdout evaluation.

## Recomputed results

| Method | Correct / 5,897 | Micro F1 | Macro F1 | TP by class 0 / 1 / 2 / 3 |
|---|---:|---:|---:|---|
| Seed42 LightGBM reference | 3,476 | 0.589452 | 0.519210 | 2,389 / 889 / 108 / 90 |
| Stacker12 baseline | 3,407 | 0.577751 | 0.481603 | 2,428 / 800 / 104 / 75 |
| Stacker20 spatial candidate | 3,363 | 0.570290 | 0.497078 | 2,317 / 844 / 116 / 86 |
| Historical 5-seed reference | 3,497 | 0.593013 | 0.525272 | 2,381 / 908 / 116 / 92 |

Against Stacker12, the candidate gained 245 correct IDs and lost 289, for a net **−44** correct (micro-F1 −0.007461). The recomputed paired bootstrap 95% percentile interval is [−0.015266, 0.000170]. Macro F1 rose by 0.015475, reflecting class gains despite the lower total correct count.

The frozen absolute protection floors were class 0 TP ≥ 2,389 and class 3 TP ≥ 92. Candidate counts were 2,317 and 86, respectively, so **both floors failed**. Candidate TP was also below the historical reference in classes 0 (−64), 1 (−64), and 3 (−6); it matched class 2. Against seed42, candidate TP deltas were −72 / −45 / +8 / −4.

Candidate changes versus each protected reference, shown as gain / loss / net true positives:

| Reference | Class 0 | Class 1 | Class 2 | Class 3 |
|---|---:|---:|---:|---:|
| Historical 5-seed | 197 / 261 / −64 | 167 / 231 / −64 | 62 / 62 / 0 | 6 / 12 / −6 |
| Seed42 LightGBM | 191 / 263 / −72 | 178 / 223 / −45 | 66 / 58 / +8 | 8 / 12 / −4 |

## What accounts for the lower micro score

The class TP change relative to Stacker12 is **−111 / +44 / +12 / +11** for classes 0 / 1 / 2 / 3; the three gains sum to +67 and do not offset the 111 lost class-0 true positives. The class-0 recall fell from 0.8315 to 0.7935. Its precision did not fall: it moved from 0.5922 to 0.5967, while class-0 false positives decreased from 1,672 to 1,566. Thus the directly observed issue is weaker recovery of true class-0 rows, not a measured class-0 precision decline.

Precision fell for classes 1 (0.5722 → 0.5428) and 2 (0.3925 → 0.3706); their false-positive counts increased by 113 and 36. Their macro F1 nevertheless improved, as did class 3 F1, while class 0 F1 declined (0.6917 → 0.6812). This supports a measured tradeoff: the 20-feature model shifts errors and improves minority-class recall, but the class-0 losses dominate the micro score and violate the frozen TP floors.

The specific mechanism behind that shift is not established by this audit. A representation/decision-boundary effect from adding spatial Bhat features is plausible, but unproven. Any suggestion that the 394-row SELECT stage caused overfitting is also a hypothesis, not a result here. No follow-on experiment was run for this review.

## Limits

This verifies consistency of the saved Round021 development-OUTER outputs only. It does not establish performance on an independent, untouched holdout or on a later cohort, and it does not establish causality for the class tradeoff. No 2025 or holdout predictions were inspected in this review.

Machine-readable details and every check are in [`verification.json`](verification.json). The audit implementation is [`verify_saved_outputs.py`](verify_saved_outputs.py).
