# TabICL replay runtime contract

**Status:** source review complete; this agent did not run the replay. No package import, data/checkpoint load, inference, training, or F1 evaluation was performed.

## Historical settings and package defaults

The seed-42, fold-0 runner explicitly used TabICL 2.2.0 with the local pinned checkpoint, `allow_auto_download=False`, `n_estimators=8`, `batch_size=1`, `random_state=42`, `use_amp=False`, `use_fa3=False`, `offload_mode="auto"`, a fold-local disk offload directory, and `n_jobs=3`. The historical device was CUDA. For the requested pilot, CPU is a deliberate runtime change.

The runner did not pass the following options; these are TabICL 2.2.0 defaults, not independently recorded historical overrides: `norm_methods=None` (expanded during fit to `none` and `power`), feature shuffle `latin`, class shuffle `shift`, temperature `0.9`, average logits enabled, outlier threshold `4.0`, many-class support enabled, KV cache disabled, and verbose disabled. Four classes are within the model's native class support. `batch_size=1` batches ensemble views; it does not split query rows.

Historical `predict_proba` received the complete 787-row INNER matrix in the recovered `inner_ids` order in one call. Canonical output class order is `[0, 1, 2, 3]`.

## Query subset interpretation

Source inspection found that preprocessing is fitted on FIT and then applied to query rows; column embedding defaults to `embed_with_test=False` and uses FIT positions; and ICL attention uses query rows as queries while restricting keys/values to the FIT positions. CPU inference does not internally split the supplied query group. These source paths support per-query mathematical independence from other query rows for fixed FIT.

That is not a measured equivalence claim. No comparison established bitwise or tolerance-level equality between predictions from the first two INNER rows on CPU and the historical 787-row CUDA call. Sequence shape and backend/device can change numerical results. Treat the two-row call as a bounded runtime pilot only; compare against persisted probabilities with a predeclared tolerance before calling it a replay-equivalent result.

## Bounded pilot requested for the next round

- Seed 42, fold 0; FIT only for fitting: 3,144 rows x 312 columns, `float32`.
- Predict the first two INNER row IDs in original recovered `inner_ids` order. The context-recovery owner must supply those IDs and matrix lineage; do not infer them here.
- Fit labels only enter `fit`; INNER labels are not used for fitting or selection.
- CPU, 3 threads, 600-second wall cap. Start only if available RAM is at least 3 GiB; stop this pilot's own child if available RAM falls below 1.5 GiB. Do not terminate other processes.
- No F1, hyperparameter selection, or performance conclusion in this pilot.

The 312-column lineage remains unresolved: historical code/fold preprocessor metadata indicate FIT-median imputation plus raw missing flags (156 raw columns to 312), while the README and run settings say no missing flags. Use the recovered context evidence to settle the actual matrix contract before launching.

## Evidence and limits

Historical runner: `comparison_models.py`, SHA-256 `F818C0F2C3BB79CD80781A4DF22C3D6CCA425528FC3E3DF4A08E55324D914251`, especially lines 206-230 (constructor/policy), 314-340 (ordered split roles and complete-role prediction). Installed package metadata identifies TabICL 2.2.0. Classifier source SHA-256 `64F5EF7EF88A920A3F7A5F6E2D9D8DC08769EC343E931F910ACC2D9C4EAA5534`; query/attention implementation source hashes and line references are recorded in [`replay_contract.json`](replay_contract.json).

The manager reported a prior **synthetic smoke** result: 13.047 seconds, 27,552,258 parameters, matching output head, CPU and FP32. This is manager-reported evidence, not this agent's measurement, and is not an estimate of the full FIT pilot's runtime or memory.

Unknowns: recovered FIT/INNER identifiers and 312-column lineage; CPU two-row prediction agreement with stored historical CUDA probabilities; and full-pilot wall time and memory use. The JSON file holds the complete source hash/line manifest and structured contract.
