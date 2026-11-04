# Round 004 independent final review

**Status: PASS_WITH_LIMITATIONS**  
**Decision: accept round004 with the synthetic smoke result and the unexecuted context export clearly distinguished.**

## Verified results

- The pinned CPU environment installed successfully in 150.437 seconds. All six install steps exited successfully, `pip check` was clean, and the aggregate stayed within the 900-second bound. The 283,868,825-byte peak is local wheel/temp disk usage, not exact network traffic accounting.
- The first RAM gate was below threshold, so that attempt did not launch the model. After the user's explicit recheck instruction, available RAM was 3.986 GiB; the wrapper measured 4.045 GiB at launch. The single synthetic smoke completed in 13.047 seconds with exit code 0 and no timeout.
- The smoke used only 16 synthetic FIT rows and 4 synthetic query rows with 312 FP32 features, four classes, one estimator, CPU, and disabled AMP/FA3/automatic downloads. It confirmed 27,552,258 parameters and the named `icl_predictor.decoder` dimensions 512→1024→10. Parameters and buffers were on CPU; floating parameters were FP32.
- The 4×4 probability output was finite, row sums passed the 1e-5 tolerance, the class inverse mapping and predicted-label argmax matched, and the repeated call had maximum absolute difference 0. No gradients were present. These are synthetic runtime checks, not a model score, real-data inference, or CPU/GPU equivalence result.
- The development-only lineage check independently confirmed the three frozen NPZ hashes, feature names/order, roster roles and labels, six saved-median comparisons, and all 12 candidate 312-column tensor/row hashes. The maximum median difference was 2.8421709430404007e-14. The candidate tensors use NPZ/roster order and are not original saved-model replay arrays.
- The ID-only manifest has 5,897 development IDs, 1,475 holdout IDs, and three ordered folds. Its `known_holdout_reused=true` flag and `development exploratory nested early-stop evaluation` scope are recorded as provenance. The source verifier rejects development/holdout ID overlap, but the flag does not establish fresh evaluation independence; prior exposure history remains unresolved.
- The fold0/seed42 context exporter received static review and is ready for one bounded execution in round005. It pins the development NPZ hash, binds the manifest hash to the frozen rule and parent fingerprint, filters role maps to fold0, validates development/holdout ID disjointness, and limits output to FIT/INNER arrays. **The exporter was not run by the 17:15 UTC cutoff.** No context NPZ, ordered-ID export, direct INNER digest comparison, or output hash has been produced.
- The updated round report and next-session draft reflect the smoke pass, preserve the holdout provenance caveat, and plan a single context export followed—if its gates pass—by one 600-second CPU pilot for two fixed INNER queries. The plan excludes F1, OUTER inference, training, and a repeat smoke.

## Limits

The review did not read protected feature/label/probability rows, load a model, run training or inference, compute F1, or validate hardware. Pointwise equality to all historical F156 values, vocabulary value regeneration, original GPU probabilities, and CPU/GPU numerical equivalence remain unestablished. The context-export code was reviewed statically but not executed, so its output arrays and ordered-ID hashes have not been independently checked.

Machine-readable review and evidence hashes are in [review.json](review.json). Focused smoke and source-precheck records are in [runtime_smoke_review.json](runtime_smoke_review.json) and [context_precheck.json](context_precheck.json).
