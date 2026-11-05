# Round021 baseline source review

**Decision: GO for `fit_baseline` only.** This approves the fixed 12-feature SELECT-only baseline fit/save/reload stage. It does not approve spatial extraction, candidate fitting, OUTER probability access, historical prediction-row access, or performance evaluation.

Reviewed 2026-11-05 00:16 UTC. The hash-bound source approval is `baseline_approved_sources.json`.

## Evidence and checks

- Runner `run_performance.py` SHA256: `1329B5EE7152D04310BF15D5F37CEE05098B11AEC90AD8118361035D413200DA`.
- Worker `fit_meta_worker.py` SHA256: `EACBB986FA8C11FA710C4BB31E0520308B6BC95D1A54A87945CC0BFB4CA52ED6`.
- Config SHA256: `07F4B526D6EFDCF6E2E0CECF80B9D27C7AAC09BF3F56147951A48322685A5245`.
- Launcher SHA256: `4A221F280C07641BADF4BCC1E03FBCAFC2DEB59C10BE9A0F4A80E925C33D6171`.
- Frozen plan SHA256: `F52F64A5CB616F7E07EBD9060D8643E066FA78A9E3D04EF1B6146D6EDC1F070D`.
- The loader validates all 787 fold-local TabICL INNER IDs, labels, and observation days, parses probabilities only for the 394 SELECT rows, then joins/reorders by vessel ID against the canonical round002 SELECT roster.
- Baseline inputs are the frozen 12 log-probability columns; StandardScaler and multinomial LogisticRegression settings match the plan. The stage performs exactly three sequential fits, saves each model, and compares a pre-save SELECT probability array against predictions from the reloaded model at absolute tolerance `1e-12`.
- The worker is a child process with a 120-second hard timeout, treats `ConvergenceWarning` as an error, and records the pre-save SELECT probabilities. The parent writes row-keyed raw SELECT probabilities with id/year/fold/role/model/p0–p3/y/observed_days.
- `--fit-baseline` calls the baseline-only function and exits after three successful reload checks. It does not call `load_outer_after_reload()`, `evaluate()`, the spatial reader, or the historical prediction-row reader. `--run` is disabled in this snapshot.
- Runner, worker, launcher ASTs and config JSON parsed successfully. No model fit or OUTER/historical-row read was performed by this reviewer.
- The manager reported the prior SELECT-only prepare completed with exit code 0 in 7.38 seconds, zero fits, and `outer_probability_values_loaded=false`. The old manifest was created under runner hash `998284...`; the manager will refresh/bind the current source snapshot before baseline execution.

## Scope notes

The source manifest hashes the frozen OUTER probability files, the historical prediction file, and the spatial parquet as provenance, but the baseline path does not parse their values. The prepare/alignment code reads OUTER role/label/day metadata from the archived development feature arrays; it does not load OUTER probability arrays or compute scores. This is recorded as a metadata limitation, not as a new blind evaluation.
