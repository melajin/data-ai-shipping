# Round014 independent source review

## Verdict and scope

**Static source review approved for the exact Round014 process-control smoke and standard-library mock.** The synthetic M4 implementation was also reviewed statically against the bounded contract, but no synthetic model execution was authorized or attempted in this review window. Manager deferred it to a fresh round because the remaining 170-second compute plus cleanup budget no longer fit before the 21:22:19 UTC cutoff. This review is not evidence of Python/PowerShell runtime behavior, checkpoint integrity, tensor results, model performance, FIT, F1, or hardware behavior.

## Freeze and direct hashes

The author ACK declares write-stop at `2026-11-04T21:19:00.3646625Z` and no author executions. Its requested settings are GPT-6 Luna / xhigh / fork none; the ACK explicitly does not assert execution identity, which remains separate manager evidence. Candidate manifest SHA-256 is `5239194656ecad7758865b6b706593c1427aca5a39fbda91dd2202c979e1d813`; freeze ACK SHA-256 is `de124bc75d76328503b1ed0d66eec08ffe421663a4131c182f218af5d5358e63`.

I independently calculated these direct disk hashes and confirmed each matches both the candidate manifest and freeze ACK:

| Frozen source | SHA-256 |
|---|---|
| `rounds/round_014/code/m4_synthetic.py` | `06319a56f3194c11edb405695e0e87b331c555a04340c62cf5e9810dd099c199` |
| `rounds/round_014/code/test_m4_mock.py` | `119f9431f7d562d379ca720fb815efde13eba2fdd5a4dca48e8d6c7c5dece1eb` |
| `rounds/round_014/code/run_m4.ps1` | `330a6ccd14eb2b69c6adf5d5ca2d4749a0bbe476cff7961561a2771ce201e10e` |

The final compatible approval map is `approved_sources.json`, SHA-256 `872d5eba99b7d3a3bdc1dcfd89b857a1b781a527cde676652573d7c5e5455d24`. An earlier map attempt omitted the last `e` in the runner hash; the manager caught the mismatch before execution. It is preserved as `invalid_approved_sources_attempt_01.json` (SHA-256 `d2a02735d77e4a0db010d4278d6dedcd5126a1b3ace98d8dbe379bbd10b001a9`). That map was never used to launch a process. The corrected map was rebuilt from direct `Get-FileHash` results and rechecked against the manifest and ACK.

## Source-grounded findings

- The implementation fixes the input seed and synthetic context/target dimensions, fits only the 16 context rows, delays target-label creation until after its single `predict_proba`, and uses target labels only for the external head losses. The target-only hook copy validates the full 20-row decoder output and retains only the final four rows.
- The final-layer path and dimensions are asserted after fit. Hooks observe the Linear input and output without mutation and are removed in `finally`; the code compares frozen-model parameter/buffer/gradient/mode/hook signatures before and after.
- The member order is read from the fitted generator’s actual `class_shuffles_` under the single `none` normalization. The code pairs member labels as `p[y]` and restores output columns using `out[...,p]`; loss uses the first four of ten output columns.
- M4-a updates a copied W with fixed bias; M4-b keeps W/b fixed, learns the rank-2 factors, merges once, and rejects a second merge. The M4-a reload comparison is now pre-save trained-head output versus the reloaded head. Planned external head evaluations total 12, backward calls 4, and native forwards 4. No CE value is a selection condition.
- Probability reconstruction now follows the source’s averaged-logit, temperature, softmax and row-normalization sequence, with finite/range/row-sum and fixed tolerance checks.
- The process runner uses the base Python executable directly, `-B -S`, removes inherited `PYTHONPATH` and `PYTHONHOME`, and inserts the pinned environment’s `site-packages` only after source/path checks. It snapshots exactly the three frozen source files, checks the exact approval map, requires successful same-map smoke before mock and same-map mock before synthetic, drains both redirected streams, records integer exit status and process identity, and enforces the configured start-RAM and stop-RAM thresholds for the synthetic mode.
- The installed M4 source files were read as text and directly hashed; their recorded hashes match `rounds/round_011/m4_contract/source_evidence.json` (`learning.py`, `tabicl.py`, `inference.py`, `classifier.py`, `preprocessing.py`). I separately hashed installed `_sklearn/base.py` as `7f8f284ca91bf1f5a016179834e508890b3f5368c4a48a7dcb6cb4b83a30051a` for the conditional next-integration checklist. Installed files remain read-only.

The source-grounded checkpoint path is `model_cache/tabicl-classifier-v2-20260212.ckpt`; Round004 saved metadata records the expected 110,368,038 bytes and SHA-256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`. This reviewer did not read, hash, or load the checkpoint. The executable is designed to perform one streaming hash at run time, but no such check occurred here.

## Limits and remaining unknowns

No Python imports, tests, PowerShell runner, checkpoint, model, project data, or numerical evaluation was run/read by this reviewer. The author ACK reports Python AST and PowerShell parser-only checks; I did not rerun those checks. No smoke/mock receipts or outputs exist from this review. Their runtime behavior and exit/cleanup results therefore remain unknown.

The process runner takes a final owned-tree snapshot and fails its completion check if an unexpected descendant remains after normal root exit; it does not attempt another kill on that normal-exit path. The reviewed inference path uses one base-Python process and sequential estimator forwards, with no source-observed subprocess launch. Timeout/low-RAM cleanup attempts to stop the owned descendants and root, but that cleanup branch has not been dynamically exercised. Resource-curve peak and minimum values are sampled at roughly one-second intervals; they are not continuous maxima/minima. The 1,536 MiB expected peak is a planning assumption, not a measurement.

All Round014 sources and installed environment files remain read-only after the ACK. Any future synthetic execution requires a fresh-round copy, fresh approval map, and the manager’s current RAM/time gate; this Round014 map does not approve Round015 files or execution.
