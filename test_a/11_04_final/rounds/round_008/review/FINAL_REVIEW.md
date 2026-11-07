# Round 008 — Independent final review

**Decision:** The bounded pilot stopped at the configured RAM guard. No prediction probability result or new F1 was produced. The saved execution evidence is internally consistent with that stop, and the owned process tree was terminated. No rerun is approved in this round.

## Saved-output verification

The wrapper receipt records status `failed_or_stopped`, exit code 1, `stop_reason=available_ram_below_1_5_gib`, elapsed 25.64 seconds, and termination confirmation with no remaining owned processes. It records 4.1443 GiB available at launch, a 1.3800 GiB observed minimum, and a 3,182,952,448-byte sampled owned-tree working-set peak. This sampled value is not a bound on total memory demand.

The receipt's pilot, adapter, and wrapper hashes match the approved manifest and unchanged-source flags. The saved result matches the frozen context/freeze hashes and records the fixed IDs and model settings. `fit` returned once. `predict_proba` was attempted once and did not complete; probabilities and comparison are null. The completed column event is call 0 on `(1,223,3146,3)`, producing `(1,223,3146,128)` after 14/14 chunks: thirteen width-16 chunks and a final width-15 chunk. Sequence length 3,146, FIT size 3,144, and group width 3 were retained. No later column call began.

The child result remains `STARTED` at `predict_proba_start` because the wrapper externally stopped the process. `adapter_restored=false` is recorded; the process did not return through Python `finally`. The owned process tree is confirmed empty, so no owned Python process remains. This is a resource-guard stop, not a numerical failure or evidence of model accuracy.

One result-record caveat: the pilot stage logger overwrote the initial top-level `source` metadata object with the configure-source label. The wrapper receipt, approved manifest, and execution snapshot hashes still identify the executed source; the result's `source` field itself is not source-hash metadata.

## Failure localization and next hypothesis

The last recorded computational boundary is `column_chunk_call_completed`. In pinned `tabicl.py`, `_inference_forward` calls `col_embedder` and then `row_interactor` (`tabicl.py:422–432`). `RowInteraction._inference_forward` configures the ROW manager and submits the full embedding tensor to `_aggregate_embeddings` (`interaction.py:215–250`). The pinned `InferenceManager` CPU path directly runs `_prepare_inputs` and `_run_forward` without automatic batching (`inference.py:1291–1298`). A subsequent ROW allocation is therefore plausible if execution had continued. The saved trace contains no ROW-start event, so it does not establish that the ROW path started or caused the RAM guard.

For a next round, compare the column16-only baseline with column16 plus row-axis chunk8 on a tiny synthetic pair such as FIT `32×312` and two queries `2×312`. The row adapter must preserve each row's full feature-token axis; the ICL context axis remains whole. Require the synthetic equivalence gate to pass before planning another full-context replay. This is a candidate to investigate, not a diagnosis from this run. Do not use this run to claim memory reduction, probability reproduction, F1, OUTER, holdout, or official-score evidence.

## Scope and provenance

Review used the saved JSON/streams and static pinned-source text only; no model or mock was rerun, and no NPZ arrays, raw data, OUTER data, holdout, or `y_inner` were loaded. Requested reviewer setting: `gpt-6-luna` / `xhigh` / `fork_turns=none`. Manager-recorded host turn-context evidence is in `manager/assistant_host_evidence.json`; it is evidence metadata, not internal model authentication.

Key evidence hashes:

- Pilot receipt: `e5a1a8be6ffa8f9c52a9a099c147a211056228b10783577fc38f8fb979ae1c0a`
- Saved pilot result: `bb4b2b4b1ae3fd1c741eb2c43f47a162f98a0bc1a8b47bf64f438f6f01348547`
- Pilot stdout: `d1c5dd67d6a8c72a18212a15dc731e18a89adc3249d2ced5bc407a2e722fc2bd`; stderr is empty.
- Executed source/wrapper: pilot `112ca09e7abba9c194421c22bd38771563636e2852c867c089cb27e985c39b0d`; adapter `bf263ba75bef5ed9aab04364459e426f3a82be92da2ce642e89b06558fd9cded`; wrapper `6962c94fa07a36cd7b3429eaeb27ac851aee3104e9b77758d7a99c0fc1a48e1d`.
- Pinned post-column sources reviewed: `tabicl.py` `583786e5ffd70b9eb425bca8e52aed415dadcdf4254c908b3b6fa52026a56491`; `interaction.py` `6f35b5a70cd7b7ea44286faa8921b64c2cc83aca8ed49a4ad8b287abe54cbf27`; `inference.py` `f9e3cf0d83047e06df7d6763bb8d8ee7a00ff1ba6708299a14635831f60ba4fc`.
