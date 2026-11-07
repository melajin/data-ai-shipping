# Round 8 Shape Evaluator and Runner Notes — Gemini Owner

## 1. System Architecture and Ownership Boundaries

- **Gemini scope**: `evaluate_shape.py`, `run_shape.py`, `check_shape_eval.py`, `eval_checks.json`, `EVAL_NOTES.md`, and small synthetic verification artifacts (`synthetic_execution/`).
- **Luna scope**: `extract_geometry.py`, `shape_rules.py`, `check_extract_geometry.py`, `check_shape_rules.py`, `EXTRACT_NOTES.md`, `RULE_NOTES.md`.
- **Coordinator / Root scope**: Contract reconciliation (`CONTRACT.md`), integration sign-off (`INTEGRATION_SIGNOFF_DESIGN.md`, `INTEGRATION_FIXES_03_REVIEW_BOUNDARIES.md`), and final data release for actual devset evaluation.
- **Strict boundary**: Implementation and synthetic unit/fixture checks only. No actual dev parquets or Test B datasets are accessed, and no model training, Test B inference, or external submissions are performed. Actual execution on real dev data is held until root integration release and immediate RAM preflight.

---

## 2. Review Disposition and Root Addenda

Per `REVIEW_IMPLEMENTATION_TERRA.md` and `INTEGRATION_FIXES_03_REVIEW_BOUNDARIES.md`:
Root accepted three boundary defects identified by Terra review:
1. **Time & Ordinal Key Validation Before Cast**:
   Original raw columns must be validated for finite integer values, non-boolean, non-negative range, and source-clock hours **before** any type conversion. Early `astype('int64')` in runner was removed; `validate_raw_keys()` enforces this on raw inputs for both canonical and geometry frames.
2. **Explicit Missingness and Finite/Infinite State Agreement**:
   Shared numeric comparison (`validate_and_merge_geometry`) now strictly compares missingness (`isna()`) and finite/infinite states. One-sided missingness or NaN-skipping false matches are completely prevented.
3. **Exact Integer Count +5%p Operational Gate Boundary**:
   The primary gate condition 1 (+5.0 percentage points) now evaluates exact count:
   $$20 \times (G_{\text{hits}} - B0_{\text{hits}}) \ge n_{\text{tier01}}$$
   This prevents binary floating-point rounding errors where $5/60$ vs $2/60$ ($+3/60 = +0.05$) yielded $0.049999999999999996 < 0.05$.
4. **Post-Evaluation Frozen Byte-Identity Verification**:
   Pre-label frozen SHA-256 hashes for `predictions.csv` and `pool_manifest.csv` are checked post-evaluation against final disk files; any mutation triggers `RuntimeError`.
5. **Updated RAM Preflight Accounting**:
   Resource allocation accounting explicitly covers Luna extraction ($768$ MiB), Sonnet review ($512$ MiB), and system reserve ($640$ MiB), giving a total requirement of $1920$ MiB ($2,013,265,920$ bytes).

---

## 3. Evaluator Implementation (`evaluate_shape.py`)

- **Pre-Label Frozen Persistence**:
  In `evaluate_shape()`, pre-label files are persisted if not already present. If already written by `run_shape.py` before label parsing, re-writing is bypassed to guarantee byte-identical preservation.
- **Strict Integer Epoch-Hours**:
  The canonical source clock operates purely on integer epoch hours via `to_epoch_hour()`.
  - Integer values are preserved directly without datetime or timezone conversion.
  - Nanosecond-scaled timestamps, fractional hours, or timezone shifts are rejected with `ValueError`.
  - Selected predictions with `pd.NaT` raise `ValueError`.
- **Generic Stage Specification (`STAGE_SPEC`)**:
  Consumes generic stage dictionaries (`s0`..`s4`), dynamically building `stage_counts.csv` across three categories:
  1. `candidate_transition`: `input`, `keep`, `reject`, `defer`, `not_applicable`.
  2. `rfid_candidate_presence`: `present_ge_1`, `absent_zero`.
  3. `method_actual_pool_coverage`: `primary_pool`, `fallback_pool`, `empty_pool`.
