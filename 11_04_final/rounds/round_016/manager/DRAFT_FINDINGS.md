# 실행 전 초안 검토

22:00UTC경 초기 초안을 읽었으며 이 시점에는 candidate/ACK/approval map도 실행 claim도 없었다. 아래는 실행 실패가 아닌 정적 발견이다. 최종 승인 소스와 구분한다.

- `run_probe`는 exit7을 `nonzero_exit`로 분류하면서 `completed`에는 `completed` 분류만 허용했다. 기대 종료코드7 시험이 무조건 실패할 수 있었다.
- `owned_tree_clear=exit_confirmed`는 root 종료와 전체 자식트리 정리를 혼동했다. 종료 확인/소유트리 잔존은 각각 관찰해야 한다.
- cleanup 예외 경로의 인수 없는 `communicate()`는 유한 정리 상한을 보장하지 않았다.
- probe별 RAM/다른 작업 확인, 실행 전체상한, source/map/snapshot 사후해시가 빠져 있었다.
- 일부 mock는 실제 판독/검증 함수를 호출하지 않고 Python 상수식으로만 거부 여부를 표현했다. 반례가 실제 코드 경로에서 거부되는지 검증하도록 요청했다.
- `raw.decode('utf-8')` 뒤 JSON 문자열 파싱은 PowerShell이 쓴 UTF-8 BOM을 거부할 수 있다. 원본 바이트/해시를 보존한 `utf-8-sig` 판독 및 같은 바이트 해시 일치를 요청했다.

작성자에게 수정 요청을 전달하고 검토자에게 별도 통보했다. 작성자는 기존 ProcessStartInfo 제어를 적용한 wrapper와 JSON 수정을 제안했다. 소스 동결·독립승인 전 동적 모드를 실행하지 않았다. 전체 실행 마감22:12:03UTC는 유지한다.
