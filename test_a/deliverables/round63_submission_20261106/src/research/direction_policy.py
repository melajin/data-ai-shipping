"""User-controlled next-experiment rule; never a prediction threshold."""
from pathlib import Path
import json
from datetime import datetime
from zoneinfo import ZoneInfo
B = Path(__file__).resolve().parent

def decision(score, previous, best):
    p = json.loads((B / 'DESIGN_POLICY.json').read_text(encoding='utf-8'))
    previous_reference = p.get('comparison_reference') == 'previous primary REPORT Micro-F1'
    gain = score - (previous if previous_reference else best)
    met = gain + 1e-12 >= p['minimum_absolute_gain']
    return {'previous_micro': previous, 'absolute_improvement': score - previous, 'best_before_round_micro': best, 'absolute_improvement_over_best': score - best, 'direction_gain': gain, 'threshold': p['minimum_absolute_gain'], 'comparison_reference': p['comparison_reference'], 'improvement_requirement_met': met, 'next_must_change_core_structure': not met, 'minimum_goal_micro_f1': p['minimum_goal_micro_f1'], 'minimum_goal_comparison': '>', 'candidate_exceeds_minimum_goal': score > p['minimum_goal_micro_f1'], 'policy_updated_at': p['updated_at_Asia_Seoul']}

def state_fields(d, best_so_far):
    return {'current_transition_threshold_absolute': d['threshold'], 'current_transition_reference': d['comparison_reference'], 'last_absolute_improvement': d['absolute_improvement'], 'last_improvement_over_best': d['absolute_improvement_over_best'], 'next_requires_core_direction_change': d['next_must_change_core_structure'], 'minimum_goal_micro_f1': d['minimum_goal_micro_f1'], 'minimum_goal_comparison': '>', 'performance_goal_achieved': best_so_far > d['minimum_goal_micro_f1']}