- **Event Coverage and Linkage**:
  - `stage_event_coverage.csv` records window observability across stages $s_0..s_4$ for each incident event.
  - Repeat incidents on the same vessel RFID share the exact same prediction list without quota splits.
  - `event_results.csv` records predictions, absolute time errors, hit booleans ($|t_{\text{pred}} - t_{\text{acc}}| \le 6$ hours), pool stages, fallback reasons, and actual pool sizes.
- **Method & Cohort Separate Random Expectations**:
  Random expectations are calculated strictly over each method's actual candidate pool and cap:
  - Top-1: $h / n$ ($0.0$ if $n = 0$).
  - Top-4: Exact combinatorial hypergeometric probability $1 - \frac{\binom{n-h}{k_{\text{cap}}}}{\binom{n}{k_{\text{cap}}}}$.
  - Computed and stored strictly separately for `all` (100 events / 82 RFIDs) and `tier01` (60 events / 55 RFIDs) scopes.
  - Verified numerically that Tier01 G random expectation differs from All G random expectation ($0.7222$ vs $0.6333$), and that the operational gate strictly evaluates against Tier01 G random expectation.
- **Paired RFID Cluster Bootstrap**:
  - $B = 4000$ paired cluster bootstrap resamples clustered by vessel RFID with fixed seed $20261105$.
  - Generates mean difference and two-sided 95% confidence intervals for $G - B_0$, $G - S$, and $S - B_0$ across $k \in \{1, 4\}$.
- **Primary Operational Gate**:
  Evaluates strictly $G$ vs $B_0$ top-1 with four explicit booleans and observed values:
  1. `tier01_top1_diff_g_vs_b0`: Exact integer count $20 \times (G_{\text{hits}} - B0_{\text{hits}}) \ge n_{\text{tier01}}$ (observed float difference reported descriptively).
  2. `tier01_top1_ci95_lower_positive`: Paired RFID cluster bootstrap 95% CI lower bound $> 0.0$.
  3. `whole100_non_worsening`: All-100 top-1 integer count $G_{\text{hits}} \ge B0_{\text{hits}}$ ($G - B_0 \ge 0.0$).
  4. `tier01_top1_exceeds_random`: Tier01 $G$ top-1 hit rate strictly exceeds **Tier01** $G$ actual-pool random expectation.

---

## 4. Runner Implementation (`run_shape.py`)

### 4.1. Raw Key Validation (`validate_raw_keys`)
```python
def validate_raw_keys(df: Any, name: str = "frame") -> Any
```
- Validates raw uncasted columns:
  - `ts`: non-boolean, numeric, finite, non-negative, exact integer (`ts % 1 == 0`), bounded within reasonable epoch-hours ($\le 10,000,000$).
  - `source_ordinal`: non-boolean, numeric, finite, non-negative, exact integer, unique.
  - `(rfid_id, ts)`: unique pairs.
- Returns DataFrame with strictly validated `int64` and `str` types.

### 4.2. Geometry Merge & State Agreement (`validate_and_merge_geometry`)
```python
def validate_and_merge_geometry(canonical_frame: Any, geom_df: Any, tolerances: dict[str, float] | None = None) -> Any
```
- Validates raw keys on both frames via `validate_raw_keys`.
- Compares missingness (`isna()`) on shared numeric columns (`len_m`, `bbox_m`, `cen_lon`, `cen_lat`, `score`). One-sided missingness strictly raises `ValueError`.
- Compares finite vs infinite states. Sign-checks infinite pairs. Compares finite pairs against declared tolerances.
- Excludes duplicate numeric columns from `geom_df` before one-to-one inner merge to prevent column suffixing (`_x`, `_y`), verifying original canonical order is preserved.

