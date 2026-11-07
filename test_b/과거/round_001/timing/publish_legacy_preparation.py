"""Create Round 001 timing evidence by linking (not modifying) legacy W2 work."""
from __future__ import annotations
import csv, hashlib, json, shutil, sys, platform
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
PROJECT = OUT.parents[2]
LEGACY = PROJECT / "26_11_5/testb_next_experiment_20261105/timing"
REPO = Path(r"D:/repos/fishing-track-classification")
RUN = OUT / "round_001"
RUN.mkdir(exist_ok=True)

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def meta(path: Path) -> dict:
    return {"path": str(path), "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": digest(path) if path.is_file() else None}

def main() -> int:
    started = datetime.now(timezone.utc).astimezone().isoformat()
    legacy_csv = LEGACY / "comparison_readiness_100.csv"
    output_csv = OUT / "comparison_readiness_100.csv"
    shutil.copyfile(legacy_csv, output_csv)
    with output_csv.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 100 or any(r["B_status"] != "not_computed" or r["C_status"] != "not_computed" for r in rows):
        raise RuntimeError("readiness table validation failed")

    refs = [
        LEGACY / "timing_interface.py", LEGACY / "build_inherited_comparison.py", LEGACY / "run_preparation.py",
        LEGACY / "run_001/process_result.json", LEGACY / "run_001/environment.json",
        LEGACY / "run_001/synthetic_self_check.stdout.log", LEGACY / "run_001/synthetic_self_check.stderr.log",
        LEGACY / "run_001/inherited_baseline_table.stdout.log", LEGACY / "run_001/inherited_baseline_table.stderr.log",
        legacy_csv,
        REPO / "code/tools/run_008_testB_20261101.py", REPO / "results/work_008/scores_meta.json",
        REPO / "results/work_008/scored_rows.pkl", REPO / "results/submission_20261101/testB_submission.csv",
        PROJECT / "26_11_5/testb_next_experiment_20261105/integration/runtime_receipts/W2_start.json",
        PROJECT / "26_11_5/testb_next_experiment_20261105/integration/runtime_receipts/W2_process.json",
    ]
    manifest = {
      "manifest_version": "round001-timing-preparation-1.0",
      "status": "preparation_only_pending_supervisor_gate",
      "input_version": "legacy_inputs_only; 1103_v2_not_read_or_verified",
      "sources": [meta(p) for p in refs],
      "score_contract": {
        "score_direction": "higher is more anomalous; exploratory composite, not accident probability",
        "score_formula": "nanmean(s_zone, s_change, s_gap); available components only; all-missing -> NaN; positive floor 1e-6",
        "timing_input_required": ["rfid_id", "ts", "score", "source_row_id"],
        "scoring_features_required_from_source": ["rfid_id", "part_dt", "rfid_time", "cen_lon", "cen_lat", "len_m", "bbox_m", "wkt_valid"],
        "time_contract": "integer hour index; ts aligns with (part_dt, rfid_time); bins represent [hour start, next hour start); timezone conversion evidence not located",
        "sort_contract": "A selects the first maximum in original source order; stable timestamp then source ordinal ordering is used only for B/C; preserve row ID; no coordinate-line joining",
        "positive_floor_semantics": "the score floor is an implementation detail; its accident-decision meaning, evidence basis, and data sufficiency remain unresolved",
        "historical_cache": "2025 Test B only: 100 vessel keys, 82,626 rows, 16 columns; inherited A validated 100 vessels and eight compared output fields mismatch=0",
        "2026_scores": "not present in identified work_008 cache; do not assume generated",
        "source_row_trace": "current timing interface accepts source_row_id; the inherited scored cache's persisted original file/shard row ordinal was not verified",
      },
      "reference_and_fit_scope": {
        "known": [
          "gap/jump quantile references: 3,879,693 adjacent valid train rows across labeled train population; p50 gap 1h, jump 85.723526m",
          "density maps: 1,376,741 fishing-mask rows, 102,053 fine and 9,174 coarse cells; labels from train population (7,372 vessels per plan)",
          "zone distance component uses fixed 20km scaling/clipping, documented as simplification rather than fitted train distribution",
          "per-vessel change scores use prior history >=24 rows; row count is not consecutive-hour guarantee",
        ],
        "unknown_or_unmeasured": [
          "whether accident spreadsheet may be used as development labels despite test-data filename",
          "confirmed accident-to-vessel identity, confirmed negative/normal examples, source authenticity of negatives",
          "actual contribution of 95 overlapping target IDs to reference-map cells or their resulting score changes",
          "threshold source, comparator boundary, max temporal gap, persistence minimum hours/rows",
        ],
        "threshold_fitting": "forbidden now; never derive from 2025 test-score quantiles",
      },
      "split_design_pending": {
        "actual_assignment": "pending; train/dev/calibration/eval memberships not fabricated",
        "leakage_grouping": "build connected components on event-vessel bipartite graph; events sharing any candidate vessel remain in one component; merge duplicate/linked event records before splitting; do not split one vessel across roles",
        "roles": {
          "reference_preprocessing_fit": "train groups only; density/normalizers/scalers and any feature selection; exclude all dev/calibration/eval vessel IDs and linked event groups",
          "model_or_threshold_selection": "development groups only; threshold source must be documented independent of final evaluation",
          "calibration": "separate calibration groups, if score calibration is introduced; never fit on final eval",
          "final_evaluation": "event and vessel groups held out; freeze full-period predictions before looking at accident timestamps; compare predictions afterward",
        },
        "pending_conditions": ["authorized development use", "confirmed identity evidence", "credible positive and negative references", "sufficient independent event-vessel components", "supervisor-defined grouping and split seed/period", "official metric formula and 6h boundary"],
      },
      "method_states": {
        "A": "inherited_existing_baseline only; no recomputation in this worker",
        "B": "same anomalous segment containing A peak; onset timestamp",
        "C": "persistence check on exactly B's segment; if passes C=B, else persistence_not_met and no substitute time",
        "segment_breaks": ["NaN or missing score", "above-threshold condition false", "adjacent time gap > configured max_gap_hours; hourly max_gap_hours must be >0 and <=1 so an unobserved hourly bin cannot be bridged"],
        "ties_and_duplicates": "A is the first maximum in original input order (idxmax semantics); sort by timestamp then original ordinal only for B/C; preserve duplicate rows and source IDs; identical same-time scores are allowed, conflicting valid or missing/valid scores return data_conflict / duplicate_timestamp_scores_conflict with A/B/C blank; count unique timestamps for persistence; duplicates do not imply elapsed duration",
        "params": ["threshold", "exceedance gt/ge", "max_gap_hours", "persistence_min_hours", "persistence_min_rows", "threshold_source"],
      },
      "scope_limits": ["no 2026 score creation", "no actual B/C", "no threshold fitting", "no performance evaluation", "no accident-near timestamp selection", "no external intake or v2 claims"],
    }
    (OUT / "input_split_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    process = json.loads((LEGACY / "run_001/process_result.json").read_text(encoding="utf-8"))
    summary = {
      "status": "preparation_only_pending_supervisor_gate",
      "input_version": "legacy; no 1103_v2 data loaded or verified",
      "prepared_vessels": len(rows), "A_source_status": "inherited_existing_baseline; prior validated A reproduction retained, not rerun",
      "B_computed": 0, "C_computed": 0,
      "B_C_unavailable_reason": "2026 scores absent; threshold source, boundary, max gap, persistence minima and approved label/split evidence unresolved",
      "synthetic_checks": {"status": "inherited_legacy_only", "checks": 7, "actual_exit_code": process["steps"][0]["exit_code"], "log": str(LEGACY / "run_001/synthetic_self_check.stdout.log"), "scope": "legacy run only; does not verify the Round 001 timing interface"},
      "inherited_table_step_exit_code": process["steps"][1]["exit_code"],
      "score_cache": "2025 Test B only; 100 IDs; 82,626 rows; 16 columns",
      "target_reference_id_overlap": {"count": 95, "of": 100, "interpretation": "membership only; actual density/map contribution and score dilution unmeasured"},
      "tie_break_contract": "A = first maximum in original input order (idxmax); source order retained for A; stable time plus source ordinal ordering is used only for B/C",
      "A_tie_semantics": "first maximum in original input order (idxmax); sort by time only for B/C segment search",
      "max_gap_policy": "hourly max_gap_hours must be >0 and <=1; values above 1 are rejected; missing hourly bins cannot be bridged",
      "duplicate_timestamp_policy": "identical scores are retained with source rows; conflicting valid or missing/valid scores return data_conflict / duplicate_timestamp_scores_conflict and leave A/B/C blank; persistence row minimum counts unique timestamps",
      "score_floor_semantics": "positive floor's actual accident-decision meaning and evidence sufficiency remain unresolved",
      "legacy_target_limit": "100-vessel table is legacy only; W0 report of zero overlap with the new v2 Test B roster is pending independent confirmation; do not relabel rows or transfer predictions",
      "model_effort": {"requested": {"model": "gpt-6-luna", "effort": "xhigh"}, "runtime_receipt": str(PROJECT / "testB/round_001/integration/runtime_receipts/W2F_start.json"), "process_receipt": str(PROJECT / "testB/round_001/integration/runtime_receipts/W2F_process.json"), "observed": "W2F Orca start receipt reports model gpt-6-luna, effort xhigh; provider internal runtime not independently observable"},
      "actual_exit_code": 0,
      "legacy_process_record": str(LEGACY / "run_001/process_result.json"),
      "comparison_table": str(output_csv),
      "manifest": str(OUT / "input_split_manifest.json"),
    }
    summary["round_output_hashes"] = {p.name: digest(p) for p in [output_csv, OUT / "input_split_manifest.json"]}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report = f'''# Test B 시각추정 준비 — Round 001\n\n작성 시각: {started}\n\n## 현재 결과\n\n100척 비교표에는 기존 제출 CSV에서 읽은 A만 `inherited_existing_baseline`으로 기록했다. 이 worker는 A를 재계산하지 않았고, 이미 승인된 재현 결과(100척, 비교 8열 불일치 0)를 계승했다. B와 C는 모두 계산하지 않았으며 각 행에 이유를 기록했다. 이 상태는 사고 확정이나 미사고 판정이 아니다.\n\n2025 Test B 캐시는 100척·82,626행·16열로 기록돼 있다. 2026 학습 항적과 사고 167건은 별도 데이터 역할이며, 기존 점수 캐시는 2026 점수를 포함하지 않는다. 기존 점수는 `nanmean(s_zone, s_change, s_gap)`로, 높은 값이 더 이상한 쪽인 탐색 지표이며 사고 확률이 아니다. 구역/공백 정규화는 학습참조 분포를 사용했고 구역 과거 미방문 거리는 고정 20km 스케일이다. 참조 라벨 집합 7,372척, 대상 ID 겹침 95척은 집합 중복이며 실제 격자 기여나 점수 희석을 입증하지 않는다.\n\n## 입력·분할 설계\n\n`input_split_manifest.json`에는 필요한 계산 열, 단위와 시간 구간, 방향, 원본 계보, 참조집합과 적합범위를 기록했다. 반복 후보가 있는 사건과 선박은 사건–선박 이분 그래프의 연결요소로 묶어 같은 분할에 둔다. 전처리/참조 지도 적합은 train, 선택·임계는 dev, 보정이 도입되면 별도 calibration, 최종 평가는 독립 event-vessel 그룹으로 분리한다. 평가 기간 예측을 먼저 고정한 뒤 사고 기록과 대조한다. 실제 배정은 `pending`이다.\n\n사고자료 개발 사용 허용, 확정 신원, 신뢰할 양·음성 근거, 표본 분할 가능성은 확인되지 않았다. 따라서 임계값, comparator, 구간 최대 간격과 지속 최소 시간/행수는 선택하지 않았다. 공식 F1 수식과 6시간 경계도 미확정이다.\n\n## A/B/C 인터페이스와 검증\n\n`timing_interface.py`는 명시적 매개변수만 받아 A peak, A와 같은 이상구간 B onset, 해당 구간에서의 C 지속 조건을 계산하는 순수 함수 스켈레톤이다. 시간 구간을 넘겨 연결하지 않고 NaN은 끊음, 동점은 시간순 최초, 중복 시간은 원행 ID를 보존하며 elapsed duration을 늘리지 않는다. C가 통과하면 C=B, 실패하면 시각을 대체하지 않는다. CLI는 합성 자기검사만 지원하며 이 실행에서 실제자료 입력은 열지 않았다.\n\n합성 검사 7종이 실제 종료코드 0으로 통과했다(경계 비교 gt/ge, 정렬·동점, 누락 간격 분절, NaN 분절, 중복시각 추적/지속시간, C=B, 점수 결측). 실행 로그와 환경·해시는 선행 legacy 경로 아래 보존되어 있으며 이 Round 산출물은 원 경로와 해시로 연결한다.\n\n## 감독자가 고정할 다음 조건\n\n1. 사고 스프레드시트의 개발 사용 권한과 라벨 출처를 확정한다.\n2. 신원 확정 기준 및 정상/미사고 근거를 제시한다.\n3. 반복 후보 연결요소 단위의 train/dev/calibration/eval 배정과 고정 시드를 승인한다.\n4. 참조 지도·분위수 전처리에서 각 eval vessel/event를 제외할 범위를 확정한다.\n5. 임계값 출처, 초과 경계, 최대 구간 간격, 지속 최소 행수·시간을 사전 고정한다.\n6. 전체 예측을 사고시각 열람 전에 동결하고, 공식 시간오차 F1 수식·6시간 경계를 확인한다.\n\n1103_v2는 부모가 intake 중이며 worker는 이를 읽거나 기존 자료와 비교하지 않았다. 모든 관찰은 legacy 자료에 한정된다.\n'''
    report += '''
## Timing guard clarification

A is the first maximum in original input order (`idxmax` semantics); time ordering is used only for B/C segment search. Hourly `max_gap_hours` must be greater than 0 and at most 1, so an unobserved hourly bin cannot be bridged. Identical duplicate scores retain all source rows and count once toward unique-timestamp persistence. Conflicting same-time scores, including missing/valid conflicts, return `data_conflict / duplicate_timestamp_scores_conflict` and leave A/B/C blank. The actual accident-decision meaning of the positive score floor remains unresolved.

The 100-vessel table is a legacy target table. A W0 report of zero overlap with the new v2 Test B roster is pending independent confirmation; do not rename these rows as new targets or transfer predictions. Legacy synthetic checks are not evidence of the current Round 001 interface or actual-data performance.
'''
    (OUT / "readiness_report.md").write_text(report, encoding="utf-8")
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    summary["round_output_hashes"].update({
        "timing_interface.py": digest(OUT / "timing_interface.py"),
        "publish_legacy_preparation.py": digest(Path(__file__).resolve()),
        "readiness_report.md": digest(OUT / "readiness_report.md"),
    })
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    env = {"python": sys.version, "platform": platform.platform(), "copy_operation": "stdlib byte-copy of prepared legacy CSV; no scoring code imported", "legacy_actual_exit_code": process["exit_code"], "round_artifact_creation_exit_code": 0}
    (RUN / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    audit = {"started_at": started, "ended_at": datetime.now(timezone.utc).astimezone().isoformat(), "exit_code": 0,
             "operation": "copy inherited preparation CSV and write manifest/summary/report; no new calculations",
             "source": meta(legacy_csv), "outputs": [meta(output_csv), meta(OUT / "input_split_manifest.json"), meta(OUT / "summary.json"), meta(OUT / "readiness_report.md")],
             "preserved_legacy_execution": meta(LEGACY / "run_001/process_result.json")}
    (RUN / "round_output_process.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"exit_code": 0, "vessels": len(rows), "output": str(OUT)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