def register():
    state = json.loads((B / 'PAUSE_STATE.json').read_text(encoding='utf-8'))
    at = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    p = {'updated_at_Asia_Seoul': at, 'effective_from_round': 28, 'minimum_absolute_gain': 0.01, 'comparison_reference': 'best prior primary REPORT Micro-F1', 'minimum_goal_micro_f1': 0.63, 'minimum_goal_comparison': '>', 'aspirational_micro_f1': 0.65, 'best_at_update': state['best_micro_f1'], 'user_request': 'Micro-F1이 0.01이상 증가하지 않으면 방향성을 좀 바꿔보는 것으로 진행하자. 해당 조건을 만족하지 않으면 세부 내용을 조금씩 수정하는 방법은 필요 없을 것 같아. Micro-F1이 최소 0.63은 넘어야 해', 'implementation': 'Below+0.01 versus best prior primary score, change input representation, learning task or model decision structure; do not spend subsequent numbered rounds on small hyperparameter tweaks. Preserve any improved result. Continue until user stops.', 'evaluation_scope': 'Repeated development REPORT, not official Test; unchanged boat split and denominator.', 'running_round_note': '28 was already running old code when this instruction arrived; apply this direction rule after completion without changing its trained models or TUNE selection.'}
    (B / 'DESIGN_POLICY.json').write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
    (B / 'round_28' / 'policy_update_during_run.json').write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
    state.update(current_transition_threshold_absolute=0.01, current_transition_reference=p['comparison_reference'], minimum_goal_micro_f1=0.63, minimum_goal_comparison='>', performance_goal_achieved=state['best_micro_f1'] > 0.63, updated_at_Asia_Seoul=at)
    (B / 'PAUSE_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    with (B / '1105 신규 아이디어.md').open('a', encoding='utf-8') as f:
        f.write('\n\n## 28차 진행 중 사용자 기준 변경\n\n앞으로 기존 최고 주 결과 Micro-F1 대비 절대값 +0.01 이상 개선되지 않으면 세부 설정 탐색을 이어가지 않고 입력 표현·학습 방식·판정 구조의 핵심 방향을 변경한다. 최소 목표는 Micro-F1 **0.63 초과**, 0.65는 발전 목표로 유지한다. 소폭 개선 결과도 보존한다. 이 규칙은 다음 설계 방향에 적용하며 진행 중인 28차의 모델·TUNE 선택 규칙을 변경하지 않는다. REPORT는 반복 개발 자료이다.\n')
    print('DIRECTION_POLICY_UPDATED', json.dumps({k: p[k] for k in ['effective_from_round', 'minimum_absolute_gain', 'minimum_goal_micro_f1', 'best_at_update']}))

def apply_running_round28():
    rd = B / 'round_28'
    feedback = json.loads((rd / 'feedback.json').read_text(encoding='utf-8'))
    p = json.loads((rd / 'policy_update_during_run.json').read_text(encoding='utf-8'))
    d = decision(feedback['micro_f1'], feedback['previous_micro'], p['best_at_update'])
    feedback.update(d)
    feedback['applied_after_completion_because_runner_already_loaded'] = True
    (rd / 'feedback.json').write_text(json.dumps(feedback, ensure_ascii=False, indent=2), encoding='utf-8')
    (rd / 'direction_policy_applied.json').write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    state = json.loads((B / 'PAUSE_STATE.json').read_text(encoding='utf-8'))
    assert state['last_round'] == 28
    state.update(state_fields(d, state['best_micro_f1']))
    (B / 'PAUSE_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ROUND28_DIRECTION_POLICY_APPLIED', json.dumps(d))

def register_network():
    p = json.loads((B / 'DESIGN_POLICY.json').read_text(encoding='utf-8'))
    at = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    p.update(updated_at_Asia_Seoul=at, comparison_reference='previous primary REPORT Micro-F1', comparison_reference_effective_from_round=30, neural_structure_change_required_from_round=30, preprocessing_plus_neural_structure_required=True, neural_module_change_if_gain_below=0.01, first_neural_module_to_examine='row_interactor', current_round29_note='Already running weight-training-range experiment; distinguish from actual architecture changes. Its previous primary score equals the best score, so the numerical+0.01 decision is unchanged.', latest_user_request='다음 모델 설계 시도부터 전처리 방식 변형 + TabICLv2 신경망 자체적인 변형. 어느 부분을 먼저 변형할지 생각한 후 진행. 최소0.63 초과, 최대한0.65 근접. 이전 설계 시도보다0.01 높아지지 않으면 신경망의 다른 부분 변형 고려.', implementation='From30, combine coherent preprocessing variation with an explicit TabICLv2 architecture change and an unchanged-network control. Choose and justify the neural component before training. Below+0.01 versus previous primary score, consider a different neural component instead of minor tuning. Preserve the best observed model; each round starts with original public weights and freshly initialized new modules.')
    (B / 'DESIGN_POLICY.json').write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
    (B / 'round_29' / 'next_round_network_requirement.json').write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
    state = json.loads((B / 'PAUSE_STATE.json').read_text(encoding='utf-8'))
    state.update(neural_structure_change_required_from_round=30, preprocessing_plus_neural_structure_required=True, next_transition_reference='previous primary REPORT Micro-F1', updated_at_Asia_Seoul=at)
    (B / 'PAUSE_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    with (B / '1105 신규 아이디어.md').open('a', encoding='utf-8') as f:
        f.write('Fixed configuration and provided target observation bundle.')
    print('NETWORK_STRUCTURE_POLICY_UPDATED', json.dumps({'from_round': 30, 'comparison_reference': p['comparison_reference'], 'minimum_gain': 0.01, 'minimum_goal': 0.63}))

def register_variants():
    p = json.loads((B / 'DESIGN_POLICY.json').read_text(encoding='utf-8'))
    at = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    p.update(updated_at_Asia_Seoul=at, neural_variation_required_from_round=30, preprocessing_plus_neural_variation_required=True, allowed_neural_variations=['partial_module_replacement', 'task_specific_finetuning', 'fusion_with_another_model', 'borrowed_architecture_or_separate_encoder'], neural_structure_change_required_from_round=None, preprocessing_plus_neural_structure_required=False, first_explicit_structure_round=30, latest_user_request='신경망 일부를 다른 구조로 변경, 파인튜닝, 새로운 모델과의 결합/융합, 다른 모델의 일부 구조를 현재 신경망과 함께 쓰는 방법도 허용. 다양한 변형 실험.', implementation='Combine coherent preprocessing variation with a substantive neural variation. Fine-tuning and model/encoder fusion are also explicitly authorized. Choose the component and purpose first, isolate major changes with matched controls, and vary direction below+0.01 versus previous primary score. Preserve best result. Never initialize from a previous round task-trained model; original public TabICL initialization and fresh new-module initialization remain the default.')
    (B / 'DESIGN_POLICY.json').write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
    (B / 'round_30' / 'expanded_neural_variation_authorization.json').write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
    state = json.loads((B / 'PAUSE_STATE.json').read_text(encoding='utf-8'))
    state.update(neural_structure_change_required_from_round=None, preprocessing_plus_neural_structure_required=False, neural_variation_required_from_round=30, preprocessing_plus_neural_variation_required=True, allowed_neural_variations=p['allowed_neural_variations'], updated_at_Asia_Seoul=at)
    (B / 'PAUSE_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    with (B / '1105 신규 아이디어.md').open('a', encoding='utf-8') as f:
        f.write('\n\n## 신경망 변형 범위 확대\n\n사용자는 부분 구조 교체뿐 아니라 파인튜닝, 다른 모델과의 결합/융합, 다른 모델의 일부 구조나 별도 인코더 사용을 명시적으로 허용했다. 진행 중인30차는 그대로 유지한다. 이후에는 전처리와 의미 있는 신경망 변형을 함께 검토하고, 각 시도의 핵심 변화와 목적을 정한 뒤 대조한다. 기존 회차 학습 가중치·학습 결과를 다음 회차 초기화나 입력으로 가져오지 않는 조건, 직전 대비+0.01 방향 전환 기준, 0.63 초과·0.65 근접 목표를 유지한다.\n')
    print('NEURAL_VARIATION_SCOPE_EXPANDED', json.dumps(p['allowed_neural_variations']))
if __name__ == '__main__':
    import sys
    if sys.argv[1] == 'register':
        register()
    elif sys.argv[1] == 'apply28':
        apply_running_round28()
    elif sys.argv[1] == 'network':
        register_network()
    elif sys.argv[1] == 'variants':
        register_variants()
    else:
        raise ValueError(sys.argv[1])
