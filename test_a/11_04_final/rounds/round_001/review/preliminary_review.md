# Round 001 preliminary independent review

Status: `PENDING_EXECUTION` — this is pre-result evidence and a review checklist only. No round execution output was available when this note was written. It makes no claim that T5 reconstruction, parser comparison, or model replay has run.

Review scope: existing source/report inspection and a read-only availability check for TabICL/S4/TabM follow-up candidates. Source repo and raw data were not modified; no training, installation, external research, or holdout label/feature read was performed by this reviewer.

## Confirmed from existing reports and code

- The stored baseline is `sqrt_macro`, 5 seeds, 3-fold development OUTER: 3,497/5,897 = 0.5930133966423605 micro-F1; macro-F1 0.5252719738966167. It is prior work, not a round001 result or independent/official score. The 6-source mean at 3,499/5,897 = 0.5933525521451586 is an exploratory maximum (+2 net correct, lower macro-F1, paired interval including zero), not the baseline or an adopted improvement. Sources: source `coach/gpt/rank1_experiments_20261104/reports/final_report.md` lines 5, 34–48; `reports/exp01/final_summary.md` lines 3–9, 53–66.
- The historical S6 JSON stores an accuracy of 0.59183 and macro-F1 0.52179 at decision multiplier 1.0. It is a rounded prior aggregate; the current experiment report says it was not rescored. No historical per-vessel prediction artifact or run-time source snapshot was found in the supplied evidence, so a paired reconstruction or exact provenance link is not available yet.
- The current S6 Python source reconstructs T5 per fold dynamically via `_fishing_mask_global()`, `_build_t5_dicts()` and `t5_features_for()`; it states seeds `(42, 2026, 7, 1, 2024)`, inverse-square-root FIT weights and INNER macro-F1 early stopping with patience 200. This describes the checked-in source, not proof that this exact file revision generated the historical .59183 aggregate.
- The exp01 X304 matrix is 156 F156 + 10 T5 + 68 behavior + 70 local_rel. The earlier “305” metadata count included an incorrect behavior-width description; the current reports identify the actual 304-column matrix and say `obs_days` is reporting-only.
- `run_005_main_20261101.py::stage_export` builds fold T5 values through the same `t5_features_for()` call and writes `DataFrame.to_csv(index=False)` without an explicit `float_format`. The provenance addendum says cache IDs/schema were checked but no bitwise comparison with the original in-memory dynamic array was made, leaving CSV float round-trip differences unmeasured. This makes dynamic-array vs cached CSV a useful diagnostic, but a current-source reconstruction cannot by itself establish which source revision produced the old score.
- The known T5 contract is FIT-only fold labels for class counts, with FIT vessels leave-self-out. Shared harbor candidate geometry includes Jan–Jun 2026 Train and 2025 Test rows; local_rel uses whole-Train regional median/MAD and includes self. These are documented transductive conditions, not FIT-only preprocessing. Any reconstruction must preserve or explicitly distinguish them.
- Existing reports state that raw 12-file inventory/size was checked but raw files were not rehashed; existing feature caches were reused. “No valid observation loss was found” is bounded to the prior audit’s inspected inputs. It is not a full revalidation of every raw observation.

## Plausible causes for `.59183` vs `.593013`, in investigation order

1. **T5 input realization:** dynamic in-memory output vs the CSV materialization used to construct cached X304, including cell values, NaN mask, row/column order, or CSV serialization/parser behavior. This is the direct known gap in provenance.
2. **Input/source revision:** the historical run has no linked source snapshot or exact T5 array artifact. The checked-in S6 code, generator, and current exp01 cache are useful references but do not prove byte-for-byte historical execution identity.
3. **Environment and training details:** the current exp01 run records Python 3.13.3, NumPy 2.2.5, pandas 2.2.3, LightGBM 4.7.0, Windows 11, 3 CPU threads. The old S6 JSON does not establish its Python/library/OS/thread environment. Seeds and key model settings match in the inspected code, lowering—but not eliminating—this as a cause without an old launch snapshot.
4. **Old input assembly:** the new report verifies current X304 blocks and IDs/roles; this does not establish the old run’s per-vessel inputs, especially because old dynamic T5 values and run-time source hashes are absent.

