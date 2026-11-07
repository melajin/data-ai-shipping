# Round011 independent audit

Status: **PASSED**, 2026-11-05. Design/code review, independent result recomputation, and fixed raw-window sample checks completed. No blocking experiment defect found.

Reviewer role requested: `sol_review`, GPT-6.1 Sol, high. Local `.codex/agents/sol_review.toml` matches that configuration. This is a configuration receipt, not independent proof of the provider's executing model.

## Contract checks to reproduce

- Both current and reference features use only trailing `[t-6,t]` observations. A reference end must be in inclusive `[t-720,t-24]`; its window therefore cannot overlap the current window. No accident labels enter feature/reference selection.
- Valid window: at least four valid observations, three valid `bbox_m/len_m` ratios with `len_m>=1`, and two valid center pairs exactly one hour apart. Negative lengths and nonfinite coordinates are invalid; no interpolation over gaps.
- Each context selects one reference from each of the latest ten qualifying epoch days. Within-day order is T: circular hour distance, observation-count distance, earliest timestamp; L: location distance, observation-count distance, earliest timestamp; TL: hour, location, observation count, timestamp. References are from the same vessel; insufficient days remain unknown.
- Compute midrank using exact original float equality and ten references. Evaluate all ten scores on one common per-vessel time universe (at least 100 timestamps). Accident-relative times are confined to evaluation.
- Recompute fractional top-1 ties, exact top-10 boundary-tie selection probability, and chance using the same candidates. No candidate inside accident ±6h is a failure for an otherwise evaluable vessel, not an exclusion.
- Tier0-1 denominators are 60 total events and all-events denominators are 100. Preserve unavailable events in conservative rates. Bootstrap resamples vessels with multiplicity and all their events together; four predefined differences, B=4000, seed=11052026, 98.75% intervals. Improvement requires lower bound >0 and >=30 common evaluable events.
- Reporting must distinguish accident-associated behavior from observed physical drift, observational time-center displacement from actual speed, and reused-development exploratory intervals from confirmation.

## Execution boundary

No concurrent dataset computation. Full audit waits for the parent output-ready signal. Before reading output/raw data, check available RAM at the execution boundary; expected reviewer peak <=256MiB and required available RAM >=768MiB. Stream CSV and raw parquet, process one vessel at a time, retain only bounded audit samples. No polling or process termination.

## Findings

No blocking protocol inconsistency found in the initial text review. The independent data audit subsequently passed as detailed below.

Pre-run static review of `run_experiment.py`: no blocking issue found. Checked BOM-safe integer event parsing, duplicate event and vessel/hour rejection, trailing-window boundary pairs, inclusive past-only references, context ordering, exact-float percentiles, shared finite-score candidate universe, no-near failures, exact tie metrics, conservative denominators, and vessel-resampling multiplicity. Input labels are confined to target-vessel filtering and evaluation; accident-relative time is not used in features or reference selection. Empty-primary bootstrap omits some fixed bootstrap metadata, a nonblocking receipt detail because PROTOCOL.md states the settings.

Independent `audit_round011.py --self-test` passed synthetic exact tie/no-hit/small-universe ranking, circular hour, inclusive past bounds, latest ten distinct days, and zero-movement joint-rank caveat. These are code checks, not real-data or hardware evidence. The independent audit imports no experiment code; it expands repeated bootstrap vessel draws into event indices, rather than reusing the experiment's cluster sums/counts calculation.

Conceptual cross-check received from Astra via parent (not a separate data verification): H2 is a product of relative ranks. It can be positive even when current and every reference M are zero, because the midrank of tied zeros is 0.5. A positive joint score therefore does not establish ongoing motion. TL's requirement for ten historical days within 10km can exclude newly visited or displaced locations. Preserve M, near-event unknown reasons, and unconditional 60/100-event rates; do not introduce a post-result movement gate or widen matching conditions.

## Independent execution evidence

`python -B -X utf8 audit_round011.py --sequential-ready` exited 0 after the parent confirmed the experiment exited and its lock was removed. [audit.json](audit.json) records **1,603,464** successful check evaluations and no failures; [audit_stdout.log](audit_stdout.log) records the result and stderr is empty. The audit imports no experiment implementation.

