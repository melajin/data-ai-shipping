# Technical review of the 0.70 roadmap

**Disposition: proposal only; implementation and performance claims are unverified.** This is a source-and-report review. I did not load a model, raw feature/label data, or the checkpoint; run experiments; train; infer; calculate metrics; or contact external services. Only this Markdown file and `technical_review.json` are authored for this review.

## Assessment

The roadmap identifies plausible research directions, but it combines several new variables and gives stage scores (`0.628`, `0.669`, `0.708+`) without measurements in the reviewed rounds. Treat them as aspirational targets, not forecasts or commitments. Round 003 measured a narrowly defined post-hoc policy comparison on repeatedly observed development OUTER predictions: `A_raw` averaged micro-F1 `0.593013`; `A_micro_select` averaged `0.593353`, with paired 95% CI `[-0.000933, +0.001611]`, and failed the preregistered promotion gate. That result does not prove a theorem that every post-hoc policy must fail; it supports rejecting the particular tested policy under that gate. Round 004 reports no new real-data inference, training, or F1.

The roadmap's arithmetic gap to 0.70 on 5,897 development vessels is not evidence that its proposed features or models will recover those additional correct predictions. No independent holdout or official score is available in the reviewed evidence.

## What the reviewed artifacts establish

- The canonical labels are four **vessel-level fishing-type classes**. The reviewed files contain no segment-level activity labels. Do not treat a vessel label as a label for each transit, set, haul, or other track segment.
- The approved Round 004 input audit used development-only per-vessel feature tensors. Each cached tensor has 304 columns: the first 156 are the F156 feature contract, and 148 additional columns belong to other feature groups. The TabICL preprocessor path imputes the 156 F156 values and appends 156 missingness flags, giving a 312-column float32 input. The lineage check supports names/order, FIT medians, and roster mappings, but did not compare every feature value to protected raw rows. The exporter for the original FIT/INNER row order was not run by the Round 004 cutoff.
- The reviewed/approved inputs are summaries, not timestamped point tracks. Round 004 explicitly read zero raw rows. The project rule forbids deriving physical speed or acceleration from coordinates without per-point time. The raw source's point-timestamp availability was not examined here; therefore these features are unavailable from the reviewed tensors, while availability in a future authorized raw-data path remains unknown.
- The successful Round 004 smoke used synthetic 16 FIT rows and 4 query rows, 312 float32 columns, four labels, CPU/FP32, and no training. It observed 27,552,258 parameters. The actual final registered decoder layer is `icl_predictor.decoder.2`, a Linear layer `1024 -> 10` with weight shape `[10, 1024]`. The smoke exposed four probabilities after class inverse mapping; this is not evidence of a native `1024 -> 4` final layer. No gradients accumulated.
- The smoke's peak working set was about 726 MiB on its tiny synthetic case. A 3 GiB available-RAM preflight is a start gate, not a full-fit or training memory guarantee. Full FIT inference, backpropagation, optimizer state, feature creation, and stacking costs remain unmeasured.

## Review of the proposed pillars

### 1. 120 AIS dynamics features

The proposed time-weighted speed-regime occupancy, distance fractions, acceleration dispersion, turn sequence measures, and day/night ratio cannot be reconstructed from the reviewed per-vessel summaries. They require a permitted source with point observations and the needed fields/timing. Mean or standard deviation summaries cannot recover dwell-time fractions or an ordered trajectory. Do not fabricate timestamps or join points based only on vessel IDs.

The speed bands listed in the PDF leave 5-8 knots unassigned. Define disjoint boundaries, invalid/missing speed handling, the source field and units, and time/distance denominators before extraction. ROT kurtosis and heading-change Shannon entropy are different statistics: kurtosis summarizes a distribution's tails/peakedness; entropy summarizes a defined distribution of discretized events. One cannot substitute for the other. Define heading wrap, sampling interval, event bins, minimum sequence length, and whether ROT is a direct sampled field. A day/night ratio additionally needs a time basis (UTC/local solar), location, and the operational-speed/event rule.

The PDF names 120 features but does not provide a closed, testable feature registry with formulas, units, missing-value rules, and a final model input schema. Specify whether the 120 means raw feature values or includes missingness flags, and how it fits the current 312-column TabICL contract. Gate this pillar on an authorized, development-only timestamped point source and a reviewed schema; otherwise defer it.

### 2. M4 head adaptation, LoRA, and 16-shot context

The proposed `Wout: 1024 -> 4` does not match the smoke-observed final decoder Linear `1024 -> 10`. Since the classifier returns four task probabilities through class mapping, the training design must explain how the ten-way decoder outputs map to the four task labels under feature/class shuffling. Do not assume that rows 0-3 of the stored weight are the four class head. Either specify a compatible task head/wrapper and its initialization, label mapping, loss, serialization, and inference path, or revise the proposed update to match the actual module. This is an architecture/API change that requires a separate review and gradient test.

Keep head-only adaptation, rank-4 LoRA, and context selection as separate experiments. They change different parts of the model and should not be combined in the first adaptation comparison. The historical runner uses the full FIT context (fold 0 has 3,144 FIT rows); selecting 16 prototypes is a new inference-context variable, not a cheaper equivalent of the fixed FIT replay. Define the class allocation and centroid/boundary algorithm, calculate selection statistics within each training fold only, and compare 16-shot with the full-FIT context on the same held-out queries. A prototype chosen using INNER/OUTER labels or embeddings fitted across held-out folds would leak information.

