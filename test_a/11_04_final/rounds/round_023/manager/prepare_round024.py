"""Low-memory sequential setup for Round024 per user steering (2026-11-05). No training and no raw rescan."""
import datetime
import hashlib
import json
import os
import shutil
from pathlib import Path
import psutil

OLD = Path(__file__).resolve().parents[1]
ROOT = OLD.parents[1]
NEW = ROOT / 'rounds/round_024'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

assert not NEW.exists(), 'Existing round024: inspect owner/claim; never overwrite'
guard = json.loads((OLD / 'manager/next_resource_contract.json').read_text(encoding='utf-8'))
memory = psutil.virtual_memory()
other_jobs = []
ancestors = {p.pid for p in psutil.Process().parents()} | {os.getpid()}
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        d = p.info
        if d['pid'] not in ancestors and 'python' in (d['name'] or '').lower():
            other_jobs.append({'pid': d['pid'], 'cmdline': d['cmdline']})
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
preflight = dict(
    utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    available_gib=memory.available / 2**30,
    required_entry_gib=guard['minimum_entry_available_gib'],
    other_python_jobs=other_jobs,
    estimate_basis=guard['basis'],
    prepared=False,
)
write(OLD / 'manager/round024_setup_preflight.json', preflight)
assert not other_jobs, 'Other Python jobs active: establish ownership/concurrency before setup'
assert memory.available >= guard['minimum_entry_available_gib'] * 2**30, (
    'Resource not ready: defer; do independent work then recheck, no RAM polling or repeated fresh-manager launches'
)

approval = json.loads((OLD / 'review/gate_approved_sources.json').read_text(encoding='utf-8-sig'))
assert approval['approved']
for rel, expected in approval['source_hashes'].items():
    assert sha(ROOT / rel).lower() == expected.lower(), rel

files = [
    'code/run_gate.py',
    'code/s1_features.py',
    'code/t5_rebuild.py',
    'code/prepare_t5_cache.py',
    'configs/experiment.json',
    'artifacts/t5_fishing_profiles.npz',
    'artifacts/t5_fishing_profiles.manifest.json',
    'artifacts/t5_mask_equivalence.json',
    'tmp/s1_profiles.sqlite',
    'tmp/s1_profiles.sqlite.manifest.json',
    'review/verify_gate_result.py',
    'code_author/supplement_metrics.py',
    'manager/launch.py',
    'manager/freeze_stage.py',
]
for rel in files:
    assert (OLD / rel).is_file(), rel
for folder in ['code', 'configs', 'artifacts', 'tmp', 'review', 'manager', 'logs', 'code_author']:
    (NEW / folder).mkdir(parents=True, exist_ok=True)
copied = {}
for rel in files:
    shutil.copyfile(OLD / rel, NEW / rel)
    assert sha(OLD / rel) == sha(NEW / rel)
    copied[rel] = sha(NEW / rel)

# 1. Low-memory / 1-thread config patch (preserves exact model hyperparameters, seed42, 4-fold, alpha=5, resolutions)
exp_cfg = json.loads((NEW / 'configs/experiment.json').read_text(encoding='utf-8-sig'))
exp_cfg['threads'] = 1
exp_cfg['lgbm']['n_jobs'] = 1
write(NEW / 'configs/experiment.json', exp_cfg)

# 2. T5 rebuild: immediately release 567k-element `seen` set after duplicate check
t5_src = (NEW / 'code/t5_rebuild.py').read_text(encoding='utf-8')
t5_old = "seen.add(key);profiles[row].append((month,(fx,fy),(cx,cy),count))"
t5_new = "seen.add(key);profiles[row].append((month,(fx,fy),(cx,cy),count))\n    del seen"
assert t5_src.count(t5_old) == 1
(NEW / 'code/t5_rebuild.py').write_text(t5_src.replace(t5_old, t5_new), encoding='utf-8')

