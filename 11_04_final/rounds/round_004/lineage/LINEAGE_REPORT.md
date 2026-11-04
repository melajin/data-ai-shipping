# Round 004 input lineage audit

**Result: PASS_WITH_LIMITATIONS.** The development NPZs provide a source-supported route to the 156 F156 columns used by the saved TabICL preprocessors. The numeric FIT-median check passes for every seed and fold. This does not prove the original saved model's exact row sequence or independently reproduce every protected F156 value.

## Scope and constraints

Read: the frozen round002 config; the three exp01 feature NPZs and their development-only roster; P's `development_roles_long.csv`; P feature/class/settings metadata and rebuild/model/vocabulary source; and the seed 42/2026 fold preprocessor, training, parent-fingerprint, and fold-vocabulary metadata.

Read **zero** full-7372 F156 rows, `train_labels.csv` rows, `components/*train` rows, holdout IDs/rows, Test2025 rows, and raw rows. No model/checkpoint load, training, inference, F1 computation, or other performance calculation occurred. Original source/package directories were read-only; outputs are confined to this lineage directory.

## Findings

- Round002 freezes three 5,897-row, 304-column NPZs: F156 (156), T5 (10), behavior (68), local-relative (70). All NPZ SHA256 values match the frozen round002 config.
- The exp01 adapter source puts `F156_train.csv`'s ordered feature columns in the first 156 positions; P's rebuild source selects the ordered `metadata/feature_columns.json` list and the fold-specific vocabulary scope. All 156 NPZ names match P's 156 feature-column names and dictionary positions in all three folds. All dictionary rows have a definition and group. This is name/order plus source-contract evidence; there was no direct value-by-value comparison with protected F156 files.
- NPZ IDs and roles match, in order, both the exp01 development roster and P's development roles table. NPZ integer labels match the exp01 development roster labels under the P/exp01/round002 four-class order. Fold counts are FIT/INNER/OUTER = 3144/787/1966, 3144/787/1966, and 3145/787/1965. The complete NPZ's remaining 148 columns are outside P's 156-column F156 contract.
- P's three vocabulary-state records report FIT ID counts 3144/3144/3145. Their saved hashes match the sorted FIT IDs in the corresponding NPZ folds. The 34 F156 vocabulary columns have the same names/order in each matching fold. Vocabulary feature values were not regenerated.
- Each saved preprocessor has 156 medians and kind `fit_median_and_raw_missing_flags`. NPZ FIT-row `nanmedian` values match all six seed×fold saved medians at absolute tolerance `1e-10`: **zero mismatches**, maximum absolute delta `2.842170943040401e-14`.
- The saved `run_settings.json` says “no missing flags,” which conflicts with `comparison_models.py` and the saved preprocessor kind. The source code imputes non-finite values from FIT medians, appends the raw missing mask, and casts to float32. That produces an expected width of 312 (156 values + 156 flags); this is the implemented contract used below.

## Mismatch mapping

| Finding | Resolution / limit |
|---|---|
| exp01 cache width is 304 while the saved TabICL transform is 312 | The first 156 columns are the candidate F156 source; exclude exp01's additional 148 columns and append missing flags after median imputation. |
| run settings says no missing flags, but code and saved preprocessor add them | Treat this as a documentation conflict; follow the source transform and stored preprocessor kind. |
| original `fit_ids` / `inner_ids` sequence is not in the allowed roster | Current tensor hashes use NPZ/development-roster order. The source uses ordered ID lists; inspect only their split metadata in a later audit. |
| per-row values were not compared to protected F156 files | Source, schema, row membership, vocabulary FIT-ID hashes, and FIT medians support the path; exact per-row equality remains unproven. |

## Reconstructed input hashes

These are SHA256 hashes of C-order float32 arrays formed from the NPZ's first 156 columns, using each saved preprocessor median and the code's impute-then-append-flags transform. Hashes were computed for FIT context and INNER query rows. Seed 2026 hashes are identical to seed 42 for each fold/role. **The rows are in NPZ/development-roster order, not yet proven to equal the original ordered `fold['fit_ids']` / `fold['inner_ids']` used by P's comparison runner.**