The already planned next step is to export and verify the original ordered FIT/INNER arrays, then run the bounded CPU original-output replay. The Round 004 report says that export did not run by its cutoff. Keep this replay distinct from M4 training; do not infer full-FIT training feasibility from the synthetic smoke.

### 3. 12-dimensional stacking and isotonic calibration

The proposed 12 dimensions imply one four-class vector for each of three base families. If LightGBM is a five-seed ensemble, state whether its seeds are averaged into one four-class vector first; otherwise the feature count is not 12. The PDF also describes meta inputs as probabilities in one section and logits in its phase table. Choose one representation and define class order and calibration/normalization rules.

The reviewed outputs contain no new CatBoost or M4 base predictions and no meta-level out-of-fold predictions. Build base OOF outputs inside each evaluation fold using only that fold's training data; fit the meta learner and calibrator without the evaluation fold's labels. In particular, do not use the same INNER labels both to select M4/prototypes, fit the stacker, tune isotonic calibration, and report the result. Repeatedly observed development OUTER results are not an independent final estimate. Preserve a nested, vessel-grouped evaluation, and keep the existing holdout/Test2025 boundary closed until the full procedure is frozen.

Classwise isotonic fits can produce a vector that does not sum to one, and they can overfit when calibration samples are limited. Define the final simplex-normalization rule, calibration split, class support handling, ECE binning, and a predeclared evaluation. The PDF's `ECE <= 0.005` is a target without measured support, not a guaranteed outcome.

### 4. Separate 1-7 day segment encoder

The existing 1-7 / 8-30 / 31+ grouping is an observation-day subgroup; the prior report explicitly cautions that observed days are not actual operating time. Current tensors do not contain the time-ordered segment inputs needed by a segment encoder, and the reviewed labels are vessel-level, not segment-level. A supervised segment model therefore needs either segment labels or a clearly stated weak-label objective and aggregation rule. Do not claim labeled activity recognition from vessel classes alone. A subgroup-specific vessel classifier over available summaries is a different, testable proposal.

## Recommended gates

1. Complete the original-order FIT/INNER input export and hash check; then run only the bounded full-FIT CPU output replay with its fixed checkpoint/settings and RAM stop rule. Compare to stored probabilities using the predeclared tolerance. This is a replay check, not an F1 test.
2. Before any M4 run, resolve the decoder/class mapping and training interface. Change one variable at a time: head-only first; LoRA and 16-shot context each get separate plans and comparisons.
3. Do not start the 120-feature/segment work until the point-level data fields, timestamp semantics, label unit, feature formulas, boundaries, and final schema are available and reviewed. Fit all feature transforms within FIT.
4. Build any stack/calibrator with nested, vessel-grouped cross-fitting. Freeze meta-model, calibration, and thresholds before a final evaluation; do not recycle development OUTER as independent evidence.
5. Measure representative process/system peak memory before expanding. A 3 GiB preflight threshold only permits a start; it does not guarantee safe completion. Keep the own-process stop condition and do not terminate other processes.

## Evidence references

- `../../AGENTS.md:26,30-33` (canonical vessel classes, data boundary, feature/time rule), SHA-256 `7669FDE3225CBDF926164F72F2114B2FC38920EE8190CD98983AE287CF20F918`.
- `rounds/round_003/ROUND_REPORT.md:3-17,46,52,59-61` (policy result, observation-day caveat, repeated development OUTER and no new training/inference), SHA-256 `B545FD8893F67F3FBA5EB260EC27813B8B1F1E9F433810DAA6DC7F5802C4FCB4`.
- `rounds/round_003/verification_20261105/VERIFICATION_REPORT.md:5-8,26-31` (verification scope and promotion gate), SHA-256 `84D963FA35258BE5589C669DA6A7E2570EFC17B3A6CC4FFA7846F054BAE0FB0B`.
- `rounds/round_004/ROUND_REPORT.md:3,16-18,28-38,40-57,71` (synthetic-only smoke, input audit, memory observations, incomplete original-order export and planned replay), SHA-256 `362BB70A32A2622AE54E6F5FF08408BE94B458D7786B8C0DB5EFE284D39CB914`.
- `rounds/round_004/lineage/LINEAGE_REPORT.md:9,13-18,24-31,42-46` (reviewed input scope, 156-to-312 transform, value/order limits), SHA-256 `D6C7279B78B56FBC4527F7B185F6C25CDB118EDA788EF10E182B15B9C0E03173`.
- `rounds/round_004/artifacts/smoke.json` fields `synthetic_input`, `model.output_head_final_linear`, `checks`, `final_memory_snapshot`; SHA-256 `E26DF55A2C9501FC6A46102D323CA18226C922BD98CEB9EBA9146A0CB0643AE2`.
- `rounds/round_004/runtime_author/REPLAY_RUNTIME_CONTRACT.md` and `replay_contract.json` (historical settings, source review of query semantics, and unmeasured replay limits), SHA-256 `73997F62A289D89473DBF37917024C8F136EA5B570BB0607BCABEE7D7913967D` and `819E60FD2F05A655A86DC1CDAA5E52F5A4FD0486E78FDD5DC5A4AB140AD7E2F5`.
- `pdf_text.txt:110-119,126-154,159-199,205-228` is the extracted five-page strategy proposal. Text SHA-256 `02ED5EA2855C101CD60E635B205025483F81D905221DAF9804C210AF60428ACE`; source PDF SHA-256 from `pdf_metadata.json` is `47bb4b67d506c1e487fd076631aba5aecf3fad5052799c4c9d4a92b62ed6161a`.

See `technical_review.json` for machine-readable findings, uncertainty labels, source manifest, and scope limits.

