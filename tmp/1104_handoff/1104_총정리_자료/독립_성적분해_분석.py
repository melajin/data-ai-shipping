"""Read-only independent remeasurement of completed trials 6--10.

No model fitting, feature rewriting, or result selection occurs here.
Bootstrap intervals describe fixed stored predictions, not selection-free test risk.
"""
from pathlib import Path
import os
for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[key] = "3"
import hashlib
import json
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "TabICLv2_투트랙_6_10차_20261104"
OUT = Path(__file__).resolve().parent
CLASSES = ["연안복합", "자망", "통발", "채낚기연승낚시"]
N_BOOT = 4000
SEED = 11042026


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def metrics(y, p):
    y, p = np.asarray(y, int), np.asarray(p, int)
    cm = np.bincount(4 * y + p, minlength=16).reshape(4, 4)
    tp = np.diag(cm)
    support = cm.sum(1)
    predicted_support = cm.sum(0)
    den = support + predicted_support
    f1 = np.divide(2 * tp, den, out=np.zeros(4, float), where=den > 0)
    n = int(cm.sum())
    return {"n": n, "correct": int(tp.sum()), "micro_f1": float(tp.sum() / n) if n else None,
            "macro_f1": float(f1.mean()) if n else None,
            "weighted_f1": float(np.dot(f1, support) / n) if n else None,
            "class_f1": f1.tolist() if n else [None] * 4,
            "support": support.tolist(), "predicted_support": predicted_support.tolist(),
            "precision": np.divide(tp, predicted_support, out=np.zeros(4, float), where=predicted_support > 0).tolist(),
            "recall": np.divide(tp, support, out=np.zeros(4, float), where=support > 0).tolist(),
            "confusion": cm.tolist()}


def boot_metrics(cm):
    tp = np.diagonal(cm, axis1=1, axis2=2)
    den = cm.sum(1) + cm.sum(2)
    f1 = np.divide(2 * tp, den, out=np.zeros_like(tp, dtype=float), where=den > 0)
    micro = tp.sum(1) / cm.sum((1, 2))
    return np.column_stack([micro, f1])


def interval(values, point):
    bounds = np.quantile(values, [.025, .975], axis=0)
    return {name: {"estimate": float(point[i]), "low": float(bounds[0, i]), "high": float(bounds[1, i])}
            for i, name in enumerate(["micro_f1"] + CLASSES)}


def paired_bootstrap(y, old, new, blocks=None, seed=SEED):
    y, old, new = np.asarray(y, int), np.asarray(old, int), np.asarray(new, int)
    code = 16 * y + 4 * old + new
    counts = np.bincount(code, minlength=64)
    rng = np.random.default_rng(seed)
    if blocks is None:
        sampled = rng.multinomial(len(y), counts / len(y), N_BOOT)
        method = "IID vessel percentile bootstrap; paired same resampled vessels for old/new"
        block_details = None
    else:
        _, inv = np.unique(blocks, return_inverse=True)
        nc = int(inv.max() + 1)
        block_counts = np.zeros((nc, 64), np.int64)
        np.add.at(block_counts, (inv, code), 1)
        weights = rng.multinomial(nc, np.full(nc, 1 / nc), N_BOOT)
        sampled = weights @ block_counts
        method = "Spatial-block percentile bootstrap; equal-probability resampling of whole 0.25-degree cells"
        sizes = block_counts.sum(1)
        block_details = {"n_blocks": nc, "min_boats": int(sizes.min()), "median_boats": float(np.median(sizes)), "max_boats": int(sizes.max())}
    joint = sampled.reshape(-1, 4, 4, 4)
    m_old, m_new = boot_metrics(joint.sum(3)), boot_metrics(joint.sum(2))
    point_old, point_new = metrics(y, old), metrics(y, new)
    po = np.array([point_old["micro_f1"]] + point_old["class_f1"])
    pn = np.array([point_new["micro_f1"]] + point_new["class_f1"])
    return {"n": len(y), "replicates": N_BOOT, "seed": seed, "method": method,
            "blocks": block_details, "new_model": interval(m_new, pn),
            "paired_delta_new_minus_old": interval(m_new - m_old, pn - po)}