The roughly 0.00118 score difference (about seven vessels at this denominator) is not attributed to any cause until the execution evidence connects the specific input or replay change to prediction differences. It must not be conflated with the separate `.593353` exploratory maximum.

## Pre-result review checklist

- Verify the execution snapshot, exact commands, hashes, output paths, Python/package/OS/thread/RAM record, and whether any source import wrote outside the round folder.
- Verify IDs, fold roles, row order, 10 T5 column order, NaN masks, and finite counts separately before numeric tolerance. Report bitwise equality and abs/relative error counts/max/quantiles; do not call tolerance agreement exact equality.
- Separate default CSV parsing vs `float_precision='round_trip'` from dynamic-generator vs cache comparison. A reader comparison alone cannot establish original in-memory parity.
- For saved-model replay, verify unchanged non-T5 features and labels/IDs; compare default cached-input probabilities against recorded predictions at abs tolerance `1e-12`; then report T5-substituted probabilities/argmax changes separately. Saved-model replay is not retraining reproducibility.
- Restrict evidence to the 5,897 development vessel IDs and existing FIT/INNER/OUTER materials. Do not read the 1,475 holdout feature/label/prediction rows. If the exact shared geometry aggregate is unavailable under this boundary, mark dynamic parity unmeasured/incomplete; a different harbor population would be a semantic change, not a serialization-only test.
- Preserve the documented INNER reuse limitation: the current baseline model uses INNER for early stopping; any INNER blend choice reuses the same selection set and can be optimistic, though OUTER labels must remain unused for that choice. Keep transductive T5/local_rel population scope explicit.
- Do not broaden the prior “no proven valid-observation loss in inspected inputs” statement into an exhaustive raw-data audit.

## Follow-up model availability (file/document check only)

| Candidate | Local evidence | Reproducibility status from inspected files |
|---|---|---|
| TabICLv2 | `team/tabiclv2_f156` includes prior fold evaluation files, model code under `code/historical/TabM/.../comparison_models.py`, metadata for Python 3.12.14 / torch 2.6.0+cu124 / tabicl 2.2.0, and expected checkpoint SHA. Code path supplies fold FIT as in-context data and writes role-tagged predictions including INNER. README says pretrained weights and virtual environment are not included; the configured checkpoint path is absent and code forbids auto-download. | Code/contract path exists, but not runnable in the active environment without locating an already available checkpoint/runtime; existing INNER files need their input lineage verified before reuse. |
| TabM | Historical source and split/feature workflow exist under `team/tabiclv2_f156/code/historical/TabM/TabM_개선_20261030`; code has FIT/INNER/OUTER preparation and model checkpoint output logic. No model binary was found under this package path. | Not runnable in the active environment without setup: active Python is 3.13; package metadata query found no `torch`, `tabm`, or `tabicl`. Prior metadata is historical, not proof of currently installed packages. |
| S4 | `11월 4일/work/상한선_011/code/S4_model_choice_oracle.py` consumes six existing probability sources and explicitly optimizes an oracle over OUTER. | Not a new estimator or a replayable FIT→INNER training candidate; exclude it from the next model candidate shortlist. |

Environment check was non-mutating: launcher lists Python 3.13 only; active interpreter package metadata reports `torch/tabicl/tabm/tensorflow` absent and LightGBM 4.7.0 present. No install or model run was attempted. CatBoost/ExtraTrees were outside this targeted TabICL/S4/TabM file-level check and are not assessed here.

## Unresolved until execution review

- Whether the dynamic T5 generator can be safely reconstructed from an already available exact shared geometry aggregate without opening prohibited holdout-specific rows.
- Actual dynamic-vs-cache per-cell comparison, CSV reader deltas, and any saved-model probability/argmax effects.
- Whether a current generator/cache difference explains any of the historical score gap. The old `.59183` run remains unpaired and source/environment provenance incomplete unless new evidence closes those links.