### 4.3. Extractor Receipt & Manifest Integrity (`validate_extractor_receipt`)
```python
def validate_extractor_receipt(geom_dir: Path | str, expected_rows: int = 99677) -> dict[str, Any]
```
- Consumes extractor `runtime_receipt.json`. Requires `status == "complete"`, explicit `mismatch_count == 0`, `error_count == 0`, `rows_written == 99677`, `canonical_rows_expected == 99677`, and `release_ready_for_scoring is True` (no absent-field-as-success).
- Verifies `geometry_ledger.parquet` SHA-256 against `output_manifest.json`.

### 4.4. Traceback & Failure Receipt Preservation
- Module-level `import traceback`.
- Exception handler in `run()` records `traceback: traceback.format_exc()` into `EXECUTION.json` with `status: "failed"` and `exit_code: 1`.

### 4.5. Strict Fresh Directory & Source Tracking
- Runner strictly checks `if output_dir.exists() and (output_dir.is_file() or any(output_dir.iterdir())):` and immediately refuses execution with exit code 1 to protect prior failure evidence and results.
- `execution["sources"]` records hashes for `evaluate_shape.py`, `run_shape.py`, `check_shape_eval.py`, `shape_rules.py`, `round_002_20261105/data_eval.py`, `PROTOCOL.md`, `CONTRACT.md`, plus extractor receipt/manifest/parquet.

---

## 5. Verification Suite and Results (`check_shape_eval.py`)

Verification is fully automated in `check_shape_eval.py` across 14 test suites, with all outputs saved to `eval_checks.json`.

```
=== Running Round 8 Evaluation Suite Verification ===
  [PASS] epoch_hour_conversion (0.000s)
  [PASS] combinatorial_random_hit (0.000s)
  [PASS] paired_rfid_bootstrap (0.047s)
  [PASS] stage_counts_ledger (0.007s)
  [PASS] evaluator_end_to_end (1.153s)
  [PASS] gate_cohort_boundaries (2.205s)
  [PASS] actual_schema_merge_and_keys (0.020s)
  [PASS] raw_key_validation_and_runner_fractional (0.010s)
  [PASS] shared_numeric_missingness_infinity (0.042s)
  [PASS] exact_5pp_gate_boundary (0.000s)
Executing in SYNTHETIC test mode...
Synthetic execution completed successfully.
  [PASS] frozen_hashes_post_eval (2.059s)
  [PASS] extractor_receipt_validation (0.025s)
  [PASS] strict_fresh_dir_and_traceback (0.785s)
Executing in SYNTHETIC test mode...
Synthetic execution completed successfully.
  [PASS] runner_preflight_isolation (1.844s)

Saved verification results to eval_checks.json
Overall status: ALL TESTS PASSED
```

### Complete 14-Suite Test Registry and Derived Results

