# Round020 final review — no run performed

## Decision

**Source review: NOT APPROVED. Round020 model fits: 0. New OUTER probability reads: 0. Round020 F1: not computed.** The source snapshot failed the independent pre-execution review, so this report contains no candidate performance estimate or pass/fail result.

The exact runner/config/plan/launcher/fixed-021 hashes and blockers are recorded in `SOURCE_REVIEW.md`. In particular, the loader's 787-row fold-local TabICL INNER input is incorrectly required to equal the 394-row SELECT roster, and the reviewed runner lacks the user's protected class-0/class-3 integer TP gates. The exact snapshot was not authorized for fitting or OUTER access.

## Input review scope and result

Round002 LightGBM/CatBoost and round003 TabICL lineage evidence supports matching FIT/INNER roles, class order, and the same fold-specific 394-row SELECT IDs/labels. No raw `F:` inputs, holdout/Test2025 rows, Round020 OUTER probabilities, or historical per-vessel protection prediction file were opened. For transparency, round002's full development `y` vector was loaded for role/INNER label alignment, which technically loaded OUTER labels before freeze; no OUTER label was used to tune or change the experiment.

The saved development set is repeatedly exposed and cannot be called a new independent evaluation. No hardware experiment was conducted. No refit, simulation, or new prediction was performed; no Round020 OUTER F1, metric, or bootstrap was computed.

## Follow-up needed before any run

Author must correct the TabICL INNER-to-SELECT reader, implement the frozen `1e-6` probability gates and class-0/class-3 TP floors with per-class transition reporting, enforce a real per-fit timeout and convergence-warning failure, and save keyed SELECT probabilities plus hash-bound historical-reference lineage. Then a reviewer must approve the exact changed runner/config hashes and the manager must separately issue the matching input-bound OUTER-read approval. The current hashes above must not be reused after edits.
