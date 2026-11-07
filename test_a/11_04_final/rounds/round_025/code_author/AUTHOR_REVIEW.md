# Round025 code author review

**Status:** static author review complete; independent approval belongs to the Round025 reviewer.  
**Scope:** copied code, contracts, and transfer hashes only. No source arrays were loaded, and I did not run imports, tests, a launch, a freeze, training, scoring, or any calculation.

## Sources and transfer lineage

Reviewed `AGENTS.md`, `NEXT_SESSION.md`, `ROUND_PLAN.md`, `manager/runtime_contract.json`, `manager/source_transfer.json`, the Round025 Python files, `configs/experiment.json`, and the T5 profile manifest. `source_transfer.json` records a Round024 source approval with 22 entries and 15 copied files. The two planned executable round adaptations are recorded there: `review/reinfer_saved.py` changes the `ROUND.name` guard to `round_025`; `review/verify_gate_result.py` changes its expected round directory to `round_025`.

Static review found one more executable Round024 path guard in `review/verify_gate_result.py`: the fresh approval's source paths were required to start with `rounds/round_024/`. I changed only that prefix to `rounds/round_025/` (line 80). The prepatch SHA-256 was `7fa91d8153b0a1c260d9abcba51b2a929e8287d89a0a15e1b77dc746ebd8a3bd`; the final SHA-256 is `e0bafcde7bc3135f29b5f4e66b5b8a3503d26609281cd8716d5a670d6ed43fe3`. Other Round024 text in checker messages remains cosmetic. This author patch and the manager-owned launcher cap patch need to be represented in the manager's post-transfer patch record; `source_transfer.json` is a setup-time snapshot.

The manager subsequently changed the launcher argument ceiling from 1,200 to 900 seconds. The current launcher line 11 now matches `runtime_contract.json`'s `job_seconds_max: 900`. I did not edit manager-owned files. Current launcher SHA-256: `0370a7811a3a6079a62e50d5634602917f78357e85683e2f13c1518184d535bf`.

## Code and contract review

- `run_gate.py` selects only `roles == "FIT"` and requires 3,144 rows (lines 52–86). It makes one stratified, shuffled four-fold split with seed 42 (lines 201–221); the baseline and candidate share each fold's train/validation indices (lines 249–279).
- T5 is rebuilt per fold from `train_idx` and `y[train_idx]` (lines 222–228). `t5_rebuild.py` constructs counts from those labels only, removes the queried FIT row from its global prior and cell counts when it is a donor, and uses no validation label. The base T5 columns are replaced by the fold-local matrix before fitting (lines 235–240).
- S1 donor counts are built only from the supplied CV training indices and labels. `build_features` accepts no validation labels; for FIT donor queries, `_posterior_for_cell` subtracts that vessel from its cell counts and global prior, with coarser-cell and training-only-prior fallbacks (`s1_features.py`, lines 330–356 and 422–456). The gate records these intended boundaries per fold.
- The gate condition is the specified AND: candidate correct count at least 1,833 **and** at least 16 more correct than the matched baseline (`run_gate.py`, lines 293–298; `experiment.json`, lines 34–35). The fixed 1,817 reference remains context; this condition does not claim OUTER or official-score performance.
- The copied T5 manifest declares label-free profiles, no Test2025 labels, zero Test2025 query rows materialized, and Test2025 geometry read only for a shared-harbor aggregate. This is a manifest/code-boundary review, not an independent validation of the underlying data. Test/holdout arrays and labels were not read in this review.
- The runtime contract sets 1.5 GiB entry RAM, 1.0 GiB stage checks, 0.5 GiB expected peak, 0.75 GiB owned RSS cap, 0.5 GiB emergency free-RAM floor, one process/thread, and eight fits maximum. The launcher sets OMP/OpenBLAS/MKL/NumExpr thread variables to 1, uses below-normal Windows priority, enforces the 900-second job cap and 1,800-second total budget, and checks entry/owned-process memory. The estimator config sets `n_jobs: 1`. These are static controls; no resource behavior or peak memory was measured here.

## Current SHA-256 inventory

These are the prepared Round025 file bytes at author-review completion. The `verify_gate_result.py` author patch and manager-owned `launch.py` cap patch supersede their setup-time `destination_sha256` values until the manager records those deltas.

| File | SHA-256 |
|---|---|
| `code/prepare_t5_cache.py` | `98c4c52a36dd9bb6f289aac0705e9f031d12ff4463e193153b98844a8ab3876e` |
| `code/run_gate.py` | `1179e95cf81314be9d686a894c633c1f26592013c79970614597b36811848737` |
| `code/s1_features.py` | `6ea7177382a2151508364f8fa14bbe0c087483e42373b98fc362065b0dd14c0a` |
| `code/t5_rebuild.py` | `6b1e252928d4174f569b4225299fa7a62094f1f0f1ac6a9d92708d2fae418a16` |
| `review/reinfer_saved.py` | `424c7693ebccc4fc685f736648a25072f62616334d2652ae3e6bfc1d2ea4e71a` |
| `review/verify_gate_result.py` | `e0bafcde7bc3135f29b5f4e66b5b8a3503d26609281cd8716d5a670d6ed43fe3` |
| `configs/experiment.json` | `d6f8aa667a4a9d77e672e6d96997d535b91a8bb2e8491e7586b01cc14381ab77` |
| `artifacts/t5_fishing_profiles.npz` | `a21d74c5d644af19ae41f09ad4383e6a3992fd368cd30842c473fcc7163f3818` |
| `artifacts/t5_fishing_profiles.manifest.json` | `6fbfe1e6593f11c38255801e0d72ee3ee9c00fc83811b1dc68c425614d321f78` |
| `artifacts/t5_mask_equivalence.json` | `1b2a70d3bd945bf0eafc8864146f703731078530940a5358812d2da8407ba695` |
| `tmp/s1_profiles.sqlite` | `c4588e2c82613449e3be1ab1e149f26b4d0e78d22c84b93417e5ae9abc471efa` |
| `tmp/s1_profiles.sqlite.manifest.json` | `ba0823d27b44c1d3b809c81c59be63a26381142842095d0bfef58bf50ab21d20` |
| `code_author/supplement_metrics.py` | `f107c4929463502aa56dec4008b37ffcaec7ab1e099f3153b01df10884ed8ff1` |
| `manager/launch.py` | `0370a7811a3a6079a62e50d5634602917f78357e85683e2f13c1518184d535bf` |
| `manager/freeze_stage.py` | `88c48a90a2d8bb22be18c7494f7472d8879fe6588f7d7ec292ed139d966bf45c` |

## Model and effort evidence

The task request specifies `gpt-6-luna / xhigh`. The available `manager/host_turn_evidence.json` is for the parent manager turn and reports `gpt-6.1-sol / high` with `backend_authenticated: false`; it is not evidence of this worker's actual model/effort. I have not inferred worker runtime metadata from that parent record.

## Limits and unresolved checks

This review establishes static control flow and file hashes only. It does not validate T5/S1 artifact contents, source-data semantics, actual memory use, model behavior, fit results, or hardware behavior. No performance claim or training outcome is available from this author review.
