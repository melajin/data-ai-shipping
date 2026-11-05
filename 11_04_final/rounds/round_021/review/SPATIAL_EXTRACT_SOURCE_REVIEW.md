# Round021 spatial extraction source review

**Decision: GO for filtered profile extraction only.** This authorizes the separate development-profile extraction stage. It does not approve FIT prototypes, candidate fitting, OUTER probability access, historical prediction rows, or evaluation.

Reviewed 2026-11-05 00:19 UTC. The source approval is `spatial_extract_approved_sources.json`.

## Checks

- Extractor SHA256: `1E3EF3E47CECCF15721D324665B4436410522C6E79A9AC62163784A714B3E8BD`.
- Config SHA256: `07F4B526D6EFDCF6E2E0CECF80B9D27C7AAC09BF3F56147951A48322685A5245`.
- Launcher SHA256: `4A221F280C07641BADF4BCC1E03FBCAFC2DEB59C10BE9A0F4A80E925C33D6171`.
- Frozen plan SHA256: `F52F64A5CB616F7E07EBD9060D8643E066FA78A9E3D04EF1B6146D6EDC1F070D`.
- The script reads only the `rfid_ids` array from fold 0 metadata, constructs the 2026/full/.01/.05/development-ID predicate and six-column projection on the PyArrow scanner, then materializes filtered rows. It does not import or execute the profile builder and does not read labels, saved predictions, 2025 profiles, or holdout rows.
- It validates unique vessel IDs, duplicate cells, finite nonnegative weights, and positive per-vessel/resolution mass; it normalizes each profile and checks the parquet SHA again after extraction. Output is confined to the round021 workspace.
- Extractor and launcher ASTs parsed; config JSON parsed. No extraction was run by this reviewer.

## Invocation constraint

The extractor accepts paths as CLI arguments and checks only that it finds 5,897 unique IDs in the supplied fold0 metadata file. The launcher must pass the frozen config paths, use the existing Python313 environment with PyArrow 24.0.0, and verify the fold0 metadata path/hash against the frozen input manifest. This keeps the ID predicate tied to the approved development cohort.
