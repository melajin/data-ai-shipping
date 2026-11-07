# Round020 independent source review

**Decision: NOT APPROVED.** No `approved_sources.json` was issued. No model fit or Round020 OUTER scoring was run. This decision applies to the exact snapshot below; any edits require a fresh hash-bound review.

Review timestamp: 2026-11-05 09:01 KST (00:01 UTC). Exact current hashes:

| File | SHA256 |
|---|---|
| `rounds/round_020/code/run_performance.py` | `281B3FD93BE0DA6D278BF4B1C03E4AB9F1FAEEF19C47F422E5F1DAEC56585D05` |
| `rounds/round_020/configs/experiment.json` | `7EBD3902347E510D623C053C113E8E491C6B8A0D8D36EAA41B72960680D07378` |
| `rounds/round_020/ROUND_PLAN.md` | `187BF48BD63773DE42BBE880BF0A456FAD2DE44F228B09028B5DA3B709C307EC` |
| `rounds/round_020/manager/launch.py` | `2B6035BAFD234D07344C497BDD2B6BFFE7CF7DA41CAE70D3E2D20D024089B320` |
| `rounds/round_020/manager/ROUND021_FIXED_BRANCH.md` | `5AE49425E03A6315D7F34B4431DCA8691FA2CC4E0B9EE48D37E9849F92AAE073` |

## Findings supporting the input lineage

- Round002 source checks FIT-only LightGBM/CatBoost fitting, INNER_ES-only early stopping, `[0,1,2,3]` model class order, and INNER_SELECT-only saved probabilities. Its split manifest records 393 ES and 394 SELECT IDs per fold.
- Direct ID/label/role comparison found the stored LightGBM and CatBoost SELECT files match each other and the matching fold-local TabICL INNER SELECT subset. FIT/INNER/OUTER role IDs match the TabICL development roster. Round003 source and independent review record TabICL's FIT-context-only generation with INNER unused for fitting/early stopping. No global OOF source was used for this audit's SELECT join.
- Input review did **not** open Test2025, holdout, raw `F:` data, or any OUTER probability/prediction values. It did load the round002 `y` vector for the full 5,897-row development cache while checking INNER labels; this technically loaded OUTER labels before freeze. No OUTER labels were used to tune or alter the hypothesis. See `PRELIMINARY_SOURCE_REVIEW.md` for the exact scope and historical limitations.

## Blocking findings in the reviewed runner snapshot

1. `load_tabicl_inner()` receives a 394-ID SELECT mapping but requires the source CSV to have exactly 394 rows and requires every CSV ID to be in that map. The authorized fold-local TabICL INNER file has 787 rows, so prepare/run fails before fitting. The reader also converts probabilities for every INNER row, including ES; it should validate full INNER membership and only parse/use SELECT probabilities.
2. The config now carries sum tolerance `1e-6` and protected TP metadata (`TP0 >= 2389`, `TP3 >= 92`), but runner evaluation still validates combined probabilities at `1e-5`, retains only the generic `-0.03` all-class recall gate, and does not implement the protected integer TP checks or per-class/reference gain/loss/net and FP transitions.
3. The per-fit 120-second limit is checked only after `model.fit()` returns, so it is not a hard timeout. `ConvergenceWarning` is not promoted to failure.
4. The run output writes OUTER probabilities but does not preserve keyed INNER_SELECT raw probabilities needed for the fixed Round021 continuation. The runner's source manifest also omits the historical protection prediction file/reference, so its later ID/y/fold comparison and hash binding are not implemented.

The updated launcher correctly checks approved runner/config/launcher hashes, execution-freeze hashes, RAM thresholds, and the compute cutoff. That does not clear the runner blockers. The current config and runner snapshot therefore remain unapproved, and no manager OUTER-read approval should be inferred from this review.
