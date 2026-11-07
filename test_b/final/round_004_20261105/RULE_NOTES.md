# Luna implementation notes — Round4

`build_rules(frame, gear_registry)` is implemented in `sequence_rules.py`. It returns `ledger`, `predictions`, `pool_manifest`, and `diagnostics` as specified in the shared contract. The ledger preserves the input row order and index, carries source fields including `source_ordinal`, and adds stage masks, adjacent observation state, censoring, own/peer prior-history evidence, and explanatory `t_plus_2_status` / past-30-day same-cell fraction.

The stages are strictly observational. Stage0 requires finite nonnegative length and bbox plus finite legacy score. Stage1 requires an observed valid `t-1` row that is not small and a small current row. Stage2 adds an observed valid, small `t+1` row. Nothing is interpolated. Small is the contract's fixed dual-dimension `<=100` rule and is not interpreted as physical stopping.

The past transition baseline counts only valid consecutive triples with center `s` in `[t-719, t-2]`, the integer-hour equivalent of `s-1 >= t-720` and `s+1 < t`. It requires 24 triples and 3 center dates. The peer percentile is midrank, and eligibility requires at least 5 other eligible same-single-code records.

Singleton interpretation: a one-record gear group has no peer distribution, so it cannot get peer-based Stage3 eligibility; G falls back to Stage2 (or Stage0 if Stage2 is empty). This keeps the specified same-gear rarity comparison undefined rather than inventing a singleton score. Unknown/mixed gear also cannot enter Stage3. If neither Stage2 nor Stage0 has rows, G has a zero-size Stage0 manifest row with `no_observations`; cap is zero.

G's actual pool determines one per-RFID cap shared by B0/S/G. S alone falls back to Stage0 when Stage2 is empty. Ranking uses only legacy score except actual Stage3 G, which ranks gear priority then legacy score, timestamp, and source ordinal. All candidate lists are retrospective observed-pattern rankings; no accident probability or physical-cause assertion is produced.

`check_sequence_rules.py` builds only tiny in-memory synthetic fixtures and saves `rule_checks.json`; it does not read any Round2/3 or development data. Run from any directory with `python testB/final/round_004_20261105/check_sequence_rules.py`.
