# Component timing aggregation facts

Generated: 2026-11-05T09:16:24+09:00

This is a descriptive aggregation of the existing Test B baseline. It does not evaluate accident hits, competition performance, or accident probabilities. 2026 accident records are not 2025 ground truth; accident-RFID identities remain candidates.

Denominators: 100 vessels; 46,705 scored rows.

## Component summary

| Component | Available / 100 | Unavailable / 100 | Same time / comparable | Different time / comparable | Same row / comparable | Different row / comparable | Within ±6h / comparable | Outside ±6h / comparable | Earlier / comparable | Later / comparable | Median abs h / comparable | Max abs h / comparable | Valid rows / 46,705 | Missing rows / 46,705 | Exact-max tie vessels / 100 | All-valid-constant vessels / 100 | Zero-valued peak vessels / available |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| s_zone | 100 | 0 | 37 / 100 | 63 / 100 | 37 / 100 | 63 / 100 | 47 / 100 | 53 / 100 | 51 / 100 | 12 / 100 | 47.0 / 100 | 4247 / 100 | 46705 | 0 | 14 | 17 | 15 / 100 |
| s_change | 75 | 25 | 19 / 75 | 56 / 75 | 19 / 75 | 56 / 75 | 27 / 75 | 48 / 75 | 24 / 75 | 32 / 75 | 292.0 / 75 | 3907 / 75 | 44731 | 1974 | 0 | 0 | 0 / 75 |
| s_gap | 94 | 6 | 33 / 94 | 61 / 94 | 33 / 94 | 61 / 94 | 44 / 94 | 50 / 94 | 25 / 94 | 36 / 94 | 93.5 / 94 | 3942 / 94 | 46605 | 100 | 0 | 3 | 0 / 94 |

## Other counts

- Single-row vessels: 6 / 100.
- Vessels with fewer than 25 rows: 25 / 100.
- No valid `s_change`: 25 / 100.
- A at score floor 1e-6: 5 / 100.
- A score has exact max ties: 0 / 100.
- A missing components: {'s_zone': 0, 's_change': 39, 's_gap': 6}.
- All three component peaks available: 75 / 100; among these all three peak times equal: 2.
- A equals any available component peak time: 70 / 100; equals all available peak times: 13 / 100.
- Candidate A row and score match: 100 / 100 (score absolute tolerance 1e-12; ordinal and time exact).

## Reproducible examples

### largest_component_A_time_disagreement

{
  "rfid_id": "31010758",
  "n_rows": 1158,
  "A_time": "20250101 13",
  "A_source_ordinal": 4482,
  "components": {
    "s_zone": {
      "peak_time": "20250627 12",
      "signed_delta_hours": 4247,
      "absolute_delta_hours": 4247,
      "peak_source_ordinal": 4113521
    },
    "s_change": {
      "peak_time": "20250607 21",
      "signed_delta_hours": 3776.0,
      "absolute_delta_hours": 3776.0,
      "peak_source_ordinal": 3512019.0
    },
    "s_gap": {
      "peak_time": "20250131 5",
      "signed_delta_hours": 712.0,
      "absolute_delta_hours": 712.0,
      "peak_source_ordinal": 579988.0
    }
  }
}

### three_component_peak_time_agreement

{
  "rfid_id": "36011779",
  "n_rows": 336,
  "A_time": "20250627 11",
  "component_peak_time": "20250627 11",
  "A_equals_any_peak_time": true,
  "A_equals_all_available_peak_times": true
}

### one_row_or_floor_case

{
  "rfid_id": "36012931",
  "n_rows": 1,
  "single_row": true,
  "A_score": 1e-06,
  "A_time": "20250213 17",
  "component_peak_times": {
    "s_zone": "20250213 17",
    "s_change": null,
    "s_gap": null
  }
}

### All-three component peak-time equal vessels

| RFID | Rows | Peak time | A time | A equals any | A equals all available |
|---|---:|---|---|---|---|
| 31001774 | 37 | 20250409 15 | 20250409 15 | True | True |
| 36011779 | 336 | 20250627 11 | 20250627 11 | True | True |

### Concrete s_zone exact-tie example

{
  "rfid_id": "36107971",
  "n_rows": 31,
  "s_zone_peak_value": 0.0,
  "s_zone_max_tie_count": 31,
  "s_zone_unique_tied_timestamp_count": 31,
  "chosen_source_ordinal": 228998,
  "chosen_peak_time": "20250114 14"
}

### Requested comparison CSV rows

| RFID | Rows | A time | A score | A floor | A components (zone/change/gap) | Peak times (zone/change/gap) | Peak deltas h (zone/change/gap) | Gap previous time | Previous ordinal | Elapsed observed gap h |
|---|---:|---|---:|---|---|---|---|---|---:|---:|
| 31010758 | 1158 | 20250101 13 | 0.7317562035272891 | False | 0.5210807507353798 / None / 0.9424316563191985 | 20250627 12 / 20250607 21 / 20250131 5 | 4247 / 3776.0 / 712.0 | 20250123 23 | 483954.0 | 174.0 |
| 36011779 | 336 | 20250627 11 | 0.6624338856162725 | False | 0.28934860669348184 / 0.7607540243561295 / 0.9371990257992062 | 20250627 11 / 20250627 11 / 20250627 11 | 0 / 0.0 / 0.0 | 20250627 10 | 4096026.0 | 1.0 |
| 36012931 | 1 | 20250213 17 | 1e-06 | True | 0.0 / None / None | 20250213 17 / None / None | 0 / None / None | None | None | None |
| 34400012 | 915 | 20250110 23 | 0.816259425052932 | False | 0.8333333333333334 / 0.656198166371838 / 0.9592467754536248 | 20250126 11 / 20250110 16 / 20250126 11 | 372 / -7.0 / 372.0 | 20250120 4 | 384735.0 | 151.0 |

## Delta and gap definitions

Signed delta is component peak `ts` minus A `ts`, in integer hours; positive is later than A and negative is earlier. `ts` is the existing integer hour index, not Unix seconds. The ±6h bucket is inclusive. A component with no finite values has `no_valid_component` and null peak/time/deltas. Exact max ties choose the lowest `source_ordinal`; tie counts and tied timestamp counts remain visible.

`s_gap` peak belongs to the observation after the gap; the prior-observation fields use `(ts, rfid_time, source_ordinal)` ordering. Elapsed observed gap hours is not missing-hour count, velocity, incident duration, or incident time. Labels are `YYYYMMDD H` from `part_dt` and `rfid_time`, without timezone conversion.