| Fold | Role | Shape / dtype | SHA256 of transformed bytes | SHA256 of ordered IDs |
|---:|---|---|---|---|
| 0 | FIT | 3144 × 312 / float32 | `ac254509d62c1ee0093941fe462c9539b0184e8a50d762dc8e9ba69c140869dd` | `bdfb86ec3c99bbc783a5f0e8d3a1524b789d3c7e1101293d42805f7ccacca3f0` |
| 0 | INNER query | 787 × 312 / float32 | `03949c49801d7ed6e609bc38eaa9702fca1343af8bed6eb3f2e9a2e0bb3be361` | `54beb55ee1b36073286821b22c848ce77a18567d40ff3287794e948fec45643d` |
| 1 | FIT | 3144 × 312 / float32 | `c18269392ddfb50ef6c323b29af188ff05d8207d490f6709a9451e94a21356c3` | `07e847b2ddef7eda4efa7a3266ff2d6cd1d98f48157b01046859516202927de9` |
| 1 | INNER query | 787 × 312 / float32 | `95814c780ae8558a1c0a162b7c8a630d6fa4999cfe9c88f5a6fcd45c97bdbe20` | `6d76c015715ad40248bf435470f58efb2ec6bd4e30377906a62a9619af2694d2` |
| 2 | FIT | 3145 × 312 / float32 | `5188e5c18ddc365b15e8930000a876855665411f1e68e8cdcc16596115586c4c` | `c809c404dfdf6d647171dd21f9934d13f370f5976e375b123d681fbfe9cbe74f` |
| 2 | INNER query | 787 × 312 / float32 | `243eec1d7fe240970ee01ca49cbdc1cec54839e7315c71b5c65f09e1e44e3d2d` | `ae95018ccbb1d59606efdb39047da3b952c4704b4b40bde68bc9e29cdcd3bf02` |

The training source selects rows with `.loc[fold['fit_ids']]` and `.loc[fold['inner_ids']]`. The roster proves membership and its own row order, not that original list order. The current scope did not read `P/splits/splits_original.json`; its contents and schema were not inspected. The internal TabICL class permutation also remains unverified without model/runtime replay.

## Safe next route

After reviewing that metadata file's schema, read only the per-fold `fit_ids`, `inner_ids`, and (if needed) `outer_ids` arrays from `P/splits/splits_original.json`. Do not load feature/label rows. Verify ordered IDs and membership against the allowed development roster and saved vocabulary FIT-ID hashes. Then rebuild the same 312-column float32 tensors in the original ID order and replace the roster-order hashes above. This closes the sequence gap without full F156 or raw exports. A later model replay still requires its own bounded plan and model/runtime check; these audit results are not a replay or validation score.

## Evidence and execution

- Code: `audit_input_lineage.py`; machine output: `result.json`; stdout: `run.log`; invocation/receipt limitation: `DIAGNOSTIC_HISTORY.md`.
- Command: `& "C:\Users\dlehs\AppData\Local\Programs\Python\Python313\python.exe" "D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final\rounds\round_004\lineage\audit_input_lineage.py"`
- Erratum: eight successful audit invocations are visible in the tool transcript. `result.json` says iteration 7 with six prior diagnostics because the counter was not updated before the last rerun; see `DIAGNOSTIC_HISTORY.md`. The final command reported exit code 0; elapsed 0.517 s; stdout log SHA256 `27d962835100bbe54c748426de8840fafc803431a34104fb22b65e68ebe951ad`.
- Checks: 3/3 frozen NPZ hashes; 3/3 first-156 name orders; 3/3 roster/role/label mappings; 3/3 fold vocabulary FIT-ID hashes; 6 median comparisons with no mismatch; 12 transformed FIT/INNER arrays hashed; no protected-row reads.

Key hashes: round002 config `04993014836b851bf6b7b933287e16fcd21b9ecbc232bbf6936fc2655e115c94`; NPZ folds 0/1/2 `858688c0bd690eb82612a1d940b6cc002a31ee33d3acb2c322f176e28152de95`, `9f9d582bedaae5e4b6ae13877e70ff467e25459c3aee25916d0fed8c3ff8d992`, `f8e4c29ff7605efa4373f2514fd1933ceac57510f0d7939aa800564ff3fca633`. Complete source, metadata, input, preprocessor, and fold vocabulary hashes are in `result.json`.
