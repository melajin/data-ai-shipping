"""Round22+: all task fits and calibration are local to the numbered round.

Original public pretrained weights are initialization, not previous task results.
TabICL fit registers training context and fits preprocessing; no gradient update.
"""
from matched_contrast import *
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from direction_policy import decision as direction_decision, state_fields as direction_state_fields

def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()

def restrict_old_rounds(n):

    def audit(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes, Path)):
            return
        name = '/' + str(args[0]).replace('\\', '/')
        match = re.search('/round_(\\d+)(?:/|$)', name)
        if match and int(match[1]) != n:
            raise RuntimeError('Previous round artifact access forbidden: ' + name)
        if any((s in name for s in ['/feedback_followup_19/', '/spatial_distribution/'])):
            raise RuntimeError('Previous learned feature artifact access forbidden: ' + name)
    sys.addaudithook(audit)

def start(n, design):
    notices = [p for p in (B.parent / '공지사항').glob('*') if p.is_file()]
    notice_hashes = {str(p): sha(p) for p in notices}
    review = B / 'NOTICE_REVIEW_STATE.json'
    if review.exists():
        reviewed = json.loads(review.read_text(encoding='utf-8'))['reviewed_notice_hashes']
        assert notice_hashes == reviewed, 'NOTICE_CHANGED_REVIEW_REQUIRED: inspect changed notices before a new fit'
    rd = setup_round(n, {'design': design, 'independence_protocol': 'All heads/pairs/transforms/calibration fitted in this round. No previous task weights, probabilities, prototypes or fitted decision settings. Shared deterministic geometry summaries and fixed boat split only.', 'original_public_checkpoint_only': True, 'gradient_updates': False, 'ensemble': 4, 'observation_scope': 'Provided target vessel bundle; full or first1/3/7 observed dates. User confirmed existing aggregation on2026-11-05. No external same-ID history.', 'notice_status': 'Local notices reviewed; multi-date aggregation follows provided observation scope, provided target observations only.', 'selection': 'TUNE only; all policies persisted before REPORT scoring. REPORT repeatedly used for development.'})
    shutil.copy2(Path(__file__), rd / 'fresh_rounds.py')
    shutil.copy2(B / 'direction_policy.py', rd / 'direction_policy.py')
    shutil.copy2(B / 'DESIGN_POLICY.json', rd / 'design_policy_at_start.json')
    sources = [B.parent / '데이터 처리 1105.md', B.parent / '데이터 증강과 학습.md', B.parent / '모델 설계 시도 MD' / '피드백 MD 요약본.md']
    dump(rd / 'source_review.json', {'at': now(), 'references': {str(p): sha(p) for p in sources}, 'notices': notice_hashes, 'constraints': ['No same-ID observations outside provided target bundle', 'No artificial speed or per-point timestamp', 'Do not join disconnected parts or observation gaps', 'Fixed boat-disjoint FIT/TUNE/REPORT', 'Four-class vessel micro-F1; no excluded difficult boats'], 'observation_scope': 'Fixed configuration and provided target observation bundle.', 'official_scope_independently_confirmed': False})
    state = json.loads((B / 'PAUSE_STATE.json').read_text(encoding='utf-8'))
    current_policy = json.loads((B / 'DESIGN_POLICY.json').read_text(encoding='utf-8'))
    state.pop('current_round_correction', None)
    dump(rd / 'previous_result_at_start.json', {'previous_round': state['last_round'], 'previous_primary_micro_f1': state['last_round_micro_f1'], 'best_prior_primary_micro_f1': state['best_micro_f1'], 'use': 'scalar comparison for progress only; not training input or calibration'})
    state.update(status='resumed', continue_only_after_user_resume=False, running_experiments_remaining=True, current_round=n, completed_current_round=False, current_run_log=f'round{n}_run.log', current_phase='Fresh within-round fitting and training;REPORT not yet scored', updated_at_Asia_Seoul=now(), independence_from_round=22, report_on_each_round_completion=True, observation_scope_resolution='User confirmed existing provided-vessel aggregation; no claim of independent organizer confirmation', resume_request=state.get('resume_request', '다시 작업을 재개해줘'), next_design_status=design)
    state.update(current_transition_threshold_absolute=current_policy['minimum_absolute_gain'], current_transition_reference=current_policy['comparison_reference'], minimum_goal_micro_f1=current_policy['minimum_goal_micro_f1'])
    dump(B / 'PAUSE_STATE.json', state)
    return rd

