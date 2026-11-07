# Round 9 transition rules

## Scope and requested execution

This module implements the small-small-non-small transition and candidate
ranking contract in `TASK_LUNA.md`, `PROTOCOL.md`, and `CONTRACT.md`. The
requested model/effort is **GPT-6 Luna xhigh**. This work used synthetic
in-memory fixtures only: it did not open raw sources or caches, access labels,
score events, train a model, or run actual numeric evaluation.

No R6 run-length feature or R8 shape-CDF statistic is mixed into these rules.

## API

```python
from transition_rules import build_transition_rules

result = build_transition_rules(frame, gear_registry)
# result keys: ledger, predictions, pool_manifest, diagnostics, stage_spec
```

`frame` requires `rfid_id`, integer source-clock `ts` in epoch hours,
`source_ordinal`, `len_m`, `bbox_m`, and current legacy `score`. Each
`(rfid_id, ts)` must be unique. `gear_registry` requires unique
`rfid_id`, `primary_gear`, and `is_single_code`. Event/label-like columns are
rejected. The ledger preserves input row order and includes all input keys,
geometry-only raw masks, exact predecessor observations, history and peer
metrics, stage masks, statuses, and reasons.

`triplet_valid` is true when exact `t-2`, `t-1`, and current rows exist and all
three have finite nonnegative length and bounding-box dimensions.
`pattern` further requires both previous rows to have `len_m <= 100` and
`bbox_m <= 100`, while current dimensions are not both within those bounds.
These raw masks do not depend on any row's legacy score. Stage `s0` requires
valid current geometry and finite current legacy score; `s1` requires exact
previous keys and valid previous geometry; `s2` keeps only the transition
pattern. Missing exact keys or invalid geometry defer; an observed valid
non-pattern rejects at `s2`; later stages are not applicable after an upstream
failure.

## History and peer calculations

For query hour `t`, a reference is every contiguous valid-geometry triple
`(u-2, u-1, u)` whose full start is at least `t-720` and whose end is before
`t`. Equivalently, `u` is in `[t-718, t)`. The current-ending triple and future
triples are excluded. History counts include patterns as a subset but do not
filter on legacy score. End dates are integer `u // 24`. Stage `s3` requires at
least 24 reference triples and at least three distinct end dates. A valid
zero-pattern history has rate zero; a zero-reference history has no rate.

For a known single-code gear, peers at the same query hour are other registered
RFIDs of that gear that meet the same history gate; they do not need a current
row or current pattern. Rates are compared exactly by integer cross-products.
With `L` peer rates strictly below own rate, `E` equal rates, and `N` eligible
peers, midrank is `(L + E/2) / N` and rarity is one minus midrank, with equal
vessel weighting. Stage `s4` requires at least five such peers. Exact numerator
and denominator fields are retained in the ledger and G ranking uses rational
comparison.

## Pools and ordering

- `B0` uses all `s0` candidates, ranked by legacy score descending, then
  source time and ordinal ascending.
- `S` uses `s2`; if that pool is empty, it uses `s0` with reason
  `s2_empty_use_s0`. Its order is legacy score descending, then source time
  and ordinal ascending.
- `G` uses `s4`; if empty, it uses the actual `S` pool and stage with a
  fallback reason. When it uses `s4`, order is peer rarity descending,
  legacy score descending, then source time and ordinal ascending; on fallback
  it follows the actual pool's legacy order.
- All three methods share `cap = min(4, size of G's actual pool)`, including
  zero. Prediction rows expose pool size, cap, fallback, score kind,
  method score, and a null secondary score.

`diagnostics` includes all-row raw valid-triple and pattern counts by vessel
and gear, stage counts by gear, exact history definitions, fallback counts, and
the number of RFIDs whose selected G and S top-1/top-4 sets differ.

## Synthetic verification and code binding

`check_transition_rules.py` passed **11 synthetic checks** on 517 in-memory
rows. They cover score-independent masks and input order, exact predecessor
keys, NaN-score prior geometry, strict history boundaries, 24/23 references,
three end dates, zero rate, five prior-only peers, exact rational ties,
descending legacy and rarity-first ranking, fallbacks, shared caps of 3/1/0,
unknown/singleton gear, future-append invariance, monotone stages, and rejection
of duplicate or fractional source-clock keys. Distinct top-1 source ordinals
were B0 `53`, S `49`, and G `46`; at hour 720 own rate was `1/36` and exact
peer rarity was `9/10`.

The checker hashes both implementation files before and after fixture execution;
the values matched:

| File | SHA-256 |
| --- | --- |
| `transition_rules.py` | `80da231443a7c16b2e05d5b348bbfb30d9608594af92f971f37c0ffbfffd7360` |
| `check_transition_rules.py` | `5cf9e49f8c852c5582b2165021ba342e506102e45bbe67c587041a4275e21431` |

The full machine-readable receipt is `transition_checks.json`. Fresh preflight
at `2026-11-06 03:24:06 +09:00` found 4,570.98 MiB available, zero other
Python jobs, and 1,920 MiB required (`768 MiB` Luna fixture allowance +
`512 MiB` fixed Gemini synthetic reserve + `0 * 512 MiB` additional visible
Python jobs + `640 MiB` reserve); it passed.

## Limits / handoff

These checks establish synthetic contract behavior only. Raw format/cache
concordance and large-input memory/runtime behavior remain for the root
runner's integration path; no numeric source evaluation or label access has
occurred. The returned API is ready for root integration and inventory-count
comparison before any later label gate.
