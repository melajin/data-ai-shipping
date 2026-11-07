from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROUND_DIR = Path(__file__).resolve().parents[1]
ROOT = ROUND_DIR.parents[1]
LOG = ROUND_DIR / "logs"
for name, value in {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPYCACHEPREFIX": str(LOG / ".pycache"),
    "TEMP": str(LOG / "temp"), "TMP": str(LOG / "temp"),
    "OMP_NUM_THREADS": "3", "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
}.items():
    os.environ[name] = value
for path in (LOG, LOG / ".pycache", LOG / "temp"):
    path.mkdir(parents=True, exist_ok=True)

import numpy as np
import psutil
import sklearn
from sklearn.model_selection import train_test_split
import lightgbm as lgb

CONFIG_PATH = ROUND_DIR / "configs" / "experiment.json"
INPUT_ROOT = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01")
SOURCE_ROOT = Path(r"D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104")
ART = ROUND_DIR / "artifacts"
PROB_DIR = ART / "probabilities"
MODEL_DIR = ART / "models"
LOG_PATH = LOG / "execution.jsonl"
FIT_LIMIT, TIME_LIMIT = 6, 1800
MANAGER_STOP = datetime(2026, 11, 4, 15, 25, tzinfo=timezone.utc)
PRIOR_ATTEMPT_SECONDS = 23.5393616 + 0.8680143
MIN_FREE_RAM = int(1.5 * 2**30)
FOLDS = (0, 1, 2)
CLASSES = ["연안복합", "자망", "통발", "채낚기연승낚시"]
ALPHAS = (0.0, 0.25, 0.5, 0.75, 1.0)


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def log(event: str, **fields) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time_utc": utc(), "event": event, **fields}, ensure_ascii=False) + "\n")
        f.flush()


def probabilities(p, n: int):
    p = np.asarray(p, dtype=np.float64)
    if p.shape != (n, 4) or not np.isfinite(p).all() or np.any(p < -1e-8) or np.any(p > 1 + 1e-8):
        raise ValueError(f"invalid probability matrix shape/range: {p.shape}")
    if not np.allclose(p.sum(axis=1), 1.0, atol=1e-5, rtol=0):
        raise ValueError("probability row sum outside 1e-5 tolerance")
    return p


def metrics(y, pred):
    y, pred = np.asarray(y, dtype=np.int64), np.asarray(pred, dtype=np.int64)
    if y.ndim != 1 or pred.shape != y.shape or len(y) == 0:
        return {"n": 0}
    cm = np.bincount(y * 4 + pred, minlength=16).reshape(4, 4)
    tp = np.diag(cm).astype(float)
    rec = np.divide(tp, cm.sum(1), out=np.zeros(4), where=cm.sum(1) > 0)
    prec = np.divide(tp, cm.sum(0), out=np.zeros(4), where=cm.sum(0) > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros(4), where=prec + rec > 0)
    correct = int(np.count_nonzero(y == pred))
    return {"n": len(y), "correct": correct, "micro_f1": correct / len(y), "macro_f1": float(f1.mean()),
            "class_recall": rec.tolist(), "class_f1": f1.tolist(), "confusion_matrix": cm.tolist()}


def by_days(y, pred, days):
    out = {}
    for name, lo, hi in (("1-7", 1, 7), ("8-30", 8, 30), ("31-90", 31, 90), ("91+", 91, None)):
        mask = days >= lo if hi is None else (days >= lo) & (days <= hi)
        out[name] = metrics(y[mask], pred[mask])
    mask = ~np.isfinite(days) | (days <= 0)
    if mask.any():
        out["0_or_missing"] = metrics(y[mask], pred[mask])
    return out


def paired(y, ref, cand):
    r, c = ref == y, cand == y
    gain, loss = int(np.count_nonzero(~r & c)), int(np.count_nonzero(r & ~c))
    return {"n": len(y), "reference_correct": int(r.sum()), "candidate_correct": int(c.sum()),
            "newly_correct": gain, "newly_incorrect": loss, "net_additional_correct": gain-loss,
            "micro_delta": float(c.mean() - r.mean())}


def paired_by_days(y, ref, cand, days):
    out = {}
    for name, lo, hi in (("1-7", 1, 7), ("8-30", 8, 30), ("31-90", 31, 90), ("91+", 91, None)):
        mask = days >= lo if hi is None else (days >= lo) & (days <= hi)
        out[name] = paired(y[mask], ref[mask], cand[mask]) if mask.any() else {"n": 0}
    return out


def budget_check(start, stage):
    elapsed = time.perf_counter() - start
    if elapsed + PRIOR_ATTEMPT_SECONDS >= TIME_LIMIT:
        raise TimeoutError(f"30-minute compute budget exhausted before {stage}")
    if datetime.now(timezone.utc) >= MANAGER_STOP:
        raise TimeoutError(f"manager reserve deadline 15:10 UTC reached before {stage}")


