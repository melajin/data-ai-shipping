# V 후속: E 실패의 독립 검산 및 후속 설계 조건

같은 Round003 감독/Run이다. 오직 audit/failure_001/을 새로 소유한다. 기존 audit 정적검토와 execution 전체/선행라운드/원자료/canonical/cache는 읽기전용이다. 다른 작업자 수정 되돌리기 금지. 실제 Orca Luna/xhigh 요청·기존 launch와 provider 내부 unknown을 구분하고 worker_done으로 보고한다. 큰 실행은 계속 default deny다.

E worker_done msg_f7d45da31bf0은 failed이며 sample comparison 최종 exit2를 보존한다. execution/preflight_report.md, execution_summary.json, sample_comparison.json, execution_receipt.json, bounded_loader.py, compare_loader_sample.py, round003_runner.py와 실제 attempt receipt/stdout/stderr를 읽어 주장/코드/실제exit를 독립 대조한다. 원본4해시와 이전 round002 산출물 해시·생산파일 감사전후 불변은 필요한 작은 범위에서 검산한다.

독립적인 작은 합성에서 전역변환과 batch별변환의 RFID 9007199254740993 대 9007199254740992 반례를 재현하라. canonical load_rows AST의 실제 변환순서를 사용하고 같은코드 복사만으로 독립계산이라 부르지 않는다. 경계 key_valid_only True/False, numeric ID 필터 이후 date 변환, dtype/행·열순서·출력 index도 확인한다. 새 큰 real source scan/실제표본 재읽기는 필요하지 않다. 코드상 실제 train 표본 비교가 두8192배치에 transform_batches를 쓴 것인지, 결합16384테이블을 한 번 transform_batch에 넣은 것인지 특히 확인하고 보고서의 주장과 차이를 적어라. 합성 전체변환이 원본 AST가 아닌 수동재현이라면 그 검증범위도 한정하라. default-deny runner는 production 미구현 stub이다. 이 사실을 Testfit/쓰기 runtime 완성으로 부풀리지 마라.

다음 유효설계 두 가지를 정적 검토해 조건/예상메모리를 제안한다. (A) 전체 key Series만 순서대로 scratch/단계로 모아 원본 pd.to_numeric를 그대로 호출한 전역키결과를 고정하고 나머지 numeric feature는 batch로 투영하는 방식: 원본 ID 변환/제외 이후 date 변환순서/정수cast/global inference를 보존해야 한다. (B) 전체train key_valid 적용후 RFID/date 문자열을 bounded scan하여 제한된 정수 도메인(예: 부호/선행0 포함 정수문자열, ID 절댓값<=2^53, date int32 안전범위; null/부적합 분기 별도)과 fail-closed를 증명한 뒤 batch변환하는 방식: 1.5/scientific/초과값 등을 임의제외하지 말고 unsupported시 중단한다. 이 범위를 지켜도 null/nonnumeric가 전역float추론을 만드는 경우 값·최종dtype·순차제외가 같은지 논증/작은fixtures로 반증가능하게 검토한다. 실제도메인은 전체검사 전 unknown이다. 어느설계도 구현/전수동등성 pass라 부르지 않는다. 새 실제train 전수검사/생산은 이번에 금지다.

E 최초실패·최종exit2·실표본비교범위 한계·아직없는 full ref/score/A/membership를 명확히 구분한다. audit task의 성공은 실패검증/필요조건을 올바르게 기록하는 것이며 생산성공이 아니다. 결과 json/보고서/독립fixture코드·stdout/stderr/실제exit/해시를 남기고 worker_done 보고한다. 임계값/B/C/사고여부/성능/제출/분할/외부수집/사고파일/push 금지.

RAM: 시작/작은fixture 직전 가용RAM·다른작업·예상증분<=256MiB/세션여유512MiB·근거/시각을 기록한다. 부족시가능한작업우선·재개직전재확인, polling/watch·사용자process종료 금지. 전체CSV/parquet/pickle 로딩과 기존46705전수/26행합성 반복금지. E가 이미 settled failed이므로 execution을 수정할 사람은 없다. 필요 보수는 감독에 보고하고 이번 감사는 읽기전용으로 끝낸다.
