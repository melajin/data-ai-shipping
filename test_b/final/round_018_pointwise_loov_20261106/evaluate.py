"""One preregistered pointwise-geometry LOOV experiment; no legacy runner imports."""
from __future__ import annotations

import os
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"
import argparse
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FLEET = ROOT / "testB/final/round_017_fleet_negatives_20261106/execution_001"
TRUTH = ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"
FILES = [FLEET / f"hourly_{i:02d}.parquet" for i in range(1, 7)]
FEATURES = ["len_m", "bbox_m", "n_coords"]
COLUMNS = ["rfid_id", "ts", "source_ordinal", *FEATURES]
RESERVE_MIB = 640


def now():
    return datetime.now().astimezone().isoformat()


def write_json(path, data):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def memory_gate(stage, estimate_mib, basis, log):
    import psutil
    processes = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            processes.append({"pid": p.pid, "name": p.info["name"],
                              "rss_mib": round(p.info["memory_info"].rss / 2**20, 2)})
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            pass
    available = psutil.virtual_memory().available / 2**20
    rec = {"stage": stage, "checked_at": now(), "available_mib": available,
           "estimated_peak_mib": estimate_mib, "reserve_mib": RESERVE_MIB,
           "estimate_basis": basis, "own_rss_mib": psutil.Process().memory_info().rss / 2**20,
           "top_running_processes": sorted(processes, key=lambda p: -p["rss_mib"])[:12],
           "python_processes": [p for p in processes if "python" in (p["name"] or "").lower()],
           "allowed": available >= estimate_mib + RESERVE_MIB}
    with Path(log).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if not rec["allowed"]:
        raise MemoryError(f"DEFERRED {stage}: {available:.1f} < {estimate_mib}+640 MiB")
    return rec


def frozen_paths():
    return [HERE / "PROTOCOL.md", HERE / "evaluate.py", TRUTH, *FILES]


def validate_paths():
    root = ROOT.resolve(strict=True)
    for path in frozen_paths():
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"Input path escapes authorized workspace: {path.name}")


def freeze():
    validate_paths()
    if (HERE / "freeze.json").exists() or (HERE / "execution_001").exists():
        raise RuntimeError("Freeze/execution already exists; no overwrites")
    gate = memory_gate("freeze", 128, "1MiB sequential hash buffer; no data frames loaded",
                       HERE / "memory_preflight.jsonl")
    rec = {"frozen_at": now(), "protocol": "pointwise quadratic ridge logistic LOOV v1",
           "evaluation_count_authorized": 1, "memory": gate,
           "files": {str(p.relative_to(ROOT)): {"sha256": digest(p), "bytes": p.stat().st_size}
                     for p in frozen_paths()},
           "baseline": {"hits": 3, "vessels": 82, "source": "user supplied fixed benchmark"},
           "agents": [
               {"task": "/root/rule_design", "role": "astra_decision", "requested_model": "gpt-6-astra",
                "requested_effort": "high", "evidence": "spawn_agent returned task_name /root/rule_design; decision returned; runtime internals not independently attested"},
               {"task": "/root/contract_review", "role": "sol_review", "requested_model": "gpt-6.1-sol",
                "requested_effort": "high", "evidence": "spawn_agent returned task_name /root/contract_review; read-only review returned; runtime internals not independently attested"}],
           "parent_model_changed": False}
    write_json(HERE / "freeze.json", rec)
    print(json.dumps({"frozen_at": rec["frozen_at"], "files": len(rec["files"])}), flush=True)


def check_frozen(rec):
    validate_paths()
    if set(rec["files"]) != {str(p.relative_to(ROOT)) for p in frozen_paths()}:
        raise RuntimeError("Frozen manifest differs from exact input allowlist")
    for relative, entry in rec["files"].items():
        if digest(ROOT / relative) != entry["sha256"]:
            raise RuntimeError(f"Frozen hash changed: {relative}")


def window_mask(ts, accidents):
    import numpy as np
    hit = np.zeros(len(ts), dtype=bool)
    for acc in accidents:
        hit |= np.abs(ts - int(acc)) <= 6
    return hit


def basis(log_values, center, scale):
    import numpy as np
    z = np.clip((log_values - center) / scale, -5.0, 5.0)
    return np.column_stack([z, z * z, z[:, 0] * z[:, 1], z[:, 0] * z[:, 2], z[:, 1] * z[:, 2]])


