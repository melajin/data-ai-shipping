# Round 11 Independent Distance History Availability & Scalar CDF Notes

**Worker**: Gemini (Dispatched Worker)  
**Task ID**: `task_cdf4d11c58f0`  
**Dispatch ID**: `ctx_b83d20a5e4d8`  
**Coordinator Session**: `orca_session_id:codex_a55fd2e5_500d_4503_925f_12df6a69b424`  
**Date**: 2026-11-06  
**Status**: Completed successfully (`status='complete'`, Exit Code 0)

---

## 1. Operational Overview & Boundaries

Per `TASK_GEMINI.md`, `PROTOCOL.md`, and `CONTRACT.md` in Round 11:
- **Role**: Gemini independently computes past distance distribution availability and peer distance history eligibility across all 82 RFIDs and the full canonical observation period (99,677 rows) from verified R10 numeric position data (`round_010_20261106/probe_outputs/actual_001/position_ledger.parquet`) and R3 gear registry (`round_003_20261105/gear_registry.csv`).
- **Strict Independence & Blindness**:
  - Implemented entirely within `independent_distance_history.py` without importing Luna's module (`position_rules.py`) or reading Luna's outputs/ledger.
  - No reuse of old R8 shape Fenwick/CDF class; all empirical CDF calculations are derived independently.
  - Zero access to accident/event/label data (no positive labels loaded, no training, no scoring, no Test B inference).
  - Derived strictly from tabular numeric columns; makes no claims of physical navigation routes, harbor arrival, normal vessel waiting, or communication status.
  - Per contract directive: cross-implementation concordance with Luna's ledger is checked by Root later; no premature claims of concordance are asserted herein.

---

## 2. Resource & Memory Preflight Accounting

Under the user memory protocol (2026-11-05), RAM preflight was executed prior to loading ledger tables:
- **Available Physical RAM**: 4,076.56 MiB (4,274,581,504 bytes)
- **Memory Requirement**: 1,920 MiB (2,013,265,920 bytes)
  - Gemini Independent Probe Budget: 512 MiB
  - Luna Rule Builder Budget: 768 MiB
  - System Safety Reserve: 640 MiB
- **Preflight Outcome**: **PASSED** (4,076.56 MiB $\ge$ 1,920 MiB).
- **Execution Resource Consumption**:
  - **Peak Working Set**: 119.8 MiB (125,607,936 bytes), well within the 512 MiB allocation.
  - **Total Wall Clock Runtime**: 4.02 seconds.
  - **Computation Kernel**: 3.03 seconds.

---

## 3. Distance History Availability & Empirical CDF Methodology

### 3.1 Raw Key & R10 Ledger Validation Before Cast
- Input R10 ledger hash verified against contract expected digest:
  - Computed: `c3943c953143a4f71335bfa8cceadac6c96b30287f40a935e41b375a429b63b8` (Exact Match).
- Raw columns validated before any casting:
  - `rfid_id`: String, non-empty, non-null.
  - `ts`: Integer source-clock epoch-hours ($[0, 10,000,000]$), finite, non-negative, non-boolean, no fractional hours (`ts % 1 == 0`).
  - `source_ordinal`: Integer, finite, non-negative, non-boolean, unique, no fractional values (`source_ordinal % 1 == 0`).
  - `(rfid_id, ts)`: Uniquely identifies each observation (0 duplicates across 99,677 rows).

### 3.2 Raw Distance Available (`raw_distance_available_n`)
- Row has `raw_distance_available == True` if and only if:
  1. `R10 own_distance_eligible == True` (current coordinates valid and prior position history $\ge 24/3$).
  2. `nearest_distance_m` is finite and non-negative ($\ge 0.0$ meters).
- Exactly **96,976** rows satisfy raw distance availability.

### 3.3 Own Distance Distribution Eligibility (`self_distribution_eligible_n`)
- For vessel $v$ at query timestamp $t$, the past distance reference window is $[t - 720, t)$ ($t - 720 \le u < t$).
  (Underlying coordinate origins may trace back to $t - 1440$ as distance is a proxy derived from prior positions).
