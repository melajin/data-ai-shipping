# Test B Round002 결과

2026-11-05. **새100척의46,705행 추출·원행 추적·격리 실행기 준비와 독립검산을 완료했다. 실제 train 참조 재구축·새100척 점수·후보A는 미생성이며 사고 성능은 미평가다.**

## 질문과 판단

질문은 새 Test B100척에 기존 고정 scorer를 Test 적합 없이 적용할 수 있는가였다. 기술 목표는 명부·원행·참조 적합 범위를 확인하고 허용된 탐색 추론을 준비하는 것이다. 학습 목표는 항적 존재, 입력 유효성, 참조 적합, 후보 시각과 실제 사고 정답을 구분하는 것이다. 설명 질문은 “유효한 행이1개인 배에도 점수가 나올 수 있는데 왜 사고 판정 근거가 되지 않는가?”다.

이번 준비 범위는 완료했다. 공용 참조는2026 train에서 생성하고2025 Test는 점수 입력과 자기 과거 이력으로만 쓰는 코드 경로를 확인했다. 실제 새 참조 경로의 동적 검증은 후속이다. 기존 CLI는 옛1027 명부·canonical 고정 출력·원행 누락 문제로 실행하지 않았다. Test 적합·보정·분위수·임계값을 만들지 않았다.

입력은 v2 workbook의 정확한 문자열100ID와 원순서다. 새100척과 옛명부·옛점수의 교집합은0이다. Round001의 CSV12쌍 전량 byte 동일 증거와 당시 독립감사 범위를 계승했으며, 이번에13GB 원CSV를 다시 해시하거나 파싱하지 않았다.

## 이전과 비교

| 항목 | Round001 | Round002 |
|---|---|---|
| 새100척 항적 | RFID 열 관측100/100 | source parquet4,212,389행 독립 스캔, 선별46,705행 전수 일치 |
| 대상별 품질 | 행수·결측 미확인 | 요약100개 모든 필드 일치. 유효·finite46,705, 제외0·중복0 |
| 관측 기간 | parse 계보 | 실제 선별행2025-01-01~06-30. 선박별 범위는 요약CSV |
| 원행 추적 | scorer에 원행 누락 | 월·file·zero-based row_index·source ordinal 보존 및 전수 대조 |
| scorer 준비 | 새명부 추론 가능성 미확인 | AST 격리·해시·A 경계·독립26행 합성 scalar 검산 |
| 새100척 실제 점수/A | 없음 | 없음. 큰 참조의 RAM 상한 미확정으로 후속 |
| 사고 정답·성능 | 신원·정상 근거 부족 | 새 근거 없음. 성능 개선·악화 비교 불가 |

선박당 행수는1~3,413행이다. 전체 행이 유효하다고 개별 선박의 정보가 충분하다는 뜻은 아니다. 시간대와 CRS는 unknown이다. 부분선을 연결하거나 좌표별 시각 없이 속력·가속도를 계산하지 않았다.

## 실행과 독립검산

P는 명부·parse 계보·schema/footer·RAM 계획을 조사했고, R은 고정 코드4개와 참조 적합 경로·부작용을 검토했다. E는 batch16,384·필수열 투영으로2025 parquet6개를 스캔해 새100척 행만 월별 저장했다. 원행 ordinal은 선행 월 행수 합과 파일 내 row_index로 정의했다. 점수 계산의 시간 정렬과 A의 원입력 최초 최대값 선정을 분리했다.

동일 시각의 상충 점수 또는 valid/missing 혼합은 data_conflict로 A를 비운다. 유한 점수가 없으면 no_valid_score다. floor1e-6은 사고 판정이나 정상 확률을 의미하지 않는다. B/C·임계값·사고 여부·제출은 생성하지 않았다.

E의 최초 ID 헤더 조회 실패exit1, SQLite 재사용으로 폐기한 시도, 합성 fixture 실패와 UTF-8 손상본을 보존했다. 최종 clean row scan·문법·합성 검사는 exit0이었다. 감독이 발견한 bound-method shim, 명부 tuple unpack, 해시 guard와 UTF-8 문제를 E가 수정했다. selected parquet의 source 파일명6/6은 원문과 일치했고 데이터는 변경하지 않았다.

별도 V는 ZIP의 작은 workbook을 직접 대조하고, source parquet4,212,389행을 다시 청크 스캔했다. 선별46,705행의 값·월·파일·원행 ordinal이 모두 일치했다. 누락·추가·불일치는0이고, 대상 요약100개의 모든 필드도 일치했다. 실제 달력·hour0~23·key_valid·finite 조건을 추가로 확인했다.

