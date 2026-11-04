# Round013 — 승인 실행기의 유한 동적 검증

시작 2026-11-04T20:44:14Z. 관리자 마감21:04:14Z(20분), 실험마감21:01:14Z(문서·인계3분 확보). 인계 SHA256 23469A5E22D8572ADB9FA5C400BB48437375A157849E48F8A84B6E276B385CDA 일치. 수신 Orca session codex_cac3fd7d_98ec_4cd3_8b29_95e3f911a10c 일치. 직전 관리자는 done, 같은 회차 다른 관리자 없음. Test B 관리자는 별개 작업이며 종료하지 않는다.

가설: round012에서 승인한 ProcessStartInfo/Process 실행기가 실제 정수 exit0/7·동시 출력 수집·소유 프로세스 종료를 기록하며, fixture와 저장기록 검산을 실행할 수 있다. 변경 변수는 회차명/출력경로/schema뿐이며 round010 검산논리는 보존한다. 정적 승인과 동적 성공을 구분한다.

- smoke 1회≤10초, exit0/7 자식 각1개 순차, 재시도0. 정수 종료코드·stdout/stderr·시간·소유종료·잔존없음·해시불변 모두 충족해야 mock을 시작한다.
- 순수 fixture mock 최초1회≤30초(28+2), 실제 결함 수정·새승인 후 최대1회 추가만. 새 map에 필요한 smoke가 이미 소진됐으면 재시도하지 않고 다음 회차로 이관한다. 성공 뒤 추가mock 금지.
- 실제 저장기록 audit 1회≤30초, 재시도0. exact-map smoke/mock 성공 후만 시작. 예상 snapshot=true, live/current=false, numeric=true, audit integrity=true, historical overall=false. 검산 프로그램 성공이 역사실패를 지우지 않는다.
- 모델/checkpoint load/fit/predict/forward/backward/F1/NPZ/reference/raw/OUTER/holdout/설치/외부전송/유료0. source round010의 작은 소스·metadata·저장JSON 두질의 확률만. 큰 입력/checkpoint 재해시0.
- 원자료 F:/문제 데이터_수정_1027, 이전 repo D:/repos/fishing-track-classification, 모든 과거회차/venv 읽기전용. 모든 신규산출 round013 아래(공유 STATUS/LEDGER/NEXT와 정해진 automation receipt 예외).
- 작성자 /root/round013_author는 code/* 단독 소유, 검토자 /root/round013_reviewer는 review/* 단독 소유. 둘 다 gpt-6-luna/xhigh/forknone 명시 요청. 관리자는 실행·계획·공유상태만 소유. root+2=3≤host4, 보조2≤사용자4. 타인 수정 되돌림 금지. ACK 후 코드 쓰기 중지, 독립 직접해시 승인, live/snapshot/map 전후 불변.
- 초기 RAM4.365486GiB(20:45:18UTC), Python0. stdlib 예상peak100MiB와 문서작업200MiB는 가정. 병렬/각 실행 전 RAM·다른 작업 확인. 시작 가용≥0.5GiB. 부족하면 문서/소스 작업 후 직전 재확인, polling loop와 사용자 process 종료 금지.
- base Python C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B -S, stdlib only. Windows PowerShell5.1, 작업cwd 루트 고정.

독립 승인 후 정확 명령은 다음 순서이며 각 결과를 읽고 다음 단계를 결정한다.

```powershell
& './rounds/round_013/code/run_audit.ps1' -Mode smoke
& './rounds/round_013/code/run_audit.ps1' -Mode mock -MockNumber 1
& './rounds/round_013/code/run_audit.ps1' -Mode audit
```

기술 목표는 실행기 동적 확인과 저장 기록 검산이다. 학습 목표는 테스트통과·종료코드·수치재현·현재출처·역사전체관문 차이를 설명하는 것이다. 학습자 이해달성·실제 장치검증은 미평가. 기존 개발 OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택 탐색0.5933525521451586 유지; 독립/공식null. 새F1 없음.

성공 시 round011 M4 계약과 round012 M4 체크리스트를 근거로 다음 fresh round014에 tiny 합성 head 검증을 인계한다. 실패 시 계층과 새 원인/수정 범위를 구체화한다. 완료 보고서/STATUS(current_round=round_013,handoff.ready=true,active_workers=[])/LEDGER/NEXT 저장 후 Start-NextSession -FromRound round_013의 수락영수증 확인 즉시 이 관리자 종료.
