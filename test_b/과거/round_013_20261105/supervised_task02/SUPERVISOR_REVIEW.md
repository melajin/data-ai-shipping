# Round013 supervised Task02 감독 검토 기록

## 승인 결과

감독은 §6–7의 g6 선택·적격, 기준선, cluster bootstrap 및 MDE 구현과 `summary.json`, `independent_audit.json`, 보고서의 수치를 승인했다. Tier0–1에서 w7은 0/41, w3은 0/46이며 두 창 모두 사전 통과 기준을 충족하지 못했다. 2025 자료는 항차 수 coverage만 집계했고 100척 중 37척(37%)이 항차 수 부족이다.

이 승인으로 기술적 계산·독립검산은 완료(technical complete)로 기록한다. 학습자가 설계 이유를 설명하고 결과를 해석·진단하는 능력(learner understanding)은 평가하지 않았으며 미확인이다. 본 실험은 사후 배치 국소화 평가이지 조기경보 평가가 아니다.

## 문서 및 경로 보정

공식 사용자 결과 경로는 [한국어 결과 보고서](ROUND013_보고서_20261105.md)다. 재현 명령의 fenced PowerShell 블록, `run_round013.py` 원천 경로, AUDIT의 `rfid_id_int`/`ts` 표기를 보정했다. g6/g7 스크립트의 향후 명령 문자열은 `supervised_task02`를 포함하도록 수정했다. 기존 `execution.json`, `g6_execution.json`, `g7_execution.json`의 command 값과 실행 로그는 당시 기록으로 보존하고, 별도 `confirmed_reproduction_command` 필드와 `metadata_correction.json`에 교정 경로를 기록했다. 이 변경은 문서·로그 명령 문자열 메타데이터만 다루며 승인된 데이터 계산을 재실행하지 않았다.

폴더 분리는 root에 있던 미확인 과거 산출물과 이번 감독 승인 산출물을 혼동하지 않고, 승인된 Task02 증거·검산·보고서를 단일 경로에서 식별하기 위한 것이다. root의 미확인 파일과 원자료는 보존했다.

## 모델 요청과 실행 증거

- 최초 Orca 영수증: `dispatchId ctx_5bc067f5479b`, `model=gpt-6-luna`, `effort=xhigh` (감독이 확인한 영수증 정보).
- 후속 dispatch: `ctx_e1f790dfe8b5`; 기존 GPT-6 Luna xhigh 모델 지시 유지.
- 실제 추가 runtime telemetry: 제공되지 않았다. 요청/영수증 확인은 Python 프로세스의 runtime 모델 측정과 구분한다.
