# Frozen Round8 shape rules

## API and input contract

`build_shape_rules(frame, gear_registry)` returns a dictionary with `ledger`, `predictions`, `pool_manifest`, `diagnostics`, and generic `stage_spec`. The input contains the canonical numeric rows merged one-to-one with geometry rows. The builder preserves row order and rejects label/event columns, missing keys, non-integer source-clock hours, duplicate `(rfid_id, ts)` keys, duplicate triple keys, and duplicate registry RFIDs. It reads no event or positive-label data.

Stage masks are monotone:

- `s0`: finite nonnegative `len_m`, `bbox_m`, and finite legacy score.
- `s1`: `s0` and not `(len_m <= 100 and bbox_m <= 100)`.
- `s2`: `s1` and informative chosen-part shape with at least three unique coordinates, positive path, and finite D/L in `[0,1]`.
- `s3`: `s2` and at least 24 valid s2 rows from the same vessel in strict past `[t-720,t)`, spanning at least three source-clock dates.
- `s4`: `s3` and at least five other single-code vessels with the same qualifying strict-past history at the same query time.

The rolling state is advanced once over sorted source-clock times. Each vessel has a sliding 720-hour window, date counts, and a compressed-value Fenwick tree for exact less-than/equal counts. This keeps history calculations bounded to the number of source rows and vessels times logarithmic rank queries instead of repeatedly scanning every past window.

## Ranking and pools

B0 uses its exact s0 pool and sorts by legacy score **descending**, then timestamp and ordinal ascending. S uses s3 when available, otherwise its documented s0 fallback; its rank is self-rarity descending, legacy score descending, timestamp ascending, ordinal ascending. G uses s4 when available, otherwise S's actual pool; its rank is self-rarity descending, peer-rarity mean descending, legacy score descending, timestamp ascending, ordinal ascending. Thus the legacy baseline matches the prior R4 direction; legacy score only resolves a shape-rarity tie in S/G. Self CDF uses `(count(past < x) + 0.5*count(past == x))/n`; rarity is `1 - 2*min(p,1-p)` with exact float comparisons.

All methods for one RFID share `cap = min(4, G actual pool size)`, including cap zero. Predictions contain only rows selected from the actual pool. `method_score` is legacy score for s0 and self-rarity for s3/s4; `secondary_score` is populated only when G uses s4. The ledger retains all candidates and stage statuses. Invalid s0 inputs defer, observed-small rows reject at s1, missing geometry/history/peers defer, and downstream stages after a failed prerequisite are `not_applicable`.

Diagnostics report per-gear stage counts, G-vs-S top1/top4 changes, and peer tie activation. Peer diagnostics count exact self-rarity ties only within each RFID's actual G s4 pool, count groups whose peer values differ, and separately count rank1/top4 changes when peer rarity is added to the ranking of that same s4 pool. The no-peer counterfactual sorts by self-rarity descending, legacy descending, timestamp ascending, and ordinal ascending, holding the s4 pool fixed. Pool restriction effects are therefore not credited to the peer tie-break.

## Synthetic result

`check_shape_rules.py` verifies strict t exclusion and t-720 inclusion, 24 references/three date boundaries, six eligible peer histories at a shared query time (including peers with no row at that time), equal vessel weighting, distinct B0/S/G winners, shared cap, fallback, monotone invalid/small/missing-geometry statuses, future-row invariance, duplicate RFID/hour rejection, and fractional timestamp rejection. Its independent legacy-only/fallback fixture asserts score order `[0.9,0.5,0.1]` for B0, S and G. The direction fixture makes the B0 winner the later highest-score row, makes S choose the higher legacy score on an exact self-rarity tie, and makes G select the peer-rarity winner only on that same self-rarity tie; the peer mean at t=721 is 0.060833333333333295.

No development set, event labels, training, scoring evaluation, source extraction, CRS or timezone claim was used. The output is an implementation artifact only; it does not establish anomaly detection utility.
