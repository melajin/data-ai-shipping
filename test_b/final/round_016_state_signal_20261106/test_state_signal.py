"""사고 시각에 특정 상태(해상정지 등)가 몰리는지 검증한다.

가설: 사고 100건 중 56건이 추진·조타 상실(기관손상·부유물감김·추진기손상·표류·키손상·방향상실)이다.
이런 사고는 선박을 바다에서 멈추게 하므로 사고 시각의 상태 분포가 평소와 달라야 한다.
달라진다면 후보 시간을 그 상태로 제한해 후보 공간을 줄일 수 있다.

입력은 기존 산출물이며 새로 학습하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "deliverables/testb_system_20261106/src"))
LEDGER = ROOT / "testB/final/round_008_20261106/execution_001/candidate_ledger.parquet"
POSITIVES = ROOT / "testB/과거/round_008_linkage_audit_20261105/devset_positives.csv"
REFERENCES = ROOT / "deliverables/testb_system_20261106/references"
PROPULSION_LOSS = ("기관손상", "부유물감김", "추진기손상", "표류", "키손상", "방향상실")
WINDOW_H = 6


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    out: Path = args.output.resolve()
    if out.exists():
        raise SystemExit(f"새 출력 폴더가 필요하다: {out}")

    import frozen_baseline as fb

    ledger = pq.read_table(LEDGER).to_pandas()
    ledger["rfid_id"] = ledger.rfid_id.astype(str)
    # 원 구현의 rfid_time은 naive 시각의 시(hour)이며 정수 시간키의 24 나머지와 같다.
    ledger["rfid_time"] = (ledger.ts % 24).astype(int)
    truth = pd.read_csv(POSITIVES, encoding="utf-8-sig", dtype={"rfid_id": str})

    nearest, fine, coarse, norm_gap, norm_jump, _ = fb.load_references(REFERENCES)
    frames = []
    for n, rfid in enumerate(sorted(ledger.rfid_id.unique()), 1):
        one = (ledger[ledger.rfid_id == rfid]
               .sort_values(["ts", "rfid_time", "source_ordinal"], kind="stable")
               .reset_index(drop=True))
        frames.append(fb.score_vessel(one, nearest, None, fine, coarse, norm_gap, norm_jump))
        if n % 20 == 0:
            print(f"  {n}/82척 상태 계산", flush=True)
    scored = pd.concat(frames, ignore_index=True)

    # 저장 점수와의 일치 확인 — 상태 재계산이 원 구현과 같은 경로인지 검증한다.
    merged = scored.merge(ledger[["source_ordinal", "score"]], on="source_ordinal",
                          suffixes=("_recomputed", "_stored"))
    parity = float(np.nanmax(np.abs(merged.score_recomputed - merged.score_stored)))

    overall = scored.state.value_counts(normalize=True)

    # 사고 시각 ±WINDOW_H 안의 관측 상태
    rows = []
    for rec in truth.itertuples():
        g = scored[scored.rfid_id == rec.rfid_id]
        win = g[(g.ts - rec.acc_ts).abs() <= WINDOW_H]
        rows.append({"acc_id": rec.acc_id, "rfid_id": rec.rfid_id, "acc_ts": rec.acc_ts,
                     "발생유형": getattr(rec, "발생유형"),
                     "propulsion_loss": getattr(rec, "발생유형") in PROPULSION_LOSS,
                     "n_rows_in_window": len(win),
                     "has_sea_stop": bool((win.state == "해상정지").any()),
                     "has_any_stop": bool(win.state.isin(
                         ["해상정지", "연안정지", "정박정지"]).any()),
                     "states": "|".join(sorted(set(win.state))) if len(win) else ""})
    window = pd.DataFrame(rows)
    observed = window[window.n_rows_in_window > 0]

    # 같은 선박에서 무작위 시각을 뽑았을 때의 기대치 (선박별 가중)
    per_vessel_sea = scored.groupby("rfid_id").state.apply(lambda s: (s == "해상정지").mean())
    baseline_any_window = float(
        observed.rfid_id.map(
            # 길이 n의 창에서 해상정지가 1개 이상일 확률의 독립 근사
            lambda r: per_vessel_sea.get(r, 0.0)).pipe(
            lambda p: 1 - (1 - p) ** observed.n_rows_in_window.to_numpy()).mean())

    summary = {
        "evaluated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "hypothesis": "사고 시각 ±6h 창에 해상정지 상태가 평소보다 자주 나타난다",
        "score_parity_vs_stored_ledger": parity,
        "cohort": {"vessels": int(scored.rfid_id.nunique()), "rows": int(len(scored)),
                   "events": int(len(window)),
                   "events_with_observations_in_window": int(len(observed))},
        "overall_state_share": {k: float(v) for k, v in overall.items()},
        "accident_window": {
            "sea_stop_present": int(observed.has_sea_stop.sum()),
            "sea_stop_rate": float(observed.has_sea_stop.mean()),
            "baseline_expected_rate_same_vessels": baseline_any_window,
            "any_stop_present": int(observed.has_any_stop.sum()),
            "any_stop_rate": float(observed.has_any_stop.mean()),
        },
        "by_accident_type": {
            "propulsion_loss": {
                "events": int(observed.propulsion_loss.sum()),
                "sea_stop_rate": float(observed[observed.propulsion_loss].has_sea_stop.mean())
                if observed.propulsion_loss.any() else None},
            "other": {
                "events": int((~observed.propulsion_loss).sum()),
                "sea_stop_rate": float(observed[~observed.propulsion_loss].has_sea_stop.mean())
                if (~observed.propulsion_loss).any() else None},
        },
        "candidate_space": {
            "all_hours_per_vessel_median": float(scored.groupby("rfid_id").size().median()),
            "sea_stop_hours_per_vessel_median": float(
                scored[scored.state == "해상정지"].groupby("rfid_id").size()
                .reindex(scored.rfid_id.unique()).fillna(0).median()),
            "sea_stop_share_overall": float((scored.state == "해상정지").mean()),
        },
        "training_performed": False,
    }

    out.mkdir(parents=True)
    window.to_csv(out / "accident_window_states.csv", index=False, encoding="utf-8-sig")
    scored[["rfid_id", "ts", "source_ordinal", "state", "s_zone", "s_change", "s_gap", "score"]] \
        .to_parquet(out / "dev_scored_with_state.parquet", index=False)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    print(json.dumps(summary["accident_window"] | summary["by_accident_type"], ensure_ascii=False, indent=2))
    print("score parity vs stored:", parity)


if __name__ == "__main__":
    main()
