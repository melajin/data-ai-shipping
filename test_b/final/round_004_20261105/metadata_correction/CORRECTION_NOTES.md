# Round 4 Metadata Correction Notes: Deferred Observation Status

- **Task Reference**: `METADATA_FIX_SPEC.md` & `MIDDLE_RESULT_DECISION.md`
- **Owner**: Gemini (`gemini-3.8-flash`, high effort)
- **Directory**: `testB/final/round_004_20261105/metadata_correction/`
- **Date**: 2026-11-06
- **Status**: Completed, verified, rendered

---

## 1. Problem Statement & Root Cause

Per `CONTRACT.md` line 11:
> *"Missing/invalid adjacent observations are deferred flags, not proof of no behavior."*

And confirmed by team managers in `MIDDLE_RESULT_DECISION.md` line 7:
> *"previous_not_large는 관측부족이 아니라 ‘직전에도 작은 조건’이라는 정상적인 조건 불충족이다. missing_previous와 구분한다. missing_previous 6,287 / missing_next 963은 defer로 메타데이터 보완한다."*

In the initial implementation of `_build_stage_counts()` in `evaluate_sequence.py`, all non-keep transition reasons for Stage 1 and Stage 2 were uniformly assigned `status: "reject"`. This conflated two fundamentally different observational scenarios:
1. **Observation Gaps & Geometry Invalids** (`missing_previous`, `invalid_previous`, `missing_next`, `invalid_next`): The adjacent hour was not observed or had corrupt geometry. This is an information gap requiring **deferral** (`defer`), not proof that a transition did not occur.
2. **Condition Mismatches** (`previous_not_large`, `current_not_small`, `next_not_small`): The adjacent hour was observed and valid, but failed the physical threshold (e.g. prior hour was already small, current was not small, next was not small). This is a valid observational **rejection** (`reject`).

---

## 2. Source Code Preservation & Verification

Before modifying `evaluate_sequence.py`, the byte-exact original evaluator was copied into `metadata_correction/source_before_evaluator.py`.

### Source & Artifact Hashes (`source_hashes.json`)
- **Original Evaluator (`source_before_evaluator.py`)**: `7083bb0af757cb819b0f2fa53e2db596b2c230f4df3be42358f5f8e52a48cb8c`
- **Corrected Evaluator (`evaluate_sequence.py`)**: `a7a007ef8137019d43be77a517a9daf8b5d7acb29bb402c84b5e8c325d906da1`
- **Original Stage Counts (`execution_001/stage_counts.csv`)**: `e6bfa3b186711ec8b7eef5acb45ae16de9801dc15a069f0a990e8aa43811a1c5`
- **Corrected Stage Counts (`stage_counts_corrected.csv`)**: `4953339b1ff36e2e847f3ced3a59c5279c80917c7557472db92a74a7925b1c1a`

The original execution outputs in `execution_001/` remain 100% byte-exact and untouched.

---

## 3. Synthetic Fixture Verification (`fixture_result.json`)

Verification was executed via `check_metadata_fixture.py` on synthetic rows before rendering real data:
- `missing_previous` $\rightarrow$ `defer` (**Verified**)
- `invalid_previous` $\rightarrow$ `defer` (**Verified**)
- `previous_not_large` $\rightarrow$ `reject` (**Verified**)
- `current_not_small` $\rightarrow$ `reject` (**Verified**)
- `missing_next` $\rightarrow$ `defer` (**Verified**)
- `invalid_next` $\rightarrow$ `defer` (**Verified**)
- `next_not_small` $\rightarrow$ `reject` (**Verified**)
- All keep counts and row totals verified strictly identical.

---

## 4. Full Execution Comparison (`counts_comparison.json`)

The bounded rendering script `render_corrected_stage_counts.py` processed selected columns from `execution_001/candidate_ledger.parquet` and `execution_001/pool_manifest.csv` under native RAM preflight verification ($3904.6\,\text{MiB}$ available $\ge 1024.0\,\text{MiB}$ required).

### Status Classification Adjustments
| Stage | Reason | Original Status | Corrected Status | Row Count | Vessel Count | Description |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Stage 1** | `missing_previous` | `reject` | **`defer`** | 6,287 | 82 | Observation gap at $t-1$ |
| **Stage 1** | `previous_not_large` | `reject` | `reject` | 38,948 | 80 | Valid $t-1$ was already small ($\le 100\,\text{m}$) |
| **Stage 1** | `current_not_small` | `reject` | `reject` | 46,684 | 81 | Valid $t$ is not small ($> 100\,\text{m}$) |
| **Stage 2** | `missing_next` | `reject` | **`defer`** | 963 | 77 | Observation gap at $t+1$ |
| **Stage 2** | `next_not_small` | `reject` | `reject` | 2,434 | 75 | Valid $t+1$ was not small ($> 100\,\text{m}$) |
| **Stage 3** | `insufficient_eligible_peers` | `defer` | `defer` | 30 | 10 | Peer baseline scarcity |
| **Stage 3** | `own_insufficient_center_dates` | `defer` | `defer` | 9 | 7 | $<3$ distinct calendar dates in baseline |
| **Stage 3** | `own_insufficient_triples` | `defer` | `defer` | 152 | 60 | $<24$ triples in baseline |
| **Stage 3** | `singleton_no_peer_rule` | `defer` | `defer` | 47 | 1 | No peer comparison rule for singleton |

### Invariance Guarantees
- **Stage Keep Counts**:
  - `Stage 0`: 99,677 rows (82 RFIDs) — **Identical**
  - `Stage 1`: 7,758 rows (81 RFIDs) — **Identical**
  - `Stage 2`: 4,361 rows (77 RFIDs) — **Identical**
  - `Stage 3`: 4,123 rows (75 RFIDs) — **Identical**
- **Method Actual Pool Coverage**:
  - $B_0$: 99,677 rows (82 RFIDs) — **Identical**
  - $S$: 4,361 strict (77 RFIDs) + 1,690 fallback (5 RFIDs) — **Identical**
  - $G$: 4,123 strict (75 RFIDs) + 48 fallback stage2 (2 RFIDs) + 1,690 fallback stage0 (5 RFIDs) — **Identical**
- **Predictions & Metrics**:
  - Zero reranking, zero changes to scores, predictions, event results, or operational gate metrics.
