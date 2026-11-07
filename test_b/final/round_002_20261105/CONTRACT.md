# 모듈 공통 계약 v1

총괄만 수정한다. 작업자는 다른 담당자의 파일을 되돌리지 않고 명시 API로 연결한다.

## 입력과 정규화

Round008 dev_hourly_scores.parquet와 additional_hourly_scores.parquet에서 positiveCSV의 82개 RFID만 Arrow filter 또는 청크로 선별한다. 필요한 열만 읽고 state와 불필요한 문자열 열은 적재하지 않는다.
정규 열: rfid_id(string, 원 rfid_id_int 변환), ts(int64), source_ordinal(int64), len_m, bbox_m, cen_lon, cen_lat, score(float).
같은 RFID/source_ordinal의 값이 충돌하면 조용히 선택하지 않고 오류를 진단한다. 정확 중복은 제거한다. 같은 RFID/ts의 복수 행은 최소 ordinal을 대표로 고르고 제거 수를 기록한다. 정렬은 rfid_id, ts, ordinal 순이다.
geometry_valid는 len과 bbox가 유한하고 0 이상인 조건이다. 위치는 유한하고 lon[-180,180], lat[-90,90]일 때 유효하다. 위치 무효여도 U는 계산할 수 있다. 실제 거리 계산은 없다.

## context_features.py — Gemini 소유

API: compute_features(frame: pandas.DataFrame) -> pandas.DataFrame.
입력 열과 행 순서를 유지하고 다음 열을 추가한다: n_history(int), history_days(int), history_eligible(bool), n_cell_history(int), context_used(bool), U(float), C(float).
내부 정렬은 가능하지만 반환 index와 순서는 입력대로 유지한다. state, score, 사고정보는 특징 계산에서 사용하지 않는다.
각 t의 history는 같은 RFID의 [t-720,t) 내 geometry_valid 시간 대표행이다. 현재 행은 history 갱신 전에 평가한다.
n>=24, distinct(ts//24)>=3, 현재 geometry_valid를 모두 충족하면 특징 적격이다. 미달이면 U/C=NaN이다.
과거 전체 log1p(len), log1p(bbox) 각각 p=(현재보다 작은 개수 + .5*동률 개수)/n, r=1-2*min(p,1-p), U=(r_len+r_bbox)/2.
셀은 floor(lon/.05), floor(lat/.05)다. 현재 위치 유효하고 동일 셀의 위치 및 기하 유효 과거행이 8개 이상이면 그 셀의 분포로 같은 r 평균을 계산해 C와 context_used=True를 만든다. 그 외 C=U다.
n_cell_history는 실제 같은 셀 과거 수다. 과거 셀만 사용한다. 점수 범위는 [0,1], 상수 이력의 같은 값은0이다.
미래행 추가 시 기존 특징 불변, 720h 경계, 24행,3일,8셀행,결측,RFID 분리,동률을 작은 fixture로 확인한다.
소유 파일: context_features.py, feature_checks.py, feature_checks.json, FEATURE_NOTES.md.

## data_eval.py와 run_experiment.py — Luna 소유

load_dev(root)는 canonical frame과 positives를 반환하고 입력 진단을 저장한다. evaluate(frame_with_features, positives, output_dir)는 아래 예측과 평가를 저장한다.
root는 Path(__file__).resolve().parents[3]다. 새 출력은 이번 round 폴더에만 저장한다. context_features API를 import해서 결합하는 runner를 만든다. 공통 계약과 다른 담당 파일은 수정하지 않는다.
후보 pool: base=finite(score), common=geometry_valid & history_eligible & finite(U) & finite(C) & finite(score).
RFID에 common이1행 이상이면 U/C/B0_common은 같은 common을 사용하고 B0_full은 전체 base를 사용한다.
common이0이면 U/C는 B0_full로 RFID 단위 fallback하고 B0_common은 무예측(조건부 분석용)이다.
full 비교의 Kcap=min(K, common행수) if common>0 else min(K,base행수)로 제한하고 B0_full에도 같은 Kcap을 적용한다. common 분석은 공통 pool만 사용한다.
K=1과4를 평가하며 top1은 top4 목록의 rank1이다. 총5후보가 아니다. 중복시간 없이 점수 내림차순, ts 오름차순, ordinal 오름차순으로 선택한다. 추가 시간 간격 최적화는 없다.
RFID별 예측목록을 사고정보와 결합하기 전에 저장한다. 같은 RFID의 모든 사건은 같은 예측목록을 공유한다.

출력: predictions.csv(rfid_id,method,rank,ts,score,source_ordinal,fallback,candidate_count), event_results.csv(acc_id,rfid_id,tier,conflict,acc_ts,method,k,predicted_times,abs_error,hit,coverage flags), metrics.json, diagnostics.json, EXECUTION.json.
방법은 B0_full,B0_common,U,C다. 전체100,Tier01=60,common 존재,사고±6h 관측가능 집합의 분모를 구분한다. 무예측 error=null, hit=False다.
무작위: pool관측 n, 사고±6h 내 h개에 대해 Kcap 비복원 균등 선택의 p=1-C(n-h,Kcap)/C(n,Kcap), n=0이면0. top1은 h/n이다. common/base를 각각 보고한다. 사건별 정확 기대확률만 계산하며 사건독립 binomial p를 만들지 않는다.
bootstrap은 RFID를 복원추출해 해당 모든 사건을 반복 포함하는 사건가중 평균 차이를4000번(seed20261105) 계산한다. 전체/Tier01 각각 수행한다. C-B0_full,C-U,C-B0_common을 top1/top4로 계산한다. CvsB0_common은 common 존재 조건부 집합이다.

runner는 실행 직전 가용 RAM을 확인한다. 예상 추가 peak768MiB+reserve640MiB를 확보하지 못하면 실행을 보류하고 JSON을 남긴다. 다른 실행 작업도 기록한다.
데이터 읽기/특징/평가 단계별 시간, 프로세스 peak working set(플랫폼에서 실제 조회 가능값), 버전, 소스/입력sha256, 종료상태를 기록한다. 선박별 순차 처리를 우선한다.
미래혼입,상수,중복,무예측,RFID 내 공유예측에 관한 작은 의미 있는 fixture 확인은 수행할 수 있다.
이번 작업은 구현과 작은 fixture 확인까지다. 실제 dev 본 실험은 두 모듈 통합 후 총괄이 한 번 실행한다. 기다리는 polling이나 자동 재시도 루프는 만들지 않는다.
