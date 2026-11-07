# Round013 Sections 3–5 execution notes

Task01 executed §§3–5 only. Its fixed inputs, row/window rules, quality audit, Spearman/KS confound check, synthetic checks, and direct-sum validation are preserved in the parent folder’s `execution.json`, `g3_voyage_count_coverage.csv`, `g4_voyage_local_collapse.csv`, `g5_confound_summary.json`, and `source_hash_manifest.json`.

No ZIP input was used. The analysis used the fixed Round008 dev inputs and the existing 2025 ID/ts-only coverage source, as specified.

## Task02 continuation

Task02 ran in this isolated folder so existing root §6–7 artifacts from another source remain untouched. The execution used the reviewed root `g4_voyage_local_collapse.csv`, root `g5_confound_summary.json`, fixed Round008 positives, and Round008 parquet `rfid_id_int`/`ts` columns only for midpoint reconstruction and split parity. See `execution.json`, `input_output_manifest.json`, and `AUDIT.md` for hashes, results, resource records, and independent checks.

The worker request specified GPT-6 Luna xhigh and the project Luna profile matches that setting. The dispatch receipt/runtime telemetry did not expose an independently verifiable model identifier to this worker, so the execution record does not claim additional model verification.