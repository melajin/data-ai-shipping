# Round004 — 안전 도메인 검증과 원본 index를 보존하는 bounded loader

새 실제Sol/high감독의ACK·단일소유권활성화후round_004/에서수행한다. E/V는각각별도실제Orca gpt-6-luna/xhigh, worker_done을사용한다. round003실패원본과round001·002/원자료/canonical/cache는읽기전용이다.

## 계승·기각

새100척명부/46,705행의round002전수대조및26행점수합성을반복하지않는다. round003의단순batch numeric prototype은기각한다. E최종exit2/failed, V의원본AST반례재현fixtureexit0/감사task succeeded를구분한다. E실제16,384행은두8192batch를결합한Table에transform_batch한번이므로청크별동등성증거가아니다. 원본key_valid후concat index의구멍도보존해야한다. round002최초FAIL/metadata-only PASS10과역사44해시unknown은그대로다.

## 다음 가설·순서

1. 실제Luna 실행자는새소유execution/에서원본4해시·load_rows API/실제builder호출열/kwargs를읽고지원할범위를명시한다. 우선 **제한 정수 도메인을 bounded scan으로 증명한 뒤 같은변환을하는B방식**을검토한다. ID/date에지원하는ASCII정수문자열문법·길이·부호/leading-zero·null/명백한nonnumeric처리를명시한다. ID절댓값<=2^53/date int32범위등으로global float추론에서도정확한값이되게한다. 1.5/scientific/공백/초과값등미지원은잘못된행으로삭제하지말고전체단계fail-closed다. 원본이수용하는값을임의제외하지않는다. IDnumeric실패행제외후date검사/변환순서를지킨다. 실제전체domain은아직unknown이다.
2. 새작은fixture에서원본AST+독립oracle와값/열/월·물리순서/dtype/NaN/제외집합/**출력index**를대조한다. key_valid_only True/False,월/배치경계,빈batch,키누락,leading-zero/부호/NaN,2^53경계와넘는반례,소수/overflow/미지원중단을포함한다. 실제train작은표본을사용할경우transform_batches를실제여러번호출하고각batch/index를추적한다. 이미있는결합표검사를같은결과로반복하지않는다. 별도Luna는소스·부정검사·도메인논증·메모리예산을검산한다.
3. 위작은동등성및메모리계획이통과하면감독은2026 train key-only 전수domain검사만별도로허용할수있다. 이것은새필요검사이며기존Test전수대조의반복이아니다. 필요한열/월/기대행수/선별population·failclosed기준·hash·출력경로·예산을실행전고정한다. 원CSV재파싱/기존parquet수정/전체8열object동시로딩금지. domain검사결과는입력해시/스키마와연결하고각후속loader도지원범위밖이면중단한다. 전수검사결과·원행/전체index offset/mask·실제exit·가용RAM/RSS를별도검산한다.
4. B방식에미지원값이있거나증명이어려우면 **A방식(키열전체전역변환+feature청크)** 으로전환한다. 월/key_valid후원래concat순서의ID전체Series에원본pd.to_numeric를한번호출하고제외/cast,남은행의date전체Series에원본변환을한번호출한다. key_valid후concat ordinal을output index로보존하고숫자제외뒤구멍을유지한다. raw한열과numeric결과/마스크/문자객체·복사·scratch page cachepeak를산정한다. V의0.3~0.8GiB/열후보는미측정추정이지보장값이아니다. 전역ID/date를무조건동시에다로딩하지않는다. 원본알고리즘의반올림을임의교정하지않는다.
5. loader동등성관문통과후harbor/density/gap단계별새실행계획을수립한다. 원본순수함수재사용·상수/라벨/모집단/정렬동점/지도집합을보존한다. 숫자loader후의유지배열/정렬/groupby/set/dict/KDTree·CDFclosure와전역cache를포함하여**새실행경로**의peak를다시산정한다. 기존object경로의density3~6GiB추정또는2GiB초기추정을그대로안전보장으로쓰지않는다. 단계별subprocess/scratch·cache해제를활용하고serializer의키/값/순서도검증한다. 원본gap의미명시동점정렬을임의stable로바꾸지않는다.
6. 감독은메모리안전예산·실행명령/출력경로/파라미터·원본해시·train-onlyfit/쓰기격리·pycache/progress부작용차단의동적검사를보고큰참조기술관문을해제한다. round003 runner는미구현stub으로재사용완성품이아니다. 조건충족시2026train전용참조와새100척train label/항적membership(원문/숫자정규화정책분리)을생성한다. gap/jump각3,879,693·p50 1h/약85.723526m·density102,053/9,174·fishing1,376,741은일관성대조이며전체동등성증명이아니다. 차이가있으면점수로넘어가지않는다.
7. 안전한고정참조확보시기존46,705행을선박별고정추론해성분/score/후보A·부족표를생성하고별도실제Luna가참조입력/원행표본/성분독립계산/A100순서·공란·최대·생산불변/실제exit/해시를검산한다. round002 EXPLORATORY_EXECUTION_CONTRACT의원행/A/floor/충돌/naivetime계약을계승한다. 사고시각으로기간을자르지않는다.

## RAM·범위·종료

모든로딩/변환/병렬작업직전가용RAM·예상peak·다른작업·추정근거/확인시각을남긴다. 부족하면다른가능작업우선,보류재개직전다시확인한다. 청크/순차/동시수축소우선이며polling/watch·사용자process종료금지다. 전체trainobjectframe을이중로딩하여동등성검사하지않는다. 작은도메인검사도메모리예산을검토한다.

임계값/B/C/사고판정/성능/제출/실제split/외부수집·연락/push금지다. 사고신원·정상근거·개발사용·공식수식부족은blocked_external_evidence다. 후보/합의/목록부재를정답으로만들지않는다. 로컬유효가설은계속진행하며동일실패의의미없는반복은하지않는다. 매round보고·쉬운설명·성공조건차이·다음실제Sol/high감독ACK/단일소유권인계를지킨다.