# 3. S1 features: release period_profiles and run gc.collect() after each month
s1_src = (NEW / 'code/s1_features.py').read_text(encoding='utf-8')
assert s1_src.count("import hashlib\n") == 1
assert s1_src.count("        del counts_by_res\n") == 1
s1_src = s1_src.replace("import hashlib\n", "import gc\nimport hashlib\n", 1)
s1_src = s1_src.replace("        del counts_by_res\n", "        del period_profiles, counts_by_res\n        gc.collect()\n", 1)
(NEW / 'code/s1_features.py').write_text(s1_src, encoding='utf-8')

# 4. run_gate.py: 1.0 GiB stage guard / 0.5 GiB expected peak + free rebuild_t5 before S1/LightGBM + per-fit del/gc.collect()
rg_src = (NEW / 'code/run_gate.py').read_text(encoding='utf-8')
assert rg_src.count("import datetime as dt\n") == 1
rg_src = rg_src.replace("import datetime as dt\n", "import datetime as dt\nimport gc\n", 1)
old_snap = (
    '            "expected_peak_bytes": int(1.5 * 2**30), "minimum_free_bytes": int(2.5 * 2**30),\n'
    '            "other_python_processes": others,\n'
    '            "allowed": bool(memory.available >= 2.5 * 2**30),'
)
new_snap = (
    '            "expected_peak_bytes": int(0.5 * 2**30), "minimum_free_bytes": int(1.0 * 2**30),\n'
    '            "other_python_processes": others,\n'
    '            "allowed": bool(memory.available >= 1.0 * 2**30),'
)
assert rg_src.count(old_snap) == 1
rg_src = rg_src.replace(old_snap, new_snap, 1)
rg_src = rg_src.replace(
    'raise RuntimeError("RAM gate: available memory below 2.5 GiB; defer and recheck after independent work")',
    'raise RuntimeError("RAM gate: available memory below 1.0 GiB; defer and recheck after independent work")',
)
old_loop_head = (
    "    all_fit_indices = np.arange(len(y), dtype=np.int64)\n"
    "    for fold_idx, (train_idx, valid_idx) in enumerate(skf.split(X, y)):\n"
    "        t5_matrix = np.asarray(rebuild_t5(train_idx, y[train_idx]), dtype=np.float64)"
)
new_loop_head = (
    "    all_fit_indices = np.arange(len(y), dtype=np.int64)\n"
    "    splits = list(skf.split(X, y))\n"
    "    t5_by_fold = [np.asarray(rebuild_t5(tr, y[tr]), dtype=np.float64) for tr, _ in splits]\n"
    "    del rebuild_t5\n"
    "    gc.collect()\n"
    "    for fold_idx, (train_idx, valid_idx) in enumerate(splits):\n"
    "        t5_matrix = t5_by_fold[fold_idx]; t5_by_fold[fold_idx] = None"
)
assert rg_src.count(old_loop_head) == 1
rg_src = rg_src.replace(old_loop_head, new_loop_head, 1)
old_fit_tail = (
    '            progress.pop("current_fit", None)\n'
    '            save_json(output_dir / "fit_progress.json", progress)\n'
    '        folds.append(fold_result)\n'
    '        del s1_matrix, X_base, X_candidate, t5_matrix'
)
new_fit_tail = (
    '            progress.pop("current_fit", None)\n'
    '            save_json(output_dir / "fit_progress.json", progress)\n'
    '            del model, proba, pred\n'
    '            gc.collect()\n'
    '        folds.append(fold_result)\n'
    '        del s1_matrix, X_base, X_candidate, t5_matrix\n'
    '        gc.collect()'
)
assert rg_src.count(old_fit_tail) == 1
rg_src = rg_src.replace(old_fit_tail, new_fit_tail, 1)
(NEW / 'code/run_gate.py').write_text(rg_src, encoding='utf-8')

