# Round015 independent source review

## Verdict and scope

**Static source review approves the exact frozen Round015 process-control smoke, standard-library mock, and bounded synthetic M4 run under the fresh approval map.** This is source-level approval only. The author ACK at `2026-11-04T21:31:13.8837060+00:00` declares write-stop and no author runs. It reports parser-only PowerShell and AST-only Python checks; I did not rerun them.

## Freeze and direct hashes

Candidate manifest SHA-256: `0c580bc73781e50f778cfe95f8a41b092ebe55707f141b8127de5562cf2096dc`. Freeze ACK SHA-256: `2f8316ddd0d6d909bd01069bd931344020761971b3a86c6c24e43339e7686058`. I independently hashed all three Round015 sources and confirmed exact matches against both manifest and ACK. The Round014 originals independently match their prior approved-source map; reversing only `round_015`/`round015`/`Round015` to the corresponding Round014 spellings reproduces each original source byte-for-byte.

| Frozen source | Direct SHA-256 |
|---|---|
| `rounds/round_015/code/m4_synthetic.py` | `ac6a12e44bc82fa8a20f2be5a2fd404851e5fd7900d99c5c75a7269069e3dfa0` |
| `rounds/round_015/code/test_m4_mock.py` | `5d65af83347d68db27525e15f0e94270d25b27f3e7efc8ed71a2d6618d161847` |
| `rounds/round_015/code/run_m4.ps1` | `678fe8462575375c4bb36e3c474a66629eb46e23963e02e230c97dc90dc31aa4` |

The runner-compatible map is `approved_sources.json` (schema `round015_approved_sources.v1`, round `round_015`, exactly these three paths).

## Source-grounded findings

- Smoke is limited to two standard-library process-control children checking expected exits 0 and 7 plus stdout/stderr capture and owned-process cleanup.
- The mock imports only the stdlib-oriented source helpers and checks explicit class permutation direction, target-only row copying, bounded call counts, and one-time merge behavior.
- Synthetic mode uses generated context with 16 rows by 8 features and target with 4 rows by 8 features. Target labels are created after the sole `predict_proba` and used only for the external head losses. The readout hooks retain target rows only; the upstream model is frozen and checked before/after; head evaluations, forwards, and backward calls are capped. Artifacts are head-only, and no project data, F1, or performance selection is in scope.
- The runner verifies the exact fresh map and source snapshots, requires same-map smoke before mock and same-map mock before synthetic, disallows duplicate run receipts, and applies configured RAM/start-stop and timeout gates for synthetic execution.

## Limits and remaining unknowns

I did not execute tests, imports, PowerShell runner modes, checkpoint reads/hashes/loads, model code, project data, or numerical evaluation. No runtime success, checkpoint integrity, tensor result, measured RAM, model performance/F1, or hardware behavior is established here. Synthetic execution remains conditional on the manager's current prelaunch RAM/time gate and exact-map live precheck.