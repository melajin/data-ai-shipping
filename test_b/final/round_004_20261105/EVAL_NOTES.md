# Round 4 Evaluation and Runner Notes

- **Modules**: `evaluate_sequence.py`, `run_sequence.py`, `check_sequence_eval.py`
- **Receipts**: `eval_checks.json`
- **Owner**: Gemini (`gemini-3.8-flash`, high effort)
- **Contract Reference**: `CONTRACT.md` (v1) and `PROTOCOL.md` under `testB/final/round_004_20261105/`
- **Status**: Complete, verified (5/5 independent synthetic checks passed), integration ready

---

## 1. Executive Summary & Interface Specifications

The Round 4 evaluation and runner suite implements deterministic event evaluation, method-specific random expectations, paired vessel cluster bootstrap, explicit stage coverage ledgers, and safe resource preflight for the retrospective sequence transition models (`B0`, `S`, `G`).

### Public Interfaces

#### A. Evaluator API (`evaluate_sequence.py`)
```python
def evaluate_rules(
    artifacts: dict[str, Any],
    positives: pandas.DataFrame,
    output_dir: pathlib.Path,
) -> dict[str, Any]:
    ...
```
- **Inputs**:
  - `artifacts`: Output dictionary from `sequence_rules.build_rules()`, containing:
    - `"ledger"`: Full candidate DataFrame with boolean stage masks (`stage0_ok`, `stage1_ok`, `stage2_ok`, `stage3_ok`).
    - `"predictions"`: Pre-ranked predictions DataFrame from Luna (`rfid_id`, `method`, `rank`, `ts`, `ordinal`, `method_score`, `legacy_score`, `score_kind`, `actual_pool_n`, `cap`, `fallback_reason`).
    - `"pool_manifest"`: Manifest DataFrame defining assigned pool stages, actual pool sizes, and explicit fallback reasons.
    - `"diagnostics"`: Upstream rule diagnostics.
    - `"gear_registry"` (optional): Gear registry DataFrame from Round 3.
  - `positives`: Canonical positive events DataFrame (`acc_id`, `rfid_id`, `tier`, `conflict`, `acc_ts`).
  - `output_dir`: Target directory for artifact generation.
- **Outputs Written Directly to Disk**:
  1. `predictions.csv`: Written strictly before label join.
  2. `pool_manifest.csv`: Written strictly before label join.
  3. `candidate_ledger.parquet`: Preserved canonical row order and index with explanatory flags.
  4. `stage_counts.csv`: Transition, rejection, deferral, and fallback ledger.
  5. `stage_event_coverage.csv`: Event-window presence and strict vs fallback coverage.
  6. `event_results.csv`: Per-event hit status across methods (`B0`, `S`, `G`) and budgets ($k \in \{1, 4\}$).
  7. `metrics.json`: Fixed-denominator hit rates, paired bootstrap, random expectations, and operational gate.
  8. `diagnostics.json`: Summary counts, unobserved RFIDs, and shared helper hashes.
- **Returns**: Dictionary with in-memory references to `metrics`, `diagnostics`, `stage_counts`, `stage_event_coverage`, and `event_results`.

#### B. Execution Runner API (`run_sequence.py`)
```python
def run(
    output_dir: pathlib.Path = HERE / "execution_001",
    root: pathlib.Path = ROOT,
) -> int:
    ...
```
- **Command-line Interface**:
  ```bash
  python testB/final/round_004_20261105/run_sequence.py --output-dir testB/final/round_004_20261105/execution_001
  ```
- **Key Guarantees**:
  - Refuses overwrite if a complete `EXECUTION.json` receipt exists in `--output-dir`.
  - Executes RAM preflight check ($768\,\text{MiB}$ estimated peak + $640\,\text{MiB}$ reserve = $1408\,\text{MiB}$) before importing heavy libraries or loading data.
  - Enforces round directory boundary isolation (`output_dir` must reside inside the round folder).
  - Records input SHA256 hashes, source code SHA256 hashes, timing per stage, and process peak working set into `EXECUTION.json`.

