# Round024 supervised run and outcome checklist

This is an operator aid for the manager's single approved round024 attempt. It does not authorize a run by itself. Training and numeric verification remain manager-owned; all calculations must go through `manager/launch.py` using the frozen source snapshot.

## Current admission checkpoint

- Source approval and 22-file freeze succeeded. The manager must confirm `snapshot_s1_gate/freeze.json` and recheck its approved hashes at each launch; any mismatch aborts before a child starts.
- Manager's most recent preflight at `2026-11-05 03:11:21 UTC`: available RAM `1.3446 GiB`, independent Python jobs `0`. The round entry requirement is `1.5 GiB`, so no claim or child launch was started. Work on independent documentation was used while admission was below threshold.
- Recheck RAM and Python-job count once immediately before each supervised launch. Do not poll repeatedly. The launcher entry gate is `1.5 GiB`; the gate code's per-fit stage guard is `1.0 GiB`. All stages require no independent Python job, one thread, below-normal priority, a `0.75 GiB` owned-process RSS cap, and a `0.5 GiB` emergency free-RAM floor.

## Fixed execution order and budgets

1. **Gate training, at most 900 seconds, one attempt.** Launch `rounds/round_024/code/run_gate.py -- --run-gate` as stage `s1_gate`. The preregistered scope is FIT3144, internal 4-fold, seed42, baseline and candidate per fold (8 fits). No retry, search, raw rescan, full 3-fold, or S2 training.
2. **Saved-result consistency check, at most 180 seconds.** Only after stage 1 exits zero and records exactly 8 completed fits, launch `rounds/round_024/review/verify_gate_result.py rounds/round_024/artifacts/gate` as a separate stage.
3. **Model reload and reinference, at most 180 seconds.** Only after stage 2 passes, launch `rounds/round_024/review/reinfer_saved.py rounds/round_024/artifacts/gate` as a separate stage.
4. **Supplemental paired diagnostics, at most 180 seconds.** Only after stages 2 and 3 pass, launch `rounds/round_024/code_author/supplement_metrics.py rounds/round_024/artifacts/gate` as a separate stage.

Use the approved round024 Python environment and manager launcher for every stage. The runtime contract caps aggregate owned computation at 1,800 seconds and retains the `2026-11-05T03:36:56.500389Z` compute cutoff and `03:41:56.500389Z` manager cutoff. Launcher receipts are the record of actual wall time and sampled memory. Do not start a stage whose remaining aggregate/time budget is insufficient.

## Branch after gate training

### Complete eight-fit gate

- Require `gate_result.json`, `fit_progress.json`, exit code 0, status `complete`, `fit_attempts_started == 8`, `fits_completed == 8`, and eight unique fold/variant records. Do not infer completion from only a prediction file or a score.
- Have the manager run `verify_gate_result.py`. Continue only if its report says `status: pass` and `error_count: 0`.
- Have the manager then run `reinfer_saved.py`. Continue only if its report says `status: pass`, all eight fold/variant models were reloaded, maximum absolute probability difference is at most `1e-7`, and all argmax predictions match exactly.
- After both independent checks pass, the manager may run `supplement_metrics.py` and inspect its saved paired gain/loss/net, class transitions, observation-day bins, and seeded within-roster bootstrap.
- Apply the frozen numeric diagnostic gate as an AND: candidate correct count `>= 1,833` **and** candidate minus matched-baseline correct count `>= 16`. Report the fixed reference `1,817` separately. Do not treat the 1,817 reference as the matched baseline or as an independently evaluated result.
- If the numeric gate passes, the next action is only to plan a bounded proxy extension. It does not authorize the full original S1, a full 3-fold run, S2, OUTER evaluation, or a claim of independent/official performance.
- If it fails, record the failure as this FIT diagnostic result, preserve all artifacts, and prepare only the next-round S2 input/nested-grouped-cross-fit contract. Do not train S2 in round024.

### Partial, interrupted, or resource-stopped run

- Record the precise fit attempts started/completed, exit code, stop reason, stage receipt, and last progress record. Preserve partial artifacts.
- Do not calculate or report the result as a completed 4-fold paired comparison. Do not run the completed-result verifier or supplement on a partial gate.
- Do not retry the same claim or run the training command again. The claim/receipt is the one-attempt guard. Do not interpret a memory/deadline stop as model failure or gate failure.
- Leave earlier results unchanged: round022's two prior fits remain historical and round023's zero-fit attempt remains zero. Neither fills in the round024 gate.

### Source, output-verifier, or reinference failure

- If frozen-source recheck fails, stop before child launch; record the specific changed path and ask for a fresh independent source review/approval. Never bypass the snapshot check.
- If `verify_gate_result.py` fails, preserve its error report, stop the downstream sequence, and do not run reinference or supplemental diagnostics against a rejected result.
- If result verification passes but `reinfer_saved.py` fails, preserve both reports, stop before supplement, and do not make a performance decision from the saved score alone.
- These failures are integrity/verification outcomes, not evidence that the candidate model did or did not improve.

## Reporting boundary

Keep the following values separate in every report: paired FIT-internal CV candidate and baseline counts; the fixed 1,817 reference; the two preregistered numeric thresholds; the existing repeatedly exposed OUTER history; and any official submission score (currently none for this run). The 3,144-row FIT diagnostic is not an independent-data result. Do not claim the `0.7` goal, generalization, or official rank from this gate. Report configured RAM estimates separately from measured launcher RSS/free-RAM samples. Hardware behavior was not tested.

Learning review should ask: Was the stop caused by a resource guard or by model behavior? Which saved evidence validates the row partition, fold-local feature boundary, class order, model persistence, and paired prediction agreement? Why does passing this precheck authorize only a bounded next planning step rather than a broader evaluation?
