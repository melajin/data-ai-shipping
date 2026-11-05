# Round025 — fixed S1 gate after pre-admission resource deferral

Round024 was deferred before launch: its recorded post-independent-work check was 1.3286 GiB available RAM against the unchanged 1.5 GiB entry threshold, with no other Python process and 0 fits started. This was not an owned-RSS stop or a model result. Round025 preserves the same fixed mathematical comparison: FIT3144, internal stratified 4-fold CV, seed42, fold-local T5 from CV-train labels, S1 train-only profiles with FIT-query self exclusion, identical feature order/model settings, and the AND gate candidate>=1833 and candidate-matched-baseline>=16.

## Resource improvement evidence required

Round025 preparation itself records a fresh one-shot RAM snapshot and requires at least 1.5 GiB available with no other Python process (excluding only a direct Windows Python bootstrap parent whose script argv exactly matches this invocation). Preparation-time admission does not authorize training. Immediately before any future launch, the manager must record another qualifying snapshot. If the same experiment is considered after Round024's pre-admission shortfall, the manager must document concrete changed resource evidence or a reviewed execution-path improvement; elapsed time alone is not evidence. Do not lower the 1.5 GiB entry threshold.

The unchanged resource limits are one process/thread, OMP/OpenBLAS/MKL/NumExpr threads=1, BELOW_NORMAL_PRIORITY_CLASS, 1.0 GiB per-stage RAM guard, 0.5 GiB expected owned peak, 0.75 GiB owned RSS cap, and 0.5 GiB emergency available-RAM floor. The finite budget is at most 8 fits in one launch of at most 900 seconds, 1,800 total compute seconds, and zero retries. No full 3-fold, S2, tuning, or raw rescan.

The Round024 approval and its 22-source snapshot freeze are checked exactly before copying. Approval/freeze files are not copied or inherited: a separate Luna reviewer must inspect Round025 sources and issue a fresh approval before any freeze or training. No Round025 approval, freeze, launch, or result is created by this preparation tool.

Technical goal: complete and independently verify the fixed 8-fit FIT gate under the resource limits. Learning goal: distinguish pre-admission resource shortage from an in-run memory stop and explain how sequential lifetime management affects peak RSS.
