"""Preserve an unfinished round while applying the user's manager-model change."""
import datetime
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

amendment = '''

## 2026-11-05 최신 사용자 변경 — 관리자 GPT-6.1 Sol high

사용자 명시 지시: `model 6.1 sol high로 변경`.
이후 관리자 및 새 회차 관리자 요청은 **gpt-6.1-sol / high**로 변경한다.
이 지시는 위의 Astra 관리자 고정 규정보다 우선한다. 보조는 기존 **gpt-6-luna / xhigh**를 유지한다.
요청 설정과 호스트 turn_context 증거를 구분하며 현재 부모 모델이 문서 수정으로 바뀌었다고 주장하지 않는다.
round024는 준비만 끝났으며 학습 0회, 독립 검토/동결/실행 전이다. 새 Sol 관리자가 같은 미완료 회차를 이어간다.
'''
for name in ['AGENTS.md', 'CYCLE_PROTOCOL.md']:
    p = ROOT / name
    p.write_text(p.read_text(encoding='utf-8-sig').rstrip() + amendment, encoding='utf-8')

p = ROOT / 'automation/Start-NextSession.ps1'
original = p.read_text(encoding='utf-8-sig')
(ROOT / 'rounds/round_024/manager/Start-NextSession.before_model_change.ps1').write_text(original, encoding='utf-8')
updated = original.replace('gpt-6-astra', 'gpt-6.1-sol').replace('Astra high', 'GPT-6.1 Sol high')
p.write_text(updated, encoding='utf-8-sig')

# A separate receipt namespace preserves round023's already-accepted launch receipt.
switch = updated.replace("$receiptPath = Join-Path", "$receiptKey = 'round_024_model_switch_sol_high'\n$receiptPath = Join-Path", 1)
switch = switch.replace("($FromRound + '_", "($receiptKey + '_")
switch = switch.replace('NEXT_SESSION.md의 작업을 실제로 수행하고 결과를 저장하세요.',
    '사용자 모델 변경에 따른 동일 회차 인계입니다. round024 준비가 이미 완료되었습니다. prepare_round024.py를 다시 실행하지 마세요. 학습/동결은 아직 하지 않았습니다. round024/manager/MODEL_SWITCH_HANDOFF.md를 읽고 기존 소스를 별도 Luna 작성자/검토자로 검토한 뒤 같은 round024를 이어가세요. 이전 관리자는 실행하지 않고 종료합니다. NEXT_SESSION.md의 작업을 실제로 수행하고 결과를 저장하세요.')
(ROOT / 'automation/Switch-ManagerToSol.ps1').write_text(switch, encoding='utf-8-sig')

p = ROOT / 'NEXT_SESSION.md'
old_next = p.read_text(encoding='utf-8-sig')
(ROOT / 'rounds/round_024/manager/NEXT_SESSION.before_model_change.md').write_text(old_next, encoding='utf-8')
prefix = '''# 최신 변경: round024를 새 GPT-6.1 Sol high 관리자가 계속 실행

사용자 지시 `model 6.1 sol high로 변경`에 따른 관리자 교체이다. 보조는 Luna xhigh 유지.
round024 디렉터리와 저메모리 소스/캐시 준비가 이미 완료되었다. **prepare_round024.py 재실행 금지**.
현재 학습 0/8, 동결 0, 독립 검토 미완료. current_round=round_023은 직전 완료 회차를 뜻한다.
새 관리자는 `rounds/round_024/manager/MODEL_SWITCH_HANDOFF.md`와 작성자 노트를 읽고 별도 작성/검토 담당자를 배정한다.
기존 수학적 비교·8fit 단1회·재시도0·RAM/단일스레드/우선순위 제한을 유지한다.
runtime_contract의 기존 남은 시간 안에 수행 가능하면 그대로 진행한다. 검토 전 사용자 모델 변경으로 시간이 소진됐으면
학습이 시작되지 않았다는 증거와 새 관리자 시작 시각을 남기고 미실행 회차의 45분 관리/30분 계산/900초 단일 job 예산을 새 검토 전에 명시한다.
이 인계 자체는 round024 완료나 새 점수가 아니다. 완료 후 정규 Start-NextSession.ps1은 이제 Sol high를 요청한다.

아래는 기존 실험 절차이며 Astra 관리자 표현은 위 사용자 변경으로 대체된다.

'''
p.write_text(prefix + old_next.replace('fresh Astra high', 'fresh GPT-6.1 Sol high'), encoding='utf-8')

