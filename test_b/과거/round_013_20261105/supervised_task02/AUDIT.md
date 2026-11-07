# 독립 검산 및 출처 감사

## 감사 범위

검산 코드는 audit_round013_post.py이며 Python 표준 라이브러리만 사용하고 g6/g7 생성 함수를 import하지 않습니다. 저장된 항차별 §4 결과, §6 사건별 선택·확신도, §7 사건 결과와 요약 JSON/CSV를 다시 읽어 선정, 적격 분모, 적중, 기준선 확률, cluster bootstrap CI와 MDE를 별도 구현으로 재계산했습니다.

## 검산 결과

- 결과: True; 불일치 0건.
- g4 항차 3615건, 선박 상태 행 164건(82척 × 2창), 선택 126건, 확신도 126건, 사건×창 평가 행 200건을 확인했습니다.
- g4 항차 시작/끝/행 수 3,615건은 Round008 dev parquet에서 id와 ts만 청크로 읽고 중복키 첫 입력 행을 보존한 재구성 결과와 모두 일치했습니다. voyage split 차이는 없었습니다.
- w=7 상태는 58척 적격, raw 이력 부족 11척, 유효 이력 부족 12척, 유효항차 없음 1척입니다. 전체 사건 중 68건, Tier0–1 중 41건에 예측을 만들었습니다.
- w=3 상태는 68척 적격, raw 이력 부족 11척, 유효 이력 부족 3척, 유효항차 없음 0척입니다. 전체 사건 중 78건, Tier0–1 중 46건에 예측을 만들었습니다.
- 각 창의 선택 항차는 해당 선박의 유효 lin_min 최솟값과 일치했고, 동률 처리 순서는 시작 시각·항차 번호 순입니다. 한 선박의 여러 사건은 동일한 예측을 공유합니다. g4에는 midpoint가 없어서 g6가 원 id/ts를 읽어 행 인덱스 floor(n/2)로 복원했으며, 그 항차 분할의 시작·끝·행 수 parity 검사를 통과했습니다.
- 사건마다 collapse hit, 같은 선택 항차에서 계산한 정수 시각 baseline, midpoint/end hit를 표준 라이브러리로 재계산해 summary와 대조했습니다. 적격 Tier0–1은 w7 0/41, w3 0/46, raw p 및 보정 p는 두 창 모두 1.0입니다.
- 독립 cluster bootstrap은 각 창·모집단 4,000회, 동일 seed=11052026, 선박 단위 복원표집으로 다시 계산했습니다. 네 CI 모두 [0,0]으로 생성 결과와 일치했습니다. MDE의 임계 적중 k=3 및 최소 대립률도 표준 라이브러리 이항 꼬리 계산으로 허용 오차 1e-10 이내 재현됐습니다.
- 합성 검증 10/10 통과. Task01의 별도 9/9 synthetic checks는 이전 실행 기록으로만 참조하며 두 검증 묶음을 합쳐 세지 않았습니다.

## 입력 출처와 보존

Task02의 후반 계산 입력은 root의 g4_voyage_local_collapse.csv, g5_confound_summary.json, 고정 Round008 positives였습니다. midpoint 재구성에는 Round008의 두 parquet에서 
`rfid_id_int`와 `ts`만 청크로 읽었습니다. 원래 PROTOCOL.md, Round011/012 파일, 고정 원자료의 SHA-256은 g6/g7 실행 전후 동일합니다. 해시 세부는 input_output_manifest.json, g6_execution.json, g7_execution.json에 있습니다.

다른 출처의 root summary.json, g3_confidence.csv, g6_selection.csv, g7_event_evaluation.csv, execution.log 또는 g3_coverage.py/g4_local_collapse.py/g5_hour_confound_check.py 수치는 실행 입력이나 검산의 기준으로 읽거나 승계하지 않았습니다. 감독 지시에 따라 기존 파일은 보존하고 이 Task02의 공식 이름 산출물은 supervised_task02 아래에서만 새로 만들었습니다. root 최종 보고서는 대체하지 않았습니다.

## 검증의 한계

독립 검산은 산출물 계산의 재현성을 확인하지만 잠정 연결된 사고 정답의 실제 확정성을 보장하지 않습니다. 같은 dev 데이터에서 lin 계열이 여러 라운드 선택된 반복선택 편향, 이항근사의 사건 간 독립 가정, MDE의 비군집 근사, 퇴화한 0 적중 bootstrap 구간은 그대로 남습니다. 이 실험은 사후 배치 국소화이지 조기경보가 아니며, 학습자의 이해·진단 역량은 평가하지 않았습니다.
