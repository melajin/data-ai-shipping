"""전체 선단에 고정 기준선 점수를 적용하고 선박 단위 사고 판정력을 측정한다.

여기서 처음으로 음성 표본(미사고 선박)이 들어간다. 지금까지의 평가는 사고 연결 선박 82척만
보았으므로 정밀도를 실측할 수 없었다.

측정하는 것은 두 가지다.
  1. 선박별 최고 이상점수가 사고 선박을 위로 올리는가 (판정력)
  2. 그 판정력으로 100척 집단에서 기대할 수 있는 F1

2026 자료는 학습 사용이 허용된 기간이다. 테스트 자료(2025)는 읽지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROUND_DIR = Path(__file__).resolve().parent
ROOT = ROUND_DIR.parents[2]
sys.path.insert(0, str(ROOT / "deliverables/testb_system_20261106/src"))
REFERENCES = ROOT / "deliverables/testb_system_20261106/references"
POSITIVES = ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"
TOLERANCE_H = 6.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hourly", required=True, type=Path, help="extract_fleet 출력 폴더")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--min-rows", type=int, default=1,
                    help="이 행 수 미만의 선박은 점수 계산에서 제외하고 별도 집계")
    args = ap.parse_args()
    out: Path = args.output.resolve()
    if out.exists():
        raise SystemExit(f"새 출력 폴더가 필요하다: {out}")

    import frozen_baseline as fb

    files = sorted(Path(args.hourly).glob("hourly_*.parquet"))
    if not files:
        raise SystemExit(f"시간별 입력이 없다: {args.hourly}")
    hourly = pd.concat([pq.read_table(f).to_pandas() for f in files], ignore_index=True)
    hourly["rfid_id"] = hourly.rfid_id.astype(str)
    hourly["rfid_time"] = (hourly.ts % 24).astype(int)
    print(f"입력 {len(hourly):,}행 / {hourly.rfid_id.nunique():,}척", flush=True)

    truth = pd.read_csv(POSITIVES, encoding="utf-8-sig", dtype={"rfid_id": str})
    accident_vessels = set(truth.rfid_id)

    nearest, fine, coarse, norm_gap, norm_jump, _ = fb.load_references(REFERENCES)
    started = time.perf_counter()
    records = []
    groups = hourly.groupby("rfid_id", sort=True)
    skipped = []
    for n, (rfid, raw) in enumerate(groups, 1):
        if len(raw) < args.min_rows:
            skipped.append({"rfid_id": rfid, "rows": len(raw)})
            continue
        one = raw.sort_values(["ts", "rfid_time", "source_ordinal"], kind="stable").reset_index(drop=True)
        scored = fb.score_vessel(one, nearest, None, fine, coarse, norm_gap, norm_jump)
        finite = scored[np.isfinite(scored.score)]
        if finite.empty:
            skipped.append({"rfid_id": rfid, "rows": len(raw)})
            continue
        best = finite.sort_values(["score", "source_ordinal"], ascending=[False, True]).iloc[0]
        rec = {"rfid_id": rfid, "n_rows": len(one), "peak_score": float(best.score),
               "peak_ts": int(best.ts), "peak_state": str(best.state),
               "median_score": float(finite.score.median()),
               "p95_score": float(finite.score.quantile(.95)),
               "is_accident_vessel": rfid in accident_vessels}
        if rec["is_accident_vessel"]:
            acc = truth[truth.rfid_id == rfid].acc_ts.to_numpy()
            rec["abs_error_h"] = float(np.min(np.abs(acc - best.ts)))
            rec["within_tolerance"] = bool(rec["abs_error_h"] <= TOLERANCE_H)
        else:
            rec["abs_error_h"] = None
            rec["within_tolerance"] = False
        records.append(rec)
        if n % 500 == 0:
            print(f"  {n:,}/{len(groups):,}척 ({time.perf_counter()-started:.0f}초)", flush=True)

    vessels = pd.DataFrame(records)
    pos = vessels[vessels.is_accident_vessel]
    neg = vessels[~vessels.is_accident_vessel]

    # 선박 단위 판정력: 최고점으로 사고 선박을 가려낼 수 있는가
    from scipy import stats
    auc = float(stats.mannwhitneyu(pos.peak_score, neg.peak_score,
                                   alternative="greater").statistic / (len(pos) * len(neg)))
    mw_p = float(stats.mannwhitneyu(pos.peak_score, neg.peak_score, alternative="greater").pvalue)

    # 임계값별 선박 판정 성능과, 그 판정에 시각 적중을 결합한 F1
    rows = []
    for tau in np.round(np.arange(0.40, 0.96, 0.05), 2):
        flagged = vessels[vessels.peak_score >= tau]
        tp_vessel = int(flagged.is_accident_vessel.sum())
        fp_vessel = int(len(flagged) - tp_vessel)
        fn_vessel = int(len(pos) - tp_vessel)
        prec_v = tp_vessel / len(flagged) if len(flagged) else 0.0
        rec_v = tp_vessel / len(pos) if len(pos) else 0.0
        # 시각까지 맞은 경우만 TP로 보는 공식 규칙
        tp_time = int(flagged.within_tolerance.sum())
        fp_time = int(len(flagged) - tp_time)
        fn_time = int(len(pos) - tp_time)
        prec_t = tp_time / len(flagged) if len(flagged) else 0.0
        rec_t = tp_time / len(pos) if len(pos) else 0.0
        rows.append({"threshold": float(tau), "flagged_vessels": int(len(flagged)),
                     "vessel_tp": tp_vessel, "vessel_fp": fp_vessel, "vessel_fn": fn_vessel,
                     "vessel_precision": prec_v, "vessel_recall": rec_v,
                     "vessel_f1": 2 * prec_v * rec_v / (prec_v + rec_v) if prec_v + rec_v else 0.0,
                     "time_tp": tp_time, "time_fp": fp_time, "time_fn": fn_time,
                     "official_f1": 2 * prec_t * rec_t / (prec_t + rec_t) if prec_t + rec_t else 0.0})

    summary = {
        "evaluated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "purpose": "음성 표본을 포함한 선박 단위 사고 판정력 실측",
        "cohort": {
            "vessels_scored": int(len(vessels)),
            "vessels_skipped": len(skipped),
            "accident_vessels": int(len(pos)),
            "non_accident_vessels": int(len(neg)),
            "base_rate": float(len(pos) / len(vessels)) if len(vessels) else 0.0,
            "rows": int(len(hourly)),
        },
        "peak_score_distribution": {
            "accident": {"n": int(len(pos)), "median": float(pos.peak_score.median()),
                         "mean": float(pos.peak_score.mean()), "p25": float(pos.peak_score.quantile(.25)),
                         "p75": float(pos.peak_score.quantile(.75))},
            "non_accident": {"n": int(len(neg)), "median": float(neg.peak_score.median()),
                             "mean": float(neg.peak_score.mean()), "p25": float(neg.peak_score.quantile(.25)),
                             "p75": float(neg.peak_score.quantile(.75))},
        },
        "vessel_level_discrimination": {
            "auc_peak_score": auc,
            "mannwhitney_p_greater": mw_p,
            "interpretation": "AUC 0.5는 판정력 없음. 사고 선박의 최고점이 더 높다는 단측 검정",
        },
        "by_threshold": rows,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "training_performed": False,
        "test_data_used": False,
    }

    out.mkdir(parents=True)
    vessels.to_csv(out / "vessel_peaks.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(rows).to_csv(out / "threshold_sweep.csv", index=False, encoding="utf-8-sig")
    if skipped:
        pd.DataFrame(skipped).to_csv(out / "skipped_vessels.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    print(json.dumps({"auc": auc, "p": mw_p,
                      "accident_median": summary["peak_score_distribution"]["accident"]["median"],
                      "non_accident_median": summary["peak_score_distribution"]["non_accident"]["median"],
                      "base_rate": summary["cohort"]["base_rate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
