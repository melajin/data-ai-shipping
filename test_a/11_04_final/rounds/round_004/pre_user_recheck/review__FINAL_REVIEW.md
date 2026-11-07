# Round 004 independent final review

**Status: PASS_WITH_LIMITATIONS**  
**Decision: accept round004 with the documented limitations.**

## Findings

- The pinned CPU environment installed successfully in 150.437 seconds. All six install steps exited successfully, `pip check` was clean, and the aggregate stayed within the 900-second bound. The recorded 283,868,825-byte peak is wheel/temp disk usage, not a measurement of total network traffic.
- The synthetic smoke was **SKIPPED_RESOURCE_GATE**. The launch-time RAM sample was 2.1962547302246094 GiB against a 3 GiB minimum. The wrapper stopped before creating a probe subprocess: no model load, synthetic inference, probability checks, or F1 computation occurred. This is not a runtime failure.
- The independent development-only lineage check confirmed the three frozen NPZ hashes, feature names/order, roster roles and labels, six saved-median comparisons, and all 12 candidate 312-column tensor and row-order hashes. The median maximum difference was 2.8421709430404007e-14. These candidate tensors use NPZ/roster order; they are not original saved model replay inputs.
- The source/metadata checks do not establish pointwise equality to all original F156 values, regenerated vocabulary values, or the original ordered FIT/INNER IDs. The stored vocabulary digest confirms sorted FIT membership only.
- The history discrepancy is documented: the transcript shows eight successful lineage audit executions, while final `result.json` labels iteration 7. Earlier diagnostic snapshots and launch-time hashes were not retained. The frozen numeric results were not changed or rerun for this correction.
- `ROUND_REPORT.md` and `NEXT_SESSION_DRAFT.md` accurately preserve the above limits. The next scope uses ID-only split-order recovery and development-only input construction, and gates one synthetic smoke on launch-time RAM of at least 3 GiB. It does not authorize protected-row inspection, actual-vessel inference, F1 evaluation, or training.

## Review boundary

This review used the permitted development NPZs, their rosters and metadata, saved preprocessing/vocabulary records, the install and resource-gate receipts, and the round report/handoff draft. No protected data rows were read; no model was loaded; no training, inference, F1 calculation, or hardware validation was performed by the reviewer.

Machine-readable evidence and hashes are in [review.json](review.json). The underlying independent check is [independent_lineage_check.json](independent_lineage_check.json).
