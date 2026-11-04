# Round 009 independent final review

**Verdict: approved for the recorded, synthetic-only scope.** This is evidence that the prescribed adapters preserved the synthetic pair's result under this run. It does not establish real-context equivalence, F1, or memory savings.

## Independent source and implementation review

The pinned TabICL source establishes that ROW receives `(B,T,H+C,E)`; B and T are independent batch axes, while the final feature/register sequence is the attention axis. LayerNorm applies over E per token. ROW returns `(B,T,C*E)`. The implementation chunks only T and preserves the complete `H+C` sequence and E at each call. The ICL manager and full FIT context are unchanged. Sources, versions, and line evidence are recorded in [SOURCE_REVIEW.md](SOURCE_REVIEW.md).

Approved manifest [approved_sources.json](approved_sources.json) SHA-256: `3b48e4e9ab7a368bff2aa93baa09d04822e4a27383b8badda535bb4191dece3f`. Final source hashes were frozen before execution: column adapter `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded`, row adapter `d2a3b4d011e233baf051f4df038df6f562c2b5c73a6fc2f21284963b558e947b`, synthetic pair `dcf056bb5772a1bd31b17194ed680655e427b9914ddef953eb7b291723213c19`, mock `1a134ff544b5c67efb813417322e3304317ccd4fc2136d85650ef36c72d86ee0`, and bounded wrapper `b8e5d7de47ba070ed9df52badb1002f1955d67798e679e240e295a05ba87a439`. Manifest and wrapper snapshots matched at mock and pair gates.

## Execution and result review

The single mock completed successfully (exit 0, 0.532 s); its receipt and stream review are in [MOCK_REVIEW.md](MOCK_REVIEW.md). The manager then ran exactly one synthetic pair under the amended 180 s total limit (170 s run plus 10 s cleanup). Wrapper elapsed time was 49.187 s; child elapsed time was 46.979 s. Exit was 0, stop reason was null, the owned process tree was clear, and resource sampling completed. Host RAM was 4.44189 GiB at start and 3.93400 GiB minimum; sampled process-tree peak was 556,965,888 bytes.

Child result `SYNTHETIC_PAIR_COMPLETE`: one fit and two `predict_proba` calls completed. On fixed synthetic FIT32×312 and two query rows, both probability gates passed; maximum absolute difference was 0, exact numeric equality was true, and argmax indices `[1,2]` matched. The test tolerance was `1e-5`. Runtime manager state and inputs/shuffle state were unchanged, and all managers/adapters were restored. The synthetic class order was `[0,1,2,3]`.

ROW event evidence records 8 calls and 40 completed chunks. The observed first-call input was `(1,34,316,128)`; chunks along T had widths `8,8,8,8,2`, preserving the full 316-token feature/register sequence and embedding width 128. These are call-shape observations, not a timing or memory comparison against an unchunked control.

## Evidence boundaries and consistency

I reviewed the receipt and JSON result metadata/comparison fields, wrapper streams, source snapshots, and report summaries. I did not execute the mock/model and did not open the generated NPZ payload; its SHA-256 was checked as metadata: `6f2892bbb6a3677195dc4f7d990a5f86b4fea225f0d8376d18daa792080d729e`. Child JSON SHA-256: `6c8e7eb8cc147de6255a009f9bbfd5055055f9c14204325da91f5b1fc97c8b92`; manager summary SHA-256: `b8ebcb1ddb6a48ebc8e9977153983a3ab9e5166d1c09b15d3488c557420bfc37`.

ROUND_REPORT, NEXT_SESSION, and STATUS consistently record the synthetic equivalence pass, zero new F1, no real/OUTER/holdout reads, and the next bounded actual-context replay as a separate future gate. Existing development OUTER baseline remains 0.5930133966423605 micro-F1; the project objective of 0.7 is not met. This pair supplies no actual-context performance or memory-savings evidence. No hardware behavior was tested.

Requested execution evidence identifies manager Astra/high and reviewer Luna/xhigh; host turn-context records were checked as session metadata, not treated as attestation of model internals.
