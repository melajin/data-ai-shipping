# Round018 실행 제어 관찰

`claimed=$true` 수정으로 첫 writer와 실패 영수증 보존이 실제 동작했다. smoke 외부 PS PID7468, 22:46:03.1598164–22:46:11.8258763 UTC, 8.6628274초, OS exit1이다. 15초 상한 내 실패이며 정상 통과가 아니다. 네 probe는 모두 실행됐고 auditor/mock/audit/model은 실행되지 않았다.

앞의 세 probe는 예상 exit0/exit7/지연exit0, 스트림 drain, 소유트리 잔존없음 조건을 통과했다. 네 번째 timeout probe의 사실은 다음과 같다.

- deadline 0.5초, 마지막 짧은 WaitForExit 반환false 시각0.4959699초.
- 이후 RAM/CIM 모니터링을 거쳐 deadline 도달 관찰0.9381056초.
- kill_attempted=true, cleanup 뒤 exit 관찰0.9397325초.
- 분류 indeterminate, timed_out=false, exit_code=-1, exit_confirmed=true, process_exit_utc=1601-01-01.
- stdout/stderr drain=true, 기록된 owned residual0, tree clear=true.

실제 분류 함수는 마지막 Wait 반환시각이 deadline 이상일 때만 뒤늦은 종료를 deadline_timeout으로 만든다. 이번에는 마지막 짧은 Wait는 deadline 전이고 모니터링 중 deadline을 넘었으므로 그 분기가 성립하지 않았다. 마지막 Wait의 시간은 실제 deadline 도달 관찰과 다르다. 다만 이 조건을 단순 삭제하여 모든 늦은 관찰을 timeout으로 바꾸면 자연 종료의 불확정 경계를 지울 수 있다.

후속 가설: deadline 뒤에 여전히 실행 중이라는 관찰을 별도로 기록하고, 정리 전후 종료 관찰을 분리하면 마지막 Wait의 조기false에 의존하지 않고 timeout과 불확정을 구분할 수 있다. 감독 모니터의 지연도 포함한다. 정상 종료를 deadline 전에 관찰한 증거는 보존한다.

`-1`은 실제 `.ExitCode` 속성에서 읽혔지만 killed process의 OS 종료 사실을 별도 확인해야 한다. 1601년 값은 정상적인 이번 실행 종료시각으로 쓸 수 없다. 현재 `HasExited` 뒤의 cleanup while은 이미 true면 WaitForExit를 생략한다. 캐시/종료 신호/ExitTime 관찰 순서가 원인일 수 있지만 이번 자료로 확정하지 않는다. 후속에서는 소유 Process handle에 대한 bounded 종료 wait 결과·코드 획득 성공·종료시각 유효성을 분리하고 unknown을 실패로 남긴다. -1을 임의0으로 바꾸거나 역사 영수증을 고치지 않는다.

실행 직전 가용5.486618GiB, probe 최소 관찰5.361572GiB. 예상200MiB는 가정이고 전체 process peak 실측이 아니다. RAM 부족이 원인은 아니다. 후속실행 전 새 RAM 확인이 필요하다. 실행한 네 PID 및 기록된 conhost는 현재 잔존하지 않음을 별도 확인한다.

mock/audit에 진입하지 않았으므로 parser 반례·저장 수치·provenance 관문은 미검증 상태다. 새 F1/모델호출/실제자료/holdout/체크포인트/외부송신0. 역사015wrapper=false/010gate=false를 보존한다.