def bootstrap_delta(y, ref, cand, seed, reps=5000):
    diff = (cand == y).astype(np.int8) - (ref == y).astype(np.int8)
    rng, values, n = np.random.default_rng(seed), np.empty(reps), len(y)
    for start in range(0, reps, 100):
        count = min(100, reps - start)
        ix = rng.integers(0, n, size=(count, n), dtype=np.int32)
        values[start:start+count] = diff[ix].mean(axis=1)
    return {"unit": "vessel", "repetitions": reps, "seed": seed, "point_delta_micro_f1": float(diff.mean()),
            "ci95_percentile": [float(v) for v in np.quantile(values, [0.025, 0.975])],
            "limitation": "development OUTER interval; does not remove selection bias or establish independent performance"}


def sqrt_weights(y):
    counts = np.bincount(np.asarray(y, dtype=np.int64), minlength=4)
    if np.any(counts == 0):
        raise ValueError(f"FIT lacks class: {counts.tolist()}")
    w = np.sqrt(len(y) / (4 * counts.astype(float)))
    w /= w.mean()
    return w[np.asarray(y, dtype=np.int64)]


def macro_f1_eval(y_true, y_pred):
    y, p = np.asarray(y_true, dtype=np.int64), np.asarray(y_pred)
    if p.ndim == 1:
        p = p.reshape(4, -1).T
    if p.shape != (len(y), 4):
        raise ValueError(f"LightGBM eval prediction shape={p.shape}")
    return "macro_f1", metrics(y, p.argmax(1))["macro_f1"], True


def check_classes(classes, label, fold):
    if not np.array_equal(np.asarray(classes, dtype=np.int64), np.arange(4)):
        raise ValueError(f"{label} fold={fold}: class order {np.asarray(classes).tolist()}")


def save_probs(path, fold, role, ids, y, p):
    p = probabilities(p, len(ids))
    if len(set(ids.tolist())) != len(ids) or len(ids) != len(y):
        raise ValueError(f"fold={fold} {role}: IDs duplicate or misaligned")
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, fold=np.int64(fold), role=np.asarray(role), ids=ids.astype(str),
        y_true=y.astype(np.int64), probabilities=p, predictions=p.argmax(1).astype(np.int64))


def read_probs(fold, model, role):
    path = PROB_DIR / f"fold_{fold}_{model}_{role.lower()}.npz"
    with np.load(path, allow_pickle=False) as z:
        return z["ids"].astype(str), z["y_true"].astype(np.int64), z["probabilities"].astype(float), sha_file(path)


def input_load(fold, cfg):
    path = INPUT_ROOT / f"fold_{fold}_features.npz"
    actual = sha_file(path)
    if actual != cfg["input"]["fold_sha256"][str(fold)]:
        raise ValueError(f"fold={fold} X304 input hash mismatch")
    with np.load(path, allow_pickle=False) as z:
        if set(z.files) != {"fold", "rfid_ids", "y", "roles", "X", "feature_names", "obs_days"}:
            raise ValueError(f"fold={fold} unexpected NPZ keys={z.files}")
        d = {k: z[k].copy() for k in z.files}
    d["ids"], d["roles"], d["names"] = d.pop("rfid_ids").astype(str), d["roles"].astype(str), d["feature_names"].astype(str).tolist()
    d["y"], d["X"], d["obs_days"] = d["y"].astype(np.int64), d["X"].astype(np.float64), d["obs_days"].astype(float)
    if int(d["fold"]) != fold or d["X"].shape != (5897, 304) or len(d["ids"]) != 5897:
        raise ValueError(f"fold={fold} invalid X304 shape")
    if len(set(d["ids"].tolist())) != 5897 or len(d["names"]) != 304 or len(set(d["names"])) != 304:
        raise ValueError(f"fold={fold} duplicated IDs or feature names")
    ordered_names_hash = sha_text(json.dumps(d["names"], ensure_ascii=False, separators=(",", ":")))
    if ordered_names_hash != cfg["input"]["ordered_feature_names_sha256"]:
        raise ValueError(f"fold={fold} ordered feature names hash mismatch")
    if np.isinf(d["X"]).any() or np.any((d["y"] < 0) | (d["y"] > 3)):
        raise ValueError(f"fold={fold} invalid feature values or labels")
    counts = {r: int(np.count_nonzero(d["roles"] == r)) for r in ("FIT", "INNER", "OUTER")}
    expected = {"FIT": 3144 if fold < 2 else 3145, "INNER": 787, "OUTER": 1966 if fold < 2 else 1965}
    if counts != expected or set(np.unique(d["roles"])) != set(expected):
        raise ValueError(f"fold={fold} role counts={counts}")
    d["path"], d["sha256"], d["role_counts"] = path, actual, counts
    return d


def source_hashes():
    paths = {
        "baseline_config": SOURCE_ROOT / "configs/exp01/experiment.json",
        "baseline_eval_contract": SOURCE_ROOT / "shared/eval_contract.py",
        "baseline_data_adapter": SOURCE_ROOT / "shared/data_adapter.py",
        "baseline_runner": SOURCE_ROOT / "experiments/exp01/run_exp01.py",
        "source_data_validation": SOURCE_ROOT / "reports/exp01/data_validation.json",
        "round001_manifest": ROOT / "rounds/round_001/FINAL_MANIFEST.json",
        "round001_replay_code": ROOT / "rounds/round_001/execution/replay_ensemble.py",
        "round002_plan": ROUND_DIR / "ROUND_PLAN.md",
    }
    return {k: {"path": str(p), "bytes": p.stat().st_size, "sha256": sha_file(p)} for k,p in paths.items()}