- All **99,677** timestamp rows: quality counts, raw score, common-candidate flag, timestamp rendering; all **299,031** context receipts: past-only range, same vessel, quality, count/hour/location conditions, unique epoch days; **146,790** available context score triples: exact-float midrank recomputation. Unknown scores remained unknown.
- **3,090** fixed sampled context selections: latest ten qualifying days and within-day ordering independently recomputed, including insufficient-history cases. This samples selection optimality; it does not claim every candidate's selected minimum was recomputed.
- All **1,000** event/rule rows: input identity, shared candidates, availability, near-event coverage, fractional top-1, exact-combination top-10 and chance. **610** evaluable rows and **390** unknown rows preserve the intended conservative denominators. All **20** profile/rule summaries matched.
- All four predefined contrasts and **4,000** shared bootstrap draws independently reproduced by expanding drawn vessels to event indices, retaining repeated draws and every event for each vessel. CIs and improvement flags matched.
- Raw parquet was streamed through **822,000** rows with only **3,722** needed rows retained. All **730** fixed sampled current/reference windows matched observation/validity/pair counts, lin_raw and A means, and M. Movement comparison uses a 2e-6m absolute tolerance for independent trigonometric roundoff; no coordinates were interpolated or disconnected pairs joined. Raw/event/output/code/protocol SHA256 receipts matched.

Fresh available RAM was **3028.8MiB** before the output audit and **3022.8MiB** before raw checks, versus an expected audit peak <=256MiB and required available 768MiB. Process snapshots and timestamps are in audit.json. These are availability observations and an allocation estimate, not a high-frequency measurement of peak RSS. No concurrent dataset job, model training, 2025-data use, or hardware experiment was performed by the reviewer.

## Auditor arithmetic correction and preserved first pass

The first audit failed 12 of 3,090 sampled reference-choice checks, all in context L. Its scalar haversine expression converted coordinate differences to radians. The frozen experiment converts each coordinate to radians before subtracting. These are algebraically identical but produce tiny different floats, which can change a nearest-reference tie and the following row-count/time ordering. For vessel 36101547 at t=493666, the experiment gives refs 493476 and 493475 the identical distance 32.93099382701421m and selects the better row-count match; the initial auditor gave 32.93099382703342m and 32.93099382659048m and selected the latter.

The independent diagnostic recomputed all 12 cases and **2,181** eligible candidate pairs. Maximum first-expression versus NumPy distance difference was **2.2120332232589135e-9m**. Converting coordinates before subtraction in the independent scalar formula gave maximum difference **0m** for those pairs; independent NumPy calculations reproduced all 12 stored selections. The protocol fixes original-float percentile equality but does not choose a distinct haversine evaluation order. Only the auditor's arithmetic order was corrected; no protocol, experiment code, selected reference, score, or result was changed. No substantive non-tied selection failure was waived.

The first receipt/logs remain in [audit_firstpass.json](audit_firstpass.json), audit_firstpass_stdout.log and audit_firstpass_stderr.log. [audit_distance_diagnostics.json](audit_distance_diagnostics.json) records each case's distances, row-count/hour differences, choices and receipt/script hashes. The corrected complete audit then passed every check.

## Interpretation boundaries

Tier0-1 has **35/60** evaluable events from **31** vessels; **12** of those events have no common candidate within ±6h and remain failures. All100 has **61/100** evaluable events. TL lin top-1 expected rate is **0.3975%** conditionally and **0.2319%** over all60; the same-candidate chance is **0.8010%**. These are fractional expectations under ties, not counts of actual successful alerts. None of the four fixed comparisons supports exploratory improvement.

The H2 TL-minus-T empirical bootstrap CI is [0,0] because the observed event differences are all zero. This does not establish a population null, physical drift absence, or equality under other candidate universes. Reused-development selection, provisional accident linkage, overlapping windows, unknown local timezone and restricted historical coverage remain limitations. Technical calculation checks do not verify learner understanding or real-device behavior.