---

## 2. Core Method & Evaluation Guarantees

### A. Prediction Integrity & No Reranking
- **No Evaluator Reranking**: The evaluator consumes predictions directly from `artifacts["predictions"]` as constructed by Luna (`sequence_rules.py`). It never alters candidate ordering, replaces `method_score`, or modifies ranks.
- **Shared Budget Cap**: All methods share $cap = \min(4, |G_{\text{actual}}|)$ per vessel. If a vessel has no observations, $cap = 0$ and predictions are empty.
- **Separate Method Pools**:
  - `B0`: Uses all Stage 0 valid candidates (`stage0_ok`).
  - `S`: Uses Stage 2 common transition candidates (`stage2_ok`), falling back to Stage 0 only if Stage 2 is empty (`fallback_reason: no_common_transitions`).
  - `G`: Uses Stage 3 peer-gear eligible candidates (`stage3_ok`), falling back to Stage 2 (`fallback_reason: no_gear_eligible_candidates`), then to Stage 0 (`no_common_transitions`), then empty (`no_observations`).

### B. Separate Method Actual Pools & Random Expectations
- **Actual Assigned Pools**: Rather than evaluating random expectation over an idealized pool, each method's random expectation is calculated strictly over its **actual assigned pool** (obtained via `pool_manifest` and the corresponding ledger boolean stage mask) and actual cap $k_{\text{cap}} = \min(cap, n)$.
- **Exact Combinatorial Formula**:
  For an event on vessel with actual pool size $n$, $h$ candidates within $[acc\_ts - 6, acc\_ts + 6]$, and budget $k_{\text{cap}}$:
  $$\text{Top1 Expected} = \begin{cases} \frac{h}{n} & \text{if } n > 0 \\ 0.0 & \text{if } n = 0 \end{cases}$$
  $$\text{Top4 Hit Probability} = \begin{cases} 1 - \frac{\binom{n - h}{k_{\text{cap}}}}{\binom{n}{k_{\text{cap}}}} & \text{if } n > 0, k_{\text{cap}} > 0, n - h \ge k_{\text{cap}} \\ 1.0 & \text{if } n > 0, k_{\text{cap}} > 0, n - h < k_{\text{cap}}, h > 0 \\ 0.0 & \text{otherwise} \end{cases}$$
- **Complete Pool Separation**: `B0`, `S`, and `G` pools, event records, and mean expectations are recorded separately across both `all` (100) and `tier01` (60) scopes.

### C. Fixed Denominators & Paired RFID Bootstrap
- **Preserved Denominators**: Denominators are strictly fixed to:
  - Whole 100 positive events ($N=100$, 82 unique RFIDs).
  - Tier 01 positive events ($N=60$, 55 unique RFIDs).
  Unobserved vessels (e.g. vessels with 0 frame rows or $cap=0$) are **never dropped from denominators**; they are recorded with `hit = False` and `abs_error = None`.
- **Paired RFID Cluster Bootstrap**:
  - Resampling unit is `rfid_id` to account for vessels with multiple accidents.
  - Repetitions: $B = 4000$, fixed seed: $20261105$.
  - Evaluated pairs: `G - B0`, `G - S`, `S - B0` across `all` and `tier01` at `top1` and `top4`.
  - Reuses verified Round 2 pure numerical helper `_bootstrap_diff` (with recorded dependency SHA256).

### D. Fixed Operational Gate Formulation
The operational gate in `metrics.json` records four explicit boolean conditions:
1. `tier01_top1_diff_g_vs_b0`: $\text{HitRate}(G, \text{top1}, \text{Tier01}) - \text{HitRate}(B0, \text{top1}, \text{Tier01}) \ge +0.05$ (+5.0 percentage points).
2. `tier01_top1_paired_bootstrap_ci95_lower`: Paired cluster bootstrap 95% CI lower bound $> 0.0$.
3. `whole100_top1_non_worsening`: $\text{HitRate}(G, \text{top1}, \text{All}) \ge \text{HitRate}(B0, \text{top1}, \text{All})$.
4. `tier01_top1_exceeds_random`: $\text{HitRate}(G, \text{top1}, \text{Tier01}) > \text{MeanRandomExpected}(G, \text{top1}, \text{Tier01})$.
- `overall_passed`: True iff all four conditions are met. Failures are explicitly enumerated in `gate_failures`.
- **No Probability Claims**: `"probability_outputs": false` is strictly enforced.

