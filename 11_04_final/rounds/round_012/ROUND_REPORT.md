# Round012 — 종료코드 실행기 수정·소스 승인, 시간 관문으로 실행 보류

이번 회차는 실행기를 수정하고 독립 소스 승인을 받았다. 승인 수신 뒤 smoke를 시작하려 했으나, 실행 전 UTC 관문이 20:42:00 마감 도달을 확인하여 runner 호출 전에 차단했다. 따라서 smoke0, mock0, 실제 저장기록 audit0, 모델0, 새F1 없음이다. 종료코드 결함이 실제로 해결됐다고 주장하지 않는다.

## 이전 → 현재 → 다음

Round011은 fixture2개 stderr OK에도 영수증 exit_code=null/completed=false여서 본검산을 못 했다. 이번에는 과거코드를 읽기전용으로 두고 round012 사본에 ProcessStartInfo/Process 직접생성, 핸들 유지, stdout/stderr 동시 ReadToEndAsync, 정수 ExitCode 타입 확인, 28+2초 상한, 소유PID/생성시각 종료·잔존 확인, claim과 승인map/live/snapshot 전후SHA를 구현했다.

실행 전 검토에서 PowerShell5.1에 맞지 않는 ArgumentList/Environment API, unary-comma 반환의 중첩배열, null을0으로 바꿀 수 있는 int cast를 발견했다. 작성자가 동결 전에 Arguments의 Windows CRT quoting/EnvironmentVariables, 평탄한 해시목록, raw Int32 검증으로 수정했다. 이들은 소스 수정 근거이며 동적 성공 증거가 아니다. 후보 ACK는20:38:41UTC, 독립 승인map의 reviewed_at은20:41:00UTC다. 승인 전달 후 관리자의 실제 launch guard는 cutoff 도달로 차단했다. 모든실행0, 새claim/child없음, 과거선택8파일 해시불변이다.

다음 Round013은 승인코드를 새회차로 최소 버전복사하고 경로·schema만 바꾼 diff를 신속 독립검토하여 process smoke→mock→저장기록audit를 수행한다. 코드 새설계를 반복하거나 M4 준비문서를 다시 연구하지 않는다. M4 모델실행은 저장검산 성공 뒤 다음fresh회차로 미룬다.

## 결과와 한계

- 산출: code/*와 candidate_sources.json, review/approved_sources.json 및 SOURCE_REVIEW/FINAL_REVIEW, M4_NEXT_CHECKLIST, 실행명령, host 모델근거, resource/인계/동결/마감차단 기록.
- 정적 승인map SHA256 b8e4e72b2cce5ee17535042a1fcd88e5c594a1cd9325f3a3dae81648e6def5ca. 실행검증은 미수행이다. artifacts/provenance_audit.json은 생성되지 않았다.
- 초기가용RAM4.1446GiB(20:26:06UTC), 실행준비4.4427GiB(20:38:57UTC), 당시 다른Python0. stdlib 예상peak100MiB/문서작업200MiB는 계획가정이며 실측최대가 아니다. RAM 때문에 보류한 것은 아니다.
- 관리자20분(20:25→20:45), 실험cutoff20:42, 문서·인계3분을 확보했다. source review 완료가 늦어 실행시간 확보에 실패한 운영 한계가 있다. 다음은 새구현 범위를 최소화하고 코드복사4분/검토3분/계산10분이내 착수 목표를 둔다.
- raw/NPZ/reference/OUTER/holdout/checkpoint읽기·해시0, 실제자료학습/F1/장치실험/설치/외부업로드/공식제출/유료0. 원자료·이전repo·과거회차·venv수정0.
- round010 저장 두질의 maxabs1.8446231598301388e-6/argmax일치는 과거관찰이며 이번 재검산값이 아니다. 과거source-freeze 전체false를 유지한다.

개발OUTER5897 baseline micro0.5930133966423605/macro0.5252719738966167, 미채택 탐색0.5933525521451586 유지. 독립/공식null, 목표0.7미달. 기술목표는소스수정·승인까지만달성, 동적검산미달성. 학습자이해와하드웨어검증은미평가다. 학습질문: 코드검토승인과실행성공은왜다른가? null을int로변환하면왜증거가왜곡되는가? 시간관문으로실행하지않은경우를실험실패로세면왜안되는가?

호스트 turn_context는 관리자gpt-6-astra/high와 작성자·검토자gpt-6-luna/xhigh를기록한다. 요청과메타데이터를저장했으며내부모델인증은아니다. root+2보조≤host4. 완료후STATUS.current_round=round_012/handoff.ready=true/active_workers=[]로두고 fresh Astra high 인계수락정본 automation/receipts/round_012_launch.json 확인후즉시중지한다. structured-chat닫기CLI지원없으므로필요시이완료세션탭만수동닫는다.
