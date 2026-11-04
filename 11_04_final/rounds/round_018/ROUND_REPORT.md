# Round018 — 첫 영수증 수정 성공, timeout 종료 판정에서 smoke 실패

PowerShell `claimed=$true` 최소 수정 후 첫 영수증 작성과 실패 영수증 보존이 정상 동작했다. **smoke 1회에서 네 probe를 실행했으며 정상 종료 세 건은 통과, 의도한 timeout은 `indeterminate`로 남아 전체 smoke가 실패했다.** 외부 OS exit1, 8.6628274초로 15초 상한 안에 끝났다. 재시도0, auditor0, mock0, saved-audit0, model0, 새 F1 없음이다.

## 이전 → 현재 → 다음

Round017은 첫 writer에서 bareword `true` 명령 해석 오류로 child를 하나도 시작하지 못했다. 이번에는 동결017 소스를018로 복사하고 회차 표기와 `claimed=true` 한 곳만 변경했다. 작성자와 별도 Luna 검토자가 정확한 변환·문법·해시를 확인한 뒤 같은 승인map으로 실행했다. 실제 writer는 동작했고 네 child의 영수증을 보존했다.

새 실패는 마지막 짧은 Wait와 실제 deadline 사이의 종료 관찰 공백이다. timeout probe의 마지막 WaitForExit는 false로 **0.4959699초**에 반환됐고, 다음 모니터링 뒤 **0.9381056초**에 deadline0.5초 도달을 관찰했다. kill 뒤 exit 관찰은 **0.9397325초**다. 분류 함수는 마지막 Wait 반환이 deadline 이후인 경우만 timeout으로 처리하므로 이번 경로는 indeterminate가 됐다. 이는 현재 증거에 대한 보수적 판정이며 성공으로 소급 변경할 수 없다. `exit_code=-1`, `process_exit_utc=1601-01-01`도 기록됐다. -1을0으로 고치지 않았고, 1601년을 유효한 종료시각으로 해석하지 않았다. 종료 신호·속성 캐시/조회 순서의 정확한 원인은 아직 가설이다.

다음 Round019는 deadline 이후 생존 관찰과 정리 전후 종료 관찰을 분리하고, bounded 종료 wait·OS 코드 획득·종료시각 유효성을 각각 기록하는 최소 제어 수정으로 진행한다. 모든 늦은 종료를 timeout으로 단순 변환하지 않는다. 이번 실패 영수증과 동결 소스는 보존하며 재실행하지 않는다. 전체 estimator 통합은 아직 후속 조건부 작업이다.

## 실행 증거

| Probe | OS code 기록 | 분류 | 판정 |
|---|---:|---|---|
| 즉시 exit0 | 0 | completed | 통과 |
| 즉시 exit7 | 7 | nonzero_exit | 예상된 비정상코드 시험 통과 |
| 1.2초 뒤 exit0 | 0 | completed | 통과 |
| sleep5초 / deadline0.5초 | -1 | indeterminate | 실패, 종료시각1601년은 유효한 실행시각 아님 |

네 probe 모두 스트림 drain과 기록된 소유트리 잔존없음을 확인했다. 사후 별도 조회에서도 기록된 Python/conhost PID 잔존0, 다른 Python0이었다. 이 관찰은 전역 프로세스 소유 증명을 대신하지 않는다. 사용자 프로세스를 종료하지 않았다.

외부 PS PID7468, 시작22:46:03.1598164 UTC, 종료22:46:11.8258763 UTC. 승인map은 실행 전후 동일했다. Python auditor의 receipt는 없다. wrapper receipt는 `state=failed`, `claimed=true`이며 정확한 오류를 보존했다. 이전 단계 전체 성공 관문을 지켜 mock·audit는 실행하지 않았다.

실행 직전22:46:03.1163168 UTC 가용 RAM **5.486618GiB**, 다른 Python0. probe 최소 관찰 **5.361572GiB**였다. 예상 peak≤200MiB는 작은 stdlib파일·직렬해시·PS+Python 가정이며 전체 peak 실측이 아니다. RAM 부족이 실패 원인이 아니다.

## 보존·평가 한계

선택한 기존 파일 **83개**의 전후 SHA256이 일치했다. 이는 원자료 전체 전수검산이 아니다. 동결 Python SHA `49cbf5785791d2c3b843ad095985162675d5a1b2dc3a5a324a9a4a2207048e7a`, PS SHA `acf4865ce46b1d12f506853c03f1d4f78a13deb8cc19b45ccdfdc1bfb8eb862a`, 승인map SHA `bc586a48880da1e7942db80e2f2b58b2d236bd62fce9580508abadc81328f587`를 보존했다. manifest/ACK 사후해시도 일치한다.

원자료·이전repo·OUTER·holdout·checkpoint 접근0, .pt 역직렬화0, head opaque hash0, 설치/외부업로드/공식제출/유료0. 작성자의 공개 Microsoft 문서 참조는 별도 진단 기록에 남겼다. 저장 수치·provenance 감사는 아직 미실행이며 역사015wrapper=false/010gate=false를 유지한다.

반복 노출된 개발 OUTER5897 기준 micro-F1 **0.5930133966423605**, macro0.5252719738966167, 미채택 탐색 최고0.5933525521451586 유지. 독립/공식 점수null, 목표0.7 미달이다. 이번 제어 시험 성공 부분을 모델 성능 개선으로 표현하지 않는다.

## 역할·학습·인계

호스트 turn_context에는 관리자 Astra/high, 작성·검토 Luna/xhigh가 기록됐다. 요청과 호스트 증거를 분리했고 내부 모델 인증이라고 주장하지 않는다. root+2=3으로 호스트4슬롯/사용자 보조4명 상한을 지켰다. 관리자는 계획·실행·공통상태, 작성자는 code, 검토자는 review만 담당했다.

기술 목표는 부분 달성(첫 writer·정상3probe), 전체 동적 관문은 미달이다. 학습 목표는 문법과 실행 의미, 단조시계 deadline과 짧은 Wait, child·wrapper·저장감사·F1의 구별이다. 조건·예상·실제값은 계획과 위 표에 남겼다. 학습자 이해·하드웨어 검증은 미평가이며 설명 질문은 LEARNING_NOTES.md에 있다.

독립 최종검토는 review/FINAL_REVIEW.md, 최소 후속 범위는 review/NEXT_REPAIR_SCOPE.md와 NEXT_SESSION.md에 저장한다. 완료 STATUS의 current_round=round_018, handoff.ready=true 및 LEDGER를 갱신한 뒤 새 Astra high 세션에 인계하고 수락 영수증 확인 즉시 종료한다. 현재 Orca CLI에는 structured-chat 닫기 명령이 없어 필요하면 이 완료 세션 탭만 수동으로 닫는다. 수락 후 새 관리자가 사용하는 공유 상태를 다시 수정하지 않는다.
