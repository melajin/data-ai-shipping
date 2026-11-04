# Round 009 — pure mock gate review

**Decision:** `mock_01` passes. The approved `pair_01` source set and wrapper hashes are unchanged, and the receipt confirms the exact approved hash map. This mock verifies the ROW adapter's pure-Python slicing/reassembly/configuration/restoration contract only; it does not run PyTorch, TabICL, a model prediction, or project data.

## Saved evidence

- Manager pre-mock resource check: 4.5215 GiB available RAM, no other Python process; manager estimate 50 MiB for the pure mock (from the manager's contemporaneous evidence).
- Wrapper receipt `rounds/round_009/logs/mock_01/receipt.json`: status `completed`, exit 0, elapsed 0.532 s under the 30 s bound, `stop_reason=null`, 4.4251 GiB preflight RAM, 4.4158 GiB minimum observed RAM, sampled owned-tree peak 27,189,248 bytes, `owned_tree_remaining=[]`, `owned_tree_status=clear`, `uninspectable_tree_pids=[]`, and resource sampling complete.
- Standard output is exactly `round009 ROW adapter pure mock passed`; stderr is empty. The resource curve ends with no owned processes.
- Receipt `source_sha256` matches approved mock `1a134ff544b5c67efb813417322e3304317ccd4fc2136d85650ef36c72d86ee0`; `wrapper_sha256` matches approved wrapper `b8e5d7de47ba070ed9df52badb1002f1955d67798e679e240e295a05ba87a439`. Receipt's `approved_sources.sha256` equals the reviewer's manifest map. I independently hashed each copied round009/code `.py` snapshot and copied wrapper; all matched the manifest/receipt. The receipt also reports original and snapshot source hashes unchanged.
- Artifact hashes: receipt `0766ff34017a7bcfe6fa5535b19036ecbb9eee2a986637501082d3b0b138c026`; stdout `1c0108897694a73588326cd91bb7faee3dc7fecc8ab97d5058bb41c429b12cd8`; stderr `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

## Gate and limits

The wrapper's `pair_01` gate accepts this completed mock because its kind, exit code, stop state, process-tree state, unchanged-source flags, wrapper hash, and exact approved SHA map match. Manager has launched the single approved pair under the 180-second total bound (170 seconds compute + 10 seconds cleanup); this review does not inspect or claim its outcome. Mock success verifies only a small fake tensor contract. It does not establish runtime numerical equivalence, resource savings, F1, actual-data reproduction, or hardware behavior.

Requested reviewer setting: `gpt-6-luna` / `xhigh` / `fork_turns=none`. Host turn-context evidence remains in `rounds/round_009/manager/assistant_host_evidence.json` as metadata, not internal attestation.

