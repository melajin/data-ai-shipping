# Round 11 position-distance CDF rules

## Scope and API

Requested model/effort: **GPT-6 Luna xhigh**. This worker implements code and
synthetic checks only. The feature is a one-tail empirical CDF of a vessel's
past mean-centroid nearest-distance proxy; it is not an actual-route, port,
normal-waiting, or accident-truth claim. No actual numeric source, score
evaluation, events, labels, TestB data, model training, or predictions were
read or run here.

```python
from position_rules import build_position_rules

result = build_position_rules(frame, registry)
# keys: ledger, predictions, pool_manifest, diagnostics, stage_spec
```

`frame` is the root-merged R4/R10 all-row ledger. It requires canonical R4
fields `rfid_id, ts, source_ordinal, len_m, bbox_m, score`, plus the R10
`own_distance_eligible` and `nearest_distance_m` fields. Other R10 fields are
copied through unchanged. The registry requires `rfid_id, primary_gear,
is_single_code`; premerged gear metadata, if present, must match the registry.
The builder rejects event/label-like fields, null/fractional keys, duplicate
`(rfid_id, ts, source_ordinal)` keys, and a changed registered gear mapping.

The exact new ledger fields are `raw_distance_available`,
`self_distance_ref_n`, `self_distance_ref_dates`, `self_distance_cdf`,
`self_distance_history_eligible`, `peer_distance_eligible_n`,
`peer_distance_cdf_mean`, `peer_distance_history_eligible`, and the generic
`s0..s4_ok/status/reason` fields. Existing R10 coordinate-history fields such
as `own_ref_n`, `own_ref_dates`, `own_distance_eligible`, `nearest_*`, and
`peer_eligible*` remain metadata and are not replaced by the new distance
history fields.

## Frozen calculations

`raw_distance_available` is exactly R10 `own_distance_eligible` plus a finite,
nonnegative `nearest_distance_m`. Distance-history references are every such
value at `[t-720,t)`, regardless of legacy score or length/bounding-box values;
current and future distances are excluded. The history gate is 24 distance
values and three distinct `floor(ts/24)` source-clock dates. The underlying
distance at time `s` may itself refer to coordinate history as early as `s-720`,
so values in the query history can depend on coordinates as far back as
`t-1440`; there is still no future input.

For eligible own history, `self_distance_cdf` is
`(count(past < current) + 0.5 * count(past == current)) / n`. Comparisons use
the raw distance floats exactly. This is a high-tail one-tail CDF; the former
two-tail rarity is never called. For each current distance, eligible other
vessels of the same known single-code gear contribute their own CDF from their
distance histories at the same query `t`. `peer_distance_cdf_mean` is the
equal-vessel mean, not a pooled-row CDF. Peers need no current row. R10
`peer_eligible` and coordinate reference counts are not used to decide R11
peer-history eligibility.

Stages are: `s0` finite nonnegative `len_m`/`bbox_m` and finite legacy score;
`s1=s0` plus raw R10 distance availability; `s2=s1` plus own distance-history
eligibility; `s3=s2` plus at least five other registered vessels in the same
known single-code gear; and `s4=s3` plus at least five of those peers with
eligible distance histories at the same `t`. The raw self/peer distribution
eligibility flags are independent of current legacy score; stage masks then
apply their upstream admission conditions.

Pools are `B0=s0`, `S=s2` with `s0` fallback, and `G=s4` with the actual `S`
pool/stage fallback. B0 and `s0` fallbacks rank legacy score descending. S
ranks self CDF descending then legacy descending. G ranks self CDF descending
first, peer-CDF mean descending only within an exact self-CDF tie, legacy score
descending next, then source timestamp and ordinal ascending. All methods share
`min(4, G actual pool size)` as their cap. Prediction and pool-manifest field
orders match the contract; diagnostics include per-vessel/per-gear history
counts, stage counts, fallbacks, G/S selection changes, and a fixed-s4-pool
peer-tie comparison that leaves self-CDF priority unchanged.

The builder reuses only the read-only R8 `HistorySweep` rolling history and
`cdf` implementation. The pinned source is
`round_008_20261106/shape_rules.py`, SHA-256
`6eb571aef12dc881b78dc4c93fd77683ba4068d22be654ee46c208eab78e4472`.
`HistorySweep.rarity` and all shape inputs are unused; the new CDF inputs are
only raw available distance values.

## Synthetic evidence and code binding

`check_position_rules.py` passed **13 synthetic checks** on 378 in-memory rows
and 17 input RFIDs (18 including the registry-only zero-count RFID). They cover
all-row/R10 metadata preservation and API field names; 24/23 value and 3/2
date gates; strict `t-720` inclusion and `t-721`/current/future exclusion;
NaN-score and invalid-geometry raw-history independence; R10 coordinate
eligibility differing from distance-history eligibility; one-tail exact tie
counting; five same-time history-only peers; singleton/unknown gear; equal-vessel
peer CDF weighting with unequal reference counts; G self-CDF priority and peer
tie-break; distinct B0/S/G winners; legacy-descending fallback; shared caps of
3/1/0; future-append invariance; and key validation.

For the synthetic V candidate at `t=720`, own one-tail CDF was `19/24`;
peer-CDF means for two exact self-CDF ties were `0.4958333333333333` and
`0.5013888888888889`. B0/S/G top source keys were `(719,24)`, `(720,25)`, and
`(720,26)` respectively. The higher self-CDF always outranked a lower one in a
direct ordering check even when its peer CDF was lower.

The full receipt is `rule_checks.json`; module, checker, and permitted R8
helper hashes matched before and after the synthetic run:

| File | SHA-256 |
| --- | --- |
| `position_rules.py` | `8ecee18232a1978ac8559ed8f630404528625b96df1b7fc6bfe64f8e00fda759` |
| `check_position_rules.py` | `a41200d9fc9b7915a3e0c92f88a207f822f9bae2f793618f3838c408907c0bbc` |
| R8 `shape_rules.py` | `6eb571aef12dc881b78dc4c93fd77683ba4068d22be654ee46c208eab78e4472` |

Fresh preflight at `2026-11-06 04:23:59 +09:00` recorded 4,471.43 MiB
available, against 1,920 MiB required (768 MiB Luna + 512 MiB Gemini + 640 MiB
reserve and no additional visible Python jobs).

Two early synthetic harness invocations stopped before a result receipt: the
first caught a typo in the pinned R8 helper hash, and the next caught missing
registry metadata on an appended synthetic row. Both were corrected; the final
13-check run passed, and no actual source data was read.

## Remaining validation and limits

Actual input coverage, the all-82 independent distance-history counts, and the
12 scalar CDF comparisons remain for root after merging validated R10 and R4
rows. No event labels or actual scoring have been accessed. CRS/track geometry,
normal behavior, ports, waiting, and accident meaning remain unknown; a high
self-distance CDF is only a candidate spatial anomaly signal.
