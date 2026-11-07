# Round 10 Independent Position Availability Notes

**Worker**: Gemini (Dispatched Worker)  
**Task ID**: `task_2aed70026611`  
**Dispatch ID**: `ctx_8433c01a5b6e`  
**Coordinator Session**: `orca_session_id:codex_a55fd2e5_500d_4503_925f_12df6a69b424`  
**Date**: 2026-11-06  
**Status**: Completed successfully (`status='complete'`, Exit Code 0)

---

## 1. Operational Overview & Boundaries

Per `TASK_GEMINI.md`, `PROTOCOL.md`, and `CONTRACT.md` in Round 10:
- **Role**: Gemini independently computes position validity, own past history availability, and peer history eligibility across all 82 RFIDs and the full canonical observation period (99,677 rows) from R4 numeric data (`round_004_20261105/execution_001/candidate_ledger.parquet`) and R3 gear registry (`round_003_20261105/gear_registry.csv`).
- **Strict Independence & Blindness**:
  - Implemented entirely within `independent_availability.py` without importing Luna's module (`position_probe.py`) or reading Luna's outputs/ledger.
  - Zero access to accident/event/label data (no positive labels loaded, no training, no scoring, no Test B inference).
  - Derived strictly from tabular numeric columns; makes no claims of physical navigation routes, harbor arrival, normal vessel waiting, or communication status.
  - Per contract directive: cross-implementation concordance with Luna's ledger is checked by Root later; no premature claims of concordance are asserted herein.

---

## 2. Resource & Memory Preflight Accounting

Under the user memory protocol (2026-11-05), RAM preflight was executed prior to loading canonical tables:
- **Available Physical RAM**: 4,060.71 MiB (4,257,964,032 bytes)
- **Memory Requirement**: 1,920 MiB (2,013,265,920 bytes)
  - Gemini Independent Probe Budget: 512 MiB
  - Luna Probe Budget: 768 MiB
  - System Safety Reserve: 640 MiB
- **Preflight Outcome**: **PASSED** (4,060.71 MiB $\ge$ 1,920 MiB).
- **Execution Resource Consumption**:
  - **Peak Working Set**: 125.6 MiB (131,739,648 bytes), well below the 512 MiB allocation.
  - **Total Wall Clock Runtime**: 4.15 seconds.
  - **Availability & Distance Computation Kernel**: 3.14 seconds.

---

## 3. Availability Methodology & Contract Alignment

### 3.1 Raw Key Validation Before Cast
Adhering to strict input hygiene, raw columns are validated before any casting:
- `rfid_id`: String, non-empty, non-null.
- `ts`: Integer source-clock epoch-hours ($[0, 10,000,000]$), finite, non-negative, non-boolean, no fractional hours (`ts % 1 == 0`).
- `source_ordinal`: Integer, finite, non-negative, non-boolean, unique, no fractional values (`source_ordinal % 1 == 0`).
- `(rfid_id, ts)`: Uniquely identifies each observation (0 duplicates across 99,677 rows).

### 3.2 Coordinate Validity (`valid_position_n`)
- Coordinates `cen_lon` and `cen_lat` must be finite and within geographic bounds:
  - $\text{cen\_lon} \in [-180.0, 180.0]$
  - $\text{cen\_lat} \in [-90.0, 90.0]$
- Per contract: no `len_m`, `bbox_m`, or `score` filter is applied for position availability.
- All 99,677 rows in the canonical ledger possess valid geographic coordinates.

