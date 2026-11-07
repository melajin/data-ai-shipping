# Round017 — 제어 소스 승인, 첫 영수증의 PowerShell 상수 오류로 smoke 중단

종료 관찰·CIM 생성시각·배타 실행 표식·전체 시간 예산을 수정하고 독립 소스 승인을 받았다. 하지만 **smoke 실행기 1회가 첫 영수증 작성에서 OS exit1로 실패했다.** `Save-WrapperReceipt`의 `claimed=true`가 PowerShell 명령 `true` 호출로 해석됐으며 올바른 불리언은 `$true`다. 시험용 Python child를 시작하기 전의 실패다. 재시도0, probe child0, Python auditor0, mock0, saved-audit0, model0, 새 F1 없음이다.

## 이전→현재→다음

Round016은 deadline/종료관찰 경계 때문에 소스를 승인하지 못했다. 이번에는 단조시계 경과·종료관찰·Wait 반환·OS exit를 분리하고 불확정 경계를 실패로 남기도록 수정했다. CIM DateTime/DMTF와 루트 생성시각의 UTC 정밀도를 맞추고, 실행 전 claim 및 실패 영수증, 전체 모드 시간 예산을 추가했다. 작성자 ACK 뒤 별도 검토자가 정확한 소스 해시를 승인했다. 문법검사도 통과했지만 유효한 PowerShell 명령 표현식인 `true`는 문법 오류가 아니어서 실행 오류를 놓쳤다.

첫 `Save-WrapperReceipt 'running'`에서 실패했고 catch가 같은 writer를 다시 호출하므로 wrapper receipt도 생성되지 않았다. manager의 외부 실행 로그·OS 종료코드와 `logs/smoke_01/execution.claim`은 남았다. 이번 관찰은 실행제어 계층의 구체적 런타임 결함이며 deadline·트리 정리 시험이나 저장 수치 감사의 성공을 뜻하지 않는다. 실패 claim과 동결 소스를 수정하거나 재실행하지 않았다.

다음 Round018은 동결 소스를 복사하여 회차 경로/스키마와 `claimed=true` 한 곳만 수정하고 새 해시 승인을 받는다. bareword 상수 표현식을 별도로 검토한 뒤 동일한 model-zero smoke→mock→audit를 한 번씩 수행한다. 전체 estimator 통합은 이번 실패로 여전히 조건부 후속이다.

## 관찰과 자원

| 항목 | 결과 |
|---|---|
| 외부 PowerShell 실행 | 22:35:08.8689192–22:35:12.5241218 UTC, 3.6515994초, PID13392, exit1 |
| 15초 smoke 전체상한 | 실제 실행은 상한 내 종료; gate 실패 |
| 실행 표식 | 22:35:11.5164502 UTC, 자식 시작 전 배타 생성 |
| probe / auditor / mock / audit / model | 모두0; smoke wrapper 시도만1 |
| 실행 직전 RAM | 22:35:08.8184464 UTC 가용5.5104904GiB, 다른Python0 |
| 메모리 추정 | 작은 stdlib JSON/직렬해시/PS+Python ≤200MiB 가정, 실측 peak 아님 |
| 기존 선택 파일 보존 | 45개 전후 SHA 일치; 원자료 전체 전수검산은 아님 |

원자료·이전repo·실제자료·OUTER·holdout·checkpoint 접근0, .pt 역직렬화0, head opaque hash도 audit 미실행으로 이번0이다. 외부업로드·설치·공식제출·유료0. 실행 후 다른Python이 없음을 확인했으며 사용자 프로세스를 종료하지 않았다. RAM 부족이 원인은 아니다.

Python SHA `8ca9be725be25a6d4e80d43a17a82341ef78a94ea33115ff8d3bfef10ce4b227`, PS SHA `fba54fd84873430039348f8d15a6660655126df7bc19ed2bdde8f4c71c7de720`, 승인map SHA `9d20b92bf696b7d6d2003c9bd34bb4105f8fd6ebc4113e357f94f5595e100fe9`. ACK/manifest 및 관리자 사후해시가 일치한다. 모델 요청과 로컬 host turn_context는 관리자 Astra/high, 작성·검토 Luna/xhigh로 일치하며 내부 모델 인증으로 주장하지 않는다.

조건은 고정 저장 JSON과 모델 없는 프로세스 시험이었다. 예상은 정상·timeout 분리 후 저장감사였으나 실제 관찰은 첫 영수증 writer의 명령 해석 실패다. 기술 목표는 미완료, 학습 질문은 문법검사와 실행 의미 검증의 차이 및 child 성공/실행기 성공/저장감사/F1의 구별이다. 학습자 이해·하드웨어 검증은 미평가다.

반복 노출된 개발 OUTER5897 baseline micro-F1 **0.5930133966423605**, macro0.5252719738966167, 미채택 탐색0.5933525521451586 유지. 독립/공식null, 목표0.7 미달. round015 역사 wrapper=false 및 round010 역사 gate=false도 보존한다.

완료 REPORT/STATUS(current_round=round_017,handoff.ready=true)/LEDGER/NEXT를 저장한 뒤 새 Astra high 세션의 prompt 수락을 확인하고 종료한다. structured chat 닫기 명령은 현재 CLI에 없어 필요한 경우 이 완료 세션 탭만 수동으로 닫는다. 새 수신자가 쓸 공유 상태는 수락 후 수정하지 않는다.
