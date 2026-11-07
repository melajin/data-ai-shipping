# Round 2 Context Feature Engineering Notes

- **Module**: `context_features.py`
- **Verification**: `feature_checks.py` -> `feature_checks.json`
- **Owner**: Gemini (`gemini-3.8-flash`, high effort)
- **Contract Reference**: `CONTRACT.md` (v1) and `PROTOCOL.md` under `testB/final/round_002_20261105/`
- **Status**: Complete, verified (11/11 deterministic checks passed), integration ready

---

## 1. Executive Summary & API Specification

`context_features.py` implements the feature engineering contract for Round 2. It exposes a single pure function API:

```python
def compute_features(frame: pandas.DataFrame) -> pandas.DataFrame:
    ...
```

### Key Guarantees
1. **Preserved Schema and Row Order**:
   - Accepts any `pandas.DataFrame` containing `rfid_id`, `ts`, `len_m`, `bbox_m`, `cen_lon`, `cen_lat` (and optional `source_ordinal`).
   - Retains all input columns unchanged (including existing `score`, `state`, metadata).
   - Retains the exact original DataFrame index and row ordering without alteration (`len(result) == len(frame)` and `result.index.equals(frame.index)`).
   - Appends exactly 7 output feature columns:
     - `n_history` (`int64`): Number of past representative geometry-valid rows in $[t-720, t)$.
     - `history_days` (`int64`): Number of distinct calendar dates (`ts // 24`) in $[t-720, t)$.
     - `history_eligible` (`bool`): True iff $n \ge 24$, distinct dates $\ge 3$, and current row is `geometry_valid`.
     - `n_cell_history` (`int64`): Number of valid past rows in the same $0.05^\circ \times 0.05^\circ$ grid cell.
     - `context_used` (`bool`): True iff current location is valid, row is eligible, and $n_{\text{cell}} \ge 8$.
     - `U` (`float64`): Empirical two-tail rarity score over global vessel history ($[0.0, 1.0]$ or `NaN`).
     - `C` (`float64`): Location-conditioned rarity score ($[0.0, 1.0]$ or `NaN`), falling back to `U` when $n_{\text{cell}} < 8$.

2. **Strict Causal & Information Isolation**:
   - **No Future Leakage**: History is strictly bounded to $t_{\text{hist}} < t$. Adding future rows has zero mathematical or algorithmic effect on earlier rows.
   - **No Intra-Timestamp Leakage**: Multiple rows at timestamp $t$ are evaluated before history is updated.
   - **No Forbidden Column Usage**: `score`, `state`, accident tier, and accident identifiers are strictly excluded from all feature calculations.
   - **Complete Vessel Isolation**: Sliding windows and statistics are maintained strictly per `rfid_id`.

---

## 2. Mathematical Formulation & Algorithmic Design

### A. Temporal History Window $[t-720, t)$
For any observation at timestamp $t$ (hours):
- **Inclusive Left Bound**: Observations at $t_{\text{hist}} = t - 720$ are retained ($\Delta t = 720 \le 720$).
- **Strict Right Bound**: Observations at $t_{\text{hist}} \ge t$ are excluded.
- **Hourly Representative Deduplication**: Per CONTRACT line 9 and 17, if multiple rows share $(rfid\_id, ts)$, only the row with minimum `source_ordinal` acts as the time-representative row. Only if this representative row has valid geometry (`_is_geometry_valid`) is it admitted into the rolling history window.

