# 합성 통과 시에만 채택할 다음 회차 설계 초안

현재는 실행 전 초안이며 실제 실행 승인/통과 사실이 아니다. 최종 결과 검토 뒤 NEXT_SESSION을 확정한다.

round010: 고정 실제 FIT3144×312와 기존 두 INNER 질의에 검증 column16+row8을 함께 적용하는 재현1회. 모델/특징/클래스/head/입력 순서/정밀도/seed/estimators/배치 설정은 기존 유지. checkpoint1/contextfit1/predict1, 원경로 추가실행0, M4/새 계수학습/OUTER/holdout/F1/원자료읽기0. 실제 입력은 이미 승인된 development context만.

입력은 round008/artifacts/context_export_attempt_001에서 새회차로 바이트복사한 후 hash 확인: context NPZ1916394bytes/9c6142974a2eb09baa8d4da3eebfde5d71fca40dd2fafbfe1bf21e22a08ea5c5, query_freeze748bytes/6b5c5c7e3e13ad105e641bf8a442af0ae7d5b68ae81be865fd1fcfd99acb23ef. 고정 ID [36001915,31703435], digest7750db94f83f57a4e58b62f29b32ba2e737339108e0923a970f9a924bf9be969. 보호자료·명부를 탐색하여 다른 질의를 고르지 않는다. reference는 round008 pilot의 고정경로 첫 두 행만 기존 reader로 읽으며 y_inner는 읽지 않는다.

작성자는 새 pilot/mock/wrapper, 검토자는 source/승인manifest/결과 독립검산, 관리자는 계획/입력복사/실행/공유문서. 어댑터 두 개는 round009 실행 승인본을 바이트복사한다. ROW는 실제재현에서 baseline이 없으므로 fit직후 원ROW에 resolved ROW_CONFIG를 configure한 뒤 어댑터를 설치해야 한다. COL도 기존 configure-before-install 유지. 원관리자 복원은 모든 설치 이후 진단을 포함하는 try/finally 안에서 기록보다 먼저 수행한다.

ROW/ICL 단계별 진입/완료를 기존 호출 안에서 기록하여 이후 실패를 좁힌다. 새로운 forward/predict를 추가하지 않는다. ICL 전체 T문맥·train_size를 자르지 않는다. source 객체 덮어쓰기 금지, configure_source 등 별도 키 사용. 설치 전 mock은 callable 가짜원관리자, 설정 전달, 두 어댑터 공존/복원, 짧은 청크/순서/미인식 tensor 거부를 검증한다.

통과 조건은 기존 실제재현과 동일: finite/[0,1]2×4, 클래스[0,1,2,3], 행합오차≤1e-5, 고정 historical reference와 최대절대차≤1e-4, 두argmax일치, 입력/shuffle불변. exact와 tolerance 구분. tolerance를 합성1e-5와 혼동하지 않는다. 실패 후오차완화·질의교체·재시도 금지.

예산 초안: 관리자30분, mock1회≤30초+결함수정후1회, 실제1회≤600초(정리10 포함), 큰계산동시1/threads≤3. 실제실행 전RAM≥4GiB, 실행중<1.5GiB에서소유PID/생성시각/실행상태확인후정리. 새경로전체peak미측정; 이전중단sampled peak약2.96GiB/실제수요상한아님, 잔존column출력/ICL위험기록. 부족하면계절metadata/소스계약·문서검산후재확인. 대체작업후에도부족하면같은RAM조회만하는후속세션을만들지말고정확한재개조건을남긴다.

성공은고정두질의재현증거뿐이다. M4 실행은자동으로추가하지않고다음별도회차에서평가계약/자원/선택규칙을검토한다. 실패는마지막ROW/ICL/column경계와자원·수치·설정계층을분리하고동일무변경실험을반복하지않는다.
