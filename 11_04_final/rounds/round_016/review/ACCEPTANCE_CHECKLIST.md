# Round016 independent acceptance checklist

Prepared before source freeze from `AGENTS.md`, `rounds/round_016/ROUND_PLAN.md`, `rounds/round_016/manager/incoming_NEXT_SESSION.md`, and Round015 source/final reviews, saved audits, and receipts. Static review only; no candidate modes or model execution.

## Provenance and freeze

- [ ] Candidate manifest, author write-stop ACK, and `round016_approved_sources.v1` map identify the same exact set of files under `rounds/round_016/code/`; all digests are lowercase or uppercase 64-character SHA-256 values and match direct reviewer hashes.
- [ ] Runner-consumed map schema, round identifier, and `sha256` mapping match the established `round015_approved_sources.v1` convention and are confirmed with the author before freeze.
- [ ] Directly hash every source, candidate manifest, and ACK after write-stop. Record method, UTC time, byte size, and digest in the source review and approved map. Do not approve an unfrozen or internally inconsistent set.
- [ ] Saved audit is read-only against Round015 sources, result JSON, receipts, maps, and logs. No receipt/map/result rewrite or historical “completed” repair.
- [ ] Verify fixed input path, byte size, and SHA-256 from the incoming plan. For `.pt` inputs, use size and streaming SHA-256 only; never deserialize or otherwise inspect their contents.
- [ ] For each historical receipt, compare approval-map digest, direct live-source hashes, source-snapshot hashes and snapshot postchecks against the frozen source set. Reject missing, extra, duplicate, path-escaping, or mismatched entries.

## JSON and consumer boundary

- [ ] Use base Python with `-B -S` and stdlib only for JSON reading. Reject duplicate object keys with `object_pairs_hook`; reject `NaN`/`Infinity` with `parse_constant`; reject missing required fields and wrong types instead of truthy coercion.
- [ ] Preserve the valid empty key at `upstream_model.module_training_before_after[""]`; it denotes the root module. Do not delete, rename, or rewrite it in the original JSON.
- [ ] Project only explicit, fixed, non-empty summary keys for PowerShell. Avoid carrying arbitrary JSON keys into a PowerShell 5.1 object/property namespace, including case-insensitive key collisions.
- [ ] Bound accepted file sizes and resolve inputs against the expected workspace paths before reading. Keep report booleans for saved numeric checks, provenance checks, and historical wrapper gates distinct.

## Expected historical state and numeric saved checks

- [ ] Saved Round015 smoke and mock receipts remain `completed=true`; synthetic wrapper receipt remains `completed=false` even though its child has exit code 0 and result JSON says `status=completed`.
- [ ] Preserve `historical_round015_wrapper_gate=false` and `historical_round010_gate=false`, independently from any new parser, current-source, provenance, or saved-numeric pass.
- [ ] Require six recorded result comparisons to meet `max_abs_logit_difference <= 1e-5` and `max_abs_probability_difference <= 1e-6`; verify finite probabilities, `[0,1]` range, row-sum error `<=1e-6`, and argmax equality.
- [ ] Check the recorded call counts against both their expected limits and observed counts: checkpoint load 1, context fit 1, `predict_proba` 1, full forward 4, head evaluation 12, backward 4.
- [ ] Check saved assertions for gradients, inactive rows, fixed bias, head-only reload, upstream unchanged, hooks restored, and the recorded config/seed/shapes/permutation. These are claims parsed from the saved JSON, not tensor re-computation.
- [ ] Report `numeric_saved_checks_pass`, `saved_provenance_audit_pass`, `current_round015_source_matches`, `historical_round015_wrapper_gate=false`, and `historical_round010_gate=false` as distinct outcomes. Do not infer F1, full-estimator reload, or checkpoint correctness from these checks.

## Process-control source review

- [ ] Source behavior distinguishes observed process exit, wait completion, actual deadline reached, memory stop, kill attempt, stream drain, and owned-tree cleanup. A single `WaitForExit(1) == false` must not set `timed_out` unless the actual configured deadline was reached.
- [ ] Preserve an exit already observed before the deadline; an actual timeout child may have a nonzero OS exit code. Do not demand exit 0 for a timed-out child.
- [ ] Normal exit with an unexpected owned descendant is a failure. Confirm cleanup applies only to processes owned by this run.
- [ ] Mock fixtures cover normal completion, actual time limit, memory stop, empty root key, duplicate keys, non-finite constants, missing fields, wrong types, and a falsely claimed completed receipt; false historical gates remain false.
- [ ] Do not run candidate modes as reviewer. Manager owns the single planned smoke, mock, and saved-audit execution sequence and execution budget.

## Evidence and limits

- [ ] Record source approval separately from later execution/final review. Final review must inspect manager receipts and the final source/map/snapshot hashes independently.
- [ ] No Torch/NumPy/TabICL imports, checkpoint access, `.pt` deserialization, model re-run, actual-data access, F1 computation, external transfer, installation, or hardware claim.
- [ ] Current host evidence available at review preparation: manager startup recorded 5.6724 GiB free RAM at `2026-11-04T21:51:19.3833330Z`, no other Python process, estimated text/hash peak 200 MiB. This is a point-in-time observation and estimate, not proof of later availability or execution peak.