status_path = ROOT / 'STATUS.json'
s = json.loads(status_path.read_text(encoding='utf-8-sig'))
write_json(ROOT / 'rounds/round_024/manager/STATUS.before_model_change.json', s)
s['updated_at_utc'] = now
s['manager_model_request'] = {'model': 'gpt-6.1-sol', 'effort': 'high', 'source': 'explicit user model change', 'actual_current_parent_switched': False}
s['manager_intake'] = {'round': 'round_024', 'state': 'prepared_unfinished_awaiting_sol_manager', 'fits_started': 0, 'fits_completed': 0, 'setup_completed': True, 'independent_review_complete': False, 'frozen': False}
s['latest_user_steering'] = {'utc': now, 'text': 'model 6.1 sol high로 변경', 'scope': 'manager model; Luna xhigh workers unchanged'}
s['handoff']['ready'] = True
s['handoff']['status'] = 'same_round_model_switch_pending_acceptance'
s['handoff']['launch_receipt'] = 'automation/receipts/round_024_model_switch_sol_high_launch.json'
s['handoff']['next_session_launched'] = False
s['handoff']['next_session_id'] = None
s['handoff']['completed_session_id'] = os.environ.get('ORCA_AGENT_SESSION_ID')
s['handoff']['note'] = 'round023 remains last completed; round024 setup only, 0 fits; model switch transfer is not round completion'
write_json(status_path, s)

evidence = []
session_id = os.environ.get('CODEX_THREAD_ID')
for f in Path('C:/Users/dlehs/.codex/sessions/2026/11/05').glob('*' + session_id + '*'):
    with f.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get('type') == 'turn_context':
                v = j['payload']
                evidence.append({'source_path': str(f), 'utc': j.get('timestamp'), 'model': v.get('model'), 'effort': v.get('effort')})
write_json(ROOT / 'rounds/round_024/manager/model_switch_evidence.json', {
    'utc': now, 'old_orca_session': os.environ.get('ORCA_AGENT_SESSION_ID'), 'old_thread': session_id,
    'requested_next_manager': {'model': 'gpt-6.1-sol', 'effort': 'high'}, 'old_host_turn_context': evidence,
    'worker_request': {'model': 'gpt-6-luna', 'effort': 'xhigh', 'task': '/root/code_author'},
    'backend_authenticated': False, 'training_started': False,
})
(ROOT / 'rounds/round_024/manager/MODEL_SWITCH_HANDOFF.md').write_text('''# 사용자 요청에 따른 동일 회차 관리자 교체

round024 setup은 정상 종료했다. 동일 회차를 이어가며 새 회차로 계산하지 않는다.
round023 NEXT_SESSION 수신 SHA256은 641B220EBC6997DDED59F11A76A3EC920E6EE7BC2F0AA94FDE906678A48E6E58과 일치했다.
기존 launch 영수증의 세션 ID는 현재 이전 관리자 ORCA_AGENT_SESSION_ID와 일치해 중복 수신이 아니었다.
학습 Python 없음, 0fit, source freeze 없음. Luna code_author에게 정적 검토를 맡겼으나 사용자 모델 변경 후 중지를 요청했다.
작성자 인계 노트가 있으면 읽고 새 Luna 작성/검토 담당자를 배정한다. 다른 사람 수정사항을 되돌리지 않는다.

다음 순서: 기존 setup/소스 확인 → 작성자 수정 완료 → 별도 검토자 승인 hash → freeze → RAM 재확인 → launch 단1회(900초/8fit)
→ 성공 시 verify_gate_result → reinfer_saved → supplement_metrics → 결과/STATUS/ledger/NEXT_SESSION 갱신 → 새 Sol high 관리자 인계.
상세 명령은 NEXT_SESSION.md. 원자료/이전 repo 읽기 전용, 추가 holdout 접근 금지, 기존 자료 경계 유지.

이전 관리자 호스트 turn_context는 Astra high였다. 변경 요청은 Sol high이며 새 세션 launch receipt와 새 turn_context로 확인한다.
현재 세션이 이미 Sol로 바뀌었다고 주장하지 않는다. 기존 round023 launch receipt는 덮어쓰지 않는다.
round024 결과 보고서/ledger 완료행은 아직 만들지 않는다. 실제 실행 완료 후 새 관리자가 작성한다.
''', encoding='utf-8')
print(json.dumps({'prepared': True, 'manager_request': 'gpt-6.1-sol/high', 'round024_complete': False}))