# 5. runtime_contract.json and launch.py: 1 thread, BELOW_NORMAL_PRIORITY_CLASS, 1.5 GiB entry, 0.75 GiB RSS cap
now = datetime.datetime.now(datetime.timezone.utc)
contract = dict(
    started_utc=now.isoformat(),
    compute_deadline_utc=(now + datetime.timedelta(minutes=40)).isoformat(),
    manager_deadline_utc=(now + datetime.timedelta(minutes=45)).isoformat(),
    compute_seconds_max=1800,
    job_seconds_max=900,
    threads_max=1,
    concurrency=1,
    minimum_available_gib=guard['per_stage_free_guard_gib'],
    minimum_entry_available_gib=guard['minimum_entry_available_gib'],
    expected_peak_gib=guard['owned_job_expected_peak_gib'],
    owned_rss_limit_gib=guard['owned_job_peak_limit_gib'],
    emergency_min_free_gib=guard['emergency_free_floor_gib'],
    below_normal_priority=True,
    production_fits_max=8,
    retries=0,
    full3fold=0,
    s2=0,
    procedure='One fixed S1 8-fit replay in user-directed low-memory sequential background mode (threads=1, below-normal priority, immediate gc.collect() between steps); round022 2 fits and round023 0 fits preserved; no tuning/raw rescan',
)
write(NEW / 'manager/runtime_contract.json', contract)

launcher = (NEW / 'manager/launch.py').read_text(encoding='utf-8')
launcher = launcher.replace(
    "OMP_NUM_THREADS='3',OPENBLAS_NUM_THREADS='3',MKL_NUM_THREADS='3',NUMEXPR_NUM_THREADS='3'",
    "OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1'",
)
launcher = launcher.replace("expected_peak_bytes=int(1.5*2**30)", "expected_peak_bytes=int(0.5*2**30)")
old_guard = "if memory.available<2.5*2**30:raise RuntimeError('RAM gate: defer stage and do independent work before recheck')"
new_guard = "if memory.available<float(json.loads((R/'manager/runtime_contract.json').read_text(encoding='utf-8'))['minimum_entry_available_gib'])*2**30:raise RuntimeError('Entry RAM gate: defer before claim/job; do independent work then recheck')"
assert launcher.count(old_guard) == 1
launcher = launcher.replace(old_guard, new_guard, 1)
launcher = launcher.replace(
    "creationflags=subprocess.CREATE_NO_WINDOW",
    "creationflags=subprocess.CREATE_NO_WINDOW|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0x00004000)",
)
launcher = launcher.replace("if rss>1.5*2**30 or free<.5*2**30:stop='memory_stop'", "if rss>0.75*2**30 or free<.5*2**30:stop='memory_stop'")
(NEW / 'manager/launch.py').write_text(launcher, encoding='utf-8')

# 6. verify_gate_result.py: fix round_022 prefix split so round_024 approved hashes are checked directly
checker = (NEW / 'review/verify_gate_result.py').read_text(encoding='utf-8')
assert checker.count('rel.split("round_022/")[-1]') == 1
checker = checker.replace('rel.split("round_022/")[-1]', 'rel.split(f"{round_dir.name}/")[-1]')
(NEW / 'review/verify_gate_result.py').write_text(checker, encoding='utf-8')