| # | Test Name | Key Assertions / Invariants | Status | Elapsed |
| :-: | :--- | :--- | :---: | :---: |
| 1 | `epoch_hour_conversion` | Integer hours preserved; hour-aligned timestamps converted; 24ns timestamps rejected; non-aligned and fractional hours raise `ValueError`; NaT in active predictions rejected. | PASS | 0.000s |
| 2 | `combinatorial_random_hit` | Exact match against hand-calculated values: $n=10, h=2, k=1 \to 0.20$; $k=2 \to 1 - \frac{28}{45} \approx 0.3778$; $k=4 \to \frac{2}{3} \approx 0.6667$; boundary conditions ($h=0, k=0, n=0, h \ge n$). | PASS | 0.000s |
| 3 | `paired_rfid_bootstrap` | RFID cluster bootstrap generates exact deterministic CIs ($B=4000$, seed $20261105$); extreme separated and identical-hit fixtures match theoretical expectations. | PASS | 0.047s |
| 4 | `stage_counts_ledger` | Generic stage transitions tracked across $s_0..s_4$; category types `candidate_transition`, `rfid_candidate_presence`, and `method_actual_pool_coverage` dynamically generated. | PASS | 0.007s |
| 5 | `evaluator_end_to_end` | Multi-vessel fixture ($4, 3, 1, 0$ caps), fallbacks, repeat events on same RFID; all 8 artifacts emitted; prelabel persistence verified; numeric random expectations verified ($0.7222$ Tier01 G vs $0.6333$ All G; gate expectation equals Tier01 G). | PASS | 1.153s |
| 6 | `gate_cohort_boundaries` | Passing fixture validates all 4 gate booleans (`overall_passed: true`); failing fixture with perturbed predictions triggers gate failures and records explicit failure reasons. | PASS | 2.205s |
| 7 | `actual_schema_merge_and_keys` | Extractor schema merge with duplicated numerics and null geometry produces unsuffixed columns; duplicate `source_ordinal`, duplicate `(rfid_id, ts)`, fractional hours, and numeric discrepancies rejected. | PASS | 0.020s |
| 8 | `raw_key_validation_and_runner_fractional` | Uncasted raw key validation strictly rejects fractional `ts` ($123.5$), fractional `source_ordinal` ($10.5$), boolean keys, negative values, out-of-range timestamps, and duplicate keys before any lossy cast. | PASS | 0.010s |
| 9 | `shared_numeric_missingness_infinity` | Shared numeric comparisons explicitly check missingness and finite/infinite states; rejects one-sided NaNs, full-column NaNs vs finite, and sign mismatches in infinite values. | PASS | 0.042s |
| 10 | `exact_5pp_gate_boundary` | Exact count condition $20 \times (G - B_0) \ge n_{\text{tier01}}$: $5/60$ vs $2/60$ passes condition 1 despite float $0.049999999999999996$; $4/60$ vs $2/60$ fails condition 1; equal-count non-worsening verified. | PASS | 0.000s |
| 11 | `frozen_hashes_post_eval` | Pre-label frozen `predictions.csv` and `pool_manifest.csv` SHA-256 hashes verified byte-identical post-evaluation, with equality confirmed in execution receipt. | PASS | 2.059s |
| 12 | `extractor_receipt_validation` | `validate_extractor_receipt` validates complete receipt and manifest hash; rejects nonzero mismatches/errors, unready scoring, absent required fields, and hash mismatches. | PASS | 0.025s |
| 13 | `strict_fresh_dir_and_traceback` | Runner refuses existing non-empty directory preserving prior evidence; runner failure writes `EXECUTION.json` with full formatted traceback without `NameError`. | PASS | 0.785s |
| 14 | `runner_preflight_isolation` | RAM preflight accounting ($1920$ MiB = $768$ extract + $512$ review + $640$ reserve), working set tracking, round directory boundary check, and synthetic runner execution verified in clean temporary directory. | PASS | 1.844s |

---

## 6. Code Hashes (SHA-256)

- `run_shape.py`: `a71f0c014a057ee199bec5dfe36695279a9e3964d5e52f39f0549137e5fa8dcf`
- `evaluate_shape.py`: `a44526673ce492b1fbbbfe3df6a581c11df63ca1c68cdab17c7cf850d02cdb4d`
- `check_shape_eval.py`: `24bc256103109b10f7224dc32fd16829832adfb878d059d6cd408c17b91ef983`
- `eval_checks.json`: `a32e76f00ae28ae75709f522141538f6c604bb3ac8c14801a49cc1d51f627471`

---

## 7. Readiness for Root Release

1. **All Review Defects Resolved**: Key validation prior to cast, explicit missingness and finite/infinite state comparisons, exact count $+5$\%p threshold calculation, post-eval byte-identical hash verification, and updated RAM preflight ($1920$ MiB) are fully implemented and verified.
2. **Deterministic Reproducibility**: All 14 unit tests in `check_shape_eval.py` pass cleanly in $\approx 8.3$ seconds with zero errors or warnings.
3. **Standing by for Root Integration**: Gemini worker implementation is finished. No further actions or real data reads will be executed until root issues the integration release.
