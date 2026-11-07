# Round 007 — Final independent review

## Decision

**The approved synthetic pair and its saved artifacts pass review.** The result supports numerical equality for this fixed synthetic comparison only. It does not establish equivalence on vessel data or a memory reduction for the full context.

## Bounded execution

The manager receipt records `pair_01` as completed with exit code 0 in 30.078 seconds. The executed source SHA-256 matched the approved `synthetic_pair.py` hash `67F74942B38C4C2EE42C6A0509C39997828C0E98658BC04ADB2CA96850F445B3`; the wrapper hash was `2820871E8884A0FD642E550301154C16039D6C85C6168BDA32CBF67340F3BEE4`. The preflight gate was met at 4.7878 GiB available RAM; the observed minimum was 4.1396 GiB. Sampled owned-tree peak working set was 780,906,496 bytes, and the receipt reports no remaining owned processes.

The run performed one checkpoint fit and exactly two `predict_proba` calls on the same fitted estimator: baseline once and column-chunked once. The adapter was restored and the original manager reinstated. No actual-data inference, new F1 evaluation, holdout access, or retry occurred.

The synthetic inputs were `X_fit (32,312)` and `X_query (2,312)` float32 from `default_rng(20261105)`, with four tiled classes. The model exposed eight column-manager calls. Each call had input shape `(1,316,34,3)` and output shape `(1,316,34,128)`; each was split into 20 chunks, width 16 except the final width 12. Sequence length 34, fit context 32, and group width 3 were preserved. This verifies the run's chunk path and shape contract, not the full-context resource profile.

## Independent artifact verification

I ran [verify_synthetic_artifacts.py](verify_synthetic_artifacts.py) with the round004 environment Python. The checker imported NumPy and standard-library modules only; it did not import Torch or TabICL. It independently regenerated the seeded inputs, verified shapes/dtypes/labels and all saved input SHA-256 fingerprints, compared the NPZ probabilities with the JSON values, recomputed the probability gates, maximum difference, exact equality and argmax, and checked chunk coverage and manager restoration. **All 50 checks passed.**

- Result JSON: `DE911BA39E2389D8282A1DD754AA0DED8457157AFA3C7416CA7C2AC4F219B07A`
- Bounded-run receipt: `2DFC818217E2F87C2F29B561034BAE5E4D9C7F50114939D5660CC8EFD80778CF`
- NPZ: `D950C5E5C8783DF382A659D961D7F1B885686402B573F33071736FAA6B89DCEC`

Both probability arrays were finite, within `[0,1]`, and had maximum row-sum error `5.960464477539063e-08`. Their maximum absolute difference was `0.0`; they were exactly equal numerically, with matching argmax `[1,2]`. The fixed `1e-5` probability and argmax gates passed.

The first invocation of my checker stopped before opening the result because of a reviewer-script project-root path error. I corrected the path and ran the checker to completion; this did not rerun or alter the approved model computation.

## Limits and follow-up

This is a two-query, synthetic-only numerical comparison. It does not establish actual-vessel replay equivalence, F1, independent or official score, full-context memory reduction, or hardware behavior. The final run data and full check list are in [synthetic_artifact_verification.json](synthetic_artifact_verification.json); the source contract and earlier mock review are in [REVIEW.md](REVIEW.md).

## Review timing and RAM record

The fresh available-RAM observation before artifact inspection was **4.878 GiB at 2026-11-04T18:28:36Z**. This precedes opening the result/NPZ and is not the manager's model-run preflight or a sample taken immediately before the verifier command. The verifier handled only the result metadata and small synthetic arrays (array payload estimate below 0.1 MiB); estimated incremental use for the NumPy/JSON check was below 0.15 GiB. A separate post-verification reading was **4.813 GiB at 2026-11-04T18:32:58Z**. Review start and finalization timestamps are recorded separately in inal_review.json.
