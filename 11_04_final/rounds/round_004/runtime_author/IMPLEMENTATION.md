# Round 004 runtime probe implementation

## Scope

This authoring task owns `code/probe_tabicl_runtime.py` and this directory only. The probe is bounded to a 16-row synthetic FIT context and four synthetic query rows with 312 float32 features, seed `20261105`, labels `0,1,2,3` repeated four times, one TabICL estimator, CPU inference, and the existing local classifier checkpoint. It does not open project datasets, train weights, calculate F1/accuracy, or run the smoke itself.

## API evidence

The API was checked against the official `soda-inria/tabicl` `v2.2.0` tag, matching the requested package pin:

- [`TabICLClassifier` constructor and `fit`](https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_sklearn/classifier.py#L2184-L2231) expose `n_estimators`, `batch_size`, `model_path`, `allow_auto_download`, `device`, `use_amp`, and `use_fa3`. `fit` loads the checkpoint and binds its input context; its docstring states that model weights are not trained on the data ([`fit` documentation](https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_sklearn/classifier.py#L2432-L2451)).
- The same source constructs `model_` from checkpoint config/state ([checkpoint load](https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_sklearn/classifier.py#L2422-L2430)).
- The prediction path wraps model forward calls in `torch.no_grad()` ([forward path](https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_sklearn/classifier.py#L2711-L2741)); `predict_proba` documents output shape `(n_samples, n_classes)` ([method](https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_sklearn/classifier.py#L2813-L2849)).
- The version-pinned model builds its dataset-wise predictor from `ICLearning` ([TabICL model wiring](https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_model/tabicl.py#L2442-L2470)); that module defines its output decoder as `Linear(d_model, 2*d_model) -> GELU -> Linear(2*d_model, out_dim)` ([ICLearning decoder](https://github.com/soda-inria/tabicl/blob/v2.2.0/src/tabicl/_model/learning.py#L2008-L2017)). The probe reports this named `icl_predictor.decoder` head and its final Linear separately from every registered Linear layer.
- The release page for the existing `tabicl==2.2.0` metadata is retained at `rounds/round_003/m4_readiness/tabicl_2_2_0_pypi.json`.

After the manager installed the pinned environment, I also read (without importing) `environments/round_004_tabicl_cpu/Lib/site-packages/tabicl-2.2.0.dist-info/METADATA` and the installed `_sklearn/classifier.py`, `_sklearn/base.py`, `_model/tabicl.py`, and `_model/learning.py`. The metadata says `Version: 2.2.0`. The installed constructor includes all configured options; `fit` assigns `device_`, loads `model_`, and moves it with `.to(self.device_)`; `ICLearning.decoder` is the named `Linear -> GELU -> Linear` output head; and `_batch_forward` uses `torch.no_grad()`. This confirms the checked code paths against the installed source. No package import, checkpoint load, or model execution was performed for this source-only confirmation.

The script also records installed versions and live signatures at execution time and fails if the installed TabICL version is not exactly `2.2.0` or the required constructor arguments are absent. The module tree, all registered `torch.nn.Linear` layers, named output head, model config, and parameter totals are obtained from the single loaded model instance. It asserts that the estimator resolved to CPU, model parameters and buffers are on CPU, and floating parameters are FP32. This avoids a second checkpoint/model allocation. The historical comparison checks total parameters against `27,552,258` and the named output head dimensions against `[[512, 1024], [1024, 10]]`; a false comparison is evidence of a difference, not a failure by itself.

## Invocation and output

The manager wrapper may invoke:

```powershell
& './environments/round_004_tabicl_cpu/Scripts/python.exe' `
  './rounds/round_004/code/probe_tabicl_runtime.py' `
  --checkpoint './model_cache/tabicl-classifier-v2-20260212.ckpt' `
  --output './rounds/round_004/artifacts/smoke.json'
```

Relative `--checkpoint` and `--output` arguments resolve from the project root, independent of the shell's current directory. `--checkpoint` defaults to the project-root `model_cache` path; `--output` defaults to `rounds/round_004/artifacts/smoke.json`. The output path must resolve inside the project root. The checkpoint basename is checked, its byte length and SHA256 are recorded, and it is passed as `model_path` with `allow_auto_download=False`, so the probe does not use Hub auto-download.

The script atomically writes a staged JSON file at startup and after meaningful stages. On exceptions, it writes `status: failed`, the failed stage, exception type/message, and traceback to the same JSON path where possible. It prints the current JSON record to stdout and exits nonzero on failure. The record captures Python/TabICL/Torch/NumPy/scikit-learn versions, API signatures, synthetic input hashes and dimensions, per-phase wall and process CPU time, process memory snapshots, model structure and actual parameter devices/dtypes, first/repeat probability arrays as soon as each prediction returns (including if a later stage fails), class inverse mapping, repeat-call probability delta, and whether gradients were attached or accumulated.

## Checks performed by the probe

- FIT shape `(16,312)` and query shape `(4,312)`, both `float32`; all four FIT labels are present.
- `predict_proba` output shape `(4,4)`, finite values, and row sums within absolute tolerance `1e-5` of one.
- Reported `classes_` equals `[0,1,2,3]`; `predict` labels equal `classes_[argmax(predict_proba)]`.
- Two identical `predict_proba` calls differ by at most `1e-7` absolute tolerance.
- Both probability matrices are included in the JSON record so the reviewer can recalculate finiteness, row sums, and repeat delta independently.
- No parameter `.grad` is populated and NumPy probability output has no gradient attribute enabled.

Thread bounds are set to three for common BLAS/OpenMP variables and PyTorch intra/inter-op threads; estimator `n_jobs=1`. Memory snapshots use Windows process working-set counters and psutil RSS/available RAM when available. The recorded peak is process high-water memory; it is not a device-memory or full-workload capacity estimate.

## Actual result and unknowns

Implementation is authored. Static reads of the installed package metadata/source confirm version `2.2.0` and the API/model paths described above. This agent did **not** import the package, load the checkpoint, run the smoke, or run tests. Therefore the checkpoint hash as seen by the probe, exact loaded model architecture and output head, model device/dtype, output probabilities, repeat-call delta, CPU time, and memory consumption remain unmeasured. The code's synthetic shape/config checks are implementation intent until the manager executes the approved wrapper and the independent reviewer clears the source.

The smoke only checks that the pinned CPU inference stack can load the specified checkpoint and produce well-formed repeatable probabilities for the fixed synthetic input. It cannot establish real-ship behavior, predictive quality, F1, performance on 5,897 rows, original probability reproduction, hardware behavior, or learner understanding.