def fit_arm(rd, arm, v, x, s):
    fit = s.split.eq('FIT').to_numpy()
    q = ~fit
    y = s.y.to_numpy()
    tasks = []
    specs = [('head', fit)] + [(f'pair_{a}_{b}', fit & np.isin(y, [a, b])) for a, b in itertools.combinations(range(4), 2)]
    pair = np.ones((q.sum(), 4, 4))
    for name, ctx in specs:
        assert not set(s.index[ctx]) & set(s.index[q])
        seed = SEED + 910 if name == 'head' else SEED + 1100 + 10 * int(name[-3]) + int(name[-1])
        begun = now()
        p, cc = predict(x.loc[ctx], y[ctx], x.loc[q], seed, 4)
        if name == 'head':
            assert list(cc) == [0, 1, 2, 3]
            joint = p
        else:
            a, b = map(int, name.split('_')[1:])
            pa = p[:, list(cc).index(a)]
            pair[:, a, b] = pa
            pair[:, b, a] = 1 - pa
        np.save(rd / f'{arm}_{v}_{name}.npy', p)
        tasks.append({'arm': arm, 'view': v, 'task': name, 'started': begun, 'finished': now(), 'seed': seed, 'n_context': int(ctx.sum()), 'n_query': int(q.sum()), 'n_features': x.shape[1], 'context_ids_sha256': hashlib.sha256(s.index[ctx].to_numpy().tobytes()).hexdigest(), 'query_ids_sha256': hashlib.sha256(s.index[q].to_numpy().tobytes()).hexdigest(), 'original_checkpoint': str(CHECKPOINT), 'fresh_fit': True, 'gradient_updates': False})
        with (rd / 'fresh_fit_calls.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(tasks[-1]) + '\n')
    np.save(rd / f'{arm}_joint_{v}.npy', joint)
    np.save(rd / f'{arm}_pair_{v}.npy', pair)
    return (joint, pair)

def fresh_base_select(pa, pb, y):
    best = None
    candidates = []
    for beta in [0.0, 0.5, 1.0]:
        j = (1 - beta) * pa[0] + beta * pb[0]
        p = (1 - beta) * pa[1] + beta * pb[1]
        alpha, w, key = policy(j, p, y)
        key = (*key, -beta)
        candidates.append({'beta': beta, 'alpha': alpha, 'weights': w.tolist(), 'TUNE_correct': key[0], 'TUNE_macro': key[1]})
        if best is None or key > best[0]:
            best = (key, beta, alpha, w)
    return (best[1:], candidates)

def complete(rd, s, base, prob, pairs, final, decisions, controls, eligible_for_best=True, *, update_session=True):
    sub = s.loc[s.split != 'FIT']
    tu = sub.split.eq('TUNE').to_numpy()
    qy = sub.y.to_numpy()
    dump(rd / 'decision_policy.json', decisions)
    tp = np.concatenate([prob[v][tu] for v in VIEWS])
    ty = np.tile(qy[tu], 4)
    ts = np.array([np.quantile(tp[ty == c, c], 0.1, method='lower') for c in range(4)])
    dump(rd / 'thresholds.json', ts.tolist())
    dump(rd / 'selection_frozen.json', {'at': now(), 'policy_sha256': sha(rd / 'decision_policy.json'), 'REPORT_used_for_selection': False})
    for v in VIEWS:
        np.save(rd / f'prob_{v}.npy', prob[v])
        np.save(rd / f'pair_{v}.npy', pairs[v])
    m = evaluate(rd, s, base, prob, ts, final, controls)
    cm = {v: {name: {sp: metrics(qy[z], pred[z]) for sp, z in [('TUNE', tu), ('REPORT', ~tu)]} for name, pred in controls[v].items()} for v in VIEWS}
    dump(rd / 'controlled_metrics.json', cm)
    if not update_session:
        dump(rd / 'review_completion.json', {'review_only': True, 'session_state_updated': False, 'eligible_positive_body': bool(eligible_for_best), 'full_REPORT': m['full']['REPORT']})
        return m
    score = m['full']['REPORT']
    n = int(rd.name.split('_')[1])
    state = json.loads((B / 'PAUSE_STATE.json').read_text(encoding='utf-8'))
    previous = state['last_round_micro_f1']
    oldbest = state['best_micro_f1']
    direction = direction_decision(score['micro_f1'], previous, oldbest)
    state.update(last_round=n, last_round_micro_f1=score['micro_f1'], last_round_f1=score['f1'], completed_current_round=True, current_phase='REPORT scored;post-run reconstruction audit pending', running_experiments_remaining=False, next_round_number=n + 1, next_round_number_if_user_resumes=n + 1, updated_at_Asia_Seoul=now(), last_absolute_improvement=score['micro_f1'] - previous, next_requires_core_direction_change=direction['next_must_change_core_structure'], results_status='Repeated REPORT development score; user-confirmed provided-bundle scope, not official Test result.')
    state['completed_independent_rounds'].append(n)
    state['completed_fully_refitted_rounds'] = state.get('completed_fully_refitted_rounds', []) + [n]
    if eligible_for_best and score['micro_f1'] > state.get('best_fully_refitted_micro_f1', -1):
        state.update(best_fully_refitted_round=n, best_fully_refitted_micro_f1=score['micro_f1'])
    if eligible_for_best and score['micro_f1'] > oldbest:
        state.update(best_micro_round=n, best_micro_f1=score['micro_f1'], best_micro_round_f1=score['f1'])
    state.update(direction_state_fields(direction, max(oldbest, score['micro_f1']) if eligible_for_best else oldbest))
    dump(B / 'PAUSE_STATE.json', state)
    dump(rd / 'feedback.json', {'round': n, 'micro_f1': score['micro_f1'], **direction, 'all_task_fits_fresh': True, 'best_prior_preserved': True, 'eligible_for_best': eligible_for_best})
    report = B / '1105 신규 아이디어.md'
    config = json.loads((rd / 'config.json').read_text(encoding='utf-8'))
    weight_note = config.get('gradient_description') or ('공개 원본에서 시작해 ICL 가중치 미세조정을 실제 수행했으며, 변경 여부와 최종 채택 여부는 별도 기록했다.' if config.get('gradient_updates') else 'TabICL 가중치의 경사 학습은 수행하지 않았다.')
    with report.open('a', encoding='utf-8') as f:
        f.write(f'\n\n## {n}차: 회차 내 전체 재적합\n\n이전 회차의 학습 가중치·예측·판정 설정을 읽지 않고 공개 원본 체크포인트에서 모든 문맥 적합과 TUNE 선택을 새로 수행했다. {weight_note} 제공된 선박 관측 묶음을 사용하는 범위는 제공된 대상 관측 묶음으로 제한한다.\n\n')
        f.write('|입력 범위|Micro-F1|연안복합 F1|자망 F1|통발 F1|채낚기연승낚시 F1|\n|---|---:|---:|---:|---:|---:|\n')
        for v in VIEWS:
            z = m[v]['REPORT']
            f.write('|' + v + '|' + '|'.join((f'{a:.6f}' for a in [z['micro_f1'], *z['f1'].values()])) + '|\n')
        f.write(f'\n구성·선택: `round_{n:02}/config.json`, `decision_policy.json`. 원본부터 수행한 적합 호출: `fresh_fit_calls.jsonl`. REPORT는 반복 개발 평가이며 독립 최종 성적이 아니다.\n')
    print('FRESH_ROUND_COMPLETE', json.dumps({'round': n, **score}, ensure_ascii=False), flush=True)
    return m

def round22():
    rd = start(22, 'Equal-day geometry/time mixture features; fresh compact150 and state337 controls, full fresh calibration')
    restrict_old_rounds(22)
    from fresh_day_inputs import build
    build(rd)
    s, base = load()
    sub = s.loc[s.split != 'FIT']
    tu = sub.split.eq('TUNE').to_numpy()
    qy = sub.y.to_numpy()
    prob = {}
    pairs = {}
    final = {}
    decisions = {}
    controls = {}
    inputs = {}
    for v in VIEWS:
        compact = base[v].join(pd.read_csv(B / f'layout_features_{v}.csv', index_col='id')).reindex(s.index)
        state = compact.join(pd.read_csv(B / f'state_features_{v}.csv', index_col='id'))
        daily = state.join(pd.read_csv(rd / f'day_features_{v}.csv', index_col='id'))
        pa = fit_arm(rd, 'compact', v, compact, s)
        pb = fit_arm(rd, 'state', v, state, s)
        pc = fit_arm(rd, 'daily', v, daily, s)
        (beta, alpha, w), cand = fresh_base_select(tuple((z[tu] for z in pa)), tuple((z[tu] for z in pb)), qy[tu])
        bj = (1 - beta) * pa[0] + beta * pb[0]
        bp = (1 - beta) * pa[1] + beta * pb[1]
        best = None
        choices = []
        for gamma in [0.0, 0.25, 0.5, 0.75, 1.0]:
            j = (1 - gamma) * bj + gamma * pc[0]
            p = (1 - gamma) * bp + gamma * pc[1]
            pr = apply_policy(j, p, alpha, w)
            mm = metrics(qy[tu], pr[tu])
            key = (int((pr[tu] == qy[tu]).sum()), mm['macro_f1'], -gamma)
            choices.append({'gamma': gamma, 'TUNE_micro': mm['micro_f1'], 'TUNE_macro': mm['macro_f1']})
            if best is None or key > best[0]:
                best = (key, gamma, j, p, pr)
        _, gamma, prob[v], pairs[v], final[v] = best
        decisions[v] = {'base_beta': beta, 'alpha': alpha, 'weights': w.tolist(), 'base_candidates': cand, 'daily_gamma': gamma, 'daily_candidates': choices}
        controls[v] = {'fresh_base_prediction': apply_policy(bj, bp, alpha, w), 'daily_only_prediction': apply_policy(*pc, alpha, w), 'compact_only_prediction': apply_policy(*pa, alpha, w), 'state_only_prediction': apply_policy(*pb, alpha, w)}
        inputs[v] = {'compact_columns': compact.columns.tolist(), 'state_columns': state.columns.tolist(), 'daily_columns': daily.columns.tolist(), 'shared_deterministic_sha': {str(p): sha(p) for p in [B / f'features_{v}.csv', B / f'layout_features_{v}.csv', B / f'state_features_{v}.csv']}}
        print('FRESH_SELECTION', v, json.dumps(decisions[v]), flush=True)
    dump(rd / 'input_audit.json', inputs)
    complete(rd, s, base, prob, pairs, final, decisions, controls)
if __name__ == '__main__':
    assert sys.argv[1] == '22'
    round22()
