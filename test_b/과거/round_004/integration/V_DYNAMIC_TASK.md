# V 独립 동적 검산 — E 완료 snapshot

별도 실제 Orca gpt-6-luna/xhigh V 검산자. 요청/Orca launch 설정과 provider 내부 unknown을 구분한다. 최초 task ctx_a8eef931ac8d의 정적검토 뒤 후속이다. E 최초 worker_done msg_dd0fa18d7756(task_90c7d3fb7fca/ctx_5c62c63dcf5d) 및 최신후속 worker_done msg_cf5c24f09425(task_98ff809b03bc/ctx_94f3ac9fe789)가 모두 succeeded다. 같은 handle의 이전 task만으로 종료를 판단하지 않는다.

ORCA_CLI_COMMAND 지정 실행파일과 실제버전 skills get orchestration/orca-cli, AGENTS RAM 규칙부터 확인한다. AGENTS.md, ROUND_PLAN.md, integration/E_TASK.md, audit/independent_static_review.md, followup_dynamic_review_plan.md, execution/bounded_loader.py, compare_loader_adapter.py, domain_and_equivalence.md, preflight_report.md, execution_receipt.json, artifact_hashes.json과 실제 exit/stdout/stderr를 UTF-8로 읽는다. 전제계약은 round_003/NEXT_ROUND.md와 round_002/contract/EXPLORATORY_EXECUTION_CONTRACT.md다.

소유권은 round_004/audit/dynamic_001/ 신규파일만. E execution/과 기존 정적감사 및 원자료/canonical/cache/선행round 읽기전용. 혼자 작업하는 저장소가 아니며 타인의 변경을 되돌리지 않는다. 생산 결함은 직접 고치지 말고 감독에게 보고한다.

E 산출물이 freeze된 현재 해시를 고정하고 원본4SHA, 모든 기재 출력·원본 영수증/attempt/실제 exit, 생성 scope를 확인한다. E 코드/비교기를 복제하지 않은 whole-column 독립 oracle, pinned load_rows 원본 AST, 명시 hand-expected 값을 먼저 서로 비교하고 E adapter를 세 번째로 대조한다. 계획의 fixture 행렬 전체를 검토한다: key_valid True/False, ID/date only/둘다/둘다없음/explicit key_valid/month/열순서, 월·batch 경계·빈batch/빈month/전체empty/빈months, null/NaN·명백한 nonnumeric, 부호/leadingzero/±2^53/dateint32양끝, invalid ID의 unsupported date 미검사, 소수/scientific/공백/Unicode/범위·문자길이초과 전체 fail-closed. 열/값/순서/dtype/NaN/제외집합/출력 index 구멍을 reset_index 없이 비교한다. 누락 지원 API는 pass로 추정하지 않는다.

감독 확인점도 독립적으로 검토:
1. E 전수scan 초안의 4,212,389행이 Train 계보에 맞는지 metadata/source history를 직접 확인한다. 이 값은 기존 Test 총행수와 같고 Train 기존기록은3,887,069이므로 현재 초안을 전수scan 계약으로 채택하지 않는다. 실제 parquet full scan은 금지; footer/schema metadata 작은 읽기 또는 기존 pinned metadata만 허용한다.
2. transform_months는 trace=None이어도 local_trace에 모든 batch output_index list를 보유한다. 큰 월에서 보유량이 커지는지, streaming·offset 전달과 메모리 계획 주장을 만족하는지 정적으로 추적한다. 수정하지 않는다.
3. transform_batches의 late unsupported 전에 yield한 결과가 부분 성공으로 사용될 수 있는지, 전체 fail-closed 주장에는 caller quarantine/atomic commit이 추가로 필요한지 검토한다. synthetic late unsupported를 통해 구별한다. 현재 생산runner는 완성품이 아니다.

실제 작은 표본 독립 검산도 허용한다: 고정 train month1 rows_train_1.parquet SHA7f1b4d82970e5214f9c1cd45b860175578a94ae3974aa3a69a790c9842bc6140, 물리 첫16,384행/10열[row_index,rfid_id,part_dt,rfid_time,key_valid,wkt_valid,len_m,bbox_m,cen_lon,cen_lat], batch<=4096. 읽기전 selection/expected rows/sha를 기록한다. V가 직접 제한 iteration해 원본AST/독립oracle와 실제 여러 batch E 호출을 대조한다. 전체 표본만 합쳐 E를1회 호출하면 검증실패다. 각 batch/물리 offset/global ordinal/제외/index를 추적한다. 이 범위는 sample 증거이며 전체 domain coverage가 아니다. E의 전체 비교기를 그대로 재실행하지 않는다.

RAM: 감독06:08:31KST 가용2,007,920KiB/총14,480,244KiB, 다른 powershell PID30764 RSS약2.34GiB 및 Orca/host가 관측됐고 귀속은unknown이다. 이전값을 실행허가로 사용하지 않는다. 시작/각 메모리작업 직전 가용·총RAM/타작업/예상peak·근거·시각을 새로 기록한다. synthetic/선택표본 증분<=256MiB 계획, 전체 Python 과정<=512MiB 추정+1GiB 여유를 요구해 최소1.5GiB 가용을 계획한다. 추정은 작은 투영표본/원본AST에 근거하며 실측보장 아님. 부족/불확실하면 정적검토·fixture작성 등 가능작업부터 하고, 재개직전 재확인한다. 순차/청크축소 우선; polling/watch·사용자process 종료 금지. Python -B/격리 cwd로 bytecode/progress 쓰기를 차단한다. peak RSS/commit과 host free RAM을 구분해 기록한다.

실제 full train key scan/참조/새점수/A/membership/기존Test전수대조/26행합성/임계값/B/C/사고판정/성능/제출/실제split/사고파일개발사용/외부수집·연락/push 금지. Round003 Efailed exit2/V실패재현exit0감사succeeded, Round002초기FAIL/deltaPASS10exit0/역사44해시unknown 보존. 보고/manifest/코드/실행명령/실제exit/stdout/stderr/hash·RAM을 새 소유폴더에 남기고 worker_done으로 판정·수정요청·미확인사항을 보고한다. 검산에서 생산결함을 정확히 발견/확인하는 deliverable은 audit task succeeded일 수 있지만 fixture 불일치 exit는 실제대로 보존하고 생산 PASS와 구분한다.
