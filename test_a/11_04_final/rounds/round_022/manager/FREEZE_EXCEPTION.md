# 준비 단계 동결 기록 예외

prepare_t5는 독립 소스 승인 후 01:58:29 UTC 시작했다. 같은 PowerShell 호출에서 앞선 snapshot helper가 `utf8-sig`라는 잘못된 Python codec 이름으로 실패했으나, 뒤의 launch 명령이 독립 줄이어서 계속됐다. helper 수정 후 SHA256 대소문자 비교도 수정했고 snapshot은 실행 중 생성됐다. 따라서 **snapshot 사본이 실행 전 만들어졌다고 주장하지 않는다**.

실행 전 독립 승인 JSON의 5개 active source/config/plan 해시와 launcher가 프로세스를 시작하기 직전에 기록한 해시, 실행 후 해시는 대소문자를 정규화하면 모두 같다. 활성 코드의 승인 후 변경은 없었다. 실행과 무관한 run_gate.py는 작성자가 동시 수정했으며 준비 script에서 읽거나 import하지 않았다. 해당 변경은 launch before/after 로그에 남아 있다.

준비 프로세스 재실행은 하지 않았다. helper를 수정했고 이후 단계는 동결 도구의 성공을 별도 호출 결과로 확인한 뒤 launcher를 호출한다. T5 준비 완료 뒤 manifest reader의 codec도 utf-8-sig로 수정했으며 이는 다음 gate 승인/동결에 새 해시로 포함한다.