def create_split(folds, seed):
    roster, detail = [], {}
    for fold, d in folds.items():
        ix = np.flatnonzero(d["roles"] == "INNER")
        es, sel = train_test_split(ix, test_size=0.5, stratify=d["y"][ix], random_state=seed)
        es, sel = np.sort(es), np.sort(sel)
        if set(d["ids"][es].tolist()) & set(d["ids"][sel].tolist()) or len(es)+len(sel) != len(ix):
            raise ValueError(f"fold={fold} ES/SELECT split overlap or loss")
        def counts(q): return {CLASSES[c]: int(np.count_nonzero(d["y"][q] == c)) for c in range(4)}
        detail[str(fold)] = {"inner": len(ix), "inner_es": len(es), "inner_select": len(sel),
            "inner_es_counts": counts(es), "inner_select_counts": counts(sel),
            "inner_es_ids_sha256": sha_text("\n".join(d["ids"][es].tolist())),
            "inner_select_ids_sha256": sha_text("\n".join(d["ids"][sel].tolist())),
            "inner_es_label_sha256": sha_text("\n".join(f"{d['ids'][i]}:{int(d['y'][i])}" for i in es)),
            "inner_select_label_sha256": sha_text("\n".join(f"{d['ids'][i]}:{int(d['y'][i])}" for i in sel))}
        for role, q in (("INNER_ES", es), ("INNER_SELECT", sel)):
            roster.extend({"fold": fold, "role": role, "rfid_id": str(d["ids"][i]), "y_true": int(d["y"][i])} for i in q)
    import csv
    path = ART / "inner_split_roster.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fold", "role", "rfid_id", "y_true"]); w.writeheader(); w.writerows(roster)
    obj = {"random_state": seed, "method": "sklearn train_test_split; test_size=0.5; stratify=INNER labels",
        "class_order": CLASSES, "folds": detail, "roster_rows": len(roster), "roster_sha256": sha_file(path)}
    write_json(ART / "inner_split_manifest.json", obj)
    return obj


def fit_baseline(fold, d, es, sel, fit_num, start):
    budget_check(start, f"baseline fold {fold}")
    fit = np.flatnonzero(d["roles"] == "FIT")
    if len(es) == 0 or len(sel) == 0 or not np.all(d["roles"][es] == "INNER") or not np.all(d["roles"][sel] == "INNER"):
        raise ValueError(f"fold={fold}: invalid explicit ES/SELECT indices")
    free = int(psutil.virtual_memory().available)
    if free < MIN_FREE_RAM: raise MemoryError(f"available RAM {free/2**30:.3f} GiB < 1.5 before baseline fit")
    start = time.perf_counter(); log("fit_started", fold=fold, model="baseline_lightgbm", fit_num=fit_num+1, pid=os.getpid(), ram=free, threads=3)
    m = lgb.LGBMClassifier(objective="multiclass", num_class=4, n_estimators=8000, learning_rate=.01,
        num_leaves=127, min_child_samples=10, colsample_bytree=.6, subsample=.8, subsample_freq=1,
        reg_lambda=1.0, random_state=42, n_jobs=3, verbosity=-1, metric="None")
    m.fit(d["X"][fit], d["y"][fit], sample_weight=sqrt_weights(d["y"][fit]),
        eval_set=[(d["X"][es], d["y"][es])], eval_metric=macro_f1_eval,
        callbacks=[lgb.early_stopping(200, first_metric_only=True, verbose=False)])
    check_classes(m.classes_, "LightGBM", fold)
    live_es, live_sel = probabilities(m.predict_proba(d["X"][es], num_threads=1), len(es)), probabilities(m.predict_proba(d["X"][sel], num_threads=1), len(sel))
    path = MODEL_DIR / f"fold_{fold}_baseline_lightgbm.txt"; path.parent.mkdir(parents=True, exist_ok=True)
    m.booster_.save_model(str(path)); best = int(m.best_iteration_ or 8000); del m
    saved = lgb.Booster(model_file=str(path)); re_es, re_sel = probabilities(saved.predict(d["X"][es], num_threads=1), len(es)), probabilities(saved.predict(d["X"][sel], num_threads=1), len(sel))
    delta_es, delta_sel = float(np.max(np.abs(live_es-re_es))), float(np.max(np.abs(live_sel-re_sel)))
    if max(delta_es, delta_sel) > 1e-12: raise ValueError(f"LightGBM reload max delta {max(delta_es,delta_sel)} > 1e-12")
    save_probs(PROB_DIR / f"fold_{fold}_baseline_lightgbm_inner_es.npz", fold, "INNER_ES", d["ids"][es], d["y"][es], re_es)
    save_probs(PROB_DIR / f"fold_{fold}_baseline_lightgbm_inner_select.npz", fold, "INNER_SELECT", d["ids"][sel], d["y"][sel], re_sel)
    rec = {"model": "baseline_lightgbm", "fold": fold, "fit_num": fit_num+1, "pid": os.getpid(), "free_ram_before_bytes": free,
        "fit_seconds": time.perf_counter()-start, "n_fit": len(fit), "best_iteration": best, "threads": 3,
        "weights": "sqrt inverse frequency from FIT only, normalized mean 1", "early_stop": "unweighted macro F1 on INNER_ES",
        "model_path": str(path), "model_sha256": sha_file(path), "reload_max_abs_inner_es": delta_es, "reload_max_abs_inner_select": delta_sel}
    log("fit_completed", **rec); return rec


