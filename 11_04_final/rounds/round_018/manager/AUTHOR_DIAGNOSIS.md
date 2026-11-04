# 작성자 후속 읽기전용 진단

작성자는 소스 동결 뒤 파일 수정·동적 재실행 없이 다음을 보고했다. 마지막 WaitForExit(false)는 해당 짧은 대기 구간만 종료됐다는 의미다. 이번 false 반환0.4959699초가 global deadline0.5초 전이므로 이것만으로 timeout이라고 할 수 없다. 다음 RAM/CIM 모니터링이 시간을 사용하여 deadline 관찰은0.9381056초로 늦어졌다. 실제 분류기의 indeterminate는 현재 기록된 증거에 대한 보수적 결과이며 실패를 정상으로 숨기지 않았다.

후속 권고는 absolute monotonic deadline, wait 시작/요청길이/종료 기록, 남은 시간의 올림 변환, 종료 경계 직전 불필요한 blocking inventory 방지다. deadline 이후 여전히 살아 있다는 직접 관찰 없이 늦은 종료를 timeout으로 승격하지 않는다. 이미 deadline 전 종료를 관찰한 경우 그 증거를 보존한다.

1601년은 FILETIME 기준점과 일치하지만 현재 영수증만으로 발생 원인을 확정할 수 없다. 속성의 원값·조회오류·유효성 및 종료 signal 대기 성공을 구분하고 정수 -1 자체는 실패를 은폐하기 위해 변경하지 않는다. 작성자가 참고한 공식 설명은 [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes), [FromFileTimeUtc](https://learn.microsoft.com/en-us/dotnet/api/system.datetime.fromfiletimeutc), [Process.ExitTime](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.exittime)다. 문서와 해당 실행의 실제 원인 증명은 별개다.
