# Round014 — M4 합성 코드 동결, 동적 실행 보류

M4-a/b tiny 합성 head 학습·병합·head-only 재로드 코드와 실행기를 작성하고 동결했다. **smoke0회, mock0회, 합성모델0회, 새 F1없음**이다. 30분 관리자 예산과 문서·인계3분 확보 조건 때문에 모델 실행을 시작하지 않았다. 마지막 승인map의 잘못된 해시도 실행 직전 대조에서 차단했다. 모델·gradient·병합·재로드의 동적 성공을 주장하지 않는다.

## 이전 → 현재 → 다음

Round013은 ProcessStartInfo 실행기의 종료코드와 저장기록 검산을 완료했다. 이번 회차는 이를 기반으로 실제 M4 합성 논리, 표준 라이브러리 mock, RAM·프로세스 트리 감시가 있는 실행기를 만들었다. 정적 검토에서 M4-a 재로드 자기비교와 학습후 head의 원head 동일성 요구, raw view 전체비교, 확률 행합, 출력경로 검증순서, PowerShell 조건식, 정리 시간과 신원불명 프로세스 판정을 보완했다. 작성자는21:19:00UTC에 쓰기를 동결했다. Python AST·PowerShell parser만 통과했으며 테스트나 모델을 실행한 것은 아니다.

합성180초와 문서 시간을 모두 확보하려면21:19:19UTC까지 시작해야 했으나 독립승인은 그 뒤였다. 실행마감21:22:19UTC도 보존했다. 첫 승인map의 runner SHA가63자리로 잘못 적힌 것을 관리자가 직접파일해시와 대조해 발견했다. 다른 두파일은 일치했으며 실행기는 호출하지 않았다. 검토자에게 잘못된map 보존·직접해시 재생성·사건기록을 지시했다. 최종 정적승인 및 한계는 review/SOURCE_REVIEW.md와 FINAL_REVIEW.md, map변경증거를 따른다. 동적실행0이라는 사실은 수정된map으로도 바뀌지 않는다.

다음 Round015는 승인코드 세파일을 회차경로·schema만 바꿔 복사하고, 작성자동결→독립직접해시→smoke→mock→합성1회를 조기에 수행한다. 수학이나 실행기를 다시 설계하지 않는다. 후속 전체estimator통합은 이번 합성성공 이후에만 진행한다. 이번 회차의 지연 원인은 RAM이 아니라 새코드 구현·검토시간과 승인map 전사오류다.

## 산출과 검증 경계

- code/m4_synthetic.py: 합성context16×8/target4×8, 4view, target-only hidden캐시, 외부a/b각2SGDstep, gradient·inactive행·bias·upstream불변·병합·head재로드검사. 실제 실행결과는 없다.
- code/test_m4_mock.py: 클래스복원방향·context제외/복사·호출상한·중복merge거부 4개시험의 소스. 실행0회다.
- code/run_m4.ps1: 기존basePython -B -S와 명시venv site-packages/DLL경로를 쓰는 단일process, source/map/snapshot해시·동시stdoutstderr·170+10초·RAM시작3GiB/중단1.5GiB·소유트리검사. runtime동작은 미검증이다. 정상종료 후 예외적인 잔존자식은 완료실패로 남기며 자동종료하지 않는 제한이 있다. 예상 실행경로는 subprocess가 없는 단일Python이다.

원자료·NPZ·reference·OUTER·holdout 접근0, checkpoint해시/로드0, fit/predict/fullforward/backward0, 설치/네트워크/외부전송/공식제출/유료0. 기존원자료·repo·설치본·과거회차를 수정하지 않았다. 선택한 과거자료·설치소스·운영문서28개 전후해시가 일치했다. 실제프로세스receipt·tensor결과·자원peak는 생성되지 않았다.

## 자원·모델 증거·학습

초기 RAM3.867046GiB(20:56:25UTC), 문서·소스작업 후5.660015GiB(21:16:51UTC), 다른Python0이었다. 예상tiny peak≤1.5GiB는 checkpoint약105MiB·로딩사본·Torch여유·H320KiB/target64KiB에근거한가정이며 실측아니다. RAM부족보류나 사용자process종료는 없었다. 반복RAM대기loop도 만들지 않았다.

관리자 host turn_context는 gpt-6-astra/high, 작성자·검토자는 gpt-6-luna/xhigh로 기록됐다. 요청명세와 실행메타데이터는 manager/host_turn_evidence.json·worker_model_summary.json에 분리했다. 검토자의 추가 자문child 생성은 명시model/effort/forknone 규정과 달랐으며 manager/DELEGATION_DEVIATION.md에 남겼다. 실제호스트기록은 추가child도 Luna/xhigh였고 총4슬롯이내였다. 자문은 채택하지 않았고 추가생성을금지했다. 역할명만으로 Astra실행이었다고 표현하지 않는다. 호스트기록은 모델내부인증이 아니다.

기술적 달성은 구현·정적구문·소스검토까지이며 동적관문은 미달성이다. 학습질문은 LEARNING_NOTES.md의 p[y]/out[...,p], B=0첫Agrad0, context/target분리, head검증과F1차이다. 학습자의 이해·장치검증은 미평가다.

개발 OUTER5897 baseline micro-F1 **0.5930133966423605**, macro0.5252719738966167, 미채택 탐색0.5933525521451586 유지. 독립/공식null, 목표0.7미달. round010의 역사·현재 source gate false는영구보존한다.

## 완료·인계

STATUS.current_round=round_014, handoff.ready=true, active_workers=[]로 저장하고 EXPERIMENT_LEDGER/NEXT를 갱신한다. Start-NextSession.ps1 -FromRound round_014의 수락영수증 automation/receipts/round_014_launch.json에서 새session과prompt전달을 확인하는 즉시 현재관리자는 종료한다. 수락 전 다음session실행을 주장하지 않는다. 현재 orca agent 도움말에는 structured chat닫기명령이없으므로 앱전체/무관한세션을종료하지않고 필요시이완료탭만수동으로닫는다.