def fit_candidate(fold, d, es, sel, cfg, fit_num, start):
    budget_check(start, f"CatBoost candidate fold {fold}")
    from catboost import CatBoostClassifier, Pool
    fit = np.flatnonzero(d["roles"] == "FIT")
    if len(es) == 0 or len(sel) == 0 or not np.all(d["roles"][es] == "INNER") or not np.all(d["roles"][sel] == "INNER"):
        raise ValueError(f"fold={fold}: invalid explicit ES/SELECT indices")
    free = int(psutil.virtual_memory().available)
    if free < MIN_FREE_RAM: raise MemoryError(f"available RAM {free/2**30:.3f} GiB < 1.5 before CatBoost fit")
    tr = LOG / "catboost_train" / f"fold_{fold}"; tr.mkdir(parents=True, exist_ok=True)
    p = cfg["candidate"]
    m = CatBoostClassifier(iterations=3000, depth=6, learning_rate=.03, l2_leaf_reg=3,
        loss_function="MultiClass", eval_metric=p["eval_metric"], random_seed=42,
        task_type="CPU", thread_count=3, nan_mode="Min", od_type="Iter", od_wait=200,
        use_best_model=True, verbose=False, allow_writing_files=True, train_dir=str(tr))
    start = time.perf_counter(); log("fit_started", fold=fold, model="candidate_catboost", fit_num=fit_num+1, pid=os.getpid(), ram=free, threads=3, train_dir=str(tr))
    fit_pool = Pool(d["X"][fit], label=d["y"][fit], feature_names=d["names"])
    es_pool = Pool(d["X"][es], label=d["y"][es], feature_names=d["names"])
    m.fit(fit_pool, eval_set=es_pool, verbose=False)
    check_classes(m.classes_, "CatBoost", fold)
    live_es, live_sel = probabilities(m.predict_proba(d["X"][es], thread_count=3), len(es)), probabilities(m.predict_proba(d["X"][sel], thread_count=3), len(sel))
    path = MODEL_DIR / f"fold_{fold}_candidate_catboost.cbm"; path.parent.mkdir(parents=True, exist_ok=True)
    m.save_model(str(path), format="cbm"); best, trees = int(m.get_best_iteration()), int(m.tree_count_); del m
    saved = CatBoostClassifier(); saved.load_model(str(path), format="cbm"); check_classes(saved.classes_, "CatBoost reload", fold)
    re_es, re_sel = probabilities(saved.predict_proba(d["X"][es], thread_count=3), len(es)), probabilities(saved.predict_proba(d["X"][sel], thread_count=3), len(sel))
    delta_es, delta_sel = float(np.max(np.abs(live_es-re_es))), float(np.max(np.abs(live_sel-re_sel)))
    if max(delta_es, delta_sel) > 1e-12: raise ValueError(f"CatBoost reload max delta {max(delta_es,delta_sel)} > 1e-12")
    save_probs(PROB_DIR / f"fold_{fold}_candidate_catboost_inner_es.npz", fold, "INNER_ES", d["ids"][es], d["y"][es], re_es)
    save_probs(PROB_DIR / f"fold_{fold}_candidate_catboost_inner_select.npz", fold, "INNER_SELECT", d["ids"][sel], d["y"][sel], re_sel)
    rec = {"model": "candidate_catboost", "fold": fold, "fit_num": fit_num+1, "pid": os.getpid(), "free_ram_before_bytes": free,
        "fit_seconds": time.perf_counter()-start, "n_fit": len(fit), "best_iteration_zero_based": best, "tree_count": trees, "threads": 3,
        "sample_weight": "none", "eval_metric": p["eval_metric"], "early_stop": "unweighted Accuracy on INNER_ES, wait 200", "nan_mode": "Min",
        "model_path": str(path), "model_sha256": sha_file(path), "train_dir": str(tr),
        "reload_max_abs_inner_es": delta_es, "reload_max_abs_inner_select": delta_sel}
    log("fit_completed", **rec); return rec