독립26행 합성 fixture는 haversine375회, 과거24행 전후의 s_change와 state를 통과했다. 한 행의 각 점수 성분을 별도 scalar 식과 대조했고, A·floor·충돌 경계도 확인했다. 이는 실제 새100척의 점수 계산이 아니다.

## 감사 실패와 정정

초기 V는 **7pass/1fail/2unknown, aggregate exit1**이었다. 행 대조와 합성 검사는 통과했으나 manifest의 별도44개 해시 중4개가 현재 파일과 달랐고 역사 표시가 없었다.

생산자는 수정 전 manifest의 byte 동일 snapshot을 보존하고44개 digest를 그대로 historical 필드로 옮겼다. 현재 맵은56/56 일치로 단일화했다. 역사44개 digest의 최초 의미·시점, 옛 코드·pyc 바이트 복원은 unknown이다.

별도 변경 검산은 **10pass/0fail, validator exit0**이다. 전후 manifest SHA, snapshot, 역사값 보존, current56/56·prior53/53, self-hash 배제 정책, 코드·보고·scan·selected 불변을 확인했다. 초기 FAIL/exit1은 그대로 보존했다. 변경 검산은 전체 스캔·fixture를 반복하지 않았다. 생산자 정정exit0은 영수증·stdout/stderr 근거이며 별도 exit sidecar는 없다. 독립 delta의 실제 exit 파일은 있다.

## RAM과 다음 관문

E scan의 batch 경계 RSS 표본 증가는68.3MiB, V 독립 scan은134.8MiB, delta는0.6MiB다. 순간 peak를 보장하는 값이 아니다. 단계마다 가용 RAM·예상량·병행 프로세스를 확인했다. delta 직전에는 다른 Python 약1,194.8MiB도 관측했다. 사용자 프로세스를 종료하지 않았다. 감독의05:04:39KST CIM 가용량은4,378,144KiB였으며 다음 실행의 허가값으로 쓰지 않는다.

원본 train loader는 월별 object frame을 모아 concat한 후 숫자로 바꾼다. 여러 참조 builder의 반복 로딩·정렬·그룹 처리와 전역 배열 cache가 겹친다. 초기2GiB 추정은 상한이 아니다. RAM 부족을 실측했다고 단정하지 않으며, 사용량 상한 미확정으로 큰 참조를 보류했다. 그동안 작은 준비·수정·독립검산을 수행했다.

다음 가설은 숫자 변환을 청크별로 먼저 수행하고, 사전 할당·mmap·순차 단계를 사용하면서 원본 값·순서·dtype·제외집합을 보존할 수 있는가다. 동등성과 RAM 관문을 충족하면 고정 참조를 재구성하고 탐색 점수/A를 생성한다.

## 역할·완료 범위·정리

감독은 codex_5a0d6578_03b7_45e9_a0ae_0064ecb43bef, Run은 run_a0639d5ac36a다. 감독 요청·Orca launch 설정은 gpt-6.1-sol/high다. P/R/E/V는 각각 실제 별도 Orca gpt-6-luna/xhigh 세션이며 내부 subagent로 대체하지 않았다. provider 내부 모델·effort는 모두 unknown이다.

성공기준1은 새명부·항적·원행 범위에서 확장됐고,6은 준비 생산변경의 검산·정정을 완료했다. 7의 보고·설명·다음 검증을 작성했다. 사고 신원·정상 정답·독립 분할·최종 사고 출력·실제 성능은 미충족이다. 기준을 낮추거나 근본 성공을 선언하지 않았다. 학습자의 설명 능력과 실제 선박 안전도 검증하지 않았다.

완료 handle의 최신 dispatch와 활성 후속이 없음을 확인했다. P/R/E는 closed_agent_terminal 응답, V 최신 요청은 already_released/processAction none을 확인했다. 옛 retained dispatch를 새 활성 작업으로 보지 않는다. Round001의 user_kept/identity_unproven 잔여 창은 강제 종료하지 않았고 추가 닫힘을 주장하지 않는다. 후속 감독의 생성·ACK·소유권 전환은 HANDOFF_RECEIPT와 STATUS를 따른다.

근거: [입력 준비](preparation/preparation_report.md), [코드 검토](scorer_review/scorer_review.md), [실행기 준비](execution/preflight_report.md), [초기 감사](audit/preparation_001/audit_report.md), [변경 감사](audit/manifest_delta_001/audit_report.md), [다음 검증](NEXT_ROUND.md).