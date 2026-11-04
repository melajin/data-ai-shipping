# Round003: 메모리를 제한한 고정참조 재구성·가능한 탐색점수

Round002준비는완료, 실제참조/점수/A는미생성이다. 다음새Sol/high감독의ACK·소유권활성화이후round_003/에서진행한다. 범위를사고성능으로확장하지않는다.

## 계승하는완료근거

새명부정확100문자열/순서/해시,2025parquet선별46,705행/100척은독립전수비교완료다. source4,212,389행스캔·대상요약100개·유효/finite46,705·누락/추가/중복0,선박당1~3,413행. 초기VFAIL은stale해시구분문제였고metadata-only정정delta10pass/exit0로해소됐으며초기FAIL은보존한다. 같은전량scan/합성검사를새증거없이반복하지않는다. round002산출물은읽기전용이다.

## 새가설과실행순서

가설: 원본loader의월별문자열frame들을모은뒤숫자로변환하는비용을, batch별동일numeric변환·유효키규칙·dtype·원행순서를유지하며조기숫자변환/사전할당/mmap으로줄일수있다. 참조생성의계산규칙/집합/정렬동점/라벨/상수는바꾸지않는다. 이방법이동등성과실행예산을충족하면동일2026train기준을만들어새2025행에고정추론한다. 알고리즘상복잡성을늘리기전에기존순수함수를재사용한다.

1. 새감독은실제Luna/xhigh실행자에새round003소유권을지정한다. 기존loader/load_rows와trainparquet schema/footer·parse계보를읽어단계별유지캐시/배열/정렬/그룹/지도크기를계산한다. 실RAM·다른작업·예상peak·근거를기록한다. 원본loader는key_valid후badnumeric ID/date행제외, rfid_id:int64/part_dt:int32/month:int8을만든다. 청크화가제외집합/값/dtype/순서를바꾸면안된다. 원본parser나전체CSV를재실행하지않는다.
2. 실행자는안전한작은실제train표본(정확선택범위명시)과경계합성에서원본loader와새loader의열/순서/값/결측/dtype를대조한다. 별도Luna가그차이와Testfit차단·write격리를검토한다. 전체trainobjectframe을동시에이중로딩해서동등성검사하지않는다. stockCLI/stage실행금지, canonicalimport의pycache/progress를차단한다. 원본코드해시불일치면진행보류.
3. 감독이검토한메모리예산과실행명령/출력경로/파라미터/계보를실행전에고정한다. RAM부족시다른작은작업후재개직전재확인한다. 최소여유는OS/다른프로세스와예상불확실성을반영해명시하며모든builder의중첩상한을반영한다. 필요시harbor/density/gap을순차분리·scratch저장·전역cache해제한다. 반복polling/watch나사용자프로세스종료는금지다.
4. 조건충족시Luna가2026train전용참조를재구성하고생성입력/중간메타/해시/실제exit/단계RSS·가용RAM을기록한다. gap/jump각3,879,693·gap p501h·jump p50약85.723526m·density fine102,053/coarse9,174·fishing1,376,741의기존summary는일관성대조이며전체동등성증명이나성능목표로취급하지않는다. 차이가있으면원인검토전새점수로진행하지않는다. 새100척의train라벨membership와train항적membership를별도필드로원문ID/정규화정책과함께기록한다. 사고파일은사용하지않는다.
5. 안전한고정참조확보후46,705행을선박별처리해성분/score와최고점후보A·부족표를round003에저장한다. round002/contract/EXPLORATORY_EXECUTION_CONTRACT.md의원행/A/충돌/floor/naivetime계약을계승한다. B/C·임계값·사고여부·제출·F1·실제split생성금지. 실제사고시각으로기간을자르지않는다. 실제점수와candidateA를사고정답/검증발생시각으로부르지않는다.
6. 다른실제Luna/xhigh가변경범위·참조적합·loader동등성·원행표본/성분독립계산·A100순서/공란/최대값·생산불변·exit/해시를검산한다. 미확인/실패를pass로덮지않는다.

## 종료·연속작업

메모리를 안전하게 제한할 수 없으면 큰 실행을 보류하고 동등성·계보·단계 분리 등 유효한 작업을 진행한다. 현재 RAM이 충분한지와 예상 peak가 불명확한 문제를 구분한다. 성공 조건 미달의 이유는 원래대로 남긴다. 실제 사고 신원·정상 근거·개발 사용·분할·공식 수식은 blocked_external_evidence이며 로컬 계산으로 정답을 만들지 않는다.

보고는이전대비/현재/다음검증과쉬운설명을작성하고유효한후속이있으면다시실제새Sol/high감독에ACK/단일소유권인계한다. 실행·독립검산은각각실제OrcaLuna/xhigh이며내부subagent대체금지다. 완료handle은최신dispatch/활성후속확인후release/실제닫힘을기록한다. historical44해시의원래바이트/최초기록시점은unknown으로남긴다.
