# Round 9 Independent Inventory Notes: Contiguous Triples & Transition Patterns

**Worker**: Gemini (Dispatched Worker)  
**Task ID**: `task_47b43dfe0155`  
**Dispatch ID**: `ctx_a5737b7ae5b9`  
**Coordinator Session**: `orca_session_id:codex_a55fd2e5_500d_4503_925f_12df6a69b424`  
**Date**: 2026-11-06  
**Status**: Completed successfully (Exit Code 0)

---

## 1. Operational Overview & Boundaries

Per `TASK_GEMINI.md`, `PROTOCOL.md`, and `CONTRACT.md`:
- **Role**: Gemini independently counts all valid contiguous triples and `small-small-non-small` patterns across all 82 RFIDs and the full observation period on existing R4 canonical numeric data (`round_004_20261105/execution_001/candidate_ledger.parquet`, 99,677 rows) and R3 gear registry (`round_003_20261105/gear_registry.csv`).
- **Scope & Independence**:
  - Implemented entirely within `independent_inventory.py` without importing Luna's module (`transition_rules.py`).
  - Completely blind to event/accident/label data (no positive labels loaded, no training, no scoring, no Test B inference).
  - Derived strictly from tabular numeric columns; makes no claims of physical normal state, real waiting, or vessel restart.
- **Root Gate Purpose**: Root runner uses these independent counts as an automated pre-label concordance gate before positive labels are loaded into memory.

---

## 2. Resource & Memory Preflight Accounting

Under the user memory protocol (2026-11-05), RAM preflight was executed before loading canonical tables:
- **Available Physical RAM**: 4,084.96 MiB (4,283,387,904 bytes)
- **Memory Requirement**: 1,920 MiB (2,013,265,920 bytes)
  - Gemini Inventory Budget: 512 MiB
  - Luna Synthetic Fixtures Budget: 768 MiB
  - System Safety Reserve: 640 MiB
- **Preflight Outcome**: **PASSED** (4,084.96 MiB $\ge$ 1,920 MiB).
- **Execution Resource Consumption**:
  - **Peak Working Set**: 154.0 MiB (161,484,800 bytes), well within the 512 MiB allocation.
  - **Total Wall Clock Runtime**: 1.488 seconds.
  - **Counting Kernel Time**: 0.455 seconds.

---

## 3. Inventory Methodology & Contract Alignment

### 3.1 Raw Key Validation Before Cast
Adhering to the Terra review defect resolution from Round 8, raw columns are validated before any casting:
- `rfid_id`: String, non-empty, non-null.
- `ts`: Integer source-clock epoch-hours ($[0, 10,000,000]$), finite, non-negative, non-boolean, no fractional hours (`ts % 1 == 0`).
- `source_ordinal`: Integer, finite, non-negative, non-boolean, unique, no fractional values (`source_ordinal % 1 == 0`).
- `(rfid_id, ts)`: Uniquely identifies each observation (0 duplicates across 99,677 rows).

### 3.2 Contiguous Triples (`triplet_valid`)
- Historical reference and candidate triple unit is defined as contiguous observations at integer hours $(t-2, t-1, t)$ for the same vessel.
- **Geometry Validity**: Finite `len_m >= 0` and `bbox_m >= 0`.
- **Legacy Score Independence**: Contiguous triple validity is evaluated strictly on geometry, independent of whether legacy `score` is finite.
- A triple is valid if and only if observations at $t-2$, $t-1$, and $t$ exist for that `rfid_id` and all three exhibit valid geometry.

### 3.3 Transition Pattern (`pattern`)
- A triple $(t-2, t-1, t)$ constitutes an observed transition pattern if:
  1. `triplet_valid` is `True`.
  2. `is_small(t-2)` is `True` ($\text{len\_m} \le 100$ and $\text{bbox\_m} \le 100$).
  3. `is_small(t-1)` is `True` ($\text{len\_m} \le 100$ and $\text{bbox\_m} \le 100$).
  4. `is_small(t)` is `False` ($\text{len\_m} > 100$ or $\text{bbox\_m} > 100$).

---

## 4. Aggregate Inventory Findings

### 4.1 Global Counts
| Metric | Count | Fraction of Canonical Rows | Fraction of Valid Triples |
| :--- | :--- | :--- | :--- |
| **Total Canonical Rows** | 99,677 | 100.00% | — |
| **Total Valid RFIDs** | 82 | 100.00% | — |
| **Valid Contiguous Triples (`valid_triple_n`)** | **88,036** | 88.32% | 100.00% |
| **Transition Patterns (`pattern_n`)** | **3,807** | 3.82% | 4.32% |

### 4.2 Breakdown by Primary Gear
| Primary Gear | Vessels | Canonical Rows | Valid Triples | Patterns | Pattern Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **연안복합** (Coastal Mixed) | 37 | 29,209 | 25,703 | 1,470 | 5.72% |
| **자망** (Gillnet) | 31 | 48,272 | 42,921 | 1,733 | 4.04% |
| **통발** (Trap) | 13 | 20,288 | 17,677 | 564 | 3.19% |
| **채낚기연승낚시** (Jigging/Longline) | 1 | 1,908 | 1,735 | 40 | 2.31% |
| **Total** | **82** | **99,677** | **88,036** | **3,807** | **4.32%** |

---

## 5. Earliest Pattern Cases (`cases.csv`)

Per contract: deterministic selection of one earliest pattern per gear, breaking ties by `ts ASC`, `rfid_id ASC` (lexicographical), then `source_ordinal ASC`. For each selected pattern, exactly 3 source rows $(t-2, t-1, t)$ are recorded (4 gears $\times$ 3 rows = 12 rows total):

