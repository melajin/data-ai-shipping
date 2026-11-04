# Context recovery readiness (fold 0, seed 42)

Status: `EXPORT_NOT_RUN`. The parent set a 17:15 UTC execution cutoff before reviewer approval; this is a reviewed-candidate handoff, not a completed context export. No Python audit/export, model load, training, inference, or F1 computation was run. No NPZ context output or launch PID/stdout/stderr/exit receipt exists.

## Source and manifest evidence

- The ID-only split manifest is `P/splits/splits_original.json`, SHA256 `b99a81c7573acbc65ab4b8780790dfc2377252893a0947ac760eedc510dae686`. This SHA matches both the frozen decision rule's `split_manifest_sha256` and the seed-42 parent fingerprint's recorded `work/splits.json` hash.
- Reviewer schema inspection found top-level `development_ids` (5,897), `holdout_ids` (1,475), and three folds. Fold entries expose ordered `fit_ids`, `inner_ids`, and `outer_ids` lists with counts 3,144 / 787 / 1,966 for fold 0. No feature/label fields were in this manifest schema. The reviewer did not print identifier values.
- The frozen seed-42/fold-0 decision rule records expected INNER-list digest `cb82568ecf4cedf20a5706d15db6a76f84f84a23b9273aa4b18948c3014ed0c3`, using the `BASE.digest_json` JSON serialization (`json.dumps(jsonable(value), sort_keys=True, ensure_ascii=False)` encoded as UTF-8, SHA256). The single direct ordered-list comparison is in the candidate script and remains unexecuted; equality is not claimed here.
- Historical `comparison_models.py` uses `.loc[fold['fit_ids']]`, so list order is the relevant source order. `build_context.py` is set to check P and exp01 role mappings after filtering to fold 0, and compare FIT membership against the frozen vocabulary fingerprint.
- The exp01 development NPZ SHA256 is `858688c0bd690eb82612a1d940b6cc002a31ee33d3acb2c322f176e28152de95`. The candidate pins this input hash before loading numeric arrays.

## Candidate

`build_context.py` SHA256: `1E87753EDA6E5253CF248C1ABBDE6E1155D7EEE3693D91495D8E78C8AC884C6D`.

The candidate is limited to fold-0 FIT and INNER rows and exports only those ordered IDs, labels, transformed 312-column float32 tensors, feature names, and class names. It checks development/holdout ID disjointness using manifest IDs, uses outer-ID metadata only for the fold-0 list count, and records that holdout ID metadata is present while holdout feature/label/probability rows loaded are zero. It expects the reviewer-approved one-run workflow; do not treat the proposed output hashes as actual measurements.

## Open evidence

The exact ordered INNER digest, selected-array hashes/dtypes, NPZ export hash, and source-at-launch/input hash receipt are pending because export did not run. No source hash-at-launch, PID, command receipt, stdout/stderr, or exit code is available. The safe next action is a final reviewer check of the pinned candidate followed by one authorized execution that writes the receipt and development-only NPZ under `context_recovery/`.
