# Round013 Sections 3–5 execution notes

**Scope:** This run executes the voyage-count coverage and local-collapse/confound checks only. §6 voyage selection/confidence and §7 endpoint/evaluation calculations were not run. The supervisor-fixed interpretation was applied before examining results; `PROTOCOL.md` remains unchanged.

## Inputs and rules

- Dev positives: 100 linked events on 82 vessels; Tier0?1: 60 events. Dev track rows were streamed from the two Round008 parquet files in 65,536-row batches, reading only `rfid_id_int`, `ts`, `len_m`, `bbox_m`, `cen_lon`, `cen_lat`, and `state`, then filtering to linked vessels. 2025 coverage read only `rfid_id` and `ts` from `first_results/hourly_scores.parquet`.
- Duplicate `(vessel, ts)` keys preserve the first row in concatenated parquet/input order, matching Round012. Dev had 45,750 extra duplicate rows across 45,750 key groups; conflicting duplicate payloads: 0. The 2025 file had 0 duplicate rows.
- Raw eligibility is `total_voyages >= 11`, because excluding the target must leave at least ten other voyages. The protocol table?s `<10` category is also reported separately. Exactly ten voyages therefore fail the fixed eligibility rule although they are not in the table?s `<10` bucket.
- Voyages split on same-vessel adjacent `ts` differences `>=6h`. Local windows use integer epoch-hour ranges `[h-w+1,h]`, every integer `h` from voyage start + `w-1` through voyage end, without interpolation. Minimum ties choose the earliest `h`.
- Stored epoch-hour modulo 24 is used; it is not asserted to be local time. Day is `[06,18)`, night is the remainder. An accident-related voyage has at least one same-vessel `acc_ts` in the inclusive interval `[t_start-6,t_end+6]`; all other voyages are controls, not confirmed normal.

## ?3 voyage coverage

| Dataset | Vessels | Median voyages | Min | `<10` (table field) | `<5` | Raw LOO eligible (`>=11`) | Exactly 10, therefore ineligible |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dev | 82 | 44.5 | 2 | 9 (11.0%) | 5 (6.1%) | 71 (86.6%) | 2 |
| 2025 Test B | 100 | 20.0 | 1 | 36 (36.0%) | 21 (21.0%) | 63 (63.0%) | 1 |

Dev has 11 raw-history ineligible vessels (9 below ten and 2 at ten). For 2025 the corresponding counts are 37 (36 below ten and 1 at ten). The CSV has one row per vessel and includes per-window effective-voyage counts and eligibility fields.

## Input audit and ?4 calculation

- Dev selected rows: 145,427; after first-row deduplication: 99,677. Nonfinite/negative `len_m` and `bbox_m`: all zero. `ts` nonfinite, negative, or noninteger: all zero. No negative `bbox_m` was found, so the stop condition did not trigger.
- 2025 timestamps were finite, nonnegative integers; no feature columns were read or calculated.
- Window-valid voyage counts: w=3: 3,138 voyages across 81 vessels; w=7: 2,386 voyages across 80 vessels. Tier0?1 vessel descriptive subsets: w=3 2,066 voyages/54 vessels; w=7 1,591/54.
- Independent actual-data direct summation checked 60 voyage/window cases (30 per w); mismatches: 0. This is a computation cross-check, not hardware testing.

## ?5 confound statistics

Spearman p-values are descriptive; the fixed confound rule uses `|rho| >= 0.2`. The KS tests compare the modulo-24 collapse-hour distribution of accident-related versus control voyages; two tests form one family, with Bonferroni-adjusted p-values.

| w | Population | Valid voyages | Spearman rho | Accident / control voyages | KS statistic | KS raw p | KS Bonferroni p | Fixed confound indicator |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 3 | ALL | 3138 | 0.051934 | 93 / 3045 | 0.074294 | 0.672825 | 1.000000 | False |
| 7 | ALL | 2386 | 0.064014 | 86 / 2300 | 0.114853 | 0.207050 | 0.414100 | False |
| 3 | Tier0?1 vessels (descriptive only) | 2066 | 0.094814 | ? | ? | ? | ? | Not separately tested |
| 7 | Tier0?1 vessels (descriptive only) | 1591 | 0.084490 | ? | ? | ? | ? | Not separately tested |

The fixed-rule indicator is false for both windows (`|rho|<0.2` and adjusted KS p?0.05). The 24-hour distributions are in `g5_hour_distribution.csv`. This reports the computed branch indicator; supervisor review owns the decision for the next stage. Same-bucket effective reference counts for a possible future day/night branch are retained in `g5_same_bucket_reference_coverage.csv` and per-voyage columns.

## Validation, resources, and execution evidence

- Synthetic code checks: 9/9 passed; see `synthetic_validation.json`. Actual-data independent sum checks are separately recorded in `real_direct_sum_audit.csv`.
- Memory checks: pre-run 4882 MiB available at 2026-11-05T19:48:23.0197278+09:00; estimated added peak 350 MiB. Before the 2025 stage, the in-process snapshot is preserved in `execution.json`. Before final audit/docs: 4379.9 MiB at 2026-11-05T19:49:19.5647426+09:00; estimated added peak 120 MiB. No concurrent data-calculation process was run.
- Python: 3.13.3; package versions are in `execution.json`. Successful run exit code: 0. Source/contract hashes before and after match; see `source_hash_manifest.json`.
- Requested model: GPT-6 Luna xhigh, matching the dispatch and `.codex/agents/luna_worker.toml`. The runtime did not expose an independently verifiable model telemetry field, so `execution.json` records that limitation rather than asserting it.

## Files produced

See `execution.json` and `source_hash_manifest.json` for complete run metadata. Files created by this worker: `run_round013.py`, `validate_round013.py`, `EXECUTION_NOTES.md`, `execution.json`, `run_execution.log`, `run_preflight.json`, `finalization_preflight.json`, `source_hash_manifest.json`, `synthetic_validation.json`, `g3_voyage_count_coverage.csv`, `g3_coverage_summary.json`, `g4_voyage_local_collapse.csv`, `g5_confound_summary.json`, `g5_hour_distribution.csv`, `g5_same_bucket_reference_coverage.csv`, `input_quality_dev.json`, `input_quality_2025.json`, and `real_direct_sum_audit.csv`. At final inventory, additional files were visible that were absent from the initial folder listing (`g3_coverage.py`, `g3_summary.json`, `g3_vessel_level_coverage.csv`, `g4_local_collapse.py`, `g4_summary.json`, `g4_voyages.csv`, `g5_confound_result.json`, `g5_confound_summary.csv`, `g5_hour_confound_check.py`, `round013_util.py`, `test_g4_g5_synthetic.py`, `execution.log`); this worker did not create or alter them, and their provenance/content were not reviewed. No §6/§7 results or final conclusion were produced.
