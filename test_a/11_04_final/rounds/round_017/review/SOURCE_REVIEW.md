# Round017 independent source review

## Verdict

**Approved for the planned model-zero smoke, mock, and saved-audit modes under this frozen source set.** This is a static source approval only. It does not establish runtime behavior or approve model execution.

The author write-stop ACK is timestamped `2026-11-04T22:32:29.7994582Z`. My direct SHA-256 hashes after that freeze match the candidate manifest and ACK. The exact two-file source set, round/schema identifiers, candidate-manifest hash, ACK hash, and file digests agree.

| Frozen source | Bytes | Direct SHA-256 | Manifest/ACK match |
|---|---:|---|---|
| `rounds/round_017/code/saved_m4_audit.py` | 49,394 | `8ca9be725be25a6d4e80d43a17a82341ef78a94ea33115ff8d3bfef10ce4b227` | yes |
| `rounds/round_017/code/run_saved_m4_audit.ps1` | 29,662 | `fba54fd84873430039348f8d15a6660655126df7bc19ed2bdde8f4c71c7de720` | yes |

Candidate manifest SHA-256: `aff522305a7a1d8b0215caa598eaecbe3fc4596060c7afa335ee8fb5c1a29449`.

Author ACK SHA-256: `fbde4e6b3426ee3e399a82aa35e1108fc9ef388d73e4eab4c7c7f8ee4269652b`.

The runner-compatible map records these exact two paths and binds both the direct candidate-manifest and ACK hashes. The author ACK records `write_freeze=true`, no author runs, and requested Luna/xhigh/fork none settings; model identity is not independently attested by this review.

## Static findings supporting approval

- `Convert-CimCreationUtc` distinguishes native `DateTime` from DMTF strings, normalizes both to UTC at a shared millisecond precision, and rejects null, blank, or unsupported values. Root identity uses the same representation. Tree/residual checks bind PIDs to creation times, reject a missing parent identity during scan, and do not convert identity-query errors into a clear tree.
- `Get-ProcessClassification` is used by both probe and auditor paths. It keeps the monotonic `Stopwatch` deadline fact separate from wait return, observed exit time, OS exit time/code, and memory stop. Normal completion requires exit observation before the deadline; an after-deadline or boundary case is not converted to normal completion. The mock writes counterexamples from this PowerShell production function for deadline-before, deadline-after, deadline-boundary, and memory-stop cases, which the Python mock validates.
- The wrapper creates its exclusive execution claim before launching probes or the auditor. Post-claim wrapper errors preserve a failure receipt. The single smoke budget covers all four probes and the auditor with reserved cleanup/drain/finalization time; mock and audit each have their own finite 30-second budget.
- The Python auditor uses only the standard library, strict bounded JSON parsing, exact source/map/snapshot checks, and read-only saved-result assertions. The `.pt` files are handled as opaque bytes for size and streaming SHA-256 only. Historical Round015 wrapper failure and Round010 gate failure remain distinct from new saved-numeric and provenance outcomes.

## Limits

I inspected source and frozen metadata only. I did not run the PowerShell parser, Python AST check, any candidate mode, or a runtime process probe; the author reports parser/AST-only checks in the ACK. I did not import the auditor or Torch/NumPy/TabICL, read or hash a checkpoint, deserialize `.pt`, recompute tensors, read project data, calculate F1, or test hardware. Runtime deadlines, process identity/tree cleanup, stream draining, wrapper receipts, and saved JSON validation remain unverified until the manager's one planned same-map smoke → mock → audit sequence. No model execution is approved by this source review.

The source approval applies only to these exact frozen hashes and the planned smoke/mock/audit sequence. Any source or map change requires a new freeze and review.