def build_training(groups, training_truth, heldout):
    import numpy as np
    assert heldout not in groups and heldout not in training_truth
    assert set(groups) <= set(training_truth)
    active = [(key, group) for key, group in sorted(groups.items()) if len(group["ts"])]
    if not active:
        raise ValueError("No training candidates")
    logs, ys, weights, audit = [], [], [], []
    for key, group in active:
        y = window_mask(group["ts"], training_truth[key]).astype(float)
        present = np.unique(y)
        w = np.empty(len(y), dtype=float)
        for cls in present:
            mask = y == cls
            w[mask] = 1.0 / (len(active) * len(present) * int(mask.sum()))
        logs.append(group["log_geometry"])
        ys.append(y)
        weights.append(w)
        audit.append({"rfid_id": key, "rows": len(y), "positive_rows": int(y.sum()),
                      "weight_sum": float(w.sum())})
    raw = np.concatenate(logs)
    q25, center, q75 = np.percentile(raw, [25, 50, 75], axis=0, method="linear")
    scale = q75 - q25
    scale[scale == 0] = 1.0
    return basis(raw, center, scale), np.concatenate(ys), np.concatenate(weights), center, scale, audit


def fit_predict(groups, training_truth, heldout, test):
    import numpy as np
    from scipy.optimize import minimize
    from scipy.special import expit
    x, y, w, center, scale, audit = build_training(groups, training_truth, heldout)
    assert np.isclose(w.sum(), 1.0)
    if len(np.unique(y)) != 2:
        raise ValueError("Training fold has one global class: no finite unpenalized-intercept optimum")

    def objective(theta):
        eta = theta[0] + x @ theta[1:]
        loss = np.sum(w * (np.logaddexp(0, eta) - y * eta)) + 0.005 * (theta[1:] @ theta[1:])
        residual = w * (expit(eta) - y)
        gradient = np.r_[residual.sum(), x.T @ residual + 0.01 * theta[1:]]
        return loss, gradient

    result = minimize(objective, np.zeros(10), jac=True, method="L-BFGS-B",
                      options={"maxiter": 1000, "ftol": 1e-12, "gtol": 1e-8, "maxls": 50})
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError(f"Optimizer failed for fold {heldout}: {result.message}")
    score = result.x[0] + basis(test["log_geometry"], center, scale) @ result.x[1:]
    if not np.isfinite(score).all():
        raise ValueError("Nonfinite prediction")
    fold = {"heldout": heldout, "train_vessels": len(audit), "train_rows": len(y),
            "heldout_in_fit": False, "training_ids": [a["rfid_id"] for a in audit],
            "training_vessel_weights": audit, "center": center.tolist(), "scale": scale.tolist(),
            "coefficients_intercept_first": result.x.tolist(), "optimizer_success": bool(result.success),
            "optimizer_message": str(result.message), "iterations": int(result.nit),
            "objective": float(result.fun), "gradient_max_abs": float(np.max(np.abs(result.jac)))}
    return score, fold


def best_index(score, source_ordinal, ts):
    import numpy as np
    return int(np.lexsort((ts, source_ordinal, -score))[0])


def worst_overlap(hits, baseline=3, n=82):
    from scipy.stats import binom
    cases = []
    for overlap in range(max(0, hits + baseline - n), min(hits, baseline) + 1):
        gains, losses = hits - overlap, baseline - overlap
        p = float(binom.sf(gains - 1, gains + losses, 0.5)) if gains + losses else 1.0
        cases.append({"overlap": overlap, "gains": gains, "losses": losses, "one_sided_p": p})
    return {"worst_one_sided_p": max(c["one_sided_p"] for c in cases), "possible_overlaps": cases}


def poisson_binomial(probabilities, hits):
    import numpy as np
    pmf = np.array([1.0])
    for p in probabilities:
        pmf = np.convolve(pmf, [1 - p, p])
    return float(pmf[hits:].sum()), pmf


