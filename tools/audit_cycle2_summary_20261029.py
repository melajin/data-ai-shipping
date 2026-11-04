"""Recalculate saved development metrics only; no fitting or final access."""
from pathlib import Path
import hashlib
import itertools
import json
import statistics as st

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'outputs/cycle2_20261029/development_ablation.json'


def main():
    raw = SOURCE.read_bytes()
    report = json.loads(raw)
    levels = [('s4', 'all'), ('none', 'balanced'), ('dist36', 'dist36_scale32')]
    names = ['sample', 'weight', 'features']
    cells = {tuple(c['cell'][n] for n in names): c for c in report['cells']}
    seeds = report['contract']['development_seeds']
    assert len(cells) == 8

    def values(key, metric):
        splits = {s['seed']: s for s in cells[key]['splits']}
        return [splits[s]['macro_f1'] if metric == 'macro_f1' else
                splits[s]['per_class_recall'][1] for s in seeds]

    def summary(v):
        return dict(values=v, mean=st.mean(v), min=min(v), max=max(v),
                    sd=st.stdev(v), positive_splits=sum(x > 0 for x in v))

    contrasts = []
    for i in range(3):
        for key in itertools.product(*levels):
            if key[i] != levels[i][0]:
                continue
            target = list(key)
            target[i] = levels[i][1]
            target = tuple(target)
            row = dict(factor=names[i], source=key, target=target)
            for metric in ['macro_f1', 'pot_recall']:
                row[metric] = summary([b-a for a, b in zip(values(key, metric), values(target, metric))])
            # sample changes coverage, hence the sets of scored vessels differ.
            row['same_scorable_set_by_construction'] = i != 0
            contrasts.append(row)

    base = tuple(v[0] for v in levels)
    def f(bits):
        return values(tuple(levels[i][bit] for i, bit in enumerate(bits)), 'macro_f1')

    interactions = []
    for i, j in itertools.combinations(range(3), 2):
        k = next(k for k in range(3) if k not in (i, j))
        for fixed in (0, 1):
            v = [0.] * len(seeds)
            for a, b in itertools.product((0, 1), repeat=2):
                bits = [0, 0, 0]
                bits[i], bits[j], bits[k] = a, b, fixed
                v = [x + (-1)**(a+b)*y for x, y in zip(v, f(bits))]
            interactions.append(dict(factors=[names[i], names[j]],
                                     held_fixed={names[k]: levels[k][fixed]}, **summary(v)))
    third = [sum((-1)**(3-sum(bits))*f(bits)[s]
                 for bits in itertools.product((0, 1), repeat=3)) for s in range(len(seeds))]
    singles = [next(c for c in contrasts if c['factor'] == name and tuple(c['source']) == base)
               for name in names]
    summed = sum(c['macro_f1']['mean'] for c in singles)
    joint = st.mean([b-a for a, b in zip(f((0, 0, 0)), f((1, 1, 1)))])
    out = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=hashlib.sha256(raw).hexdigest(),
               seeds=seeds, contrasts=contrasts, interactions=interactions,
               third_order=summary(third), baseline_single_sum=summed, joint_delta=joint,
               cell_macro_f1=[dict(cell=k, **summary(values(k, 'macro_f1'))) for k in cells],
               limitations=['Two tree initializations are probability-averaged before scoring; separate seed variance unavailable.',
                            'Three development splits can reuse vessels and are not independent replications.',
                            'sample contrasts change both training and validation feature aggregation and coverage.',
                            'Recall stored at five decimal places; recall differences are approximate.',
                            'No individual predictions, confusion matrices or probabilities are stored in source.'])
    dest = ROOT / 'outputs/cycle2_20261029/summary_audit.json'
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['| 요인 | 고정 조건 | ΔF1 평균 | 분할별 ΔF1 (3201 / 3202 / 3203) | 범위 | SD | 양수 분할 |',
             '|---|---|---:|---|---|---:|---:|']
    for c in contrasts:
        d = c['macro_f1']
        fixed = ', '.join(v for i, v in enumerate(c['source']) if names[i] != c['factor'])
        lines.append(f"| {c['factor']} | {fixed} | {d['mean']:+.5f} | "+
                     ' / '.join(f'{v:+.5f}' for v in d['values'])+
                     f" | {d['min']:+.5f} ~ {d['max']:+.5f} | {d['sd']:.5f} | {d['positive_splits']}/3 |")
    detail = ['# 2차 해설 검산 — 2026-10-29', '',
              '범위: 저장된 개발 지표의 산술 재계산과 코드 검토. 재학습·원자료 재추출·final 평가는 수행하지 않았다. 2차 runner는 전체 특징 캐시를 먼저 메모리에 로드한 후 final/dev를 분리한다. final의 학습 입력·예측·성능 평가 미사용과 캐시 자체의 로드를 구별한다.', '',
              '## 1. 표본 단위와 분모', '',
              '`aggregate()`는 선박별로 선택된 모든 월의 유효 행을 합쳐 shape9 각 열의 평균·표준편차·25%·75% 분위수를 만든다. 선박당 dist36 한 벡터를 학습한다. scale8도 같은 네 통계로 요약하여 32개를 추가한다. balanced는 유효 학습 선박의 클래스 수에 적용된다. 행수의 역수로 선박 가중치를 줄 문제는 현재 구조에 해당하지 않는다.', '',
              's4→all의 정확한 이름은 **선박별 분포 특징에 사용하는 관측 행 확대**다. 학습 선박 명부는 같지만 유효 특징을 가진 선박 수와 평가 coverage도 바뀐다. train·validation 양쪽 특징을 함께 바꾸므로, 특징 추정 정밀도만의 효과나 학습자료 확대만의 효과로 분리할 수 없다.', '',
              '최고 셀의 평가가능 수는 분할별 879/875/876(합 2,630), 통발은 125/125/124(합 374)다. 동일 선박이 분할 사이에 재등장할 수 있으므로 독립 고유 선박 수가 아니다. 1차 재현 셀은 878/874/876(합 2,628)으로 평가집합도 조금 다르다. 1차 final의 204와 직접 전후 비교하지 않는다.', '',
              '## 2. 분할을 맞춘 대조', '',
              '초기화 42·137의 확률을 먼저 평균한 뒤 분할당 지표 하나를 계산했다. 따라서 저장 결과는 셀당 지표 3개이며, 초기화별 성능 분산은 복원할 수 없다. 아래 SD는 세 paired difference의 표본 표준편차(ddof=1)다. 분할은 독립 반복이 아니므로 신뢰구간이나 유의성 검정으로 읽지 않는다. sample 대조는 같은 seed를 짝지었지만 보류 제외 집합까지 같지는 않다.', '']
    detail += lines
    detail += ['', '관측 행 확대는 네 대조 모두 3/3 양수다. 가중치와 규모 특징의 Macro F1은 각각 한 대조만 3/3 양수이며 나머지는 부호가 섞인다. 세 요인의 평균 효과가 양수라는 산술 사실과 조건 전반의 안정적인 기여는 구별한다.', '',
               '### 가중치의 통발 recall', '',
               '| 고정 조건 | 평균 차이 | 분할별 차이 | 범위 |', '|---|---:|---|---|']
    for c in contrasts:
        if c['factor'] == 'weight':
            d = c['pot_recall']
            detail.append(f"| {c['source'][0]}, {c['source'][2]} | {d['mean']:+.5f} | "+
                          ' / '.join(f'{v:+.5f}' for v in d['values'])+
                          f" | {d['min']:+.5f} ~ {d['max']:+.5f} |")
    detail += ['', '四 조건 모두 각 분할에서 양수다. 단, 공유 분할의 12개 차이를 독립 증거 12개로 세지 않는다. 현재 설계에서 일관된 개선이 관찰되지만 통발 문제는 해결되지 않았다. 원본 recall은 소수 다섯 자리로 저장되어 차이는 근삿값이다.'.replace('四', '네'), '',
               '## 3. 합산 효과와 교호작용', '',
               f'기준 셀 s4/none/dist36에서 한 요인씩 켠 차이는 +0.07511, +0.03803, +0.03599다. 반올림 전 합은 **{summed:+.5f}**이며, 표시값 합은 +0.14913이다. 종전 +0.14914의 중간 계산 근거는 기록되어 있지 않아 원본 지표에서 재계산한 값으로 정정한다. 네 조건 평균 효과의 합(+0.07421)과는 다른 비교다. 세 요인을 함께 켠 차이는 **{joint:+.5f}**다.', '',
               '다음은 각 고정 수준에서의 차이의 차이: I_AB = F11 − F10 − F01 + F00. 회귀식의 ±1 코딩 계수와는 크기 정의가 다르다.', '',
               '| 두 요인 | 고정 수준 | 평균 교호작용 | 분할별 범위 |', '|---|---|---:|---|']
    for r in interactions:
        detail.append(f"| {' × '.join(r['factors'])} | {r['held_fixed']} | {r['mean']:+.5f} | {r['min']:+.5f} ~ {r['max']:+.5f} |")
    detail += ['', '이는 Macro F1 척도에서 효과가 가산적이지 않다는 기술 통계다. 같은 다수 클래스 편향을 고친다는 메커니즘은 여기서 입증되지 않는다. 셀별 예측 비율·완전한 혼동행렬·확률이 저장되지 않아 그 계산은 이 지표 파일만으로 할 수 없다. 제한된 자리수의 F1·recall에서 혼동행렬을 역산하지 않는다.', '',
               '## 4. 후속 진단 설계와 holdout 상태', '',
               '- 우선 개발 validation 예측을 선박·seed·셀·정답·보류·확률과 함께 보존하고, 통발 혼동행렬 행과 연안복합 예측 비율을 계산한다. 현재는 미수행이다.',
               '- 통발 대 나머지의 고정 단순 모델에서 개발 AUC와 PR-AUC, recall·precision을 함께 보고 분할별 변동을 남긴다. AUC≈0.5는 그 모델·평가 조건에서 분리가 약하다는 뜻이다. 특징에 정보가 없다는 상한 증명은 아니다. 높은 AUC와 낮은 recall도 임계값·가중치 문제의 진단 단서이며 확정 원인은 아니다.',
               '- 오분류 목적지가 연안복합에 몰려도 라벨 문제로 확정하지 않는다. 특징 중첩·클래스 구성·모델 결정 규칙을 먼저 구분한다. 라벨-행동 정합성은 별도 근거로 확인한다.',
               '- 후속 행수 포화 곡선은 선박·월당 k를 늘리되 선박 명부·선택 순서를 고정하고, train만 확대/validation만 확대/둘 다 확대를 구분한다. coverage도 함께 보고한다. 이 설계는 제안이며 새 실험은 실행하지 않았다.',
               '- 2026-10-29 현재 재개봉 후보와 판정 기준은 **미동결, final 재평가 금지 유지**다. 목표 지표·최소 개선폭·NLL/Brier 비열등 허용폭·보류 규칙·후보 및 코드 해시를 한 계약에 고정하기 전에는 열지 않는다. 기존 final은 1차에서 이미 사용했으므로 재평가를 독립된 새 holdout 검증이라고 부를 수 없다.', '',
               '## 5. 근거와 재현', '',
               f'- 입력: `{SOURCE.relative_to(ROOT).as_posix()}`', f'- SHA-256: `{out["source_sha256"]}`',
               '- 재현: `python tools/audit_cycle2_summary_20261029.py`',
               '- 계산 상세: `outputs/cycle2_20261029/summary_audit.json` (셀별 F1 SD·세 요인 교호작용 포함).',
               '- 코드 근거: `tools/run_cycle2_development_20261029.py`의 aggregate/build_matrix/run_cell/evaluate.',
               '- 작성 소유자: 현재 부모 에이전트(검산 스크립트·JSON·해설·기술 문서·본 감사 문서). 독립 읽기 검토는 sol_review 역할로 GPT-6.1 Sol high를 명시해 spawn_agent를 호출했고 `/root/unit_review` 생성 응답을 받았다. 부모 세션 모델을 변경했다는 뜻은 아니다.', '',
               '학습 확인 질문: 왜 관측 행 30배 확대가 학습 예제 30배 확대와 다른가? 왜 같은 seed를 맞춰도 sample 대조의 평가집합이 달라질 수 있는가? 왜 음의 교호작용만으로 동일 편향 원인을 확정할 수 없는가?']
    (ROOT / 'docs/cycle2_summary_audit_20261029.md').write_text('\n'.join(detail)+'\n', encoding='utf-8')
    print('\n'.join(lines))
    print('BASELINE SINGLE SUM', summed, 'JOINT', joint)
    for row in interactions:
        print('INTERACTION', row)
    for c in contrasts:
        if c['factor'] == 'weight':
            print('WEIGHT RECALL', c['source'], c['pot_recall'])
    for key in [base, ('all', 'balanced', 'dist36_scale32')]:
        print('SUPPORT', key, [(s['scorable'], s['per_class_support'][1]) for s in cells[key]['splits']])


if __name__ == '__main__':
    main()
