# Round018 independent source review

## Verdict

**Approved for the exact frozen source set and the planned model-zero smoke → mock → saved-audit sequence only.** This is static source approval. It does not establish runtime behavior or authorize model execution.

The author confirmed write freeze at `2026-11-04T22:42:30.4364246Z`, with `write_freeze=true` and `no_author_runs=true`. I directly hashed the two sources, candidate manifest, and freeze ACK after that confirmation. Their direct hashes match both metadata files. The runner-compatible approval map is `approved_sources.json` (SHA-256: `bc586a48880da1e7942db80e2f2b58b2d236bd62fce9580508abadc81328f587`).

| Frozen file | Bytes | Direct SHA-256 |
|---|---:|---|
| `rounds/round_018/code/saved_m4_audit.py` | 49,394 | `49cbf5785791d2c3b843ad095985162675d5a1b2dc3a5a324a9a4a2207048e7a` |
| `rounds/round_018/code/run_saved_m4_audit.ps1` | 29,663 | `acf4865ce46b1d12f506853c03f1d4f78a13deb8cc19b45ccdfdc1bfb8eb862a` |
| `rounds/round_018/code/candidate_sources.json` | 2,679 | `0364998b6194abb8f78c373d5bb33c456150423130c458181c2ec0288377b8ff` |
| `rounds/round_018/code/author_freeze_ack.json` | 1,760 | `45abf15ad745ab338cfaf3eba0ee8e3f5fc94caef92f641776aedece2afc2fbc` |

## Static findings

- The candidate manifest and ACK describe the same exact two-path source set. Direct source hashes match both files; the ACK's candidate-manifest hash matches the direct manifest hash.
- I normalized the candidate identifiers from `round_018` / `round018` back to `round_017` / `round017`, and changed the one PowerShell literal `claimed=$true` back to `claimed=true`. Both normalized files then matched their frozen Round017 sources exactly. No other source changes were found.
- The PowerShell Parser API reports zero parse errors. Its token scan finds no remaining bareword Identifier tokens `true`, `false`, or `null`; the receipt field at `run_saved_m4_audit.ps1:78` now uses `claimed=$true`. The prior writer defect was a runtime command interpretation issue that a syntax parse alone could not detect.
- The base-Python `ast.parse` check passed for `saved_m4_audit.py`. I did not import the module.
- The approval map binds the two direct hashes, the manifest hash, and the ACK hash to `round_018`, using the runner's current schema and source-key format.

## Limits and next scope

I did not run smoke, mock, or saved-audit mode. Process deadlines, receipts, exit observation, cleanup, stream draining, and saved-evidence validation remain unverified pending the manager's planned single same-map sequence. I did not import Torch, NumPy, or TabICL; read, hash, or deserialize a checkpoint; access project data or holdout; compute F1; or test hardware. No performance claim follows from this review.

Round018 remains limited to the model-zero gates. If every gate passes, prepare a separate Round019 plan for the already preselected M4-a synthetic full-estimator save/reload scope described in Round017's `NEXT_GATE_SCOPE.md`. That later scope needs its own resource check, frozen source set, approval, and execution gate; it is not approved by this review. M4-b selection, CE selection, real-data evaluation, F1, and hardware work remain outside the current scope.