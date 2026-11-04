# Final review: technical diagnosis supplement

**Disposition: PASS_WITH_LIMITATIONS.** I reviewed the supplement against the supplied PDF, Round 003 saved metrics and verification JSONs, Round 004 smoke report, and the separate technical review. The supplement’s quantitative corrections and main scope statements are supported. I found no blocking numerical or provenance error.

## Findings

- The +631 target gap, two-seed policy averages, seed-specific +4 versus mean +2 distinction, class supports/TPs, and PDF class-table sum conflicts are consistent with the saved result and verification JSONs. Details are in [math_review.md](math_review.md) and [math_review.json](math_review.json).
- The supplement correctly limits the failed post-hoc search to tested candidates; it does not claim that all rescaling is impossible. It also states the classwise target table cannot determine F1 without false positives.
- The supplement treats the proposed 120 features, M4 adaptation, 16-shot context, stacking, calibration, and segment encoder as unvalidated proposals. It identifies missing timestamp/schema contracts, the observed 10-way decoder versus four task labels, leakage risks, and unmeasured future performance/resource needs.
- It appropriately distinguishes the 16+4 synthetic CPU smoke from vessel-level inference, training, or F1; identifies the 3-GiB RAM rule as a start gate; and keeps repeated development OUTER separate from independent/official evaluation.
- The PDF’s “104 ships sacrificed” comparison is ambiguous: A_old versus A_raw loses 100 and 114 (mean 107), while 104 is seed42 A_micro_select minus A_old. The supplement’s wording that 104 is not supported by the stated raw comparison is reasonable; clarify the comparator if that sentence is revised.

## Limits

This was a read-only report/artifact review with arithmetic checks. I did not load protected rows, inspect holdout features/labels/probabilities, rerun predictions, or train/infer a model. The machine artifacts establish reported saved-result consistency, not an independent performance evaluation. Any claims beyond the cited development and synthetic evidence remain unverified.

## Binding

- Reviewed supplement SHA-256: `0d170e316843420169338ad765c1e887a9c09869b57f4911022cd8137aace8da`.
- PDF source SHA-256: `47bb4b67d506c1e487fd076631aba5aecf3fad5052799c4c9d4a92b62ed6161a`.
- Round 003 result SHA-256: `4fa42825644b9eb93935f03e63e9d26c9f5ff7e98cdf07d0e0033b41f7c3deba`.
- Round 004 synthetic smoke SHA-256: `e26df55a2c9501fc6a46102d323ca18226c922bd98ceb9eba9146a0cb0643ae2`.
- The distinct source-only implementation review is [technical_review.md](technical_review.md); this review covers the quantitative corrections and manager supplement consistency.
