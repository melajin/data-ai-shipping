"""Small, post-hoc scenario comparison; no fitting or threshold optimization."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import psutil

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'execution_001' / 'expected_f1.csv'
H0 = .0366


def main():
    out = HERE / 'execution_001'
    out.mkdir(exist_ok=False)
    vm = psutil.virtual_memory()
    processes = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            processes.append({'pid': p.pid, 'name': p.info['name'], 'rss_mib': p.info['memory_info'].rss / 2**20})
        except (psutil.Error, AttributeError):
            pass
    memory = {'at': datetime.now(timezone.utc).astimezone().isoformat(), 'available_mib': vm.available / 2**20,
              'expected_peak_mib': 128, 'reserve_mib': 640,
              'basis': 'stdlib CSV only, 504 aggregate rows; no hourly inputs/scoring/training',
              'other_processes': sorted(processes, key=lambda x: -x['rss_mib'])[:8]}
    (out / 'memory.json').write_text(json.dumps(memory, indent=2), encoding='utf-8')
    if memory['available_mib'] < 768:
        raise RuntimeError('Deferred for RAM; recheck at next execution stage, no polling')
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    with SOURCE.open(encoding='utf-8-sig', newline='') as handle:
        source = list(csv.DictReader(handle))
    rows, sensitivity = [], []
    for r in source:
        if r['source'] != 'matched_set_weighted' or r['representative'] != 'True' or r['metric'] not in ('peak_score', 'activity_radius_km'):
            continue
        p, a, b = map(float, (r['prevalence'], r['tpr'], r['fpr']))
        denominator = p * (1 + a) + (1 - p) * b
        slope = 2 * p * a / denominator
        baseline = 2 * p * H0 / (1 + p)
        computed = slope * H0
        assert abs(computed - float(r['expected_time_included_f1'])) < 1e-12
        rows.append({'metric': r['metric'], 'threshold': float(r['threshold']), 'p': p, 'h': H0,
                     'tpr': a, 'fpr_standardized_to_linked_count_distribution': b,
                     'expected_submissions_per_100': float(r['k_per_100']), 'q_scenario': float(r['q']),
                     'selected_f1': computed, 'all_submit_f1': baseline, 'difference': computed - baseline,
                     'selected_h_to_equal_old_all_submit': baseline / slope if slope else None})
        for h in (H0, .1, .25, .5, 1):
            sensitivity.append({'metric': r['metric'], 'p': p, 'h': h, 'selected_f1': slope*h,
                                'all_submit_same_h_f1': 2*p*h/(1+p), 'old_all_submit_h00366_f1': baseline})
    assert len(rows) == 8
    assert all(r['difference'] < 0 for r in rows)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before
    for name, data in [('comparison.csv', rows), ('timing_sensitivity.csv', sensitivity)]:
        with (out / name).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    summary = {'created_at': memory['at'], 'source_sha256': before, 'source_unchanged': True,
               'analysis': 'post-hoc explanatory scenario, not new measured F1', 'new_threshold_selected': False,
               'h0': H0, 'rows': rows,
               'caveats': ['2026 provisional linkage, not 2025 Test B ground truth',
                           'Matched FPR standardized to linked count distribution, not fleet FPR',
                           'Selected h assumed equal to baseline h; not remeasured',
                           'Break-even h compares selected strategy with OLD all-submit h=.0366; if all-submit h also rises, comparison changes',
                           'These two fixed representative thresholds do not establish failure of every threshold or method']}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    names = {'peak_score': '최고점 ≥0.75', 'activity_radius_km': '활동 반경 ≥81.9936km'}
    lines = ['# 완화 기준 후보의 예상 F1 비교', '',
             '최고점과 활동 반경을 탐색 후보로 유지하되, 기존의 대표 임계값으로 전부 제출 방식과 비교했다. 후보 기준 완화와 점수 임계값 변경은 별개다. 새 임계값 선택·새 학습·2025 자료 사용은 하지 않았다.', '',
             '**두 대표 임계값 모두, 매칭 분포를 가정한 네 p 시나리오에서 전부 제출 기준보다 낮았다.** 계산 결과는 기존 Round019와 일치하며 새 성능 실측이 아니다.', '',
             '| 후보 | p | 전부 제출 F1 | 선별 F1 | 기존 전부 제출과 같아지는 선별 후 시각 적중률 |',
             '|---|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {names[r['metric']]} | {100*r['p']:g}% | {r['all_submit_f1']:.6f} | {r['selected_f1']:.6f} | {100*r['selected_h_to_equal_old_all_submit']:.2f}% |")
    lines.extend(['', '마지막 열은 전부 제출의 시각 적중률을 기존 3.66%에 고정한 손익분기 계산이다. 선별 후 적중률이 이 수치를 넘으면 그 **기존 기준**을 넘는다. 전부 제출 방식의 시각 선택도 함께 개선된다면 비교 기준도 올라간다. 같은 h를 두 방식에 동일하게 적용하면 F1이 모두 비례해 증가하므로 선별 방식의 우열은 바뀌지 않는다.', '',
                  'F1은 0–1 척도이며 분류 정확도나 실제 정답 척수의 백분율이 아니다. p와 h를 가정한 기대 개수의 비율이다. 매칭 비교군은 확정 미사고가 아니며 관측 수 분포도 전체 선단과 다르므로 2025 Test B 성능으로 이식해 단정할 수 없다.', '',
                  '관측 공백·동점 처리에 따른 사고시각 개선 효과는 이번 계산에서 측정하지 않았다. 주최 측이 허용한 후보 시각 범위에 대한 별도 실험이 필요하다. 입력 시간별 점수 전체는 Round019 결과에 저장되지 않았고 선박별 요약만 있으므로, 새 시각 선택 실험은 대상 이력을 다시 점수화하거나 검증된 기존 시간별 산출물을 확인해야 한다.', '',
                  '근거: [비교 CSV](execution_001/comparison.csv), [h 민감도](execution_001/timing_sensitivity.csv), [요약](execution_001/summary.json).'])
    (HERE / 'F1_비교.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'status': 'complete', 'rows': len(rows), 'source_unchanged': True, 'report': str(HERE / 'F1_비교.md')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
