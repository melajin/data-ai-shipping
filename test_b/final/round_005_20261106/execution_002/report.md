# Round5 execution_002 report

## Scope

Metric-only cohort-scope correction of the fixed retrospective analysis using saved Round4 artifacts. Predictions, ranking, caps, event hits, thresholds, and stage flags were not changed. No training, raw source load, feature rebuild, or TestB inference was performed.

- Events: 100; Tier01: 60; distinct event RFIDs: 82.
- S1 pools: stage1-selected=81, stage0 fallback=1; G caps preserved (1/3/4): {1: 2, 3: 1, 4: 79}.

## Top1 outcomes (hits / denominator; rate)

| Cohort | B0 | S1 | S | G |
|---|---:|---:|---:|---:|
| all | 3/100 (0.030) | 2/100 (0.020) | 1/100 (0.010) | 1/100 (0.010) |
| Tier01 | 2/60 (0.033) | 2/60 (0.033) | 1/60 (0.017) | 1/60 (0.017) |

## Cohort-matched random expectation and gate

Gate: `{"tier01_top1_gain_at_least_5pp": false, "tier01_paired_rfid_bootstrap_95ci_lower_gt_zero": false, "all100_top1_nonworse_than_B0": false, "Tier01_S1_actual_pool_top1_random_expectation_exceeded": false, "thresholds_changed_or_tuned": false}`.
Tier01 S1 top1 was 2/60 (0.033333); Tier01 actual-pool random top1 expectation was 0.034491231116. This comparison does not exceed expectation. All100 are reported separately: observed 0.020000, expected 0.023753288711.
S1-vs-B0 and S1-vs-S paired RFID-cluster bootstrap results remain in `metrics.json` (B=4000, seed=20261105). Each random expectation uses the observed S1 pool for that event RFID, falling back to stage0 only for empty stage1, and averages only within the named event cohort. Round4 B0/S/G prediction rows were copied unchanged; prior random and bootstrap summaries remain separately referenced.

## Loss observations

Loss events: stage0→stage1 52; stage1→stage2 13; union 65. Flags overlap. They describe saved observations and do not identify true waiting, movement, or accident causes. The ±6 hour table is outcome-linked evaluator-only diagnostics and did not change predictions or the baseline.

## Limits

This is a retrospective evaluation on the fixed 100 event labels, with 82 shared event RFIDs and Tier01=60. It does not establish generalization, F1, a false-positive rate, real-time behavior, or physical cause. Timestamp interpretation is the existing hourly integer contract; no physical device was tested.