# 7. Provide sequential low-memory reinfer_saved.py for reviewer inspection and execution
reinfer_code = '''"""Sequential one-model-at-a-time reinference verification for Round024 FIT gate."""
from __future__ import annotations

import datetime as dt
import gc
import hashlib
import json
import os
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[3]
ROUND = Path(__file__).resolve().parents[1]
DEFAULT_FOLD0_NPZ = Path(
    r"D:\\repos\\fishing-track-classification\\coach\\gpt\\rank1_experiments_20261104\\artifacts\\exp01\\fold_0_features.npz"
)
T5_START, T5_STOP = 156, 166


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main() -> int:
    gate_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (ROUND / "artifacts" / "gate").resolve()
    mem = psutil.virtual_memory()
    if mem.available < int(1.0 * 2**30):
        raise MemoryError("Available RAM below 1.0 GiB for sequential model reinference")
    import joblib
    import numpy as np

    result = json.loads((gate_dir / "gate_result.json").read_text(encoding="utf-8"))
    with np.load(DEFAULT_FOLD0_NPZ, allow_pickle=False) as bundle:
        roles = bundle["roles"].astype(str)
        fit_mask = roles == "FIT"
        X_fit = np.asarray(bundle["X"][fit_mask], copy=True)
        y_fit = np.asarray(bundle["y"][fit_mask], dtype=np.int64, copy=True)
    gc.collect()

    saved_preds = {}
    for variant in ("baseline", "candidate"):
        with np.load(gate_dir / f"predictions_{variant}.npz", allow_pickle=False) as z:
            saved_preds[variant] = {
                "row_index": np.asarray(z["row_index"], dtype=np.int64),
                "y_true": np.asarray(z["y_true"], dtype=np.int64),
                "y_pred": np.asarray(z["y_pred"], dtype=np.int64),
                "proba": np.asarray(z["proba"], dtype=np.float32),
            }

    records_by_key = {(int(r["fold"]), r["variant"]): r for r in result.get("fit_records", [])}
    errors: list[str] = []
    fold_checks: list[dict] = []
    all_valid: list[int] = []
    max_abs_diff_overall = 0.0

    for fold in range(4):
        ev_path = gate_dir / "feature_evidence" / f"fold_{fold}_features.npz"
        with np.load(ev_path, allow_pickle=False) as ev:
            tr = np.asarray(ev["train_indices"], dtype=np.int64)
            va = np.asarray(ev["valid_indices"], dtype=np.int64)
            ty = np.asarray(ev["train_labels"], dtype=np.int64)
            t5 = np.asarray(ev["t5_matrix"])
            s1 = np.asarray(ev["s1_matrix"])
        if len(tr) + len(va) != 3144 or (set(tr.tolist()) & set(va.tolist())):
            errors.append(f"fold {fold}: invalid split")
        if not np.array_equal(ty, y_fit[tr]):
            errors.append(f"fold {fold}: train labels mismatch")
        all_valid.extend(va.tolist())

        X_base_va = X_fit[va].copy()
        X_base_va[:, T5_START:T5_STOP] = t5[va].astype(X_base_va.dtype, copy=False)
        X_cand_va = np.concatenate((X_base_va, s1[va]), axis=1)

        for variant, X_va, expected_cols in (("baseline", X_base_va, 304), ("candidate", X_cand_va, 328)):
            rec = records_by_key.get((fold, variant))
            if not rec:
                errors.append(f"fold {fold} {variant}: missing fit_record")
                continue
            model_path = ROOT / rec["model_path"]
            actual_sha = sha256(model_path)
            if actual_sha.lower() != rec["model_sha256"].lower():
                errors.append(f"fold {fold} {variant}: model sha256 mismatch")
            model = joblib.load(model_path)
            classes = np.asarray(getattr(model, "classes_", []))
            if not np.array_equal(classes, np.arange(4)):
                errors.append(f"fold {fold} {variant}: class order mismatch")
            proba = np.asarray(model.predict_proba(X_va), dtype=np.float32)
            pred = np.argmax(proba, axis=1).astype(np.int64)
            del model
            gc.collect()

            saved_p = saved_preds[variant]["proba"][va]
            saved_y = saved_preds[variant]["y_pred"][va]
            max_diff = float(np.max(np.abs(proba - saved_p)))
            max_abs_diff_overall = max(max_abs_diff_overall, max_diff)
            argmax_match = bool(np.array_equal(pred, saved_y))
            if max_diff > 1e-7:
                errors.append(f"fold {fold} {variant}: max probability diff {max_diff} > 1e-7")
            if not argmax_match:
                errors.append(f"fold {fold} {variant}: argmax mismatch")
            fold_checks.append({
                "fold": fold,
                "variant": variant,
                "validation_rows": int(len(va)),
                "feature_columns": int(expected_cols),
                "model_sha256_match": actual_sha.lower() == rec["model_sha256"].lower(),
                "max_abs_proba_diff": max_diff,
                "argmax_exact_match": argmax_match,
            })
        del X_base_va, X_cand_va, t5, s1
        gc.collect()

    if sorted(all_valid) != list(range(3144)):
        errors.append("validation indices across 4 folds do not form an exact partition of 0..3143")

    out_report = {
        "status": "pass" if not errors else "fail",
        "verified_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "models_reloaded_and_reinferred": len(fold_checks),
        "max_abs_proba_diff": max_abs_diff_overall,
        "tolerance": 1e-7,
        "validation_partition_complete": sorted(all_valid) == list(range(3144)),
        "fold_checks": fold_checks,
        "errors": errors,
    }
    out_path = ROUND / "review" / "saved_output_verification.json"
    out_path.write_text(json.dumps(out_report, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps({"status": out_report["status"], "models": len(fold_checks), "max_abs_proba_diff": max_abs_diff_overall, "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
'''
(NEW / 'review/reinfer_saved.py').write_text(reinfer_code, encoding='utf-8')