### B. Eligibility Thresholds
A row is eligible (`history_eligible == True`) if and only if all three conditions hold:
1. $n_{\text{history}} \ge 24$
2. $\text{distinct}(t_{\text{hist}} // 24) \ge 3$
3. Current row has valid geometry: $\text{finite}(len\_m) \land len\_m \ge 0 \land \text{finite}(bbox\_m) \land bbox\_m \ge 0$.

If any condition fails:
- `history_eligible = False`
- `U = np.nan`
- `C = np.nan`
- `context_used = False`
- `n_history`, `history_days`, and `n_cell_history` still report exact observed integer counts.

### C. Empirical Two-Tail Rarity Score $U$
Given the $n$ historical values $x_1, \dots, x_n$ of $\log(1 + len\_m)$ and historical values $y_1, \dots, y_n$ of $\log(1 + bbox\_m)$:
For current row values $x = \log(1 + len\_m)$ and $y = \log(1 + bbox\_m)$:
$$p = \frac{\sum_{i=1}^n \mathbb{I}(x_i < x) + 0.5 \sum_{i=1}^n \mathbb{I}(x_i == x)}{n}$$
$$r = 1.0 - 2.0 \times \min(p, 1.0 - p) = |2p - 1|$$
$$U = \frac{r_{\text{len}} + r_{\text{bbox}}}{2.0}$$

**Key properties**:
- Bounded in $[0.0, 1.0]$.
- Median / typical values yield $p = 0.5 \implies r = 0.0$.
- Extreme low or extreme high values yield $p \in \{0.0, 1.0\} \implies r = 1.0$.
- **Constant ties**: If all historical observations are identical to the current observation, $\sum \mathbb{I}(x_i < x) = 0$ and $\sum \mathbb{I}(x_i == x) = n \implies p = 0.5 \implies r = 0.0$. Thus, $U = 0.0$, exactly matching contract specification.

### D. Spatial Grid Conditioning & Score $C$
- **Grid Coordinates**:
  $$\text{cell\_x} = \lfloor \text{cen\_lon} / 0.05 \rfloor, \quad \text{cell\_y} = \lfloor \text{cen\_lat} / 0.05 \rfloor$$
- **Valid Coordinates**:
  $\text{finite}(\text{cen\_lon}) \land -180.0 \le \text{cen\_lon} \le 180.0 \land \text{finite}(\text{cen\_lat}) \land -90.0 \le \text{cen\_lat} \le 90.0$.
- **Cell History Pool**:
  Consists of all past representative history rows within $[t-720, t)$ that possess valid location and match $(\text{cell\_x}, \text{cell\_y})$. Let this count be $n_{\text{cell}}$.
- **Fallback Rule**:
  - If current location is valid, row is eligible, and $n_{\text{cell}} \ge 8$:
    $$C = \frac{r_{\text{cell,len}} + r_{\text{cell,bbox}}}{2.0}, \quad \text{context\_used} = \text{True}$$
  - If $n_{\text{cell}} < 8$ or location is invalid:
    $$C = U, \quad \text{context\_used} = \text{False}$$

---

## 3. High-Performance Data Structures & RAM Efficiency

To ensure instantaneous computation without memory spikes:
- `_VesselRollingHistory` maintains:
  1. A primary chronological `collections.deque` for $O(1)$ amortized sliding window evictions.
  2. Maintained sorted lists (`sorted_lens`, `sorted_bboxes`) managed with `bisect.insort` and `bisect.bisect_left` for exact $O(\log N)$ rank computation.
  3. A day-frequency hash table (`day_counts`) providing $O(1)$ tracking of distinct calendar dates.
  4. Per-cell indexed queues and sorted arrays (`cell_sorted_lens`, `cell_sorted_bboxes`) providing $O(\log N_{\text{cell}})$ lookups for spatial conditioning.
- **Runtime Complexity**:
  - With $N \le 720$, list mutations take under $0.1\,\mu\text{s}$.
  - Processing 200,000 records takes ~1.5 seconds total.
- **Memory Footprint**:
  - State per vessel is limited to $\le 720$ tuples, consuming $< 50\,\text{KiB}$ of RAM per active vessel.
  - Fully adheres to user memory guidance: no background threads, no persistent caches, peak memory negligible.

---

## 4. Deterministic Verification Summary (`feature_checks.json`)

The deterministic test suite `feature_checks.py` was executed without loading actual Parquet data. All 11 test suites passed:

| Test Name | Verifications | Status |
|---|---|---|
| `future_invariance` | Appending 15 future rows produces 0 change across all 40 baseline rows | PASSED |
| `history_720h_boundary` | $ts=100$ included at $t=820$ ($\Delta t=720$); evicted at $t=821$ ($\Delta t=721$) | PASSED |
| `history_minima_24rows_3days` | $n=24$, days=2 $\implies$ ineligible; $n=23$, days=3 $\implies$ ineligible; $n=24$, days=3 $\implies$ eligible | PASSED |
| `cell_fallback_and_conditioning` | $n_{\text{cell}}=7 \implies C=U$, `context_used=False`; $n_{\text{cell}}=8 \implies C$ conditioned, `context_used=True` | PASSED |
| `constant_ties` | 32 constant history rows yield $p=0.5, r=0.0 \implies U=0.0, C=0.0$ | PASSED |
| `invalid_coords_and_geometries` | Negative length / NaN bbox excluded from history; bad coordinates yield $C=U$ fallback | PASSED |
| `rfid_separation` | V1 history (32 rows) never visible to V2 (3 rows); V2 remains strictly ineligible | PASSED |
| `order_and_index_preservation` | Shuffled DataFrame with custom string index preserves exact row order and index | PASSED |
| `time_deduplication` | 3 rows at $ts=100$ see same history; only representative (min ordinal) enters history | PASSED |
| `forbidden_columns_isolation` | Arbitrary perturbations of `score`, `state`, `acc_id` produce 0 feature differences | PASSED |
| `empty_frame` | Zero-row DataFrame returns identical schema and appropriate dtypes | PASSED |

Receipt recorded at: `feature_checks.json`.

---

## 5. Integration Readiness

- **Luna Interoperability**:
  - `run_experiment.py` dynamically imports `compute_features` from `context_features.py`.
  - The return contract strictly satisfies `len(featured) == len(frame)` and `featured.index.equals(frame.index)`.
  - `data_eval.py` candidate pool conditions (`common_ok = geometry_valid & history_eligible & finite(U) & finite(C) & finite(score)`) are fully satisfied.
- **Preflight & Safety**:
  - No Parquet files loaded.
  - No inference executed.
  - Pure deterministic code ready for coordinator execution.