def grouped(frame):
    known = frame.known_by_ref_id.to_numpy(bool)
    days = frame.observed_days.to_numpy(int)
    masks = {"all": np.ones(len(frame), bool), "known": known, "novel": ~known,
             "days_le7": days <= 7, "days_8_30": (days > 7) & (days <= 30),
             "days_gt30": days > 30,
             "known_days_le7": known & (days <= 7), "novel_days_le7": ~known & (days <= 7),
             "known_days_gt7": known & (days > 7), "novel_days_gt7": ~known & (days > 7)}
    return {k: metrics(frame.y_true[m], frame.predicted[m]) for k, m in masks.items()}


def top_errors(m):
    cm = np.asarray(m["confusion"])
    total = int(cm.sum() - np.trace(cm))
    result = []
    for y in range(4):
        for p in range(4):
            if y != p:
                result.append({"true": CLASSES[y], "predicted": CLASSES[p], "n": int(cm[y, p]),
                               "fraction_of_all_errors": float(cm[y, p] / total) if total else 0.,
                               "fraction_of_true_class": float(cm[y, p] / cm[y].sum()) if cm[y].sum() else 0.})
    return sorted(result, key=lambda r: r["n"], reverse=True)


def reid_decomposition(frame, ref):
    ref_labels = dict(zip(ref["ids"].tolist(), ref["y"].tolist()))
    labels = frame.predicted_ref_id.map(ref_labels)
    assert labels.notna().all()
    identity = frame.rfid_id.to_numpy() == frame.predicted_ref_id.to_numpy()
    same_gear = labels.to_numpy(int) == frame.y_true.to_numpy(int)
    categories = {"same_2026_id": identity, "different_id_same_gear": ~identity & same_gear,
                  "different_id_different_gear": ~identity & ~same_gear}
    masks = {"all": np.ones(len(frame), bool), "known": frame.known_by_ref_id.to_numpy(bool),
             "novel": ~frame.known_by_ref_id.to_numpy(bool),
             "retrieval_weight_positive": frame.accepted_reid.to_numpy(bool)}
    result = {}
    for group, eligible in masks.items():
        result[group] = {}
        for category, cat in categories.items():
            select = eligible & cat
            result[group][category] = metrics(frame.y_true[select], frame.predicted[select])
            result[group][category]["fraction_of_group"] = float(select.sum() / eligible.sum()) if eligible.sum() else None
    result["notes"] = ["Same ID means matching 2026 record key within this internal validation, not externally verified physical-vessel identity.",
                       "accepted_reid in trial10 means retrieval_weight>0, not a hard identification acceptance decision.",
                       "Different identity but same gear can yield correct fishing-class prediction; classification F1 is not identity accuracy."]
    return result


def remove_own_identity_diagnostic(trial, frame, ref):
    path = RUN / ("shared/retrieval10/learned/outer.npz" if trial == 10 else "shared/retrieval6/outer.npz")
    z = np.load(path, allow_pickle=False)
    assert np.array_equal(z["query_ids"], frame.rfid_id.to_numpy())
    candidate_ids = z["candidate_ids"]
    candidate_indices = z["candidate_indices"]
    assert np.array_equal(ref["ids"][candidate_indices], candidate_ids)
    before = ref["y"][candidate_indices[:, 0]]
    allowed = candidate_ids != z["query_ids"][:, None]
    assert allowed.any(1).all()
    index = allowed.argmax(1)
    after = ref["y"][candidate_indices[np.arange(len(frame)), index]]
    known = frame.known_by_ref_id.to_numpy(bool)
    assert np.array_equal(before[~known], after[~known])
    groups = {"all": np.ones(len(frame), bool), "known": known, "novel": ~known}
    return {"trial": trial, "candidate_file": str(path), "candidate_file_sha256": sha(path),
            "candidate_k_available": candidate_ids.shape[1], "original_top1_is_self_n": int((candidate_ids[:, 0] == z["query_ids"]).sum()),
            "novel_predictions_unchanged": True,
            "groups": {g: {"top1_retrieval_only": metrics(frame.y_true[m], before[m]),
                           "top1_after_own_id_removed": metrics(frame.y_true[m], after[m]),
                           "predictions_changed_n": int((before[m] != after[m]).sum())} for g, m in groups.items()},
            "interpretation": "Post-hoc same-ID reference dependence diagnostic only. Removes own-ID entries from stored ranked candidates, not from TabICL contexts, ranker training, or the full pipeline. ID is used for diagnostic exclusion, not deployed prediction."}


