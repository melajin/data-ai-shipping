"""Render Round019 tables and static statistical figures from completed outputs."""
from __future__ import annotations
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
OUT = BASE / 'execution_001'
NAMES = {'peak_score': '최고점', 'p95_score': '점수 95분위', 'median_score': '점수 중앙값',
         'n_rows': '관측 행 수(진단)', 'gap_total_h': '내부 관측 공백(h)', 'activity_radius_km': '부분선 중심점 반경(km)'}


def f(x, digits=4):
    return '미정의' if x is None or not math.isfinite(x) else f'{x:.{digits}f}'


def pformat(x):
    return '미정의' if x is None else f'{x:.4g}'


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows])


def main():
    import psutil
    memory = {'checked_at': datetime.now(timezone.utc).astimezone().isoformat(),
              'available_mib': psutil.virtual_memory().available / 2**20,
              'expected_peak_mib': 512, 'reserve_mib': 640,
              'estimate_basis': '7372-row CSV, small summary, three static matplotlib panels; no hourly loading'}
    processes = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            if p.info['memory_info']:
                processes.append({'pid': p.pid, 'name': p.info['name'], 'rss_mib': p.info['memory_info'].rss / 2**20})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    memory['other_processes'] = sorted(processes, key=lambda x: -x['rss_mib'])[:8]
    memory['passed'] = memory['available_mib'] >= 1152
    (OUT / 'report_memory.json').write_text(json.dumps(memory, indent=2), encoding='utf-8')
    if not memory['passed']:
        raise SystemExit('Report rendering deferred: insufficient RAM. Recheck before later retry; no polling.')
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    summary = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
    assert summary['stage'] == 'evaluation_complete'
    frame = pd.read_csv(OUT / 'evaluation_vessels.csv', dtype={'rfid_id': str})
    scenarios = pd.read_csv(OUT / 'expected_f1.csv')
    cohort = summary['cohort']
    match = summary['matching']
    raw = summary['uncontrolled']
    adjusted = summary['controlled_conditional']
    metrics = summary['metric_order']
    passed = summary['decision']['passing_candidates']
    scoremeta = summary['provenance']['score_metadata']
    pos = frame.is_provisional_linked
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.4), gridspec_kw={'width_ratios': [1, 1, 1.35]})
    for flag, color, label in [(True, '#c34a36', 'Provisionally linked (82)'),
                               (False, '#267c9e', 'Unlinked comparators (7290)')]:
        values = frame.loc[pos == flag, 'peak_score'].dropna()
        axes[0].hist(values, bins=np.linspace(0, 1, 31), weights=np.ones(len(values)) / len(values),
                     histtype='step', color=color, linewidth=2, label=label)
        counts = frame.loc[pos == flag, 'n_rows']
        axes[1].hist(np.log10(counts), bins=np.linspace(0, np.log10(frame.n_rows.max()) + .01, 26),
                     weights=np.ones(len(counts)) / len(counts), histtype='step', color=color, linewidth=2)
    axes[0].set(xlabel='Vessel peak score', ylabel='Fraction within group', title='Peak-score distributions (unadjusted)')
    axes[0].legend(fontsize=8)
    axes[1].set(xlabel='log10(observation rows)', ylabel='Fraction within group', title='Observation opportunity')
    y = np.arange(len(metrics))
    for data, delta, color, label in [(raw, -.12, '#8c8c8c', 'Uncontrolled AUC'),
                                     (adjusted, .12, '#1f6279', 'Matched conditional AUC')]:
        centers = np.array([data[m]['auc'] for m in metrics], dtype=float)
        lows = np.array([data[m]['ci_low'] for m in metrics], dtype=float)
        highs = np.array([data[m]['ci_high'] for m in metrics], dtype=float)
        axes[2].errorbar(centers, y + delta, xerr=[np.maximum(0, centers-lows), np.maximum(0, highs-centers)],
                         fmt='o', capsize=3, color=color, label=label, markersize=4)
    axes[2].axvline(.5, color='#b35d46', ls='--', lw=1)
    axes[2].axvline(.6, color='#b9b9b9', ls=':', lw=1)
    axes[2].set(yticks=y, yticklabels=metrics, xlim=(0, 1), xlabel='AUC and 95% percentile CI', title='Different estimands: raw vs within-match')
    axes[2].invert_yaxis()
    axes[2].legend(fontsize=8, loc='upper left')
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / 'distributions_and_auc.png', dpi=160)
    plt.close(fig)
    auc_table = table(['지표', '교란 미통제 AUC [95% CI]', 'MW 단측 p', '관측 수 매칭 내 AUC [95% CI]', '통제 Holm p', '판정'], [
        [NAMES[m], f"{f(raw[m]['auc'])} [{f(raw[m]['ci_low'])}, {f(raw[m]['ci_high'])}]", pformat(raw[m]['p_greater']),
         f"{f(adjusted[m]['auc'])} [{f(adjusted[m]['ci_low'])}, {f(adjusted[m]['ci_high'])}]",
         '진단 제외' if m == 'n_rows' else pformat(adjusted[m]['p_holm']), adjusted[m]['decision']] for m in metrics])
    dist_table = table(['집단', '척수', '평균', '25분위', '중앙값', '75분위', '95분위'], [
        ['잠정 사고 연결' if d['group'] == 'provisional_linked' else '미연결 비교군', d['n_finite'],
         f(d['mean']), f(d['p25']), f(d['median']), f(d['p75']), f(d['p95'])]
        for d in summary['distributions'] if d['metric'] == 'peak_score' and d['group'] != 'pooled_unlabeled_quantiles'])
    representatives = scenarios[(scenarios.representative == True) & (scenarios.metric.isin(['peak_score'] + passed))].copy()
    representative_rows = []
    for row in representatives.itertuples():
        representative_rows.append([NAMES[row.metric], f(row.threshold, 4),
            '교란 미통제' if row.source == 'raw_fleet_uncontrolled' else '매칭 분포 가정', f'{100*row.prevalence:g}%',
            f(row.tpr), f(row.fpr), f(row.k_per_100, 2), f(row.q), f(row.expected_time_included_f1, 6)])
    scenario_table = table(['지표', '고정 임계값', '비율의 출처', 'p', 'TPR', 'FPR', 'k/100', 'q', '기대 개수 기반 F1'], representative_rows)
    scenario_notes = []
    for metric in passed:
        selected_scenarios = representatives[(representatives.metric == metric) & (representatives.source == 'matched_set_weighted')]
        if len(selected_scenarios) == 4 and all(r.expected_time_included_f1 < 2*r.prevalence*.0366/(1+r.prevalence) for r in selected_scenarios.itertuples()):
            scenario_notes.append(f"**{NAMES[metric]}의 사전 대표 임계값에서는 매칭 분포를 가정한 기대 F1이 네 p 시나리오 모두 전부 제출 기준보다 낮았다.** AUC 연관 기준 통과를 제출 F1 개선으로 해석할 수 없다. 다른 고정 임계값도 CSV에 공개했으나 결과를 보고 최적 임계값을 채택하지 않았다.")
    scenario_note = '\n\n'.join(scenario_notes)
    baseline_table = table(['p 가정', '전부 제출, h=.0366', '전부 제출, h=1(완벽 시각)', '완벽 선별, h=.0366'],
        [[f'{100*p:g}%', f(2*p*.0366/(1+p), 6), f(2*p/(1+p), 6), '.036600'] for p in [.0227, .1, .5, 1]])
    peak = adjusted['peak_score']
    if not passed:
        conclusion = '**현재 후보로 선박의 실제 사고 여부를 판정할 근거를 확보하지 못했다. 채택 후보·임계값 없음.**'
    else:
        conclusion = '**' + ('최고 이상점수의 선박 판정력은 입증하지 못했다. ' if 'peak_score' not in passed else '') + '잠정 연결과의 관측 수 통제 후 연관 기준을 통과한 후보: ' + ', '.join(NAMES[m] for m in passed) + '. 확정 사고 판정력이나 외부 검증 완료를 뜻하지 않는다.**'
    peak_sentence = f"최고점의 관측 수 통제 후 조건부 AUC는 **{f(peak['auc'])}**, 95% CI **[{f(peak['ci_low'])}, {f(peak['ci_high'])}]**다. 최고점 판정: **{peak['decision']}**."
    b = match['log_n_rows_balance']
    quality = summary['quality']
    report = f'''# ROUND019 — Test B 선박 단위 사고 판정력 실측

{conclusion}

{peak_sentence} 이 결과는 2026 자료의 실제 계산 결과지만, 라벨은 **잠정 사고 연결**이고 비교군은 **미연결**이다. 실제 사고 여부의 확정 정답과 정상 선박 표본을 확보한 검증으로 해석할 수 없다.

## 평가 범위와 사전 고정

{cohort['rows']:,}행, {cohort['vessels']:,}척의 2026년 1–6월 보관 기하 요약을 사용했다. 제공된 100사건의 연결 목록은 {cohort['provisional_linked_vessels']}개 RFID로 줄어들며, 비교군은 {cohort['provisional_unlinked_comparators']:,}척이다. 이 평가 집단의 연결 비율은 {100*cohort['provisional_linked_vessels']/cohort['vessels']:.3f}%로, 요청된 p=2.27% 시나리오와 다르다. 167행은 고유 사고 선박 수가 아니므로 167/7,372를 실제 선단 사고율 실측치로 사용하지 않았다.

[분석 계획](PROTOCOL.md)을 2026-11-06 14:22:23 KST에 고정했다. 최고점·점수 95분위·중앙값·관측 행 수·내부 공백 총량·부분선 중심점 활동 반경을 사전 지정했으며, 방향은 모두 큰 값→잠정 연결로 고정했다. 결과를 보고 방향·후보·매칭 범위·채택 기준을 바꾸지 않았다. 관측 행 수는 편향 진단 전용이다. 신규 학습이나 점수함수 변경은 없으며, 보관된 2026 기준자료를 사용하는 사후 분석이다. 독립 검증 집단이나 당시 가용 정보만 사용하는 실시간 성능이 아니다.

## 최고점 분포와 관측 수 통제 전후

{dist_table}

{auc_table}

![집단별 최고점·관측량 분포와 AUC 신뢰구간](execution_001/distributions_and_auc.png)

미통제 AUC는 **교란 미통제**이며 그 값만으로 판정력을 주장하지 않는다. 일반 AUC는 Mann–Whitney U/(양성 수×비교군 수), 동점 0.5이며 단측 greater 점근 검정을 사용했다. CI는 두 집단 선박을 각각 복원추출한 5,000회 percentile 95% 구간이다. 구현 정의는 [SciPy Mann–Whitney 문서](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html)를 따른다.

관측 행 수 비율 1/1.10–1.10 안에서 양성당 최대 5척을 비복원 매칭했다. {match['n_sets']}/{cohort['provisional_linked_vessels']}척을 매칭해 커버리지는 {100*match['coverage']:.2f}%, 중복 없는 비교군은 {match['n_controls']}척이다. 비교군/양성 관측 수 비율은 {f(b['control_positive_ratio_min'])}–{f(b['control_positive_ratio_max'])}, 가중 log 관측 수 SMD는 {f(b['log_count_smd'], 6)}다. 점수는 매칭에 사용하지 않았다.

통제 AUC는 각 매칭 집합 내부의 양성–비교군 승률을 양성별 동일 가중치로 평균한 **조건부 AUC**다. 미통제 AUC와 표본·비교 대상을 달리하므로 단순한 보정 전후 동일 추정량으로 취급하지 않는다. CI는 고정 매칭 집합을 복원추출한 5,000회 구간이고, 단측 p는 집합 내 양성 위치 교환 9,999회 Monte Carlo(+1 보정)이다. 근접 매칭의 교환가능성을 가정하는 근사 검정이며 잔여 교란을 모두 제거했다고 주장하지 않는다. 관측 개수만 맞췄으므로 관측 기간·해역·조업 형태·시공간 연결 조건의 차이가 남을 수 있다. 판정 후보 5개의 p에 Holm 보정을 적용했다.

유한 점수 수와 원 관측 행 수가 다른 선박은 {quality['n_vessels_finite_scores_differs_from_rows']}척이다. 양성은 82척뿐이므로 CI 폭과 미검출 가능성을 함께 보아야 한다. AUC가 0.5 근처이면 판정 불가로 기록하며, 그것만으로 모든 가능한 사고 판별 방식의 무효를 입증한 것은 아니다. CI에는 잠정 연결의 오분류, 미연결 집단의 숨은 사고, 매칭 선택의 불확실성이 포함되지 않는다.

채택 기준은 조건부 AUC≥0.60, 95% CI 하한>0.50, Holm p<0.05, 양성 커버리지≥90%, |log 관측 수 SMD|≤0.10의 동시 충족이다. 실제 결과는 위 표에 모두 공개했다. 운영 임계값을 결과에 맞춰 최적화하지 않았다.

## p 가정별 시간 포함 기대 F1

TPR=a, FPR=b, 선택된 양성 선박에서의 시각 적중률 h=.0366을 놓으면 k=100[pa+(1−p)b], q=pa/[pa+(1−p)b], F1=2pah/[p(1+a)+(1−p)b]다. 선박당 1개 예측에서 시각을 틀린 양성은 FP와 FN 모두에 포함하는 계산이다. 아래는 **기대 개수의 비율로 계산한 시나리오**이며 공식 F1 실측이나 100척 표본 F1의 정확한 수학적 기댓값이 아니다.

{baseline_table}

사고 선박을 완벽히 골라도 h=.0366이면 F1 상한은 .0366이다. 1.0의 상한은 h=1과 완벽한 선박 선별을 함께 가정할 때만 성립한다.

최고점의 사전 대표 임계값 .75와 기준 통과 후보가 있을 경우 그 후보의 사전 대표 임계값을 표시한다. 기준 미통과 후보의 수치는 민감도 계산일 뿐 채택 권고가 아니다.

{scenario_table}

{scenario_note}

여기서 TPR/FPR은 잠정 연결군/미연결군의 선택률을 관례적으로 표기한 것이며 확정 사고 재현율·실제 오경보율이 아니다. 매칭 FPR은 양성의 관측 수 분포에 맞춘 값으로 전체 선단 FPR가 아니다. 미통제 수치는 관측량 교란을 포함한다. 두 종류 모두 p만 바꿔 적용하려면 조건부 점수 분포와 **선택된 양성에서의 h**가 유지된다는 미검증 가정이 필요하다. h=.0366은 사용자가 제공한 기준값으로 이번 라운드에서 재측정한 시각 적중률이 아니다. 후보마다 모든 고정 임계값·p 시나리오는 [threshold_sweep.csv](execution_001/threshold_sweep.csv), [expected_f1.csv](execution_001/expected_f1.csv)에 있다.

## 실행·검증 근거와 해석 한계

- 6개 입력의 ts가 2026년 1–6월 범위 안에 있음을 검사했다. 각 선박의 전체 이력을 정렬해 `frozen_baseline.py`를 그대로 호출했다. 부분선을 연결하거나 중심점 차이를 속력으로 변환하지 않았다.
- [점수화 메타데이터](execution_001/score_metadata.json): 완료 상태 {scoremeta['status']}, 처리 {scoremeta['rows_completed']:,}행/{scoremeta['vessels_completed']:,}척, 선박 오류 {scoremeta['vessel_error_records']}건. [전후 해시](execution_001/source_checksums_after.json)에서 입력·기준자료·고정 함수 불변 여부를 확인했다.
- 점수화 시작·진행·RAM 검사와 실제 실행 시간은 [로그](execution_001/score_progress.jsonl)에 있다. 첫 실행 직전 가용 RAM은 4,050.70MiB(약 3.96GiB)였다. 순차 실행 중 관측 RSS 약 308MiB와 실제 입력 동일성 검사의 peak 355.12MiB를 근거로, 추가 RAM 확인 뒤 4개 파티션 작업으로 전환했다. 병렬 실행 직전 가용 3,490.79MiB, 추정 parent 512MiB+worker 4×512MiB+여유 640MiB=3,200MiB 조건을 통과했다. [전환 기록](execution_001/parallel_migration.json)을 보존했다. 512MiB는 강제 상한이 아닌 추정치이고, 각 작업은 기존의 더 보수적인 1GiB 기준 단계별 메모리 검사도 수행했다. 작업별 관측 peak의 합은 {scoremeta.get('sum_of_worker_process_peak_mib', 0):.2f}MiB이며, 이 합을 동시점 실측 메모리로 부르지 않는다. 병렬 구간 경과 시간은 {scoremeta.get('elapsed_seconds', 0):.1f}초다. 전체 적재 대신 청크/파티션을 사용했고 점수 정의는 동일하다.
- 평가 직전 가용 RAM {summary['memory_before_evaluation'].get('available_mib', 0):.1f}MiB를 확인했다. 평가 입력·계획·코드·잠정 연결 목록 전후 해시 일치는 {summary['provenance']['checksums_match']}다. 보고서 렌더링 전 메모리는 [별도 기록](execution_001/report_memory.json)에 있다.
- 합성 코드 검증과 실제 선단 계산은 구분한다. 합성 점수화 검증 5개와 통계 검증 10개를 통과했다. 검증은 파티션 점수 동등성·동점·공백·결측·재개와 AUC·매칭·순열·Holm·F1 경계 사례 및 점수 CSV 변조 거부를 다룬다. 실제 결과의 AUC·매칭·F1·해시는 [별도 검산 코드](audit_verify.py)와 [검산 결과](execution_001/audit_verification.json), 검토 범위는 [독립 감사](AUDIT.md)에 기록한다. 실제 장치 실험은 하지 않았다.
- 허용된 2026 RFID 묶음 및 이미 제공된 잠정 연결 목록의 소속 여부만 사용했다. 다른 자료의 동일 선박 재식별·ID 조인·2025 테스트 적합·외부 수집은 수행하지 않았다.
- 공백은 첫·마지막 관측 사이의 미관측 시간 합계이며 통신 장애나 사고 기간 정답이 아니다. 활동 반경은 부분선 중심점의 공간 분포이며 실제 항해거리·GPS·침로·속력이 아니다. 실시간 판정 능력·확정 사고 정밀도·공식 F1은 이 결과만으로 산출할 수 없다.

## 학습 관점

기술 목표는 전체 선단의 고정 점수를 계산하고 같은 선박 단위에서 분포·불확실성·관측량 교란을 비교하는 것이다. 학습 목표는 ‘이상점수가 높다’와 ‘사고가 있었다’를 구별하는 것이다. 결과를 설명할 때에는 관측이 많은 선박이 최대값에서 유리한 이유, 매칭 조건부 AUC가 실제 선단 정밀도와 다른 이유, 시간 적중률이 F1 상한을 제한하는 이유를 답할 수 있어야 한다. 이번 결과를 넘어 새 모델·학습·운영 시스템을 자동으로 완성하지 않았다.

원시 지표 [vessel_peaks.csv](execution_001/vessel_peaks.csv), 라벨 포함 평가표 [evaluation_vessels.csv](execution_001/evaluation_vessels.csv), [summary.json](execution_001/summary.json), [매칭 명세](execution_001/matched_sets.csv)가 재검산 근거다.
'''
    (BASE / 'ROUND019_보고서.md').write_text(report, encoding='utf-8')
    print(json.dumps({'report': str(BASE / 'ROUND019_보고서.md'), 'decision': summary['decision'],
                      'peak_raw': raw['peak_score'], 'peak_matched': peak}, ensure_ascii=False))


if __name__ == '__main__':
    main()
