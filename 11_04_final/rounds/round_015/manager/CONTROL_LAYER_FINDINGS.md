# 실행 제어 계층 발견사항

작성자 독립 읽기 진단: Python stdlib json.tool은 결과 JSON을 정상 파싱했다. Windows PowerShell5.1.26100.9711 ConvertFrom-Json은 같은64851bytes 파일에서 invalid name으로 실패했다. 정확한 경로는 $.upstream_model.module_training_before_after[""]=false (결과461행). producer의 model.named_modules() 루트명이 빈문자열이므로 유효한 의미있는 값이다. runner383–385행 Read-Receipt가587행 결과읽기에서 실패했다. 빈key를 삭제하거나 원본을 덮어쓰지 않는다. 다음회차 stdlib strict JSON 감사 및 고정필드 summary로 소비자호환성을 검증한다.

검토자 별도 발견: synthetic receipt process.wait_finished=false, timed_out=true, memory_stop=false, kill_attempted=false, exit_confirmed=true, exit_code=0, owned_tree_clear=true, streams_drained=true. elapsed16.7639027초이고 wait_timeout_seconds170이다. 실제170초 경과 시간초과라고 주장할 수 없다. runner는 while 뒤 WaitForExit(1)의 거짓값만으로 timedOut을 설정하며 deadline 도달을 함께 요구하지 않는다. 어떤 동적 경로에서 거짓값이 나온 것인지는 현재 기록으로 확정하지 않는다. 소스판정 결함 가능성과 저장관찰을 구별한다.

이 두 문제 때문에 JSON만 고쳐도 기존 전체gate 성공을 주장할 수 없다. 이번 receipt와 map/source는 동결 상태로 유지한다. 다음회차는 종료 이벤트/HasExited/실제deadline/메모리중단/streamdrain을 분리해 기록하고, 모델 대신 짧은 정상종료 프로세스와 실제deadline 초과 프로세스로 검증한다. 실패 재실행0. 모델/torch/checkpoint/.pt load 없이 수행할 수 있다.

관리자 처음 JSON 조회의 PowerShell 인수 따옴표 문제는 Python SyntaxError로 끝났고 stdin 전달을 사용해 저장 JSON을 읽었다. 해당 읽기실패는 합성실험 재실행이 아니다. 학습자에게 child 계산·프로세스판정·결과파싱·통합gate가 서로 다른 층임을 설명한다.
