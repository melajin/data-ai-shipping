# Round010 independent mock review

**Verdict: mock_01 passed for the approved pure-mock scope.** This authorizes the manager to proceed with the single pilot under the same frozen SHA-256 map; it is not a real-context or performance result.

## Evidence checked

I read `rounds/round_010/logs/mock_01/receipt.json`, stdout/stderr, the copied source directory, the current `review/approved_sources.json`, and manager preflight metadata. I did not execute or import any source, run another mock, load PyTorch/TabICL, access the NPZ as an array, or read the historical reference.

- Mock receipt: `status=completed`, exit 0, stop reason null, elapsed 0.281 s against the fixed 30 s cap; process-tree status clear with no remaining owned processes or uninspectable PIDs; resource sampling complete.
- RAM: preflight available 4.5534 GiB, minimum during mock 4.5534 GiB; sampled owned-process-tree peak 8,241,152 bytes. This tiny mock measurement is not a pilot estimate.
- Stdout: `round010 COL+ROW/ICL observer pure mock passed`; stderr was empty.
- Receipt’s embedded `approved_sources.sha256` equals the current approved manifest map. Current local authored source hashes remained fixed: mock `460bf6aa7c42cdc089d897a162331a2dd2a630ed2e8212abe18e2f93e955dbf6`, replay `488b7e935188e803651ea018a57dbbeb69eb85843041df13a043300e58c28aa0`, COL `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded`, ROW `d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b`, ICL observer `73770185e12662b3c589a24736fc12af7c7673b09c296ea62c9eb12763a2659b`, wrapper `c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210`.
- I independently hashed every copied round010 code source in the mock snapshot and the copied wrapper. All matched the approved manifest; wrapper snapshot SHA-256 was `c0bb06bed9cd5a38b7d231af6c0d1f6a254adc40c0635e5ab38b831a4b75b210`. The receipt also records `source_unchanged`, `adapter_source_unchanged`, `source_snapshot_unchanged`, and `wrapper_unchanged` as true.

## Scope and limits

The mock exercises fake callable managers only. Its saved stdout and source contract cover COL/ROW chunk order and tails, configuration forwarding, coexistence and restoration, unknown tensor rejection, and transparent ICL call-through/full-context shape validation. No real tensor, estimator, checkpoint, project feature, probability, metric, or hardware path was run. The actual pilot result and memory use remain unknown.
