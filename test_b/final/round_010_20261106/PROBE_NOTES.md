# Round 10 position availability probe

## Scope and API

Requested execution model/effort: **GPT-6 Luna xhigh**. This probe measures the
nearest past-centroid haversine distance and history availability from the
projected numeric R4 ledger. It treats mean-centroid coordinates as a spatial
proxy only; it makes no actual-route, port, waiting/normal-state, speed, or
operational-truth claim. It creates no predictions, rankings, event scores, or
performance estimates and does not read event or accident labels.

```python
from position_probe import build_position_probe

result = build_position_probe(frame, registry)
# result keys: ledger, per_vessel, summary
```

The frame projection is `rfid_id, ts, source_ordinal, cen_lon, cen_lat`;
registry projection is `rfid_id, primary_gear, is_single_code`. Source-clock
`ts` and `source_ordinal` are validated as nonnull integer values before
casting. The full `(rfid_id, ts, source_ordinal)` key must be unique. All input
rows and input order are retained, including rows with invalid coordinates.
Coordinates are valid only when both are finite and longitude is in
`[-180,180]` and latitude in `[-90,90]`; no length, bounding-box, or score
filter applies.

## Frozen calculations

For each observed source-clock query `t`, own valid positions are the valid
centroids in `[t-720,t)`. The current hour and future are excluded, and an exact
`t-720` position is included. Own history counts and `floor(ts/24)` distinct
source-clock dates are recorded for each row. Own distance eligibility
requires a valid current coordinate, at least 24 past positions, and at least
three past dates.

For eligible rows, distance is the minimum spherical haversine distance using
Earth radius `6,371,000 m`, calculated against bounded chunks of past points.
Exact equal-distance ties resolve by earliest timestamp and then lowest source
ordinal. A repeat coordinate at a different past hour can yield zero distance.

At query hour `t`, peer counts include other vessels in the same known,
single-code gear group whose valid past positions meet the 24-position/3-date
history gate at that same `t`; peers need no current row. Own distance
eligibility plus at least five such peers yields peer eligibility. Unknown,
mixed, and singleton gear remain deferred at the peer stage. The ledger
includes the required coordinates, history counts, eligibility flags, nearest
neighbor key/coordinates, and explicit status/reason fields.

`per_vessel` emits one row for every observed or registry RFID with exactly
`rfid_id, primary_gear, observed_n, valid_position_n, own_eligible_n,
peer_eligible_n`. `summary` contains matching global count totals and the
calculation definitions. The actual run writes `position_ledger.parquet`,
`per_vessel.csv`, `summary.json`, `OUTPUT_HASHES.json`, and `EXECUTION.json` to
the fixed new folder `probe_outputs/actual_001`. Hash manifests exclude their
own file and `EXECUTION.json` is excluded from its own output hashes.

## Synthetic verification

`check_position_probe.py` passed **12 synthetic checks** on 275 in-memory rows
and 11 input RFIDs (12 including a registry-only RFID). Checks cover row/order
preservation, known one-degree haversine distance (`111194.92664455874 m`),
zero distance for a repeated past centroid, equal-distance timestamp/ordinal
ties, current/future exclusion, exact `t-720` inclusion and `t-721` exclusion,
24/23 positions, a 24-row/two-date defer, NaN/out-of-range coordinate defers,
five other history-only peers, own/singleton/unknown peer exclusions,
monotone stages, future-append invariance, and malformed raw-key rejection.

Synthetic receipt: `probe_checks.json`. Source and code hashes matched before
and after this run:

| File | SHA-256 |
| --- | --- |
| `position_probe.py` | `efb6f3c1b9a8256dcd5c7773b43f3c7f740705e649f15a7e365579729b0a1ddb` |
| `check_position_probe.py` | `c87d58e63f7d67b2ce9ffc0cf167ee9f21d9f5cbbb2e670e7326f5dab6e6fdcf` |