def selftest():
    import numpy as np
    assert window_mask(np.array([0, 6, 7, 14, 20, 26, 27]), [0, 20]).tolist() == [True, True, False, True, True, True, False]
    assert best_index(np.array([1., 1., 0.]), np.array([10, 3, 1]), np.array([1, 2, 3])) == 1
    assert best_index(np.array([1., 1.]), np.array([3, 3]), np.array([5, 4])) == 1
    assert worst_overlap(9)["worst_one_sided_p"] > 0.05
    assert worst_overlap(10)["worst_one_sided_p"] <= 0.05
    p, pmf = poisson_binomial([0.5, 0.5], 2)
    assert p == 0.25 and np.allclose(pmf, [0.25, 0.5, 0.25])
    toy = {"a": {"ts": np.array([0, 20]), "log_geometry": np.array([[0., 1., 2.], [1., 2., 3.]])}}
    x, y, w, center, scale, audit = build_training(toy, {"a": [0]}, "heldout")
    assert y.tolist() == [1., 0.] and np.allclose(w, [0.5, 0.5])
    assert np.allclose(center, [0.5, 1.5, 2.5]) and x.shape == (2, 9)
    try:
        build_training(toy, {"a": [0]}, "a")
    except AssertionError:
        pass
    else:
        raise AssertionError("Heldout leakage guard failed")
    score, audit = fit_predict(toy, {"a": [0]}, "heldout", toy["a"])
    assert score[0] > score[1] and audit["optimizer_success"]
    result = {"checked_at": now(), "kind": "synthetic code checks, not actual-data performance",
              "checks": ["multi-event inclusive union", "source ordinal and ts tie", "h=9/10 significance boundary",
                         "Poisson-binomial", "train-only transform and weights", "heldout exclusion guard", "optimizer toy"],
              "passed": True}
    write_json(HERE / "synthetic_checks.json", result)
    print(json.dumps(result), flush=True)