---

## 3. Explicit Ledger Formats

### A. Stage Counts Ledger (`stage_counts.csv`)
Reports three distinct accounting dimensions:
1. `candidate_transition`: Input, keep, reject, and defer counts with explicit reasons:
   - `stage0`: `geometry_valid_and_score_finite`, `invalid_geometry`, `non_finite_legacy_score`.
   - `stage1`: `observed_onset_large_to_small`, `missing_previous`, `invalid_previous`, `previous_not_large`, `current_not_small`.
   - `stage2`: `observed_persistence_at_t_plus_1`, `missing_next`, `invalid_next`, `next_not_small`.
   - `stage3`: `gear_peer_baseline_eligible`, `unknown_or_mixed_gear`, `own_insufficient_triples`, `own_insufficient_center_dates`, `singleton_no_peer_rule`, `insufficient_eligible_peers`.
2. `rfid_candidate_presence`: Distinct vessel counts with $\ge 1$ candidate at each strict stage.
3. `method_actual_pool_coverage`: Actual pool distribution and fallback reasons per method.

### B. Stage Event Coverage (`stage_event_coverage.csv`)
Provides full visibility into event-window presence and method behavior for all 100 positive events:
- Identifiers: `acc_id`, `rfid_id`, `tier`, `conflict`, `acc_ts`.
- Stratification: `primary_gear`, `is_single_code`, `gear_stratum`.
- Event Window Observability ($\pm 6\,\text{h}$): `observed_in_window`, `stage0_in_window`, `stage1_in_window`, `stage2_in_window`, `stage3_in_window`.
- Vessel Candidate Existence: `vessel_has_stage0`, `vessel_has_stage1`, `vessel_has_stage2`, `vessel_has_stage3`.
- Method Pool Stages & Fallbacks: `B0_pool_stage`, `S_pool_stage`, `G_pool_stage`, `G_fallback_reason`, `actual_G_cap`.
- Hits: `B0_hit_top1`, `B0_hit_top4`, `S_hit_top1`, `S_hit_top4`, `G_hit_top1`, `G_hit_top4`.

---

## 4. Verification Evidence (`eval_checks.json`)

Verification was executed via `check_sequence_eval.py` on independent synthetic fixtures (zero real dev parquets or TestB data accessed). All 5 checks passed cleanly:

| Check Name | Target Functionality | Status | Details |
| :--- | :--- | :---: | :--- |
| `random_hit_probabilities_exact` | Combinatorial hit formula | **Passed** | Verified $n=4,3,1,0,5$ against hand calculations |
| `paired_rfid_cluster_bootstrap` | Vessel cluster bootstrap | **Passed** | 1000 reps, seed 20261105 reproducibility verified |
| `distinct_method_predictions_and_fallbacks` | Multi-vessel simulation | **Passed** | Distinct winners ($B0=110, S=125, G=120$), fallbacks, and shared cap verified |
| `fixed_denominators_and_gate_evaluation` | Denominators & Gate checks | **Passed** | Preserved denominators, gate check reporting verified |
| `runner_preflight_and_overwrite_protection` | RAM & Overwrite guards | **Passed** | Native RAM query, process inventory, complete receipt protection verified |

---

## 5. Ready Command for Coordinator

The evaluation module and execution runner are complete, verified, and ready for end-to-end integration execution by the coordinator:

```bash
python testB/final/round_004_20261105/run_sequence.py --output-dir testB/final/round_004_20261105/execution_001
```
