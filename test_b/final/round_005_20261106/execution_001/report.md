# Round5 execution_001 report

## Scope

Fixed retrospective analysis of the saved Round4 candidate ledger and labels. No training, raw source load, feature rebuild, or TestB inference was performed. Prediction file was saved before event labels were read.

- Events: 100; Tier01: 60; distinct event RFIDs: 82.
- S1 pools: stage1-selected=81, stage0 fallback=1; G caps preserved (1/3/4): {1: 2, 3: 1, 4: 79}.

## Outcomes (hits / denominator; rate)

| Cohort / k | B0 | S1 | S | G |
|---|---:|---:|---:|---:|
| all top1 | 3/100 (0.030) | 2/100 (0.020) | 1/100 (0.010) | 1/100 (0.010) |
| all top4 | 7/100 (0.070) | 8/100 (0.080) | 7/100 (0.070) | 5/100 (0.050) |
| Tier01 top1 | 2/60 (0.033) | 2/60 (0.033) | 1/60 (0.017) | 1/60 (0.017) |
| Tier01 top4 | 5/60 (0.083) | 8/60 (0.133) | 6/60 (0.100) | 5/60 (0.083) |

## Paired bootstrap and gate

Gate: `{"tier01_top1_gain_at_least_5pp": false, "tier01_paired_rfid_bootstrap_95ci_lower_gt_zero": false, "all100_top1_nonworse_than_B0": false, "S1_actual_pool_top1_random_expectation_exceeded": false, "thresholds_changed_or_tuned": false}`. Tier01 S1-vs-B0 top1 was 0.0 percentage points (95% CI −6.78 to +6.78 pp); the lower bound is not above zero. Overall S1-vs-B0 top1 was −1.0 pp.

S1-vs-B0 and S1-vs-S paired RFID-cluster bootstrap results for all/Tier01 and k=1/4 are in `metrics.json` (B=4000, seed=20261105). For Tier01 top1, S1-vs-S was +1.67 pp (95% CI −3.51 to +7.27 pp). S1 actual-pool random expectations were 2.38% top1 and 5.67% top4; observed S1 was 2.0% and 8.0%, respectively. The S1 random expectation uses its observed stage1 pool, falling back to stage0 only when that RFID has no stage1 rows. Round4 B0/S/G prediction rows were copied unchanged; their prior random and bootstrap summaries are retained under separate reference keys.

## Loss observations

Loss events: stage0→stage1 52; stage1→stage2 13; union 65. Flags overlap. They describe saved observations and do not identify true waiting, movement, or accident causes. The ±6 hour table is outcome-linked evaluator-only diagnostics and did not change predictions or the baseline.

## Limits

This is a retrospective evaluation on the fixed 100 event labels, with 82 shared event RFIDs and Tier01=60. It does not establish generalization, F1, a false-positive rate, real-time behavior, or physical cause. Timestamp interpretation is the existing hourly integer contract; no physical device was tested.
