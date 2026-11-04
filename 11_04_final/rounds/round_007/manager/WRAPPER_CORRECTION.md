# Mock01 종료 판정 수정

18:19:46UTC mock01의 여섯 검사함수는 stdout `pure mock checks passed`, child exit0,0.281초로 끝났다. 그러나 마지막 owned_alive가 Popen 핸들이 남아 있는 종료 root프로세스30588도 alive로 간주해 receipt는 failed_or_stopped/remaining[30588]을 기록했다. 후속 Win32_Process 목록에는 root30588과 관측자식20748이 없었다. 원receipt와 snapshot은 보존한다.

PID와 생성시각만 확인하면 종료 후 커널 객체가 잠시 남아 있는 경우를 구분하지 못한다. wrapper의 counters는 SYNCHRONIZE 권한으로 handle을 열어 WaitForSingleObject(handle,0)의 WAIT_TIMEOUT(258)일 때만 running=true를 기록한다. owned_alive는 생성시각 일치와 running을 함께 요구한다. WAIT_FAILED는 오류로 처리한다. 사용자의 다른 프로세스는 종료하지 않았다.

첫 mock은 어댑터 기계적 검사 통과, 실행감시 종료판정 결함으로 구분한다. 사전예산의 실패원인 수정 후 추가mock1회 조항에 따라 두 번째이자 마지막 mock02를 새 wrapper SHA의 독립검토 후 수행한다. 어댑터/test source는 변경하지 않으며 이 검사는 모델을 불러오지 않는다. synthetic 비교는 아직0회다.
