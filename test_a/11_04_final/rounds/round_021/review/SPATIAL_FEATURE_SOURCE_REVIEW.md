# Round021 spatial feature source review

**Decision: GO for fold-local FIT-only spatial feature generation.** The approved helper can generate INNER_SELECT features for candidate fitting. Its OUTER mode is gated on both baseline and candidate fit artifacts having three successful reload checks; it generates features only and does not load OUTER probabilities or score predictions.

Reviewed 2026-11-05 00:21 UTC. The hash-bound source approval is `spatial_features_approved_sources.json`.

## Checks

- Helper SHA256: `24265ECDD609B53AE3DE1574678A3E87C42A5977A2DBF11495F49C5BF9D4F2DC`.
- Config SHA256: `07F4B526D6EFDCF6E2E0CECF80B9D27C7AAC09BF3F56147951A48322685A5245`.
- Launcher SHA256: `4A221F280C07641BADF4BCC1E03FBCAFC2DEB59C10BE9A0F4A80E925C33D6171`.
- Frozen plan SHA256: `F52F64A5CB616F7E07EBD9060D8643E066FA78A9E3D04EF1B6146D6EDC1F070D`.
- Per fold, prototype distributions use only FIT IDs and FIT labels. Each normalized vessel profile contributes equal weight to its class prototype, followed by prototype renormalization.
- For INNER_SELECT, query IDs come from the exact 394-ID round002 roster and are checked as a subset of the archived INNER role; labels are checked for roster/source alignment but are not used in feature calculations. OUTER queries come from OUTER role IDs. FIT/query overlap is rejected.
- Features are `sum(sqrt(p*q))` in the fixed order `r001_c0..c3`, then `r005_c0..c3`. Missing query profiles remain NaN for the downstream constant-zero imputer without missingness indicators. The output has id/year/fold/role plus the eight features; no query label is written.
- The helper reads the filtered profile CSV and ID/role/label metadata only; it does not read model probabilities or invoke a base model. OUTER feature generation requires baseline and candidate fit records with three successful reload checks.
- Helper and launcher ASTs parsed; config JSON parsed. No feature-generation run or model fit was performed by this reviewer.

## Required input binding

Before invoking the helper, the manager must bind all three fold metadata NPZ files, the SELECT roster, and the filtered profile CSV/manifest to the frozen source hashes. The helper confirms the profile CSV hash and source-parquet identity; the manager snapshot supplies the fold and roster hash checks.

The helper reads full `y` arrays to validate role metadata and then slices FIT labels for prototype construction. SELECT roster labels are used only for source alignment. Query labels are not included in feature computation or output.
