# Round 002 preliminary independent review

Status: `PENDING_PRE_TRAINING_CODE_REVIEW`. This note records the baseline and review contract before candidate training. No round002 code/config is available yet; `rounds/round_002/` currently contains only `startup_sessions.json`. No training, installation, or data/model artifact loading was performed by this reviewer in this pre-review phase.

## Scope and source boundary

- Work root: `D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/11_04_final`; reviewer write scope: `rounds/round_002/review/**` only.
- Prior source repo: `D:/repos/fishing-track-classification`, read-only. Raw data: `F:/문제 데이터_수정_1027`, no access by this review.
- Holdout: no individual feature/label/prediction rows read. No development NPZ loaded in this phase.
- This is a pre-run contract read, not a result review. Final verdict awaits code/config review before training and actual execution/reload evidence.

## Historical exp01 baseline evidence inspected

The read-only evidence inspected was:

- `coach/gpt/rank1_experiments_20261104/configs/exp01/experiment.json`
- `coach/gpt/rank1_experiments_20261104/shared/eval_contract.py`
- `coach/gpt/rank1_experiments_20261104/experiments/exp01/run_exp01.py`
- `coach/gpt/rank1_experiments_20261104/artifacts/exp01/sqrt_macro/run_report.json`
- `coach/gpt/rank1_experiments_20261104/reports/exp01/final_summary.md`
- Work-root `NEXT_SESSION.md`, `CYCLE_PROTOCOL.md`, `STATUS.json`, and round001 review/report evidence.

SHA-256 of the four key read-only exp01 files at review time:

| File | SHA-256 |
|---|---|
| `configs/exp01/experiment.json` | `AE901771CD7F9DB2D14B20AD919D58CB68CA54ED71EB4EE432170B941E452791` |
| `shared/eval_contract.py` | `4213E3A18FF418551B92420B04DA49B1AF6D3064AE0F02EB430040FB165A4AD1` |
| `experiments/exp01/run_exp01.py` | `AD84EE500D58983A087A5004FEF695DF030920086A490D62CA9A93DAC2800162` |
| `artifacts/exp01/sqrt_macro/run_report.json` | `DAAA7BB1B86979E06CA765E92EEC956F0F7B26F857E64ECBA5BDEB822CB42661` |

Confirmed baseline details:

- X304 is ordered as F156 (156), T5 (10), behavior features excluding `obs_days` (68), then local_rel (70); `obs_days` is reporting-only. Class index order is `[연안복합, 자망, 통발, 채낚기연승낚시]`.
- Historical exp01 `sqrt_macro` uses LightGBM multiclass; 8,000 maximum estimators, learning rate 0.01, 127 leaves, minimum child samples 10, feature fraction 0.6, row fraction 0.8 with frequency 1, L2 1.0, and 200-round early stopping.
- Early stopping is on the custom **macro-F1** callback only (`metric="None"`, `first_metric_only=True`) on the fold's entire INNER set in exp01. That old use of all INNER does not meet the new separated ES/selection design by itself.
- The `sqrt_macro` weights are inverse-square-root class-frequency weights normalized to mean 1, computed from that fold's FIT labels only. No validation or OUTER labels enter the weights.
- Historical five-seed `sqrt_macro` development OUTER result is 3,497/5,897 = 0.5930133966423605 micro-F1 and 0.5252719738966167 macro-F1. It is a repeatedly exposed development baseline, not independent or official evidence. The historical S6 aggregate near 0.59183 lacks a paired per-vessel prediction in the inspected evidence and remains unresolved.

## Required pre-training gates from the frozen round002 contract

Before the worker starts any fit, I will verify saved code/config against these points:

1. Split each same-fold INNER roster (787 vessels) by vessel ID, stratified at seed `20261105`, `test_size=0.5`, into disjoint `INNER_ES` and `INNER_SELECT`; persist exact IDs, label counts, and hashes. OUTER may not determine this split.
2. Refit one seed-42 `sqrt_macro` LightGBM baseline per fold on the same fold FIT using the historical hyperparameters and FIT-only normalized inverse-sqrt weights, with macro-F1 early stopping (patience 200) on INNER_ES only. Do not reuse the historical model trained with full INNER as the baseline for alpha selection.
3. Fit one frozen candidate per fold on FIT only, using the predeclared CatBoost path or environment-only ExtraTrees fallback. CatBoost parameters and the API's NaN handling, class order, and validation metric must be recorded before score review. Candidate scoring may use INNER_ES for early stopping but not to fit labels. For ExtraTrees, fit the imputer on FIT only and do not add INNER_ES to training.
4. Resolve probabilities to the same class order. Alpha `0, .25, .5, .75, 1` is selected independently per fold on that fold's INNER_SELECT micro-F1; tie-break to smaller alpha. No pooled INNER alpha or selection using OUTER.
5. Only after freezing baseline/candidate/blend decisions, score each fold OUTER once. Check row IDs/roles, duplicate/overlap, 304-column feature-name order, class-column order, finite normalized probabilities, and saved-model reload deltas within the predeclared tolerance.
6. Stay within 6 new fits, 30 compute minutes, one concurrent training process, at most 3 threads, and do not begin a large fit with free RAM below 1.5 GiB. All cache/temp/log/model outputs remain under the work root or its isolated CatBoost environment; source repo and global Python remain unchanged.
7. Interpret all scores as development exploration on previously exposed OUTER vessels. No holdout individual-row reads; no claim of independent/official 0.7 achievement from this result.

## Current readiness and unknowns

`rounds/round_002/` has no `ROUND_PLAN.md`, config, or execution source at this snapshot; pre-training review is therefore not yet possible. CatBoost environment/API resolution, actual split roster counts, NPZ keys/order/hash, current free RAM, execution limits, training results, and reload metrics are unverified. This note does not approve training; I will send any blocker directly to the execution worker and manager once code/config arrive.

## Update — configuration review (2026-11-04 14:47 UTC)

The manager's `ROUND_PLAN.md` and executioner's `configs/experiment.json` became available after the initial snapshot above. The config SHA-256 is `2C80307EB0ABA3E23B7342ED62246A52F227CE1E47A2B35C65961E1815F2B614`. It matches the frozen fixed X304 hash set, seed-42 same-FIT baseline, FIT-only sqrt weights, macro-F1 ES on INNER_ES, CatBoost CPU/seed42/3-thread/3000-iteration cap, unweighted Accuracy ES on INNER_ES, fold-local INNER_SELECT-only alpha choices with smaller-alpha ties, OUTER-after-freeze, and 6-fit/1800-second/3-thread/1.5-GiB limits. Config-only status: **PASS, provisional**; no training clearance is implied until source review.

Official CatBoost documentation checked for the planned API contract:

- [Python `CatBoostClassifier.fit`](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_fit): `eval_set` is used for overfitting detection and best-iteration selection; `early_stopping_rounds` defines the stopping window; object weights default to 1 when no `sample_weight` is provided.
- [CatBoost common training parameters](https://catboost.ai/docs/en/references/training-parameters/common): `eval_metric` is the metric for overfitting detection and best-model selection, with parameter syntax supported.
- [Multiclass objectives and metrics](https://catboost.ai/docs/en/concepts/loss-functions-multiclassification): `Accuracy` supports `use_weights`, where `false` ignores object/group weights.
- [CatBoost input settings](https://catboost.ai/docs/en/references/training-parameters/input): `nan_mode=Min` is supported; missing values are treated as below finite values and candidate splits separating missing from non-missing are considered.

Code remains unavailable at this update; I still need to verify data-use sequencing, exact matrix/class order, writes, and per-fit resource checks before any fit.

## Update — first runner code review (2026-11-04 14:50 UTC)

Reviewed `rounds/round_002/code/run_round002.py` at SHA-256 `25907B09A7CB864C8ABAA1263752744162D137D93BDED1D5F3DA6F1ADB1E82E0`. **Pre-training verdict on this revision: BLOCKED.** The runner's `input_load()` retains original `FIT`/`INNER`/`OUTER` roles, but `create_split()` only saves a separate ES/SELECT roster and does not change `d["roles"]`. The two fit functions then derive their SELECT indices by querying `d["roles"] == "INNER_SELECT"`, yielding empty arrays. This would save empty SELECT probability files and later divide by zero when choosing alpha. I asked the execution owner to pass the actual split selection indices to both fit functions, assert nonempty split sizes and exact roster alignment, then send the corrected source hash for a new review. No fit has been authorized or run on this revision.

I also flagged that the 30-minute computation guard currently appears only before candidate fits, not before every fit. The code must guard each baseline and candidate fit against the deadline. Workspace-contained CatBoost `train_dir`, temp/cache, input checks, output role separation, feature order checks, and alpha-before-OUTER sequence otherwise appear in the reviewed revision; I will re-check them after the patch.

## Update — corrected runner review and pre-training clearance (2026-11-04 15:00 UTC)

Reviewed the corrected source/config pair before production training:

- Runner: `rounds/round_002/code/run_round002.py`, SHA-256 `92434B512DB78551E2218DE4C266E5B2569320129B99EF1480EFE05FDA23B4D4`.
- Config: `rounds/round_002/configs/experiment.json`, SHA-256 `F7240E3EB5ADB8BC130979B7AA891762EF840993B7E6CCF39AAE8E52C85CB214`.

Pre-training verdict: **PASS** for this exact pair. The prior empty SELECT-index bug is corrected by explicitly passing the split indices; each fold replays and checks ordered ID hashes and ID+label hashes for both ES and SELECT, verifies both are nonempty and disjoint, verifies their union equals the original INNER IDs, and checks no intersection with FIT/OUTER. The original role vector is left unchanged.

The final code preserves the required sequence: same-FIT seed42 `sqrt_macro` refit and FIT-derived normalized sqrt weights; macro-F1-only ES on INNER_ES; CatBoost fitted on FIT only and unweighted Accuracy ES on INNER_ES; both models' SELECT probabilities loaded only for per-fold alpha selection; alpha JSON written and hashed before any OUTER inference; one OUTER scoring pass after freeze. Fit count and RAM checks run before each fit, and threads are fixed at three. CatBoost `train_dir`, temp and bytecode paths are inside the work root. The launch manifest snapshots and records the root NEXT_SESSION hash but no longer includes that mutable handoff document in the immutable-source comparison.

Independent fixed-development-input check: all three source NPZ files matched the configured SHA-256; each matrix reported 5,897×304, and every fold's ordered feature-name SHA-256 matched `905728e72aaad6496e57a8e82f242b86f119be86b05a565f7773cc465ee68590`. The class order matches the exp01 evaluation contract. This read was limited to the existing development X304 feature artifacts; no holdout individual rows or raw data were read.

This clearance does not certify any runtime result. It assumes the manager checks at launch that no other fit is active and free RAM is at least 1.5 GiB; execution must retain the 30-minute compute and 15:10 UTC manager stop limits. Frozen code/config must remain unchanged during execution. Result/reload and saved-probability checks remain pending.

## Runtime attempt 1 — CatBoost API failure (2026-11-04 15:01:43–15:02:06 UTC)

The captured runner manifest reports exit code 1 and `TypeError: CatBoostClassifier.__init__() got an unexpected keyword argument 'feature_names'`. The execution wrapper receipt has a separate exit-code capture gap; keep that wrapper field unknown rather than replacing it with 1 or 0. `execution.jsonl` records exactly one completed production fit: fold0 seed42 `sqrt_macro`, 23.1284587 seconds, 3 threads, 3,872,817,152 bytes available before fitting, saved-model reload deltas 0 for both INNER_ES and INNER_SELECT, model SHA-256 `1ca092222b1fd344bd9d72e19706719dd46b4b0e1f7ffbbca1b1e11cdec5c012`. CatBoost failed in constructor before `.fit`, so candidate-fit count is zero. No OUTER prediction was made. The split manifest was saved before fitting; its SHA-256 was `9e4e791199f7a29604adfe10ca3df74a4761faa94891945f9604f6b96b15dce5`.

The manager approved a single API correction using `catboost.Pool` feature names and continuation without refitting the fold0 baseline. The continuation is a new source file; the attempt1 runner, launch manifest/log, baseline model, and probability artifacts remain evidence. I will independently review the resume code and saved fold0 artifacts before continuation.

## Attempt1 fold0 baseline independent artifact verification and resume clearance (2026-11-04 15:10 UTC)

I independently read only the saved fold0 baseline outputs, the development-only split roster, and fixed development fold0 NPZ. For both `INNER_ES` (393) and `INNER_SELECT` (394), the NPZ fold/role, ordered IDs and labels matched the split roster exactly; probabilities were finite and row sums differed from 1 by at most `3.33e-16`; stored predictions equaled probability argmax; reloaded baseline model probabilities matched the saved arrays exactly (`max_abs_delta=0.0` for both roles). Probability artifact SHA-256 values were `a3b53cad3d9378376144ef88f384b3ecd046f920d4664983c4c69ccf5f74e769` (ES) and `14cd19c245dd5b070f06dbfcb3aeee4101976c5e4940e0411fc75622c00a42b3` (SELECT). Attempt1 manifest confirms the input artifact hash equals the frozen config's fold0 hash and the reviewed runner hash; the execution log shows one successful FIT and the CatBoost constructor error before any candidate fit. The wrapper receipt exit code remains unknown; preserve this.

The incremental resume runner review passed at SHA-256 `355F05E552FD994B752C26E504AECA94ABF8EB7906DA459282B4D09141EFC83E`; config remains `F7240E3EB5ADB8BC130979B7AA891762EF840993B7E6CCF39AAE8E52C85CB214`. It reuses fold0 baseline with manifest/model/split/probability/replay checks, counts that production fit toward six, fixes CatBoost feature names via `Pool`, and explicitly caps candidate prediction thread counts to three. Clearance is for the resumed computation only, under manager's 15:14 UTC deadline, RAM/concurrency guard, and original total compute/fit limits. The final report should distinguish one reused attempt1 fit plus five new fits; do not imply six new fits or manufacture an attempt1 wrapper exit code.

## Attempt2 failure and attempt3 API correction clearance (2026-11-04 15:12–15:16 UTC)

Attempt2 resumed the verified fold0 baseline without refitting it (`fit_reused` event with config/input/model and split hashes). The wrapper receipt records **exit code 1**. CatBoost raised before any training iteration because this installed version rejects `Accuracy:use_weights=false` when no non-default object weights exist. The attempt2 log contains one candidate `fit_started` event, no `fit_completed` event, and no candidate model/probability, alpha, OUTER, or result artifact. This is an API configuration failure; do not count it as a successful fit or as a candidate evaluation. Preserve its logs and exit code.

The manager then authorized the syntax-only correction from `Accuracy:use_weights=false` to `Accuracy`, retaining `sample_weight=none`, no training/evaluation object weights, and the same unweighted Accuracy selection semantics. Config carries a note explaining the API behavior and `run_round002_resume.py` checks that the only attempt1-to-current config difference is this metric syntax/note. Independent pre-resume clearance: **PASS** for runner SHA `B8113BEA3887402FB5703C79B29136D5036DF73B68A1CCAAF1503016CF28DEED` and config SHA `04993014836B851BF6B7B933287E16FCD21B9ECBC232BBF6936FC2655E115C94`. This approval permits the remaining five fits only, with the previously validated fold0 model reused; cumulative totals remain at most six successful production models and 30 minutes, with a 15:25 UTC hard stop. No independent/official score or next-session handoff is authorized by this review.

## Final artifact review (2026-11-04)

Independent recomputation from the saved development OUTER probability NPZs verified 5,897 unique rows across three folds, aligned row IDs and labels for baseline/candidate/blend, finite normalized probabilities, and saved predictions equal to probability argmax. Recomputed pooled metrics, confusion matrices and class recalls matched `artifacts/result.json`. Replaying INNER_SELECT saved probabilities reproduced the stored fold-local alpha choices `[1.0, 0.0, 0.5]`; stored blend probabilities matched the alpha-weighted components exactly (maximum absolute delta 0). No model refit was performed.

- Baseline LightGBM: 3,476/5,897 correct; micro-F1 0.5894523; macro-F1 0.5192103.
- CatBoost candidate: 3,424/5,897 correct; micro-F1 0.5806342; macro-F1 0.4689224; −52 correct and macro-F1 delta −0.0502879 versus this baseline.
- Fold-local blend: 3,474/5,897 correct; micro-F1 0.5891131; macro-F1 0.5061678; −2 correct. Trap recall delta: candidate −0.0958084, blend −0.0371257; the blend exceeds the planned 0.03 subgroup-drop limit.
- Reported vessel-bootstrap 95% development OUTER intervals: candidate micro-F1 delta [−0.0167924, −0.0006783]; blend [−0.0057656, 0.0050873]. Reviewer did not independently recompute bootstrap resampling.

Attempt 3 completed with exit code 0 and elapsed 270.172 s; it trained five new fits and reused the already verified fold-0 baseline fit from attempt 1, for six successful models counted toward the round cap. Attempt 1 launcher exit remains unavailable (Python manifest records candidate constructor failure; baseline fit succeeded); attempt 2 exit code was 1 and failed before CatBoost training iteration. Do not replace either recorded status with a fabricated success.

Protocol review: PASS for the checked split/alpha/prediction artifact invariants. Overall review: CONDITIONAL because the comparison is development-only and its OUTER split was previously exposed. Adoption: REJECT; metrics do not meet adoption guardrails. No holdout individual rows or raw data were read; source repository was not modified. See `review.json` for structured evidence and limitations.