write(
    NEW / 'manager/copied_inputs.json',
    dict(
        copied_sha256_before_low_memory_patch=copied,
        source_round='round023',
        prior_round022_fits=2,
        prior_round023_fits=0,
        low_memory_patches={
            'configs/experiment.json': sha(NEW / 'configs/experiment.json'),
            'code/t5_rebuild.py': sha(NEW / 'code/t5_rebuild.py'),
            'code/s1_features.py': sha(NEW / 'code/s1_features.py'),
            'code/run_gate.py': sha(NEW / 'code/run_gate.py'),
            'manager/launch.py': sha(NEW / 'manager/launch.py'),
            'review/verify_gate_result.py': sha(NEW / 'review/verify_gate_result.py'),
            'review/reinfer_saved.py': sha(NEW / 'review/reinfer_saved.py'),
        },
        patch_summary='User-directed low-memory sequential execution: threads=1/n_jobs=1, BELOW_NORMAL_PRIORITY_CLASS, immediate del+gc.collect() after T5 rebuild/S1 period/each LightGBM fit, 1.5GiB entry / 1.0GiB stage / 0.5GiB expected peak / 0.75GiB RSS cap; mathematical features and model specification unchanged',
        source_approval='pending independent reviewer; no approval fabricated by setup',
    ),
)
shutil.copyfile(OLD / 'review/gate_approved_sources.json', NEW / 'manager/inherited_gate_approval.json')
(NEW / 'ROUND_PLAN.md').write_text(
    '# Round024 — low-memory sequential S1 gate recovery\n\n'
    'One paired 8-fit FIT3144 internal 4-fold/seed42 replay under user-directed low-memory background mode (threads=1, n_jobs=1, BELOW_NORMAL_PRIORITY_CLASS, step-by-step del+gc.collect() so T5 rebuilder, S1 period profiles, and LightGBM models never accumulate in RAM). Mathematical features, split, hyperparameters, and gate (candidate>=1833 AND candidate-matched_baseline>=16) are unchanged. Entry threshold is 1.5GiB available RAM, per-stage guard 1.0GiB, expected owned peak 0.5GiB (hard RSS limit 0.75GiB), emergency floor 0.5GiB. No search, retries, raw rescans, full 3-fold or S2.\n\n'
    'Technical goal: complete and independently verify 8 models and paired CV output without disturbing foreground user work. Learning goal: distinguish resource interruption from model failure, and understand how sequential lifetime management (releasing intermediate closures/arrays before fitting) reduces peak RSS.\n',
    encoding='utf-8',
)
preflight['prepared'] = True
write(OLD / 'manager/round024_setup_preflight.json', preflight)
print(json.dumps(dict(prepared=str(NEW), copied_files=len(files), contract=contract)))
