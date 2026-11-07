"""공식 규칙(시간오차 고려 F1, 6시간 초과 0점, 미사고 공란)에 따른 정량 평가.

입력은 모두 기존 산출물이며 새로 학습하지 않는다.
  - 시간별 종합 이상점수: round_008 candidate_ledger.parquet (82척 / 99,677행)
  - 사고 정답:            round_008_linkage_audit devset_positives.csv (100사건 / 82척)

예측 규칙은 고정 기준선 B0이다: 선박별 종합점수 최대 시각, 동점은 최소 source_ordinal.
공란 판정은 선박별 최고점에 임계값 tau를 적용한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "testB/final/round_008_20261106/execution_001/candidate_ledger.parquet"
POSITIVES = ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"
TOLERANCE_H = 6.0
THRESHOLDS = (0.00, 0.50, 0.55, 0.60, 0.65, 0.70)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def peak_predictions(ledger: pd.DataFrame) -> pd.DataFrame:
    """B0: 선박별 종합점수 최대 시각. 동점이면 원본 source_ordinal 최솟값."""
    ordered = ledger.sort_values(["rfid_id", "score", "source_ordinal"],
                                 ascending=[True, False, True], kind="stable")
    peak = ordered.groupby("rfid_id", as_index=False).first()
    ties = (ledger.merge(peak[["rfid_id", "score"]], on=["rfid_id", "score"])
            .groupby("rfid_id").size().rename("peak_tie_count").reset_index())
    return peak.merge(ties, on="rfid_id")[
        ["rfid_id", "ts", "source_ordinal", "score", "peak_tie_count"]
    ].rename(columns={"ts": "pred_ts", "score": "peak_score"})


def match_to_truth(pred: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """선박별로 가장 가까운 사고까지의 시간오차. 다중사고는 최소 오차를 취한다."""
    joined = pred.merge(truth[["rfid_id", "acc_id", "acc_ts", "tier"]], on="rfid_id", how="left")
    joined["abs_error_h"] = (joined.pred_ts - joined.acc_ts).abs().astype(float)
    best = (joined.sort_values(["rfid_id", "abs_error_h"], kind="stable")
            .groupby("rfid_id", as_index=False).first())
    return best.rename(columns={"acc_id": "nearest_acc_id", "acc_ts": "nearest_acc_ts",
                                "tier": "nearest_tier"})


def confusion(decisions: pd.DataFrame, tau: float) -> dict:
    """공란 판정 후 TP/FP/FN. 시간오차가 허용창을 넘은 예측은 FP이자 FN이다."""
    flagged = decisions.peak_score >= tau if tau > 0 else pd.Series(True, index=decisions.index)
    within = decisions.abs_error_h <= TOLERANCE_H
    tp = int((flagged & within).sum())
    fp = int((flagged & ~within).sum())            # 예측했으나 허용창 밖 → 0점 처리
    fn = int((~flagged).sum() + (flagged & ~within).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    graded = float(decisions.loc[flagged & within]
                   .apply(lambda r: 1.0 - r.abs_error_h / TOLERANCE_H, axis=1).sum()) if tp else 0.0
    graded_precision = graded / (tp + fp) if tp + fp else 0.0
    graded_recall = graded / (tp + fn) if tp + fn else 0.0
    graded_f1 = (2 * graded_precision * graded_recall / (graded_precision + graded_recall)
                 if graded_precision + graded_recall else 0.0)
    return {"threshold": tau, "flagged": int(flagged.sum()), "blank": int((~flagged).sum()),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1,
            "graded_f1": graded_f1,
            "graded_note": "허용창 내 예측에 1-|오차|/6 가중. 공식 수식 미확인 상태의 민감도 참고값"}


def projected_f1(tp: int, fp: int, fn: int, evaluated_vessels: int,
                 cohort: int, accident_vessels: int) -> dict:
    """미사고 선박이 섞인 cohort척 집단에서의 F1 추정.

    현재 집단은 전부 사고 선박이므로 FP가 시간오차에서만 발생한다. 비율은 평가 집단
    (evaluated_vessels)에서 측정하고, 그 비율을 가정 집단에 적용한다.
    """
    if not accident_vessels or not evaluated_vessels:
        return {}
    flag_rate = (tp + fp) / evaluated_vessels         # 사고 선박에서 예측을 제출한 비율
    hit_rate = tp / evaluated_vessels                 # 사고 선박에서 허용창 내 적중 비율
    non_accident = cohort - accident_vessels
    p_tp = hit_rate * accident_vessels
    p_fp_accident = (flag_rate - hit_rate) * accident_vessels   # 사고 선박인데 시각 오류
    p_fp_non_accident = flag_rate * non_accident                # 미사고 선박에 제출
    p_fn = accident_vessels - p_tp
    p_fp = p_fp_accident + p_fp_non_accident
    precision = p_tp / (p_tp + p_fp) if p_tp + p_fp else 0.0
    recall = p_tp / (p_tp + p_fn) if p_tp + p_fn else 0.0
    return {"cohort": cohort, "assumed_accident_vessels": accident_vessels,
            "assumed_non_accident_vessels": non_accident,
            "measured_flag_rate": flag_rate, "measured_hit_rate": hit_rate,
            "projected_tp": p_tp, "projected_fp": p_fp, "projected_fn": p_fn,
            "projected_fp_from_non_accident": p_fp_non_accident,
            "projected_precision": precision, "projected_recall": recall,
            "projected_f1": (2 * precision * recall / (precision + recall)
                             if precision + recall else 0.0),
            "assumption": "미사고 선박도 사고 선박과 같은 비율로 예측을 제출한다고 가정. "
                          "실제 미사고 선박 수와 그 점수 분포는 확인되지 않았다."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="새 출력 폴더")
    args = parser.parse_args()
    out: Path = args.output.resolve()
    if out.exists():
        raise SystemExit(f"새 출력 폴더가 필요하다: {out}")

    ledger = pq.read_table(LEDGER).to_pandas()
    ledger["rfid_id"] = ledger.rfid_id.astype(str)
    truth = pd.read_csv(POSITIVES, encoding="utf-8-sig", dtype={"rfid_id": str})
    if ledger.score.isna().any():
        raise SystemExit("점수 결측이 있으면 평가 단위를 먼저 정의해야 한다")

    pred = peak_predictions(ledger)
    decisions = match_to_truth(pred, truth)
    decisions["within_tolerance"] = decisions.abs_error_h <= TOLERANCE_H

    vessel_rows = [confusion(decisions, t) for t in THRESHOLDS]
    tier01 = decisions[decisions.nearest_tier.isin([0, 1])]
    tier01_rows = [confusion(tier01, t) for t in THRESHOLDS]

    base = vessel_rows[0]
    summary = {
        "evaluated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "rule": {
            "metric": "시간오차를 고려한 F1",
            "tolerance_hours": TOLERANCE_H,
            "tolerance_basis": "주최 측 답변 '6시간 넘어가면서부터는 0점 처리'",
            "blank_policy": "미사고 판단 선박은 예측 칸 전체 공란",
            "prediction_rule": "B0 고정 기준선 — 선박별 종합점수 최대 시각, 동점은 최소 source_ordinal",
            "out_of_window_handling": "허용창을 넘은 예측은 FP로 집계하고 해당 사고는 FN으로 집계",
            "unconfirmed": ["공식 TP/FP/FN 수식", "조기·지연 추정의 비대칭 감점 여부",
                            "정확히 6시간일 때의 처리", "시각1~3의 정성평가 반영 방식"],
        },
        "cohort": {
            "vessels": int(decisions.rfid_id.nunique()),
            "accident_events": int(len(truth)),
            "multi_accident_vessels": int(truth.rfid_id.duplicated().sum()),
            "scored_hours": int(len(ledger)),
            "ts_range": [int(ledger.ts.min()), int(ledger.ts.max())],
            "true_negative_vessels": 0,
            "cohort_caveat": "이 집단은 전부 사고 연결 선박이다. 미사고 선박이 없으므로 "
                             "오경보로 생기는 FP가 측정되지 않고 정밀도는 상한값이다. "
                             "선박-사고 연결 자체도 시공간 조건으로 만든 잠정 대응이다.",
        },
        "headline": {
            "unit": "선박 (제출 양식의 1행 = 1척)",
            "threshold": 0.0,
            "description": "전 선박에 예측을 제출하는 경우",
            "precision": base["precision"], "recall": base["recall"], "f1": base["f1"],
            "tp": base["tp"], "fp": base["fp"], "fn": base["fn"],
        },
        "by_threshold_vessel_unit": vessel_rows,
        "by_threshold_tier01": tier01_rows,
        "tier01_vessels": int(len(tier01)),
        "error_distribution_hours": {
            "min": float(decisions.abs_error_h.min()),
            "p25": float(decisions.abs_error_h.quantile(.25)),
            "median": float(decisions.abs_error_h.median()),
            "p75": float(decisions.abs_error_h.quantile(.75)),
            "max": float(decisions.abs_error_h.max()),
            "within_6h": int(decisions.within_tolerance.sum()),
            "within_24h": int((decisions.abs_error_h <= 24).sum()),
            "within_72h": int((decisions.abs_error_h <= 72).sum()),
        },
        "projection_to_100_vessel_cohort": {
            f"accident_vessels_{n}": projected_f1(
                base["tp"], base["fp"], base["fn"],
                int(decisions.rfid_id.nunique()), 100, n)
            for n in (10, 20, 40, 82)
        },
        "inputs": {str(p.relative_to(ROOT)): sha256(p) for p in (LEDGER, POSITIVES)},
        "training_performed": False,
        "test_data_used_for_fitting": False,
    }

    out.mkdir(parents=True)
    decisions.to_csv(out / "vessel_decisions.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(vessel_rows).to_csv(out / "f1_by_threshold.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"f1": base["f1"], "precision": base["precision"], "recall": base["recall"],
                      "tp": base["tp"], "fp": base["fp"], "fn": base["fn"],
                      "vessels": summary["cohort"]["vessels"],
                      "median_abs_error_h": summary["error_distribution_hours"]["median"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