### 3.3 Own Past History Availability (`own_eligible_n`)
- At query timestamp $t$, the historical reference window is $[t - 720, t)$ (strictly excluding current time $t$ and future observations; exact inclusion at $t - 720$, exclusion at $t - 721$).
- A vessel observation is `own_distance_eligible` if and only if:
  1. The current observation has valid coordinates (`coordinate_valid == True`).
  2. The vessel has at least 24 valid position observations in $[t - 720, t)$ (`own_ref_n >= 24`).
  3. Those historical observations span at least 3 distinct source-clock dates (`own_ref_dates >= 3`, where date $= u // 24$).

### 3.4 Peer History Availability (`peer_eligible_n`)
- At query timestamp $t$, candidate peers are OTHER vessels ($p \ne r$) belonging to the same SINGLE known gear group (`is_single_code == True`).
- Candidate peers are evaluated at the SAME query timestamp $t$ on whether their past valid coordinates in $[t - 720, t)$ meet the 24 positions and 3 distinct dates criterion.
- Per contract: peers do NOT require an observation at the current timestamp $t$.
- An observation is `peer_eligible` if:
  1. It is `own_distance_eligible == True`.
  2. Its gear is a single known code (`is_single_code == True`).
  3. The number of eligible other peers at that timestamp is at least 5 (`peer_n >= 5`).
- Singleton gears (such as 채낚기연승낚시 with 1 vessel) and unknown/mixed gears have 0 peers and are explicitly deferred (`peer_eligible = False`).

---

## 4. Aggregate Availability Findings

### 4.1 Global Pipeline Counts
Stage availability exhibits strict monotone hierarchy across all 82 vessels:
$$\text{observed\_n} \ge \text{valid\_position\_n} \ge \text{own\_eligible\_n} \ge \text{peer\_eligible\_n}$$

| Stage / Field | Global Count | Fraction of Observed Rows |
| :--- | :--- | :--- |
| **Total Observed (`observed_n`)** | **99,677** | 100.00% |
| **Valid Coordinates (`valid_position_n`)** | **99,677** | 100.00% |
| **Own Distance Eligible (`own_eligible_n`)** | **96,976** | 97.29% |
| **Peer Eligible (`peer_eligible_n`)** | **94,525** | 94.83% |

### 4.2 Breakdown by Primary Gear
| Primary Gear | Vessels | Observed Rows | Valid Positions | Own Eligible Rows | Peer Eligible Rows |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **연안복합** (Coastal Mixed) | 37 | 30,226 | 30,226 | 29,055 | 28,918 |
| **자망** (Gillnet) | 31 | 47,447 | 47,447 | 46,411 | 46,251 |
| **통발** (Trap) | 13 | 19,894 | 19,894 | 19,449 | 19,356 |
| **채낚기연승낚시** (Jigging/Longline) | 1 | 2,110 | 2,110 | 2,061 | 0 (singleton deferral) |
| **Total** | **82** | **99,677** | **99,677** | **96,976** | **94,525** |

---

## 5. Independent Distance Verification Cases (`independent_distance_cases.csv`)

Per CONTRACT.md line 17:
- From each of the 4 primary gears, the lexicographically smallest RFID with any own eligible observation was selected:
  - **연안복합**: Vessel `31001758` (892 own eligible rows)
  - **자망**: Vessel `31007500` (1,407 own eligible rows)
  - **채낚기연승낚시**: Vessel `36314076` (2,061 own eligible rows)
  - **통발**: Vessel `31008085` (2,914 own eligible rows)
- For each selected vessel, 3 queries were taken in $t / \text{source\_ordinal}$ ascending order:
  - **FIRST** observation (index 0)
  - **MIDDLE** observation (index $\lfloor N / 2 \rfloor$)
  - **LAST** observation (index $N - 1$)
- Total queries: 4 vessels $\times$ 3 queries = **12 queries** (representing queries across gear cohorts, not accident cases).
- Nearest past distance computed using scalar stdlib Haversine ($R = 6,371,000$ m, $a \in [0, 1]$ clamp), with equal-distance tie-breaking favoring earlier timestamp then earlier ordinal:

| Gear | RFID | Query $t$ | Source Ordinal | Nearest Distance (m) | Nearest Ordinal | Nearest $u$ | Own Ref $n$ | Own Ref Dates |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **연안복합** | 31001758 | 491233 | 215433 | 56.506717 | 161455 | 491159 | 24 | 7 |
| **연안복합** | 31001758 | 493686 | 2258372 | 0.297871 | 2246595 | 493682 | 88 | 15 |
| **연안복합** | 31001758 | 494738 | 3364590 | 130.557088 | 3052798 | 494470 | 411 | 25 |
| **자망** | 31007500 | 491166 | 170135 | 1310.437749 | 138843 | 491094 | 24 | 3 |
| **자망** | 31007500 | 493733 | 2306890 | 5.917299 | 2038954 | 493472 | 321 | 23 |
| **자망** | 31007500 | 495237 | 3885346 | 0.247100 | 3876293 | 495236 | 293 | 20 |
| **채낚기연승낚시** | 36314076 | 490945 | 23971 | 0.594320 | 11304 | 490918 | 49 | 3 |
| **채낚기연승낚시** | 36314076 | 492941 | 1511689 | 12361.079352 | 1520459 | 492940 | 454 | 28 |
| **채낚기연승낚시** | 36314076 | 495239 | 3865357 | 1496.810346 | 3248203 | 494638 | 386 | 24 |
| **통발** | 31008085 | 490984 | 50421 | 1.672727 | 26048 | 490953 | 24 | 3 |
| **통발** | 31008085 | 493507 | 2061332 | 0.106979 | 1989914 | 493417 | 622 | 30 |
| **통발** | 31008085 | 495135 | 3769521 | 0.965673 | 3532348 | 494878 | 619 | 31 |

All nearest neighbors fall strictly in the historical interval $u \in [t - 720, t)$ and satisfy all reference window constraints.

---

## 6. Cryptographic Hashes & Artifact Manifest

### 6.1 Sources
| File | SHA-256 Digest |
| :--- | :--- |
| `independent_availability.py` | `7a52eab63687e5ad6c7836496e7de7c158c19130dc99da0342a55dc25f22097e` |
| `CONTRACT.md` | `b8a3372754104ec8825f313a5148acbf59900fc1631769e17c9c9fc0fda5373e` |
| `PROTOCOL.md` | `15169b9e20c11d26bb537dc5dde95441210cc40a308c475936239baba58c7ed1` |

### 6.2 Inputs
| File | SHA-256 Digest | Bytes |
| :--- | :--- | :--- |
| `round_004_20261105/execution_001/candidate_ledger.parquet` | `e0e1b5110bf3884f2dd8e0eb7e283bd455bf77069e994c176c4c437b3766d265` | 6,433,671 |
| `round_003_20261105/gear_registry.csv` | `0a94249ad364500132d70521134fc493e836ec63d7d8734cc412e33c3adb73dd` | 4,474 |

### 6.3 Outputs (`independent_outputs/actual_001/`)
| File | SHA-256 Digest | Bytes |
| :--- | :--- | :--- |
| `per_vessel.csv` | `82f7e07bb43aa04fc662912e3ee7662d0d08d39be16a3e96e311306f9d75685c` | 3,157 |
| `independent_distance_cases.csv` | `4901eb87056734a78e486a86fb5efb8ca0f69081ff937a4c0739c79f9e9e8602` | 874 |
| `summary.json` | `43ea0edae750fb64f1f54720427f7c4a89e5b672eda3a44f0186e182037bddf3` | 2,498 |
| `EXECUTION.json` | `b13fbc4f44aa9a191ef3104936babda9350dfbdc20b999167d7ac200a5ec887c` | 2,498 |

*Note: Per contract instructions, `EXECUTION.json` does not include itself inside its own `outputs` hash manifest.*

---

## 7. Sign-off & Readiness

Independent availability calculations are fully complete:
- Exact counts (`observed_n: 99677`, `valid_position_n: 99677`, `own_eligible_n: 96976`, `peer_eligible_n: 94525`) and 12 scalar distance queries are exported to `independent_outputs/actual_001/`.
- All outputs are validated, deterministic, and ready for root coordinator's independent concordance verification against Luna's probe ledger prior to positive event label evaluation.
