{
  "review_id": "round_001_independent_review",
  "review_date": "2026-11-04",
  "verdict": "CONDITIONAL",
  "verdict_scope": "Accept the parser and saved-model replay diagnostics as bounded results; do not mark dynamic T5-to-CSV parity complete.",
  "scope": {
    "source_repo": "D:/repos/fishing-track-classification (read-only)",
    "raw_data": "F:/문제 데이터_수정_1027 (read-only; no raw file parsing by this review run)",
    "write_scope": "11_04_final/rounds/round_001/review/**",
    "development_rows": 5897,
    "holdout_rows_read_reported": 0,
    "model_training": false,
    "external_research": false,
    "holdout_label_or_feature_read_by_reviewer": false
  },
  "execution": {
    "primary": {
      "result_status": "completed_with_dynamic_array_comparison_unmeasured",
      "elapsed_seconds": 33.48146870000164,
      "dynamic_t5_reconstructed": false,
      "raw_csv_or_parquet_parsed": false,
      "training": false,
      "holdout_rows_read": 0,
      "exit_code": null,
      "exit_code_status": "unavailable; detached process handle not retained",
      "launch_script_sha256": null,
      "post_run_script_sha256": "738cb598c80b1fc4443b6770a536efe25832f1b0c88e69fc0ec8f319140f778a",
      "source_files_changed_reported": []
    },
    "supplemental_attempt_1": {
      "status": "failed_fold2_roster_assertion",
      "exit_code": null,
      "failure": "Harness expected 1966 fold-2 OUTER rows; actual roster has 1965.",
      "evidence_retained": true
    },
    "supplemental_attempt_2": {
      "status": "completed",
      "elapsed_seconds": 19.226163299999826,
      "exit_code": 0,
      "launch_script_sha256": "cecb8983c3b6b896aa9ab0aa995443a53c16c12d2cce5b6bab96632f912241fd",
      "after_script_sha256": "cecb8983c3b6b896aa9ab0aa995443a53c16c12d2cce5b6bab96632f912241fd",
      "training": false,
      "raw_parsing": false,
      "holdout_rows_read": 0,
      "source_files_changed_reported": []
    }
  },
  "findings": {
    "cached_x304_vs_default_csv": {
      "result": "exact",
      "folds": 3,
      "rows_per_fold": 5897,
      "t5_columns": 10,
      "finite_pairs_per_fold": 53060,
      "nan_count_per_fold": 5910,
      "id_order_matches": true,
      "nan_masks_match": true,
      "changed_finite_values": 0,
      "boundary": "This compares cached X304 T5 values with default pandas CSV parsing, not with a dynamically reconstructed in-memory T5 array."
    },
    "csv_parser_sensitivity": {
      "comparison": "pandas default vs float_precision=round_trip",
      "changed_finite_values_by_fold": [27705, 27888, 27831],
      "finite_pairs_per_fold": 53060,
      "nan_masks_match": true,
      "max_abs_difference": 8.881784197001252e-16,
      "max_relative_difference": 1.0299913643759567e-13,
      "allclose_at_atol_1e_12_rtol_0": true,
      "same_parser_reexport_exact": true,
      "ulp_count_computed": false
    },
    "saved_model_single_model_replay": {
      "models": 15,
      "outer_model_row_instances": 29485,
      "max_probability_abs_delta_default_vs_round_trip": 0.004175363752329006,
      "outer_argmax_changes": 0,
      "training": false,
      "interpretation_boundary": "Per-model argmax stability does not prove ensemble invariance or dynamic T5 parity."
    },
    "saved_5_seed_baseline_replay": {
      "outer_rows": 5897,
      "stored_outer_argmax_matches": 5897,
      "baseline_correct": 3497,
      "baseline_micro_f1": 0.5930133966423605,
      "baseline_macro_f1": 0.5252719738966167,
      "round_trip_correct": 3497,
      "round_trip_micro_f1": 0.5930133966423605,
      "round_trip_macro_f1": 0.5252719738966167,
      "round_trip_argmax_changes": 0,
      "round_trip_gains": 0,
      "round_trip_losses": 0,
      "round_trip_changed_probability_rows": 15,
      "round_trip_pooled_max_probability_abs_delta": 0.0012018578769440735,
      "interpretation_boundary": "Re-inference of saved models on development OUTER rows; not retraining reproducibility or independent performance evidence."
    },
    "historical_score_gap": {
      "historical_s6_micro_f1_rounded": 0.59183,
      "current_sqrt_macro_micro_f1": 0.5930133966423605,
      "exploratory_six_source_mean_micro_f1": 0.5933525521451586,
      "attribution": "unresolved; this round does not establish CSV parsing as the cause"
    }
  },
  "severity_and_conditions": [
    {
      "severity": "major_scope_gap",
      "status": "unmeasured",
      "issue": "Dynamic T5-to-CSV parity was not calculated. The checked dynamic path requires all Train geometry for a global fishing mask and Train+Test geometry for shared harbors; no semantically equivalent development-only aggregate was found. The discovered train-only harbor cache has a different population.",
      "condition": "Do not breach the holdout feature boundary or substitute a different population. Leave parity unmeasured unless an exact eligible aggregate and provenance become available."
    },
    {
      "severity": "moderate_provenance_gap",
      "status": "unresolved",
      "issue": "Historical .59183 has no linked per-vessel prediction, source snapshot, or execution environment in inspected evidence.",
      "condition": "Keep historical score attribution unknown absent paired provenance."
    },
    {
      "severity": "minor_execution_record_gap",
      "status": "recorded",
      "issue": "Primary detached run has no actual exit code or launch-time source hash.",
      "condition": "Report result artifacts and captured logs as evidence; do not claim primary exit code 0."
    },
    {
      "severity": "minor_harness_issue",
      "status": "corrected_in_attempt_2",
      "issue": "Attempt 1 assumed the wrong fold-2 OUTER roster size (1966 rather than 1965).",
      "condition": "Retain failed script/log; attempt 2 records 1965 and actual exit code 0."
    }
  ],
  "score_claim_boundaries": {
    "goal_micro_f1_0_7_achieved": false,
    "stored_baseline_is_0_593013": true,
    "exploratory_0_593353_is_baseline_or_adopted": false,
    "valid_observation_loss_statement": "Existing audit did not find valid-observation loss in inspected inputs; not an exhaustive raw-data revalidation.",
    "historical_holdout_exposure_history_verified": false,
    "measurement_type": "Actual-development-data computation and saved-model inference/code validation; no retraining or hardware measurement."
  },
  "next_session_readiness": {
    "status": "not_blocked_for_bounded_development_candidate_exploration",
    "required_boundary": "Use the existing fixed development-only X304; do not read holdout rows, features, labels, or predictions.",
    "design_checks": [
      "Split each fold INNER into ES and SELECT before model/ensemble decisions.",
      "Refit seed-42 baseline on FIT for each fold using the same ES split; saved 5-seed replay is not retraining reproduction.",
      "Train candidate on FIT only; choose blend alpha only on that fold's SELECT subset.",
      "Freeze decisions before scoring each OUTER once.",
      "Describe outcomes as development exploration, not independent improvement proof.",
      "Keep T5/local_rel transductive population boundaries explicit."
    ],
    "residual_condition": "Dynamic T5 parity and historical .59183 provenance remain unresolved but do not block the fixed-cache development candidate comparison."
  },
  "candidate_availability": [
    {
      "candidate": "TabICL",
      "local_evidence": "Historical code, FIT-to-INNER path, and Python 3.12/Torch/TabICL metadata with an expected checkpoint hash exist.",
      "active_inspected_status": "No configured checkpoint found; active Python 3.13 has no Torch/TabICL package metadata.",
      "assessment": "Not currently runnable from inspected files/environment; existing INNER lineage needs verification before reuse."
    },
    {
      "candidate": "TabM",
      "local_evidence": "Historical source and split workflow exist; no checkpoint found in inspected package path.",
      "active_inspected_status": "Active Python 3.13 has no Torch/TabM package metadata.",
      "assessment": "Not currently runnable from inspected files/environment."
    },
    {
      "candidate": "S4",
      "local_evidence": "S4_model_choice_oracle.py consumes six existing OOF probability sources and performs OUTER oracle selection/weighting.",
      "assessment": "Not a new FIT-to-INNER estimator candidate."
    },
    {
      "candidate": "CatBoost_and_ExtraTrees",
      "local_evidence": "Not assessed in the preliminary TabICL/S4/TabM availability check.",
      "assessment": "Do not infer install/runtime availability from this review."
    }
  ],
  "sources": [
    "rounds/round_001/review/preliminary_review.md",
    "rounds/round_001/execution/result.json",
    "rounds/round_001/execution/supplemental_ensemble.json",
    "rounds/round_001/execution/launch_manifest.json",
    "rounds/round_001/execution/supplemental_attempt2_launch_manifest.json",
    "rounds/round_001/execution/supplemental_launch_manifest.json",
    "rounds/round_001/execution/run_t5_csv_roundtrip.py",
    "rounds/round_001/execution/replay_ensemble.py",
    "rounds/round_001/execution/environment.json",
    "rounds/round_001/ROUND_REPORT.md",
    "NEXT_SESSION.md",
    "D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/reports/final_report.md",
    "D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/reports/exp01/provenance_addendum.json",
    "D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/reports/exp01/data_validation.json",
    "D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/reports/exp01/final_summary.md",
    "D:/repos/fishing-track-classification/code/tools/run_005_F156_merge_20261101.py",
    "D:/repos/fishing-track-classification/code/tools/run_005_main_20261101.py"
  ]
}
