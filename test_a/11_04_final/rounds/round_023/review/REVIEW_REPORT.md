# Round023 independent review

## Round023 result

The single launch ended with exit code 3 after 25.10 seconds. The runner stopped at its `cv0_s1_feature_build` precheck before building the S1 features or fitting a model. The measured free RAM was 2,646,290,432 bytes (2.464 GiB) against the 2.5 GiB stage guard of 2,684,354,560 bytes, a shortfall of 38,064,128 bytes. The execution began at 2,886,963,200 bytes available. Its sampled owned-process peak was 329,039,872 bytes (0.306 GiB); this is a pre-fit observation and does not measure the full eight-fit peak.

The independent audit in `blocked_gate_audit.json` confirms the `gate_blocked.json` record, exact zero fit counters, no model or feature-evidence files, no `gate_result.json` or prediction files, and no live Round023 launcher/run_gate process. It also verifies the fold0 feature-file hash against the blocked record and checks source hashes against approval, freeze, launcher preflight, and receipt. The approved runtime-contract hash matches the current and frozen copies; the launcher receipt did not include that contract hash, but its recorded compute cutoff matches the contract deadline.

`fit_progress.json` still says `running`, while its fit counters are zero. `gate_blocked.json` and the exit-3 receipt are the terminal evidence; preserve the stale progress status and explain it rather than treating it as a successful run.

The existing result checker and any model reload/reinference were not run. They cannot run meaningfully without `gate_result.json`, predictions, and serialized models. There is no Round023 performance or gate result. Do not retry the stage: the runtime contract allows zero retries, and the existing claim/output directories represent the consumed attempt.

## Source and checker review

All eight approved gate sources match their current and frozen SHA-256 values. Seven are present in both launcher hash snapshots and receipt before/after hashes. The runtime contract is present in approval/freeze and its deadline value is recorded in launcher preflight, but is not directly hashed in the receipt.

All copied model/config/cache inputs match the recorded copied hashes. The copied checker has only the authorized path change from `root / "rounds" / "round_022"` to `out.parents[1]`; Round022 remains unchanged. The copied checker still maps approved source keys using the `round_022/` prefix, so it skips five Round023 code/config keys. The independent blocked audit checks these source hashes directly. The checker limitation is recorded in the JSON audit.

## Static review of next-round preparation

`manager/next_resource_contract.json` now sets a 4.5 GiB entry threshold: 2.5 GiB stage guard + 1.5 GiB expected/maximum owned-job budget + 0.5 GiB reserve. The full-run peak remains unmeasured; the Round022 partial 0.427 GiB observation is not a full-run bound. This is a conservative admission condition, not a guarantee that free RAM will remain available.

The unexecuted `prepare_round024.py` checks the new entry threshold and other Python jobs before creating a fresh directory, copies reviewed code and prepared caches without rescanning raw geometry, writes a fresh bounded runtime contract, and patches only the copied launcher’s initial guard to read `minimum_entry_available_gib`. The independent review and approval are intentionally still pending after creation; freeze and launch must wait for that review. No Round024 directory was created in this review.

`recheck_resources.py` is a one-shot check and was not run. The manager should run it only after independent work and immediately before the next heavy step. The launcher's strong entry guard then rechecks availability before claiming the fit stage. If the 4.5 GiB threshold is not met, save a ready resource-block handoff and exact resume command; do not create repeated fresh managers to wait for RAM.

The current draft handoff and `code_author/S2_READINESS.md` both reflect the 4.5 GiB admission threshold and preserve the eight-fit-only scope. The setup file list now copies `code_author/supplement_metrics.py` into Round024; its use remains gated on a separate passing reinference audit.

## Static review of saved-metric supplement

`code_author/supplement_metrics.py` was read only and not executed. It is scoped to an already completed FIT diagnostic: it reads saved labels/predictions plus the original FIT roster and `obs_days`, emits aggregate per-class, paired gain/loss, transition, observation-bin and 5,000-replicate vessel-bootstrap summaries, and does not load `X`/`y` from the feature NPZ, fit a model, or emit vessel IDs. Its class labels are valid UTF-8.

Before any future use, make these points explicit or address them in the script:

- The source-hash claim is narrower than the author report suggests: it checks the original fold0 NPZ hash and ordered FIT roster, not all approved model/code/cache hashes. It should either verify those hashes or document that it relies on the independent gate checker.
- It does not require a persisted passing checker result. Its safe use depends on the manager sequencing it after successful independent output verification.
- NumPy is imported at module load before the script’s RAM check. Move that import after the one-shot memory gate so the precheck precedes the heavier analysis runtime.
- It writes `supplemental_metrics.json` without refusing to overwrite an existing file; add an existence guard before use if reruns are possible.

The author’s `S2_READINESS.md` is bounded to source locations and preparation constraints and reports that external source existence, hashes, and fit-time/RAM were not verified. It correctly says the current zero-fit stop is not an S1 performance failure and now states the 4.5 GiB admission threshold.

## Scope and unknowns

No training, model fitting, saved-output verification, model reinference, raw geometry scan, holdout/Test evaluation, or S2 work was performed in this review. The full eight-fit peak and runtime remain unknown. No result can be inferred from this resource stop.

## Static-review amendment — 2026-11-05

After the author’s limited repair, I inspected only the changed parts of `code_author/supplement_metrics.py` and its report. The script now imports NumPy only after its one-shot RAM threshold passes, checks for an existing output before input-content loads, and uses exclusive `x` mode when creating the output. Its documentation and provenance explicitly limit the hash scope to fold0 NPZ bytes and the ordered FIT ID sequence; it does not claim full code/cache/checker verification. Its docstring and author report set a passing independent saved-result check as a required operator precondition. The script remains unexecuted; these are static findings only. Current SHA-256: `f107c4929463502aa56dec4008b37ffcaec7ab1e099f3153b01df10884ed8ff1`.

The Round024 setup copy list now includes this optional analysis script. The draft handoff requires a separately written and reviewed eight-model reinference audit plus a passing audit record before running the supplement. No such reinference script or result exists yet, so the handoff must keep that step pending and make no model-reload or probability-reproduction claim.