def reuse_attempt1_baseline_fold0(d, es, sel, split_entry, cfg_hash):
    old_dir = LOG / "attempt_01"
    old_manifest = json.loads((old_dir / "launch_manifest.json").read_text(encoding="utf-8-sig"))
    old_config_path = old_dir / "experiment.json"
    old_config = json.loads(old_config_path.read_text(encoding="utf-8-sig"))
    new_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    if old_manifest.get("status") != "failed" or old_manifest.get("config_sha256") != sha_file(old_config_path):
        raise ValueError("attempt 1 manifest/config hash mismatch")
    if old_config.get("candidate", {}).get("eval_metric") != "Accuracy:use_weights=false":
        raise ValueError("attempt 1 config does not have the recorded CatBoost eval metric")
    old_config["candidate"]["eval_metric"] = new_config["candidate"].get("eval_metric")
    old_config["candidate"]["eval_metric_note"] = new_config["candidate"].get("eval_metric_note")
    if old_config != new_config or new_config["candidate"].get("eval_metric") != "Accuracy":
        raise ValueError("baseline reuse only permits candidate eval-metric syntax correction")
    if old_manifest.get("error_type") != "TypeError" or "feature_names" not in old_manifest.get("error", ""):
        raise ValueError("attempt 1 failure is not the recorded CatBoost constructor API error")
    events = [json.loads(line) for line in (old_dir / "execution.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    completed = [e for e in events if e.get("event") == "fit_completed" and e.get("model") == "baseline_lightgbm" and int(e.get("fold", -1)) == 0]
    if len(completed) != 1:
        raise ValueError(f"expected one completed fold0 baseline in attempt1, found={len(completed)}")
    record = completed[0]
    model_path = MODEL_DIR / "fold_0_baseline_lightgbm.txt"
    if sha_file(model_path) != record.get("model_sha256"):
        raise ValueError("attempt1 fold0 model hash mismatch")
    fit_ids = set(d["ids"][d["roles"] == "FIT"].tolist())
    outer_ids = set(d["ids"][d["roles"] == "OUTER"].tolist())
    inner_ids = set(d["ids"][d["roles"] == "INNER"].tolist())
    es_ids, sel_ids = set(d["ids"][es].tolist()), set(d["ids"][sel].tolist())
    if es_ids & sel_ids or es_ids & fit_ids or sel_ids & fit_ids or es_ids & outer_ids or sel_ids & outer_ids or (es_ids | sel_ids) != inner_ids:
        raise ValueError("attempt1 fold0 ES/SELECT role partition failed before reuse")
    for role, ix in (("inner_es", es), ("inner_select", sel)):
        pth = PROB_DIR / f"fold_0_baseline_lightgbm_{role}.npz"
        expected_ids, expected_y = d["ids"][ix], d["y"][ix]
        with np.load(pth, allow_pickle=False) as z:
            if int(z["fold"]) != 0 or str(z["role"].item()).upper() != ("INNER_ES" if role == "inner_es" else "INNER_SELECT"):
                raise ValueError(f"attempt1 fold0 {role} probability role mismatch")
            ids, y, saved = z["ids"].astype(str), z["y_true"].astype(np.int64), probabilities(z["probabilities"], len(ix))
            if ids.tolist() != expected_ids.tolist() or not np.array_equal(y, expected_y):
                raise ValueError(f"attempt1 fold0 {role} IDs/labels mismatch")
            if not np.array_equal(z["predictions"].astype(np.int64), saved.argmax(1)):
                raise ValueError(f"attempt1 fold0 {role} prediction column mismatch")
        loaded = lgb.Booster(model_file=str(model_path))
        replay = probabilities(loaded.predict(d["X"][ix], num_threads=1), len(ix))
        delta = float(np.max(np.abs(replay - saved)))
        if delta > 1e-12:
            raise ValueError(f"attempt1 fold0 {role} saved probability replay delta={delta}")
    reuse = {"source_attempt": 1, "model": "baseline_lightgbm", "fold": 0,
        "config_sha256": cfg_hash, "attempt1_config_sha256": old_manifest["config_sha256"],
        "config_change_scope": "candidate.eval_metric syntax only; same unweighted Accuracy target",
        "input_sha256": d["sha256"], "model_sha256": record["model_sha256"],
        "inner_es_ids_sha256": split_entry["inner_es_ids_sha256"],
        "inner_select_ids_sha256": split_entry["inner_select_ids_sha256"],
        "inner_es_label_sha256": split_entry["inner_es_label_sha256"],
        "inner_select_label_sha256": split_entry["inner_select_label_sha256"],
        "reloaded_saved_probabilities_max_abs_delta": "<=1e-12", "prior_attempt_elapsed_seconds": PRIOR_ATTEMPT_SECONDS,
        "attempt1_exit_code": old_manifest.get("exit_code"), "attempt1_exit_code_status": "unavailable"}
    write_json(ART / "attempt1_baseline_reuse_validation.json", reuse)
    record["reused_from_attempt"] = 1
    record["fit_counted_toward_six"] = True
    log("fit_reused", **reuse)
    return record


def infer_outer(fold, model, d):
    ix = np.flatnonzero(d["roles"] == "OUTER"); path = MODEL_DIR / (f"fold_{fold}_baseline_lightgbm.txt" if model == "baseline_lightgbm" else f"fold_{fold}_candidate_catboost.cbm")
    if model == "baseline_lightgbm":
        p1 = probabilities(lgb.Booster(model_file=str(path)).predict(d["X"][ix], num_threads=1), len(ix))
        p2 = probabilities(lgb.Booster(model_file=str(path)).predict(d["X"][ix], num_threads=1), len(ix))
    else:
        from catboost import CatBoostClassifier
        a, b = CatBoostClassifier(), CatBoostClassifier(); a.load_model(str(path)); b.load_model(str(path))
        check_classes(a.classes_, "CatBoost OUTER", fold); check_classes(b.classes_, "CatBoost OUTER reload", fold)
        p1, p2 = probabilities(a.predict_proba(d["X"][ix], thread_count=3), len(ix)), probabilities(b.predict_proba(d["X"][ix], thread_count=3), len(ix))
    delta = float(np.max(np.abs(p1-p2)))
    if delta > 1e-12: raise ValueError(f"fold={fold} {model} OUTER reload delta={delta}")
    save_probs(PROB_DIR / f"fold_{fold}_{model}_outer.npz", fold, "OUTER", d["ids"][ix], d["y"][ix], p2)
    return p2, {"fold": fold, "model": model, "reload_max_abs_outer": delta, "model_sha256": sha_file(path)}


def run(cfg, start, manifest):
    ART.mkdir(parents=True, exist_ok=True); PROB_DIR.mkdir(parents=True, exist_ok=True); MODEL_DIR.mkdir(parents=True, exist_ok=True)
    src_before = source_hashes()
    inp_before = {str(INPUT_ROOT/f"fold_{f}_features.npz"): sha_file(INPUT_ROOT/f"fold_{f}_features.npz") for f in FOLDS}
    expected = {str(INPUT_ROOT/f"fold_{f}_features.npz"): cfg["input"]["fold_sha256"][str(f)] for f in FOLDS}
    if inp_before != expected: raise ValueError("input hashes differ from frozen config")
    folds = {f: input_load(f, cfg) for f in FOLDS}
    if any(folds[f]["names"] != folds[0]["names"] for f in FOLDS): raise ValueError("304 feature order differs by fold")
    outer_ids = np.concatenate([folds[f]["ids"][folds[f]["roles"] == "OUTER"] for f in FOLDS])
    if len(set(outer_ids.tolist())) != 5897: raise ValueError("OUTER roster is not a unique 5,897 vessel partition")
    split = create_split(folds, cfg["split"]["random_state"]); split_hash = sha_file(ART/"inner_split_manifest.json")
    manifest.update({"input_hashes_before": inp_before, "source_hashes_before": src_before, "split_manifest_sha256": split_hash})
    fit_records, nfit = [], 0
    for fold in FOLDS:
        budget_check(start, f"baseline fold {fold}")
        d = folds[fold]; inner = np.flatnonzero(d["roles"] == "INNER")
        es, sel = train_test_split(inner, test_size=.5, stratify=d["y"][inner], random_state=cfg["split"]["random_state"])
        es, sel = np.sort(es), np.sort(sel)
        es_ids, sel_ids = set(d["ids"][es].tolist()), set(d["ids"][sel].tolist())
        inner_ids = set(d["ids"][inner].tolist())
        fit_ids = set(d["ids"][d["roles"] == "FIT"].tolist())
        outer_ids_fold = set(d["ids"][d["roles"] == "OUTER"].tolist())
        sp = split["folds"][str(fold)]
        es_ids_hash = sha_text("\n".join(d["ids"][es].tolist()))
        sel_ids_hash = sha_text("\n".join(d["ids"][sel].tolist()))
        es_label_hash = sha_text("\n".join(f"{d['ids'][i]}:{int(d['y'][i])}" for i in es))
        sel_label_hash = sha_text("\n".join(f"{d['ids'][i]}:{int(d['y'][i])}" for i in sel))
        if (len(es) == 0 or len(sel) == 0 or es_ids & sel_ids or es_ids & fit_ids or sel_ids & fit_ids
            or es_ids & outer_ids_fold or sel_ids & outer_ids_fold or (es_ids | sel_ids) != inner_ids
            or es_ids_hash != sp["inner_es_ids_sha256"] or sel_ids_hash != sp["inner_select_ids_sha256"]
            or es_label_hash != sp["inner_es_label_sha256"] or sel_label_hash != sp["inner_select_label_sha256"]):
            raise ValueError(f"fold={fold}: ES/SELECT roster, label, or role partition verification failed")
        if fold == 0:
            fit_records.append(reuse_attempt1_baseline_fold0(d, es, sel, split["folds"]["0"], hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()))
            nfit += 1
        else:
            fit_records.append(fit_baseline(fold, d, es, sel, nfit, start)); nfit += 1
        budget_check(start, f"candidate fold {fold}")
        fit_records.append(fit_candidate(fold, d, es, sel, cfg, nfit, start)); nfit += 1
        budget_check(start, "next fold or selection")
    if nfit != FIT_LIMIT: raise ValueError(f"production fit count={nfit}, expected six")

    # Selection is written and hash-frozen before any OUTER prediction/score.
    alpha = {"selection_role": "INNER_SELECT only", "alphas": ALPHAS, "rule": "max correct count; ties choose smaller alpha",
        "outer_used": False, "split_manifest_sha256": split_hash, "folds": {}}
    for fold in FOLDS:
        bi, by, bp, bh = read_probs(fold, "baseline_lightgbm", "inner_select")
        ci, cy, cp, ch = read_probs(fold, "candidate_catboost", "inner_select")
        if bi.tolist()!=ci.tolist() or not np.array_equal(by,cy): raise ValueError(f"fold={fold} SELECT pair mismatch")
        choices=[]
        for a in ALPHAS:
            correct=int(np.count_nonzero(((1-a)*bp+a*cp).argmax(1)==by)); choices.append({"alpha":a,"correct":correct,"n":len(by),"micro_f1":correct/len(by)})
        best=sorted(choices,key=lambda x:(-x["correct"],x["alpha"]))[0]
        alpha["folds"][str(fold)]={"candidate_scores":choices,"chosen_alpha":best["alpha"],"baseline_probability_sha256":bh,"candidate_probability_sha256":ch}
    alpha_path=ART/"alpha_selection_frozen.json"; write_json(alpha_path,alpha); alpha_hash=sha_file(alpha_path)
    log("alpha_frozen",path=str(alpha_path),sha256=alpha_hash,choices={f:alpha["folds"][str(f)]["chosen_alpha"] for f in FOLDS})

    fold_results={}; pooled={k:[] for k in ("ids","y","days","baseline","candidate","blend")}; reload=[]
    for fold in FOLDS:
        d=folds[fold]; bi,by,bp,_=read_probs(fold,"baseline_lightgbm","inner_select"); ci,cy,cp,_=read_probs(fold,"candidate_catboost","inner_select")
        if sha_file(alpha_path)!=alpha_hash: raise RuntimeError("alpha freeze changed before OUTER inference")
        bprob,bcheck=infer_outer(fold,"baseline_lightgbm",d); cprob,ccheck=infer_outer(fold,"candidate_catboost",d); reload += [bcheck,ccheck]
        ix=np.flatnonzero(d["roles"]=="OUTER"); y=d["y"][ix]; days=d["obs_days"][ix]; ids=d["ids"][ix]
        a=float(alpha["folds"][str(fold)]["chosen_alpha"]); blendp=probabilities((1-a)*bprob+a*cprob,len(ix))
        save_probs(PROB_DIR/f"fold_{fold}_blend_outer.npz",fold,"OUTER",ids,y,blendp)
        b,c,bp= bprob.argmax(1),cprob.argmax(1),blendp.argmax(1)
        fold_results[str(fold)]={"n":len(y),"chosen_alpha":a,"baseline":metrics(y,b),"candidate":metrics(y,c),"blend":metrics(y,bp),
            "paired_candidate_vs_baseline":paired(y,b,c),"paired_blend_vs_baseline":paired(y,b,bp),
            "obs_days":{"baseline":by_days(y,b,days),"candidate":by_days(y,c,days),"blend":by_days(y,bp,days)},
            "paired_by_obs_days":{"candidate_vs_baseline":paired_by_days(y,b,c,days),"blend_vs_baseline":paired_by_days(y,b,bp,days)},
            "outer_ids_sha256":sha_text("\n".join(ids.tolist()))}
        for k,v in (("ids",ids),("y",y),("days",days),("baseline",b),("candidate",c),("blend",bp)): pooled[k].extend(v.tolist())
    ids=np.asarray(pooled["ids"],str); y=np.asarray(pooled["y"],np.int64); days=np.asarray(pooled["days"],float)
    b=np.asarray(pooled["baseline"],np.int64); c=np.asarray(pooled["candidate"],np.int64); bp=np.asarray(pooled["blend"],np.int64)
    if len(ids)!=5897 or len(set(ids.tolist()))!=5897: raise ValueError("pooled OUTER is not 5,897 unique development vessels")
    pooled_result={"n":len(y),"baseline":metrics(y,b),"candidate":metrics(y,c),"blend":metrics(y,bp),
        "paired_candidate_vs_baseline":paired(y,b,c),"paired_blend_vs_baseline":paired(y,b,bp),
        "obs_days":{"baseline":by_days(y,b,days),"candidate":by_days(y,c,days),"blend":by_days(y,bp,days)},
        "paired_by_obs_days":{"candidate_vs_baseline":paired_by_days(y,b,c,days),"blend_vs_baseline":paired_by_days(y,b,bp,days)},
        "paired_bootstrap95_candidate_vs_baseline":bootstrap_delta(y,b,c,cfg["bootstrap"]["seed"],cfg["bootstrap"]["repetitions"]),
        "paired_bootstrap95_blend_vs_baseline":bootstrap_delta(y,b,bp,cfg["bootstrap"]["seed"],cfg["bootstrap"]["repetitions"])}
    inp_after={str(INPUT_ROOT/f"fold_{f}_features.npz"):sha_file(INPUT_ROOT/f"fold_{f}_features.npz") for f in FOLDS}; src_after=source_hashes()
    if inp_after!=inp_before or src_after!=src_before: raise RuntimeError("read-only input/source hashes changed")
    import catboost
    result={"experiment":"round002 CatBoost pipeline versus re-fitted sqrt_macro LightGBM seed42",
        "status":"completed","started_at_utc":manifest["started_at_utc"],"finished_at_utc":utc(),"elapsed_seconds":time.perf_counter()-start,
        "scope":{"development_only":True,"rows":5897,"holdout_individual_rows_read":0,"raw_data_read":False,"source_repo_modified":False,
            "feature_count":304,"class_order":CLASSES,"new_production_fits":nfit,"outer_used_for_training_or_selection":False,
            "outer_inference_after_alpha_freeze":True},"environment":{"python":sys.version,"executable":sys.executable,"numpy":np.__version__,"sklearn":sklearn.__version__,"lightgbm":lgb.__version__,"catboost":catboost.__version__,"psutil":psutil.__version__},
        "input_hashes_before":inp_before,"input_hashes_after":inp_after,"source_hashes":src_before,"split_manifest_sha256":split_hash,
        "prior_attempts":[
            {"attempt":1,"elapsed_seconds":23.5393616,"exit_code":"unavailable","failure":"CatBoostClassifier constructor rejected feature_names; no CatBoost fit started"},
            {"attempt":2,"elapsed_seconds":0.8680143,"exit_code":1,"failure":"CatBoost rejected explicit use_weights=false before iteration"}],
        "prior_attempts_elapsed_seconds":PRIOR_ATTEMPT_SECONDS,
        "alpha_selection_sha256":alpha_hash,"alpha_selection":alpha,"fit_records":fit_records,"outer_reload_checks":reload,
        "folds":fold_results,"pooled_development_outer":pooled_result,
        "prior_context":{"sqrt_macro_5seed_development_micro_f1":0.5930133966423605,"macro_f1":0.5252719738966167,
            "not_directly_comparable":"this uses a new one-seed baseline with split INNER early stopping"},
        "limits":["Previously exposed development OUTER, not independent validation.","Existing X304 T5/local_rel caches retain documented population conditions.","Pipeline comparison includes model, objective, weighting, missing-value treatment and package versions; not a pure model-family causal effect.","Bootstrap does not remove candidate-selection bias."]}
    write_json(ART/"result.json",result); return result


def main():
    start=time.perf_counter(); started=utc(); cfg_bytes=CONFIG_PATH.read_bytes(); cfg=json.loads(cfg_bytes.decode("utf-8-sig")); cfg_hash=hashlib.sha256(cfg_bytes).hexdigest()
    ram=psutil.virtual_memory(); refs=source_hashes(); snap=ART/"run_snapshot"; snap.mkdir(parents=True,exist_ok=True)
    shutil.copy2(Path(__file__).resolve(),snap/"run_round002.py"); shutil.copy2(CONFIG_PATH,snap/"experiment.json"); shutil.copy2(ROUND_DIR/"ROUND_PLAN.md",snap/"ROUND_PLAN.md")
    handoff_path = ROOT / "NEXT_SESSION.md"
    handoff_sha = sha_file(handoff_path) if handoff_path.is_file() else None
    if handoff_sha is not None:
        shutil.copy2(handoff_path, snap / "NEXT_SESSION_at_launch.md")
    if sha_file(snap/"experiment.json")!=cfg_hash: raise RuntimeError("config snapshot hash mismatch")
    script=Path(__file__).resolve()
    snapshot_hash=sha_file(snap/"run_round002.py")
    if snapshot_hash != sha_file(script): raise RuntimeError("runner snapshot hash mismatch")
    manifest={"status":"running","pid":os.getpid(),"parent_pid":os.getppid(),"command":[sys.executable,*sys.argv],"cwd":str(Path.cwd()),
        "started_at_utc":started,"config_sha256":cfg_hash,"source_hashes_at_start":refs,"start_available_ram_bytes":int(ram.available),
        "next_session_sha256_at_launch":handoff_sha,
        "runner_sha256":sha_file(script),"runner_snapshot_sha256":snapshot_hash,
        "plan_snapshot_sha256":sha_file(snap/"ROUND_PLAN.md"),
        "manager_reserve_deadline_utc":MANAGER_STOP.isoformat(),"prior_attempt_elapsed_seconds":PRIOR_ATTEMPT_SECONDS,
        "max_production_fits":FIT_LIMIT,"threads_max":3,"compute_limit_seconds":TIME_LIMIT,"exit_code":None,"fit_records":[]}
    manifest_path=LOG/"launch_manifest.json"; write_json(manifest_path,manifest)
    try:
        result=run(cfg,start,manifest)
        manifest.update({"status":"completed","finished_at_utc":utc(),"exit_code":0,"elapsed_seconds":time.perf_counter()-start,
            "result_path":str(ART/"result.json"),"result_sha256":sha_file(ART/"result.json"),"fit_records":result["fit_records"]})
        write_json(manifest_path,manifest)
        print(json.dumps({"status":"completed","exit_code":0,"result":str(ART/"result.json")},ensure_ascii=False),flush=True)
        return 0
    except BaseException as exc:
        manifest.update({"status":"failed","finished_at_utc":utc(),"exit_code":1,"elapsed_seconds":time.perf_counter()-start,
            "error_type":type(exc).__name__,"error":str(exc),"traceback":traceback.format_exc()})
        write_json(manifest_path,manifest); log("execution_failed",error_type=type(exc).__name__,error=str(exc)); raise


if __name__ == "__main__":
    sys.exit(main())