Fresh synthetic preflight at `2026-11-06 03:52:26 +09:00` recorded 4,445.20
MiB available, fixed Luna 768 MiB + Gemini 512 MiB + 640 MiB reserve (1,920 MiB
required), no additional visible Python jobs, and allowed the synthetic check.

## Actual numeric probe

Exactly one authorized numeric probe completed in the fixed new folder
`probe_outputs/actual_001`. It projected only `rfid_id, ts, source_ordinal,
cen_lon, cen_lat` from the R4 parquet and `rfid_id, primary_gear,
is_single_code` from the R3 registry. No raw CSV/cache re-extraction, event or
label input, prediction, scoring, or training was used.

The complete receipt is `probe_outputs/actual_001/EXECUTION.json` and the
nonrecursive output manifest is `probe_outputs/actual_001/OUTPUT_HASHES.json`.
Status is `complete`; the input has 99,677 rows and 82 RFIDs, and the saved
position ledger preserves all 99,677 input rows. The 82-row vessel export uses
the required six fields in the required order. Recorded global counts are:

| Count | Value |
| --- | ---: |
| observed rows | 99,677 |
| valid positions | 99,677 |
| own-distance-eligible rows | 96,976 |
| peer-eligible rows | 94,525 |

The fresh actual preflight at `2026-11-06 03:53:07 +09:00` recorded 4,450.40
MiB available against 1,920 MiB required (768 MiB Luna + 512 MiB Gemini + 640
MiB reserve; zero additional visible Python jobs). Actual elapsed runtime was
4.634 seconds and peak working set was 175.94 MiB; available RAM after the run
was 4,335.27 MiB.

Source hashes were unchanged before/after the probe; input hashes were also
unchanged:

| Source | SHA-256 |
| --- | --- |
| `position_probe.py` | `efb6f3c1b9a8256dcd5c7773b43f3c7f740705e649f15a7e365579729b0a1ddb` |
| `check_position_probe.py` | `c87d58e63f7d67b2ce9ffc0cf167ee9f21d9f5cbbb2e670e7326f5dab6e6fdcf` |
| `TASK_LUNA.md` | `f6dff36ef98bd33a68b91f469a0189d97e8164c1de724c3ed39847ebe34c73e9` |
| `PROTOCOL.md` | `15169b9e20c11d26bb537dc5dde95441210cc40a308c475936239baba58c7ed1` |
| `CONTRACT.md` | `b8a3372754104ec8825f313a5148acbf59900fc1631769e17c9c9fc0fda5373e` |

| Input | SHA-256 |
| --- | --- |
| `round_004_20261105/execution_001/candidate_ledger.parquet` | `e0e1b5110bf3884f2dd8e0eb7e283bd455bf77069e994c176c4c437b3766d265` |
| `round_003_20261105/gear_registry.csv` | `0a94249ad364500132d70521134fc493e836ec63d7d8734cc412e33c3adb73dd` |

| Output | SHA-256 |
| --- | --- |
| `position_ledger.parquet` | `c3943c953143a4f71335bfa8cceadac6c96b30287f40a935e41b375a429b63b8` |
| `per_vessel.csv` | `82f7e07bb43aa04fc662912e3ee7662d0d08d39be16a3e96e311306f9d75685c` |
| `summary.json` | `15e9862f04ab335514f7bad79a1aa47eb59c1e419362beee5b198077eab082b6` |
| `OUTPUT_HASHES.json` | `26422908232b0b3fe949e670094a4d8ff10acadf48cd6a851af6c01cd13d734a` |

All three data-file hashes were recomputed from disk and matched the output
manifest. The remaining validation belongs to root: compare all 82 per-vessel
counts and the 12 independent scalar distances before any event-window
availability step. CRS precision, actual vessel route, port/waiting/normal
state, and accident meaning remain unknown; this output is a coordinate
centroid proximity proxy only.