def fmt(v):
    return "—" if v is None else f"{v:.4f}"


def metric_row(label, m):
    return f"| {label} | {m['n']:,} | {fmt(m['micro_f1'])} | " + " | ".join(fmt(x) for x in m["class_f1"]) + " |"


def write_note(result):
    rows = ["# 6~10차 독립 성적 분해와 해석", "",
        "저장된 선박별 예측 CSV를 다시 계산한 사후 분석입니다. 새 모델을 학습하거나 기존 예측을 수정하지 않았습니다. 조업 분류에서 선박당 정답 하나를 예측하므로 Micro-F1은 맞힌 선박 수÷평가 선박 수와 같습니다.", "",
        "## 1. 전체 점수와 검증 기간의 차이", "",
        "| 시도 | INNER Micro-F1 | OUTER Micro-F1 | OUTER−INNER | 연안복합 F1 | 자망 F1 | 통발 F1 | 채낚기연승낚시 F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for trial in range(6, 11):
        item = result["trials"][str(trial)]; im=item["inner"]["all"]; om=item["outer"]["all"]
        rows.append(f"| {trial}차 | {im['micro_f1']:.4f} | {om['micro_f1']:.4f} | {om['micro_f1']-im['micro_f1']:+.4f} | " + " | ".join(fmt(x) for x in om["class_f1"]) + " |")
    rows += ["", "INNER는 4월, OUTER는 5~6월이며 관측 기간 길이와 대상 선박도 다릅니다. 따라서 이 차이를 그대로 과적합의 크기라고 해석할 수는 없습니다. 같은 선박만 남긴 공통-ID 대조도 JSON에 제공합니다. INNER는 설정 선택에 사용됐으므로 점수가 더 낙관적일 수 있습니다.", "",
             f"10차에서 양쪽에 모두 관측된 {result['trials']['10']['common_id_inner_outer']['common_n']:,}척만 비교하면 INNER Micro-F1 {result['trials']['10']['common_id_inner_outer']['inner']['micro_f1']:.4f} → OUTER {result['trials']['10']['common_id_inner_outer']['outer']['micro_f1']:.4f}입니다. 전체 집단의 차이에는 대상 선박 구성 변화도 포함되어 있습니다.", "",
             "10차는 6차보다 전체 분류가 개선됐지만 모든 업종이 매번 좋아진 것은 아닙니다. 채낚기연승낚시의 OUTER F1은 9차 0.7860에서 10차 0.7261로 내려갔습니다. 전체 Micro-F1의 상승과 소수 업종의 개선은 같은 말이 아닙니다.", "",
             "## 2. 10차의 기존·신규 선박과 짧은 관측 이력", "",
             "| 집단 | 선박 수 | Micro-F1 | 연안복합 F1 | 자망 F1 | 통발 F1 | 채낚기연승낚시 F1 |", "|---|---:|---:|---:|---:|---:|---:|"]
    names={"all":"전체", "known":"REF에 ID가 있는 선박", "novel":"REF에 ID가 없는 선박", "days_le7":"관측일 1~7일", "days_8_30":"관측일 8~30일", "days_gt30":"관측일 31일 이상", "known_days_le7":"기존·1~7일", "novel_days_le7":"신규·1~7일", "known_days_gt7":"기존·8일 이상", "novel_days_gt7":"신규·8일 이상"}
    for key,label in names.items(): rows.append(metric_row(label, result["trials"]["10"]["outer"][key]))
    rows += ["", "관측일은 실제 기록이 있는 날짜 수입니다. 출항 횟수나 운항시간이 아니며, 관측 누락·선박 구성 차이도 함께 반영합니다. 이 집단 차이만으로 ‘짧아서 성능이 떨어졌다’는 인과를 확정할 수 없습니다.", "",
             "특히 1~7일 집단의 채낚기연승낚시 정답 선박은 6척뿐입니다. 이 집단의 F1 0.3030은 6척 중 5척을 맞혔지만 다른 업종 22척도 해당 업종으로 잘못 분류한 결과입니다. 작은 분모와 오탐을 함께 봐야 합니다. 신규 통발은 75척 중 6척만 맞혀 F1 0.1017로 남아 있습니다.", "",
             "| 집단 | 연안복합 정답 수 | 자망 정답 수 | 통발 정답 수 | 채낚기연승낚시 정답 수 |", "|---|---:|---:|---:|---:|"]
    for key in ["all","known","novel"]:
        rows.append(f"| {names[key]} | " + " | ".join(str(x) for x in result["trials"]["10"]["outer"][key]["support"]) + " |")
    comp=result["overall_score_composition"]
    rows += ["", f"10차 전체 Micro-F1은 **({comp['known_correct']} + {comp['novel_correct']}) ÷ ({comp['known_n']} + {comp['novel_n']}) = {comp['micro_f1']:.6f}**입니다. 기존 선박 {comp['known_fraction']:.2%}가 전체 수치를 크게 좌우합니다. 이는 같은 단일정답 분류에서 Micro-F1이 정확도와 같기 때문에 성립하는 가중 계산입니다. **업종별 F1·Macro-F1·Weighted-F1을 집단 비율로 단순 평균하면 전체 지표가 되지 않습니다.** 해당 지표는 전체 혼동행렬에서 다시 계산해야 합니다.", "",
             "## 3. 10차가 틀리는 방향", "", "| 실제 → 예측 | 오류 선박 수 | 전체 오류 중 비율 | 해당 실제 업종 중 비율 |", "|---|---:|---:|---:|"]
    for item in result["error_pairs_trial10"][:6]:
        rows.append(f"| {item['true']} → {item['predicted']} | {item['n']} | {item['fraction_of_all_errors']:.2%} | {item['fraction_of_true_class']:.2%} |")
    rows += ["", "연안복합↔자망 및 연안복합↔통발 네 방향의 오류는 합계 847척으로 전체 오류 1,055척의 80.28%입니다. 여전히 이 경계를 구분하는 것이 가장 큰 과제입니다.", "",
             "## 4. 재식별 성공과 조업 분류 성공은 구분해야 함", "",
             "| 검색 후보의 상태 | 선박 수 | 최종 분류 정답 수 | 최종 Micro-F1 |", "|---|---:|---:|---:|"]
    for key,label in [("same_2026_id","1등 후보가 같은 2026 ID"),("different_id_same_gear","다른 ID이지만 같은 업종"),("different_id_different_gear","다른 ID·다른 업종")]:
        m=result["trial10_reid_decomposition"]["all"][key]
        rows.append(f"| {label} | {m['n']} | {m['correct']} | {fmt(m['micro_f1'])} |")
    rows += ["", "다른 배를 1등 후보로 골라도 업종이 같으면 조업 분류는 맞을 수 있습니다. 반대로 다른 업종 후보를 골라도 최종 결합 모델이 바로잡을 수 있습니다. 위 표는 내부 2026 ID 일치 여부이며, 외부 확인을 거친 물리적 선박 재식별 정확도나 공식 2025 테스트 성능을 증명하지 않습니다. 10차 CSV의 accepted_reid는 검색 가중치가 0보다 큰 경우이므로 ‘신원을 확정했다’는 뜻으로 읽으면 안 됩니다.", "",
             "## 5. 자기 선박의 과거 후보를 지우면 무엇이 달라지는가", "",
             "아래는 **검색 1등 후보의 업종만 사용하는 부분 진단**입니다. 저장된 후보에서 평가 선박과 같은 ID를 제거하고 다음 후보를 골랐습니다. 전체 투트랙 모델을 다시 평가하거나 TabICL 학습 이력을 제거한 실험이 아닙니다.", "",
             "| 검색기 | 집단 | 원래 1등 업종 Micro-F1 | 자기 ID 제거 후 | 차이 |", "|---|---|---:|---:|---:|"]
    for trial in [6,10]:
        for group in ["known","novel"]:
            item=result["self_identity_removal"][str(trial)]["groups"][group]
            a=item["top1_retrieval_only"]["micro_f1"]; b=item["top1_after_own_id_removed"]["micro_f1"]
            rows.append(f"| {trial}차 검색 | {names[group]} | {a:.4f} | {b:.4f} | {b-a:+.4f} |")
    rows += ["", "이 감소는 자신의 과거 이력이 검색의 주요 단서라는 증거입니다. 기존 선박 모니터링에는 유용할 수 있지만, 새로운 선박에도 같은 성능이 나올 것이라는 근거는 아닙니다. 신규 선박은 원래 자신의 ID가 후보에 없으므로 제거 전후 예측이 완전히 같음을 확인했습니다. ID는 이 사후 진단의 제외 기준으로만 사용했습니다.", "",
             "자기 ID를 제거한 기존 선박 검색은 6차 0.4956, 10차 0.4809입니다. 따라서 큰 폭의 향상을 ‘다른 선박끼리 업종을 구별하는 보편적 능력의 향상’으로 설명하기보다, ‘반복된 자기 선박 이력을 찾아내는 능력의 향상’으로 설명하는 편이 현재 증거에 부합합니다. 다만 후보 생성·순위·원래 구성도 함께 달라 단일 요소의 순수 인과 효과로 단정할 수는 없습니다.", "",
             "## 6. 점수의 불확실성", "",
             "고정된 OUTER 예측에서 선박을 복원추출한 4,000회 paired bootstrap입니다. 같은 재표본을 6차와 10차에 적용하므로 개선량의 구간도 계산할 수 있습니다. 아래는 95% 백분위 구간입니다.", "",
             "| 지표 | 10차 | 선박 bootstrap 구간 | 6→10차 개선량 | 개선량 구간 |", "|---|---:|---|---:|---|"]
    boot=result["bootstrap"]["all_iid_6_to_10"]
    for key in ["micro_f1"]+CLASSES:
        a=boot["new_model"][key]; d=boot["paired_delta_new_minus_old"][key]
        rows.append(f"| {key} | {a['estimate']:.4f} | [{a['low']:.4f}, {a['high']:.4f}] | {d['estimate']:+.4f} | [{d['low']:+.4f}, {d['high']:+.4f}] |")
    spatial=result["bootstrap"]["spatial_blocks_6_to_10"]
    a=spatial["new_model"]["micro_f1"];d=spatial["paired_delta_new_minus_old"]["micro_f1"]
    small=result["bootstrap"]["all_iid_9_to_10"]["paired_delta_new_minus_old"]["채낚기연승낚시"]
    rows += ["", f"채낚기연승낚시의 6→10차 개선량 구간은 0을 포함하므로 뚜렷한 향상으로 단정하기 어렵습니다. 9→10차 변화는 {small['estimate']:+.4f}, 95% 구간 [{small['low']:+.4f}, {small['high']:+.4f}]로 이 저장 예측에서는 하락이 관측됩니다. 이는 여러 지표를 살핀 사후 결과이므로 단일 사전 가설의 확정 검정처럼 표현하지 않습니다.", "",
             f"서로 가까운 해역의 배들이 비슷한 오류를 공유할 가능성을 보기 위해 0.25° 공간 셀 단위로도 재표본했습니다. {spatial['blocks']['n_blocks']}개 블록의 10차 Micro-F1 구간은 [{a['low']:.4f}, {a['high']:.4f}], 6→10차 개선량 구간은 [{d['low']:+.4f}, {d['high']:+.4f}]입니다. 이것은 공간 의존성에 대한 민감도 확인이며, 고정된 최적 공간 블록이라는 뜻은 아닙니다.", "",
             "**이 구간은 반복 실험·설정 선택의 낙관적 편향을 제거하지 않습니다.** 같은 OUTER를 여러 회차 보며 다음 설계를 정했다면 완전히 미사용인 최종 시험셋의 신뢰구간으로 부를 수 없습니다. 또한 OUTER가 5~6월 두 달을 합친 선박별 예측이므로 독립적인 월 블록이 충분하지 않습니다. 월별 예측을 새로 만들지 않은 상태에서 시간 의존성을 보정했다고 주장할 수 없습니다.", "",
             "## 7. 현재 숫자로 말할 수 있는 결론", "",
             "- 6→10차의 전체 개선은 저장된 예측을 독립 재계산해 확인됐습니다. 기존 선박의 과거 위치·항적을 다시 찾는 능력이 중요한 기여를 합니다.",
             "- 신규 선박과 짧은 관측 이력은 별도 취약 집단입니다. 전체 점수 하나만으로 모든 선박에 강하다고 해석하면 안 됩니다.",
             "- 기존 선박의 과거 이력을 사용하는 것 자체가 부당한 누수는 아닙니다. 사용 가능한 과거와 정답만 참조했는지, 공식 평가에서 이 관계가 허용·유지되는지는 별개로 확인해야 합니다.",
             "- 이번 결과는 2026년 내부 시간 분할 점수입니다. 공식 테스트의 알려지지 않은 정답 점수나 2025↔2026 물리적 선박 일치의 증거가 아닙니다.",
             "- 10차가 전체 Micro-F1에서는 가장 높아도 모든 업종에서 우월한 것은 아닙니다. 소수 업종 성능과 새 선박 성능을 함께 보고 최종 선택해야 합니다.", "",
             "재현 근거: `독립_성적분해_측정.json`에 모든 회차·집단의 혼동행렬, 분모, 재표본 구간, 원본 CSV SHA-256을 저장했습니다. 분석 코드 `독립_성적분해_분석.py`는 CPU 스레드를 3개로 제한하고 기존 산출물을 읽기만 합니다."]
    (OUT / "독립_성적분해_요약.md").write_text("\n".join(rows)+"\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ref = np.load(RUN / "inputs/ref.npz", allow_pickle=False)
    frames = {}
    result = {"class_order": CLASSES, "analysis_only_no_training": True, "csv_sources": {}, "trials": {}}
    for trial in range(6, 11):
        result["trials"][str(trial)] = {}
        for role in ("inner", "outer"):
            path = RUN / f"{trial}차 시도/{role}.csv"
            frame = pd.read_csv(path, dtype={"rfid_id": str, "predicted_ref_id": str})
            base = np.load(RUN / f"inputs/{role}.npz", allow_pickle=False)
            assert np.array_equal(frame.rfid_id, base["ids"])
            assert np.array_equal(frame.y_true, base["y"])
            assert np.array_equal(frame.known_by_ref_id, np.isin(frame.rfid_id, ref["ids"]))
            assert np.array_equal(frame.observed_days, base["observed_days"])
            assert frame.rfid_id.is_unique
            frames[trial, role] = frame
            result["csv_sources"][f"{trial}_{role}"] = {"path": str(path), "sha256": sha(path)}
            result["trials"][str(trial)][role] = grouped(frame)
            # Check saved score without importing its implementation.
            saved = json.loads((RUN / f"{trial}차 시도/result.json").read_text(encoding="utf-8"))["metrics"][role]
            actual = result["trials"][str(trial)][role]["all"]
            assert np.isclose(actual["micro_f1"], saved["micro_f1"])
            assert np.allclose(actual["class_f1"], saved["class_f1"])
        first, last = frames[trial, "inner"].set_index("rfid_id"), frames[trial, "outer"].set_index("rfid_id")
        common = first.index.intersection(last.index)
        old, new = first.loc[common], last.loc[common]
        result["trials"][str(trial)]["common_id_inner_outer"] = {
            "common_n": len(common), "inner": metrics(old.y_true, old.predicted),
            "outer": metrics(new.y_true, new.predicted),
            "labels_changed_n": int((old.y_true.to_numpy() != new.y_true.to_numpy()).sum()),
            "inner_correct_outer_wrong_n": int(((old.y_true == old.predicted).to_numpy() & (new.y_true != new.predicted).to_numpy()).sum()),
            "inner_wrong_outer_correct_n": int(((old.y_true != old.predicted).to_numpy() & (new.y_true == new.predicted).to_numpy()).sum())}
    f6, f9, f10 = [frames[k, "outer"] for k in (6, 9, 10)]
    y, p6, p9, p10 = f10.y_true.to_numpy(), f6.predicted.to_numpy(), f9.predicted.to_numpy(), f10.predicted.to_numpy()
    known = f10.known_by_ref_id.to_numpy(bool)
    result["bootstrap"] = {}
    for name, mask in {"all":np.ones(len(y),bool), "known":known, "novel":~known}.items():
        result["bootstrap"][name+"_iid_6_to_10"] = paired_bootstrap(y[mask],p6[mask],p10[mask])
    result["bootstrap"]["all_iid_9_to_10"] = paired_bootstrap(y,p9,p10)
    outer = np.load(RUN / "inputs/outer.npz", allow_pickle=False)
    names = outer["feature_names"].tolist()
    lon = outer["X"][:, names.index("spatial__longitude__day_p50__period_median")]
    lat = outer["X"][:, names.index("spatial__latitude__day_p50__period_median")]
    blocks = np.array([f"{int(np.floor(x/.25))}:{int(np.floor(z/.25))}" if np.isfinite(x+z) else f"missing_{i}"
                       for i,(x,z) in enumerate(zip(lon,lat))])
    result["bootstrap"]["spatial_blocks_6_to_10"] = paired_bootstrap(y,p6,p10,blocks=blocks)
    result["bootstrap"]["interpretation_limits"] = ["Fixed stored predictions only; percentile intervals do not remove adaptive model-selection bias.",
        "Vessel IID may understate spatial/shared-environment dependence; spatial blocks are a sensitivity analysis, not proof of independence.",
        "Only two OUTER months, aggregated in each vessel prediction; month-block uncertainty is not estimable here."]
    result["error_pairs_trial10"] = top_errors(result["trials"]["10"]["outer"]["all"])
    result["trial10_reid_decomposition"] = reid_decomposition(f10,ref)
    weight = np.load(RUN / "10차 시도/outer_retrieval_weight.npy", allow_pickle=False)
    assert np.array_equal(weight>0,f10.accepted_reid)
    result["trial10_retrieval_weight"] = {"positive_n":int((weight>0).sum()), "mean":float(weight.mean()), "quantiles":np.quantile(weight,[0,.25,.5,.75,1]).tolist()}
    result["self_identity_removal"] = {str(k):remove_own_identity_diagnostic(k,frames[k,"outer"],ref) for k in (6,10)}
    kg,ng = result["trials"]["10"]["outer"]["known"],result["trials"]["10"]["outer"]["novel"]
    result["overall_score_composition"] = {"known_n":kg["n"],"novel_n":ng["n"], "known_correct":kg["correct"],"novel_correct":ng["correct"],
        "known_fraction":kg["n"]/(kg["n"]+ng["n"]),"micro_f1":(kg["correct"]+ng["correct"])/(kg["n"]+ng["n"]),
        "do_not_average_group_class_f1":True}
    (OUT / "독립_성적분해_측정.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    write_note(result)
    print(json.dumps({"trial10_groups":result["trials"]["10"]["outer"],"decomposition":result["trial10_reid_decomposition"]["all"],
                      "bootstrap10":result["bootstrap"]["all_iid_6_to_10"],"identity_removal":result["self_identity_removal"]},ensure_ascii=False))


if __name__ == "__main__":
    with threadpool_limits(limits=3):
        main()
