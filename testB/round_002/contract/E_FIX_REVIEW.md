# E 국소 수정 검토 지시

E 최초 보고 msg_ee1cdad015d2에서 실제 4,212,389행 scan/선별46,705행/100척, 중복timestamp0 및 sample RSS증가68.3MiB를 보고했다. 감독은 preflight_report/execution_manifest/isolated_runner를 읽고 아래 결함을 확인해 생산 실행 관문을 유지했다. 생산결과는 아직 독립검산 전이다.

- RemeasureShim을 class instance로 만들면서 haversine_m이 bound method가 될 수 있다. 1행 합성 검사는 이 호출 경로를 지나지 않아 검출하지 못했다. 함수의 원래 호출의미를 유지하고 실제 다행·거리/누적정박지 호출 회귀가 필요하다.
- build_train_references에서 load_inputs 반환의 첫값manifest를 target IDs로 오인한다. 명부/metadata를 분리하고 원문 ID·순서·membership 경계를 검증해야 한다.
- preflight_report의 한글과 manifest 경로가 손상됐다. 직접 UTF8로 복구하며 selected parquet source_file까지 실제 저장값을 확인한다. 전체scan을 문서수정 때문에 다시 수행하지 않는다.
- safe AST 호출에도 원본해시 일치 확인을 강제한다. 원본 import 부작용/자동parse·캐시쓰기와 큰builder 메모리 상한이 해소되기 전 실제 참조/점수는 금지한다.

E에게 동일execution/소유권으로 국소수정과 의미있는 회귀·보존로그/해시 정정을 위임했다. 새100척 전체점수는 계산하지 않았다. 수정 뒤 별도실제Luna/xhigh가 원행선별·요약·다행점수함수·격리/해시/실제exit를 검산한다. 이 준비 검산을 실제 참조재구성/점수·사고성능 검증으로 확대하지 않는다.