| Gear | Step | RFID | ts | Source Ordinal | len_m | bbox_m | cen_lon | cen_lat | Score | is_small |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **연안복합** | $t-2$ | 36316040 | 490904 | 6110 | 0.000 | 0.000 | 126.559830 | 36.030098 | 0.230875 | True |
| **연안복합** | $t-1$ | 36316040 | 490905 | 6665 | 0.000 | 0.000 | 126.559830 | 36.030098 | 0.230184 | True |
| **연안복합** | $t$ | 36316040 | 490906 | 7176 | 1951.753 | 454.466 | 126.559446 | 36.030637 | 0.347534 | False |
| **자망** | $t-2$ | 35200311 | 490896 | 43 | 30.447 | 12.169 | 127.105004 | 34.669916 | 0.000001 | True |
| **자망** | $t-1$ | 35200311 | 490897 | 131 | 41.559 | 23.719 | 127.105141 | 34.669948 | 0.332555 | True |
| **자망** | $t$ | 35200311 | 490898 | 3588 | 124.005 | 99.268 | 127.105452 | 34.670547 | 0.355718 | False |
| **채낚기연승낚시** | $t-2$ | 36314076 | 490946 | 24168 | 4.639 | 3.903 | 125.128793 | 34.050372 | 0.262068 | True |
| **채낚기연승낚시** | $t-1$ | 36314076 | 490947 | 24337 | 7.189 | 4.210 | 125.128785 | 34.050364 | 0.212392 | True |
| **채낚기연승낚시** | $t$ | 36314076 | 490948 | 24575 | 201.794 | 172.086 | 125.128697 | 34.050341 | 0.480174 | False |
| **통발** | $t-2$ | 31100492 | 490898 | 3463 | 0.000 | 0.000 | 126.133183 | 34.365003 | 0.243815 | True |
| **통발** | $t-1$ | 31100492 | 490899 | 3763 | 74.130 | 18.532 | 126.133183 | 34.364950 | 0.317535 | True |
| **통발** | $t$ | 31100492 | 490900 | 4041 | 212.866 | 23.934 | 126.133231 | 34.364848 | 0.331588 | False |

---

## 6. Root Concordance Interface Verification

`run_transition.py` performs the following checks before positive labels are loaded:
```python
own_counts = ledger.groupby("rfid_id", sort=True).agg(
    valid_triple_n=("triplet_valid", "sum"), 
    pattern_n=("pattern", "sum")
).astype("int64")
inv = pd.read_csv(inventory, dtype={"rfid_id": str})
inv = inv.set_index("rfid_id")[["valid_triple_n", "pattern_n"]].sort_index().astype("int64")
if not own_counts.equals(inv):
    raise ValueError("Independent pattern counts disagree")
summary = json.loads(inv_summary.read_text(encoding="utf-8-sig"))
for field in ["valid_triple_n", "pattern_n"]:
    if int(summary[field]) != int(own_counts[field].sum()):
        raise ValueError(f"Independent summary mismatch: {field}")
```
**Pre-verification Result**:
- `per_vessel.csv` contains exactly 82 rows with non-duplicated `rfid_id` strings and integer columns `valid_triple_n` and `pattern_n`.
- `summary.json` has top-level integer fields `valid_triple_n: 88036` and `pattern_n: 3807`, exactly equal to the column sums of `per_vessel.csv`.
- Read test with `utf-8-sig` encoding passed seamlessly.

---

## 7. Artifact Cryptographic Hashes

### 7.1 Sources
| File | SHA-256 Digest |
| :--- | :--- |
| `independent_inventory.py` | `055ea62db402abc1bc07672d689525b238024616265ba9006c1903e31e916ced` |
| `CONTRACT.md` | `d91323121932b61baeb2de4db88539a9a5fc35ea70c2b02dd8b588f09729eea3` |
| `PROTOCOL.md` | `20293cb02511b2f4f467539afbc92e5f36d42473bc63c96cc3ce584a8a9385b0` |

### 7.2 Inputs
| File | SHA-256 Digest | Bytes |
| :--- | :--- | :--- |
| `round_004_20261105/execution_001/candidate_ledger.parquet` | `e0e1b5110bf3884f2dd8e0eb7e283bd455bf77069e994c176c4c437b3766d265` | 6,433,671 |
| `round_003_20261105/gear_registry.csv` | `0a94249ad364500132d70521134fc493e836ec63d7d8734cc412e33c3adb73dd` | 4,474 |

### 7.3 Outputs (`inventory_outputs/`)
| File | SHA-256 Digest | Bytes |
| :--- | :--- | :--- |
| `per_vessel.csv` | `aa8f5e57812d08db0c4d036435038eb2b8b551f8242949b925514b4653123b57` | 2,279 |
| `cases.csv` | `a298e9062d8cf2a9a75c07c988da5c6d5a3e48edb9e89f4446009ed2ec11a90d` | 1,840 |
| `summary.json` | `d66535087aabb3bca00fc6225eb8b0be39006fd0a5a6063b0ffe0f77fa57cef2` | 2,561 |
| `execution_receipt.json` | `2318019cd655186d96f6607d88aab7c0b1cad79944e8b27f7ba5a6e453194162` | 2,566 |

---

## 8. Conclusion & Sign-off

Independent inventory counting is complete and verified against all structural and numerical contract requirements:
1. `88,036` valid contiguous triples and `3,807` transition patterns established across all 82 vessels without label exposure.
2. Interface concordance confirmed against `run_transition.py` ledger validation.
3. Ready for root coordinator comparison against Luna's actual ledger.