- Current observation $t$ and future observations are strictly excluded.
- An observation is `self_distribution_eligible` if and only if:
  1. Current observation has `raw_distance_available == True`.
  2. The vessel has at least 24 past `raw_distance_available` rows in $[t - 720, t)$ (`self_distance_ref_n >= 24`).
  3. Those historical observations span at least 3 distinct source-clock dates (`self_distance_ref_dates >= 3`, where date $= u // 24$).

### 3.4 One-Tail Self Distance CDF
- Computed against own past distances $\{d_1, \dots, d_n\}$ in $[t - 720, t)$ where $n = \text{self\_distance\_ref\_n}$:
  $$\text{self\_distance\_cdf} = \frac{\#(\text{past} < d) + 0.5 \times \#(\text{past} == d)}{n}$$
- Evaluated as a one-tail empirical CDF where higher values indicate current distance is unusually large relative to own history.

### 3.5 Peer Distance History Availability & Equal-Vessel CDF Mean
- At query timestamp $t$, candidate peers are OTHER vessels ($p \ne r$) belonging to the same SINGLE known gear group (`is_single_code == True`).
- Candidate peers are evaluated at the SAME query timestamp $t$ on whether their past `raw_distance_available` rows in $[t - 720, t)$ meet 24 values and 3 distinct dates.
- Per contract: peers do NOT require an observation at the current timestamp $t$.
- An observation is `peer_distribution_eligible` if:
  1. It is `self_distribution_eligible == True`.
  2. Its gear is a single known code (`is_single_code == True`).
  3. The number of eligible other peers at that timestamp is at least 5 (`peer_distance_eligible_n >= 5`).
- Singleton gears (채낚기연승낚시 with 1 vessel) have 0 peers and are explicitly deferred (`peer_distribution_eligible = False`).
- For each eligible peer $p$, its CDF is evaluated at the current candidate distance $d$:
  $$\text{peer\_cdf}_p(d) = \frac{\#(\text{past}_p < d) + 0.5 \times \#(\text{past}_p == d)}{m_p}$$
- Peer distance CDF mean is the equal-vessel arithmetic average across all qualified peers:
  $$\text{peer\_distance\_cdf\_mean} = \frac{1}{\text{peer\_n}} \sum_{p \in \text{qualified\_peers}} \text{peer\_cdf}_p(d)$$
  (Defined as null/NaN when $\text{peer\_n} == 0$, and computed whenever $n > 0$, even if $n < 5$).

---

## 4. Aggregate Availability Findings

### 4.1 Global Pipeline Counts
Stage availability exhibits strict monotone hierarchy across all 82 vessels:
$$\text{observed\_n} \ge \text{raw\_distance\_available\_n} \ge \text{self\_distribution\_eligible\_n} \ge \text{peer\_distribution\_eligible\_n}$$

| Stage / Field | Global Count | Fraction of Observed Rows |
| :--- | :--- | :--- |
| **Total Observed (`observed_n`)** | **99,677** | 100.00% |
| **Raw Distance Available (`raw_distance_available_n`)** | **96,976** | 97.29% |
| **Self Distribution Eligible (`self_distribution_eligible_n`)** | **94,290** | 94.59% |
| **Peer Distribution Eligible (`peer_distribution_eligible_n`)** | **91,307** | 91.60% |

### 4.2 Breakdown by Primary Gear
| Primary Gear | Vessels | Observed Rows | Raw Distance Available | Self Distribution Eligible | Peer Distribution Eligible |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **연안복합** (Coastal Mixed) | 37 | 30,226 | 29,055 | 27,909 | 27,764 |
| **자망** (Gillnet) | 31 | 47,447 | 46,411 | 45,352 | 44,986 |
| **통발** (Trap) | 13 | 19,894 | 19,449 | 18,996 | 18,557 |
| **채낚기연승낚시** (Jigging/Longline) | 1 | 2,110 | 2,061 | 2,033 | 0 (singleton deferral) |
| **Total** | **82** | **99,677** | **96,976** | **94,290** | **91,307** |

---

## 5. Independent CDF Verification Cases (`independent_cdf_cases.csv`)

Per CONTRACT.md line 19:
- From each of the 4 primary gears, the lexicographically smallest RFID with any self distribution eligible observation was selected:
  - **연안복합**: Vessel `31001758` (868 self eligible rows)
  - **자망**: Vessel `31007500` (1,383 self eligible rows)
  - **채낚기연승낚시**: Vessel `36314076` (2,033 self eligible rows)
  - **통발**: Vessel `31008085` (2,881 self eligible rows)
- For each selected vessel, 3 queries were taken in $t / \text{source\_ordinal}$ ascending order:
  - **FIRST** observation (index 0)
  - **MIDDLE** observation (index $\lfloor N / 2 \rfloor$)
  - **LAST** observation (index $N - 1$)
- Total queries: 4 vessels $\times$ 3 queries = **12 queries** (representing queries across gear cohorts, not accident cases).
- Exact scalar CDF calculations:

| Gear | RFID | Query $t$ | Source Ordinal | Nearest Distance (m) | Self Ref $n$ | Self Ref Dates | Self Distance CDF | Peer Eligible $n$ | Peer Distance CDF Mean |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **연안복합** | 31001758 | 491297 | 275535 | 100.969001 | 24 | 3 | 0.750000 | 13 | 0.595705 |
| **연안복합** | 31001758 | 493698 | 2259400 | 64.694035 | 100 | 15 | 0.900000 | 30 | 0.673854 |
| **연안복합** | 31001758 | 494738 | 3364590 | 130.557088 | 411 | 25 | 0.956204 | 24 | 0.795247 |
| **자망** | 31007500 | 491218 | 200034 | 175.129802 | 24 | 3 | 0.708333 | 10 | 0.608842 |
| **자망** | 31007500 | 493745 | 2320307 | 0.679829 | 330 | 23 | 0.296970 | 29 | 0.224162 |
| **자망** | 31007500 | 495237 | 3885346 | 0.247100 | 293 | 20 | 0.126280 | 24 | 0.130294 |
| **채낚기연승낚시** | 36314076 | 490993 | 54754 | 7965.302176 | 28 | 3 | 0.750000 | 0 | null |
| **채낚기연승낚시** | 36314076 | 492955 | 1516018 | 1828.220781 | 455 | 28 | 0.665934 | 0 | null |
| **채낚기연승낚시** | 36314076 | 495239 | 3865357 | 1496.810346 | 386 | 24 | 0.463731 | 0 | null |
| **통발** | 31008085 | 491017 | 80538 | 1.550733 | 33 | 3 | 0.606061 | 2 | 0.118056 |
| **통발** | 31008085 | 493551 | 2111936 | 1.747710 | 605 | 30 | 0.479339 | 12 | 0.216189 |
| **통발** | 31008085 | 495135 | 3769521 | 0.965673 | 619 | 31 | 0.405493 | 10 | 0.197387 |

---

## 6. Cryptographic Hashes & Artifact Manifest

### 6.1 Sources
| File | SHA-256 Digest |
| :--- | :--- |
| `independent_distance_history.py` | `2cb8dc2c5974702744d4151df2cfaa3efd104c90c5749110a666390019d9f55c` |
| `CONTRACT.md` | `c5aa07c5a66d0ff96d981d7f694173b48e1e09340b9064c15a7f670588176b31` |
| `PROTOCOL.md` | `5ff4d8c177f082fc8d1256e9fcc9a86a564328c9a74527596d6f841fd5e3713a` |

### 6.2 Inputs
| File | SHA-256 Digest | Bytes |
| :--- | :--- | :--- |
| `round_010_20261106/probe_outputs/actual_001/position_ledger.parquet` | `c3943c953143a4f71335bfa8cceadac6c96b30287f40a935e41b375a429b63b8` | 5,527,080 |
| `round_003_20261105/gear_registry.csv` | `0a94249ad364500132d70521134fc493e836ec63d7d8734cc412e33c3adb73dd` | 4,474 |

### 6.3 Outputs (`inventory_outputs/actual_001/`)
| File | SHA-256 Digest | Bytes |
| :--- | :--- | :--- |
| `per_vessel.csv` | `15401dfbed5f8a8318a7c90eae800c040102f159461e8bca67908f0bdeea2d6d` | 3,188 |
| `independent_cdf_cases.csv` | `10a4c5452a6b1f2ba331dfb96aadb786b393c22440a4d81872980f95efeade23` | 1,143 |
| `summary.json` | `efaf115628d8d9f505c925204bb6346ec40afb57be736cebbb683e3b613ea78c` | 2,684 |
| `EXECUTION.json` | `e12d9e2272ea44244ec2f2fb7bb59504e0116b5acbc71f00a8777ab8592b2f3d` | 2,548 |

*Note: Per contract instructions, `EXECUTION.json` does not include itself inside its own `outputs` hash manifest.*

---

## 7. Sign-off & Readiness

Independent distance history inventory calculations are fully complete:
- Exact counts (`observed_n: 99677`, `raw_distance_available_n: 96976`, `self_distribution_eligible_n: 94290`, `peer_distribution_eligible_n: 91307`) and 12 scalar CDF verification queries are exported to `inventory_outputs/actual_001/`.
- All outputs are validated, deterministic, and ready for root coordinator's independent concordance verification against Luna's rule ledger prior to positive event label evaluation.