def load_cohort(out):
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq
    truth = pd.read_csv(TRUTH, dtype={"rfid_id": str}, encoding="utf-8-sig")
    if len(truth) != 100 or truth.rfid_id.nunique() != 82 or truth.acc_id.duplicated().any():
        raise ValueError("Truth cardinality or event identity contract failed")
    if truth[["rfid_id", "acc_ts"]].isna().any().any():
        raise ValueError("Missing truth keys")
    at = pd.to_numeric(truth.acc_ts, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(at).all() or not np.equal(at, np.floor(at)).all():
        raise ValueError("acc_ts must be finite integer source hour")
    truth["acc_ts"] = at.astype(np.int64)
    ids = set(truth.rfid_id)
    frames, fleet_ids, file_counts = [], set(), {}
    kept_bytes = 0
    lower = int(pd.Timestamp("2026-01-01").timestamp() // 3600)
    upper = int(pd.Timestamp("2026-07-01").timestamp() // 3600)
    if not ((at >= lower) & (at < upper)).all():
        raise ValueError("Truth outside authorized 2026 Jan-Jun source-hour range")
    for path in FILES:
        total = 0
        pf = pq.ParquetFile(path)
        expected_types = {"rfid_id": "string", "ts": "int64", "source_ordinal": "int64",
                          "len_m": "double", "bbox_m": "double", "n_coords": "int64"}
        if any(str(pf.schema_arrow.field(name).type) != kind for name, kind in expected_types.items()):
            raise ValueError("Parquet key/geometry schema contract changed")
        for batch in pf.iter_batches(batch_size=32768, columns=COLUMNS, use_threads=False):
            frame = batch.to_pandas()
            total += len(frame)
            fleet_ids.update(frame.rfid_id.unique())
            if frame[COLUMNS].isna().any().any():
                raise ValueError("Missing value in required geometry/key input")
            geometry = frame[FEATURES].to_numpy(dtype=float)
            if not np.isfinite(geometry).all() or (geometry < 0).any():
                raise ValueError("Invalid geometry; no candidate filtering allowed")
            if not ((frame.ts >= lower) & (frame.ts < upper)).all():
                raise ValueError("Fleet time outside Jan-Jun 2026")
            selected = frame.loc[frame.rfid_id.isin(ids), COLUMNS].copy()
            if len(selected):
                kept_bytes += int(selected.memory_usage(deep=True).sum())
                if kept_bytes > 128 * 2**20:
                    raise MemoryError("DEFERRED retained-cohort cap 128MiB exceeded; no full load attempted")
                frames.append(selected)
        if total != pf.metadata.num_rows:
            raise ValueError("Parquet row-count mismatch")
        file_counts[path.name] = total
        print(f"Scanned {path.name}: {total:,} rows; retained memory {kept_bytes / 2**20:.1f} MiB", flush=True)
    if sum(file_counts.values()) != 3887065 or len(fleet_ids) != 7372:
        raise ValueError("Fleet cardinality differs from supplied contract")
    cohort = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    groups = {}
    for key in sorted(ids):
        one = cohort.loc[cohort.rfid_id == key].sort_values(["ts", "source_ordinal"], kind="stable")
        groups[key] = {"ts": one.ts.to_numpy(dtype=np.int64),
                       "source_ordinal": one.source_ordinal.to_numpy(dtype=np.int64),
                       "log_geometry": np.log1p(one[FEATURES].to_numpy(dtype=float))}
    audit = {"files": file_counts, "fleet_rows": sum(file_counts.values()), "fleet_vessels": len(fleet_ids),
             "cohort_rows": len(cohort), "truth_events": len(truth), "truth_vessels": len(ids),
             "multi_accident_vessels": int((truth.groupby("rfid_id").size() > 1).sum()),
             "retained_dataframe_mib": kept_bytes / 2**20, "geometry_contract_passed": True,
             "time_contract": "naive integer epoch hours, no timezone conversion",
             "model_features": FEATURES, "new_identity_mapping": False, "regional_prior_used": False,
             "noncohort_vessels_used_for_training": False}
    write_json(out / "input_audit.json", audit)
    return truth, groups, audit


def evaluate_predictions(truth, groups, predictions):
    import numpy as np
    import pandas as pd
    pred = {p["rfid_id"]: p for p in predictions}
    vessel_rows, event_rows = [], []
    for key, events in truth.groupby("rfid_id", sort=True):
        p = pred[key]
        timestamps = groups[key]["ts"]
        unique_ts = np.unique(timestamps)
        acc = events.acc_ts.to_numpy(dtype=np.int64)
        guess = p["pred_ts"]
        error = min(abs(guess - int(t)) for t in acc) if guess is not None else math.inf
        unique_hits = int(window_mask(unique_ts, acc).sum())
        row_hits = int(window_mask(timestamps, acc).sum())
        v = {**p, "n_events": len(events), "n_unique_hours": len(unique_ts),
             "eligible_unique_hours": unique_hits, "eligible_rows": row_hits,
             "chance_unique_hour": unique_hits / len(unique_ts) if len(unique_ts) else 0.0,
             "chance_row": row_hits / len(timestamps) if len(timestamps) else 0.0,
             "min_abs_error_h": error, "hit_pm6h": error <= 6}
        vessel_rows.append(v)
        for _, event in events.iterrows():
            event_error = abs(guess - int(event.acc_ts)) if guess is not None else math.inf
            event_rows.append({"acc_id": event.acc_id, "rfid_id": key, "tier": event.tier,
                               "acc_ts": int(event.acc_ts), "pred_ts": guess,
                               "abs_error_h": event_error, "event_hit_pm6h": event_error <= 6,
                               "vessel_min_abs_error_h": error, "vessel_hit_pm6h": error <= 6,
                               "vessel_n_events": len(events), "prediction_status": p["prediction_status"]})
    return pd.DataFrame(vessel_rows), pd.DataFrame(event_rows)


def render_report(summary, out):
    s = summary
    outcome = "채택(개발셋 내 명목 기준)" if s["accepted"] else "기각"
    primary, chance = s["primary"], s["chance"]
    lines = ["# ROUND018 사고시각 top-1 개선 평가", "", f"**판정: {outcome}.**", "",
             f"제공된 2026 잠정 연결 정답에서 **{primary['hits']}/82 ({primary['rate']:.4%})**가 ±6시간에 적중했다. "
             f"고정 기준선은 3/82 (3.6585%)다. 선박별 최소 절대 오차 중앙값은 **{primary['median_abs_error_h']}시간**이다.", "",
             f"고유 관측시간 균등선택의 정확한 기대는 **{chance['expected_hits']:.4f}/82 ({chance['expected_rate']:.4%})**이며, "
             f"우연모델 단측 p={chance['one_sided_p']:.8g}다. 기준선과 가능한 적중 겹침 전체에서 최악의 단측 p="
             f"{s['baseline_comparison']['worst_one_sided_p']:.8g}다.", "",
             "## 사전 고정과 평가 단위", "",
             f"고정 시각: {s['frozen_at']}. 예측 저장 시각: {s['predictions_saved_at']}. 평가 종료: {s['completed_at']}.", "",
             "[사전 규칙](PROTOCOL.md)과 [동결 해시](freeze.json)는 자료 학습·평가 전에 저장했다. "
             "부분선 길이·경계상자 크기·좌표 수의 log1p, 학습 자료 중앙값/IQR 정규화, 2차 9개 특징, "
             "선박·클래스 균형 ridge logistic(λ=0.01)을 사용했다. 모든 하이퍼파라미터·동점 처리·검정을 사전 고정했고 결과 후 변경하지 않았다.", "",
             "82회 LOOV에서 해당 선박의 모든 관측과 모든 사고를 학습/정규화에서 제외했다. 점수 최댓값 한 개를 선택하고 "
             "동점은 원래 source_ordinal, 이어 ts 순이다. 날짜·좌표·ID·시간 간격·점프·지역 사전확률을 특징으로 쓰지 않았다. "
             "2025 테스트, 새로운 재식별/ID 연결, 외부 자료는 사용하지 않았다. 기준선은 제공된 3/82를 사용했으며 기준선 함수를 다시 적합하거나 변경하지 않았다.", "",
             f"분모는 **82척**이며 정답은 **100사건**, 다중사고 선박은 **{s['input']['multi_accident_vessels']}척**이다. "
             "다중사고 선박은 모든 사고에 대한 최소 오차로 한 번만 센다. 사건별 CSV의 100행 적중은 보조 기록이며 h의 분모가 아니다.", "",
             f"고유 후보시간 중위수 {primary['median_candidate_hours']}; 원본 후보행 중위수 {primary['median_candidate_rows']}. "
             f"후보가 하나라도 사고창에 들어오는 선박 {primary['oracle_support_vessels']}/82. "
             "13시간/중위 후보 수 근사는 다중사고·관측 공백·중복을 반영하지 않아 이번 정확한 기대와 다를 수 있다.", "",
             "## 판정 근거", "",
             *[f"- {reason}" for reason in s["decision_reasons"]], "",
             "채택은 H>3, 기준선 최악 겹침 p≤0.05, 우연모델 p≤0.05, 계약/수렴/무결성 통과를 모두 요구한다. "
             "기준선 적중 선박의 명단을 추가로 읽지 않았으므로 가능한 겹침 중 가장 불리한 p를 썼다. 결과를 본 뒤 다른 창·가중치·모델로 재평가하지 않았다.", "",
             "## 검증과 해석 한계", "",
             f"전체 입력 {s['input']['fleet_rows']:,}행/{s['input']['fleet_vessels']:,}척을 청크 검사했고, "
             f"학습·예측 대상 {s['input']['cohort_rows']:,}행만 유지했다. 원자료·프로토콜·코드 전후 SHA256 일치. "
             f"82개 제외선박 모형 수렴 성공. 실행 시간 {s['elapsed_seconds']:.1f}초, 프로세스 최대 RAM {s['peak_process_mib']:.1f}MiB.", "",
             "합성 코드 검사는 창 합집합, 동점, 가중치, 학습 제외, 검정 계산을 확인했다. 별도로 실제 2026 자료를 한 번 평가했다. "
             "학습의 사고창 밖은 대조군이며 확인된 정상은 아니다. 미기록 사고나 잠정 연결의 오류가 있을 수 있다.", "",
             "이 h는 **내부 사고시각 적중률**이며 공식 F1이 아니다. 반복 사용한 개발자료와 중첩 LOOV 학습으로 검정의 명목 p값은 "
             "독립 외부자료에서 확인된 유의성이 아니다. 전체 기간의 기하를 이용한 사후 분석이며 실시간 탐지·경보 지연·실제 장치 동작을 검증하지 않았다. "
             "오차 중앙값은 탐지 해상도가 아니다.", "",
             "학습 확인 질문: 왜 이상점수 최대값과 사고시각 일치는 별개의 목표인가? 왜 다중사고를 선박 단위로 함께 제외해야 하는가? "
             "왜 우연 기대를 관측된 시간 후보와 사고창 합집합으로 계산하는가?", "",
             "## 산출물", "",
             "- [평가 코드](evaluate.py), [합성 검사](synthetic_checks.json), [사전 고정](PROTOCOL.md)",
             "- [요약](execution_001/summary.json), [사건별 100행](execution_001/event_results.csv), [선박별 82행](execution_001/vessel_results.csv)",
             "- [예측 선저장](execution_001/predictions.csv), [제외선박 학습 기록](execution_001/fold_audit.jsonl)",
             "- [RAM 게이트](execution_001/memory_gates.jsonl), [입력 계약](execution_001/input_audit.json), [무결성](execution_001/integrity.json)", ""]
    with (HERE / "ROUND018_report.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run():
    import psutil
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    check_frozen(frozen)
    # Admission is checked before creating the one-shot execution directory.
    memory_gate("run_admission", 768, "sequential 32768-row batches; retained frame cap 128MiB; no fleet concat",
                HERE / "memory_preflight.jsonl")
    out = HERE / "execution_001"
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    write_json(out / "started.json", {"started_at": now(), "freeze_sha256": digest(HERE / "freeze.json"),
                                     "command": "python evaluate.py --run", "one_shot": True})
    try:
        memory_gate("load", 768, "data imports plus sequential source batches and retained frame cap 128MiB",
                    out / "memory_gates.jsonl")
        import numpy as np
        import pandas as pd
        import scipy
        import pyarrow
        truth, groups, input_audit = load_cohort(out)
        estimate = max(768, math.ceil(input_audit["retained_dataframe_mib"] * 6 + 256))
        memory_gate("training", estimate, "six times retained cohort bytes plus 256MiB libraries; minimum768; one BLAS thread",
                    out / "memory_gates.jsonl")
        times = truth.groupby("rfid_id").acc_ts.agg(list).to_dict()
        predictions = []
        for index, key in enumerate(sorted(groups), 1):
            test = groups[key]
            training = {k: g for k, g in groups.items() if k != key}
            training_truth = {k: events for k, events in times.items() if k != key}
            scores, audit = fit_predict(training, training_truth, key, test)
            if len(scores):
                best = best_index(scores, test["source_ordinal"], test["ts"])
                pred = {"rfid_id": key, "pred_ts": int(test["ts"][best]),
                        "source_ordinal": int(test["source_ordinal"][best]), "peak_logit": float(scores[best]),
                        "n_rows": len(scores), "prediction_status": "predicted"}
            else:
                pred = {"rfid_id": key, "pred_ts": None, "source_ordinal": None,
                        "peak_logit": None, "n_rows": 0, "prediction_status": "no_candidates"}
            predictions.append(pred)
            with (out / "fold_audit.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(audit, ensure_ascii=False, allow_nan=False) + "\n")
            if index % 10 == 0 or index == 82:
                print(f"Prediction folds completed {index}/82 (no hit metrics evaluated)", flush=True)
        # Evaluation only after all out-of-vessel predictions have been persisted.
        pd.DataFrame(predictions).to_csv(out / "predictions.csv", index=False, encoding="utf-8-sig", mode="x")
        saved_at = now()
        write_json(out / "predictions_sealed.json", {"saved_at": saved_at, "sha256": digest(out / "predictions.csv"),
                                                   "predictions": len(predictions), "hit_metrics_evaluated": False})
        vessels, events = evaluate_predictions(truth, groups, predictions)
        assert len(vessels) == 82 and len(events) == 100
        vessels.to_csv(out / "vessel_results.csv", index=False, encoding="utf-8-sig", mode="x")
        events.to_csv(out / "event_results.csv", index=False, encoding="utf-8-sig", mode="x")
        hits = int(vessels.hit_pm6h.sum())
        pb_p, pmf = poisson_binomial(vessels.chance_unique_hour, hits)
        comparison = worst_overlap(hits)
        check_frozen(frozen)
        write_json(out / "integrity.json", {"checked_at": now(), "all_frozen_hashes_match": True,
                                           "prediction_sha256": digest(out / "predictions.csv"),
                                           "frozen_files": len(frozen["files"])})
        accepted = hits > 3 and comparison["worst_one_sided_p"] <= 0.05 and pb_p <= 0.05
        reasons = [f"적중 {hits}/82 {'>' if hits > 3 else '<='} 기준선 3/82.",
                   f"기준선 최악 겹침 단측 p={comparison['worst_one_sided_p']:.8g}: "
                   + ("0.05 이하 통과." if comparison["worst_one_sided_p"] <= 0.05 else "0.05 초과, 유의 개선 조건 미충족."),
                   f"균등 관측시간 우연모델 단측 p={pb_p:.8g}: " + ("0.05 이하 통과." if pb_p <= 0.05 else "0.05 초과, 우연 대비 조건 미충족."),
                   "계약·모형 수렴·학습 제외·입력 및 사전 규칙 해시 검사 통과."]
        median = float(vessels.min_abs_error_h.median())
        mem = psutil.Process().memory_info()
        summary = {"round": "Round018", "status": "complete", "decision": "채택" if accepted else "기각",
                   "accepted": accepted, "decision_reasons": reasons, "frozen_at": frozen["frozen_at"],
                   "predictions_saved_at": saved_at, "completed_at": now(), "evaluation_count": 1,
                   "metric": "internal vessel top-1 within inclusive +/-6h; not official F1",
                   "primary": {"hits": hits, "denominator": 82, "rate": hits / 82,
                               "baseline_hits": 3, "baseline_rate": 3 / 82, "delta_rate": (hits - 3) / 82,
                               "median_abs_error_h": median if math.isfinite(median) else None,
                               "median_error_is_infinite": not math.isfinite(median),
                               "median_candidate_hours": float(vessels.n_unique_hours.median()),
                               "median_candidate_rows": float(vessels.n_rows.median()),
                               "oracle_support_vessels": int((vessels.eligible_unique_hours > 0).sum()),
                               "missing_predictions": int((vessels.prediction_status != "predicted").sum())},
                   "events_secondary": {"hits": int(events.event_hit_pm6h.sum()), "denominator": 100,
                                        "not_primary_denominator": True},
                   "chance": {"null": "uniform unique observed hour, all accident windows unioned per vessel",
                              "expected_hits": float(vessels.chance_unique_hour.sum()),
                              "expected_rate": float(vessels.chance_unique_hour.mean()), "one_sided_p": pb_p,
                              "pmf": pmf.tolist(), "row_uniform_expected_hits_secondary": float(vessels.chance_row.sum()),
                              "row_uniform_expected_rate_secondary": float(vessels.chance_row.mean())},
                   "baseline_comparison": comparison, "input": input_audit,
                   "training": {"folds": 82, "scheme": "leave-one-vessel-out", "lambda": 0.01,
                                "all_heldout_rows_events_excluded": True, "all_optimizers_success": True,
                                "full_cohort_refit_after_evaluation": False},
                   "limitations": ["Reused development labels and overlapping LOOV fits: p-values are nominal, not independent confirmation",
                                   "Provisional event linkage; outside windows are contrast controls, not proven normal",
                                   "Retrospective whole-period analysis, not real-time performance"],
                   "elapsed_seconds": time.perf_counter() - started,
                   "peak_process_mib": getattr(mem, "peak_wset", mem.rss) / 2**20,
                   "versions": {"python": platform.python_version(), "numpy": np.__version__,
                                "pandas": pd.__version__, "scipy": scipy.__version__, "pyarrow": pyarrow.__version__}}
        write_json(out / "summary.json", summary)
        render_report(summary, out)
        print(json.dumps({"decision": summary["decision"], "hits": hits, "denominator": 82,
                          "median_error_h": summary["primary"]["median_abs_error_h"],
                          "chance_expected_hits": summary["chance"]["expected_hits"],
                          "baseline_worst_p": comparison["worst_one_sided_p"], "chance_p": pb_p}, ensure_ascii=False), flush=True)
    except Exception as exc:
        write_json(out / "failure.json", {"at": now(), "status": "deferred" if isinstance(exc, MemoryError) else "invalid",
                                          "type": type(exc).__name__, "message": str(exc), "retuning_allowed": False})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--selftest", action="store_true")
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        memory_gate("synthetic_checks", 384, "small synthetic arrays plus scientific library imports",
                    HERE / "memory_preflight.jsonl")
        selftest()
    elif args.freeze:
        freeze()
    else:
        run()
