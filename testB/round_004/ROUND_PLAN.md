# Round004 실행 전 계획

2026-11-05 KST. 감독 codex_8df5a67b_34a4_4a72_b561_d45861870f6f, Run run_a4759578d2ef. 최초 ACK msg_a4a6dab10faf 뒤 STATUS 소유권과 이전 감독의 활성화 msg_0c84a4c3fc9d를 모두 확인했다. 요청/기록된 Orca launch 설정 gpt-6.1-sol/high, provider 내부 모델/effort는 unknown이다.

기술 질문: 좁은 정수 도메인을 fail-closed로 검증하고 key_valid 후 concat ordinal을 보존하면 원본 전체-Series 변환과 같은 값/순서/dtype/제외/index를 유지하는 bounded loader를 만들 수 있는가? 학습 목표는 제한 도메인의 조건부 논증, 실제 표본 비교, 전수 coverage, 참조 일관성, 사고 성능을 구분하는 것이다. 설명 질문: unsupported 문자열을 잘못된 행처럼 삭제하면 왜 원본과 다른 알고리즘이 되는가?

## 계승 및 고정

Round003 단순 batch prototype은 기각됐다. E 최종 exit2/failed와 V 실패 재현 fixture exit0/감사 succeeded를 구분한다. 실제16,384행은 결합표 단일변환이므로 청크 동등성 증거가 아니다. key_valid 후 concat index의 숫자 제외 구멍을 보존해야 한다. runner는 생산 builder 없는 default-deny stub이다. 실제 train domain, 새 경로 peak는 unknown이며 실제 참조/새점수/A/membership는 없다.

Round002 새100척46,705행/source4,212,389행 독립전수대조와26행 합성을 반복하지 않는다. 초기 FAIL/exit1, metadata-only delta PASS10/exit0, 역사44해시 의미/시점/바이트 unknown을 보존한다. 원본 변환 순서/값/dtype/제외/월·물리순서/정렬동점/라벨/상수는 변경하지 않는다. 사고신원/정상근거/개발사용/공식수식은 외부근거 부족이다.

## 현재 허용 작업과 소유권

1. 실제 별도 Orca E(gpt-6-luna/xhigh)는 execution/만 수정한다. 원본4해시, load_rows API와 실제 builder의 columns/kwargs를 조사하고 제한 도메인 명세와 adapter를 구현한다. ASCII 정수/부호/leading-zero/null/명백한 nonnumeric 정책을 명시한다. ID abs<=2^53, date int32 등 정확성을 논증하되 unsupported 소수/scientific/공백/overflow를 조용히 삭제하지 않고 전체 작업을 중단한다. ID 제거 후 date 검사 순서를 보존한다. 지원범위의 작은 fixture 및 실제 작은 train 표본에서 여러 batch 변환 호출을 추적해 원본 AST와 비교한다. 각 출력 index/제외집합을 검증한다. 실제 표본 최대16,384행/필수열, 배치<=4,096으로 한정한다. 전체 key scan/참조/점수는 아직 금지다.
2. 실제 별도 Orca V(gpt-6-luna/xhigh)는 audit/만 수정한다. 첫 작업은 원본과 계약 기반 독립 정적 도메인 논증/부정검사/전역 index/메모리 조건 검토다. E 산출물 뒤 별도 후속 task에서 독립 oracle+원본 AST로 동적 검산한다. E 생산코드를 수정하지 않는다. 공통문서/통합은 감독만 소유한다. 서로의 변경을 되돌리지 않는다.
3. 작은 동등성·독립검산·메모리 예산을 통과하면 별도 사전 계약으로 2026 train key-only 전수 domain 검사를 허용한다. 월/열/기대행수/population/hash/offset·mask/출력경로/예산을 먼저 고정한다. 실제 coverage는 검사 전 unknown이다. 미지원이면 fail-closed 후 A방식(키열 전체 전역변환+feature청크)을 검토한다.
4. loader 이후 모든 중첩 배열/정렬/groupby/set/dict/KDTree/closure/cache/scratch와 serializer를 포함한 새 경로 RAM, 고정 train-onlyfit, 쓰기/pycache/progress 차단 동적관문 뒤에만 조건부 참조/탐색점수/A를 허용한다. 일관성 summary를 전수 동등성으로 표현하지 않는다.

## RAM과 종료 분기

05:51:22.7468464+09:00 CIM 가용4,441,752KiB/총14,480,244KiB 관측. 프로세스 표본은 explorer/Orca/Codex 등 복수 host 작업이며 정확한 세션별 병행부하는 unknown이다. E 경량 구현/작은표본 증분<=512MiB, V 정적검토<=256MiB, 각 세션 여유512MiB를 계획한다(합계1,792MiB 계획, peak 실측/보장 아님). 근거는 <=16,384행 필수열 투영/<=4,096행 batch와 정적 텍스트검토다. launch와 각 메모리 실행 직전 fresh RAM/타 작업/예상peak·근거·시각을 기록한다. 부족하면 다른 가능한 작업 후 재개 직전 재확인, 청크/순차/동시수 축소 우선이다. polling/watch 및 사용자process 종료 금지다.

모든 신규 산출물은 round004 소유권별 아래만. 원자료/canonical/cache/선행round 읽기전용, 원CSV 재파싱/전체object 이중로딩/stockCLI/main/stage 금지다. 임계값/B/C/사고판정/성능/제출/실제split/사고파일 개발사용/외부수집·연락/push는 금지한다. 실패는 근거와 실제 exit를 남기며 worker_done으로 보고한다. 매라운드 비교/상세보고/쉬운설명/다음검증과 실제 새 Sol/high 감독 ACK·단일소유권 인계를 유지한다.
