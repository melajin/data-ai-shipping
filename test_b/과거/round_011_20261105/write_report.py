"""Integrate the fixed Round011 outputs; does not fit or change any score."""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import hashlib
import json
from datetime import datetime

HERE = Path(__file__).resolve().parent


def main():
    summary = json.loads((HERE / 'summary.json').read_text(encoding='utf-8'))
    execution = json.loads((HERE / 'execution.json').read_text(encoding='utf-8'))
    audit = json.loads((HERE / 'audit.json').read_text(encoding='utf-8'))
    if execution['status'] != 'complete' or execution['exit_code'] != 0:
        raise RuntimeError('Do not report partial experiment output as final results')
    if audit['status'] != 'passed':
        raise RuntimeError('Final report requires completed independent output audit')
    with (HERE / 'event_metrics.csv').open(encoding='utf-8', newline='') as f:
        events = [r for r in csv.DictReader(f) if r['rule'] == 'TL_lin']
    by_vessel = defaultdict(list)
    near = {}
    for event in events:
        aid = int(event['acc_id'])
        by_vessel[int(event['rfid_id'])].append(event)
        near[aid] = Counter()
    with (HERE / 'timestamp_scores.csv').open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            t = int(row['ts'])
            for event in by_vessel[int(row['rfid_id'])]:
                if abs(t - int(event['acc_ts'])) > 6:
                    continue
                counts = near[int(event['acc_id'])]
                counts['observed'] += 1
                for context in ('T', 'L', 'TL'):
                    if not row[f'{context}_unknown_reason']:
                        counts[f'{context}_valid'] += 1
                    else:
                        counts[f'{context}_unknown:{row[f"{context}_unknown_reason"]}'] += 1
                if row['M'] and float(row['M']) == 0:
                    counts['M_zero'] += 1
    diagnostics = {}
    for name, select in (('tier01', lambda r: int(r['tier']) <= 1), ('all100', lambda r: True)):
        subset = [e for e in events if select(e)]
        diagnostics[name] = {
            'total_events': len(subset),
            'observed_near_zero': sum(int(e['observed_near_count']) == 0 for e in subset),
            'quality_near_zero': sum(int(e['quality_near_count']) == 0 for e in subset),
            'common_near_zero': sum(int(e['common_near_count']) == 0 for e in subset),
            'T_near_zero': sum(near[int(e['acc_id'])]['T_valid'] == 0 for e in subset),
            'L_near_zero': sum(near[int(e['acc_id'])]['L_valid'] == 0 for e in subset),
            'TL_near_zero': sum(near[int(e['acc_id'])]['TL_valid'] == 0 for e in subset),
            'near_M_zero_rows': sum(near[int(e['acc_id'])]['M_zero'] for e in subset),
            'near_unknown_reason_counts': dict(sum((near[int(e['acc_id'])] for e in subset), Counter())),
        }
    (HERE / 'coverage_diagnostics.json').write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding='utf-8')
    pct = lambda x: 'NA' if x is None else f'{100*x:.3f}%'
    num = lambda x: 'NA' if x is None else f'{100*x:+.3f}'
    p = summary['profiles']['tier01']
    baseline = p['rules']['raw_lin']
    supported = [c['contrast'] for c in summary['primary_contrasts'] if c['exploratory_improvement_supported']]
    if supported:
        conclusion = '사전 네 비교 중 ' + ', '.join(supported) + '에서 탐색적 개선 기준을 충족했다.'
    elif all(c['n_events'] < 30 for c in summary['primary_contrasts']):
        conclusion = '공통 평가 사건이 사전 최소30건에 못 미쳐 시간·위치 공동 비교의 국소화 개선 판정을 유보한다.'
    else:
        conclusion = '시간·위치 공동 비교의 국소화 개선은 사전 네 비교에서 지지되지 않았다.'
    text = [
        '# Round011 시간과 위치를 고려한 행동 변화 실험 결과', '',
        f'작성: {datetime.now().astimezone().isoformat()} · 실제 dev 자료 재계산 · 계약: [PROTOCOL.md](PROTOCOL.md)', '',
        '**lin_raw는 사용자 결정에 따라 특징 후보로 유지한다.** ' + conclusion,
        f'Tier0-1 전체60사건 중 공통 후보 100시각 이상을 갖춘 평가 가능 사건은 {baseline["n_evaluable"]}건/{baseline["n_evaluable_vessels"]}척이다. '
        f'이 중 사고 ±6h에 공통 후보가 하나도 없는 사건도 {baseline["n_evaluable_without_near_candidates"]}건 있으며 실패로 유지했다.', '',
        '## 세운 가설과 실제 비교', '',
        'H1은 시간·위치를 함께 맞춘 과거 이력이 시간만 또는 위치만 맞춘 이력보다 lin_raw의 사고 시점 국소화를 개선한다는 가설이다. '
        'H2는 상대적인 경로량 저하와 중심점 이동 순위의 조합에 같은 맥락 비교가 도움이 된다는 가설이다.', '',
        '각 시점의 후행7시간을 같은 선박의 24~720시간 전 이력과 비교했다. T는 저장 시간대 ±1시간, L은 위치 10km, TL은 두 조건을 함께 적용했다. '
        '최근 서로 다른10일을 하루 한 창씩 쓰며 10일 미만은 unknown이다. 모든 방식이 산출되는 공통 후보 시각에서 순위를 비교했다. '
        '동률 top-1은 균등 추첨의 기대 적중값이고, top-10은 경계 동률의 정확 비복원 추첨 적중 확률이다. 소수 적중합은 실제 정수 건수와 구분한다.', '',
        '## 주 결과 Tier0-1', '',
        '|점수|조건부 top-1 ±6h|조건부 top-10|전체60 분모 top-1|',
        '|---|---:|---:|---:|',
    ]
    for rule, r in p['rules'].items():
        text.append(f'|{rule}|{pct(r["top1_conditional"])}|{pct(r["top10_conditional"])}|{pct(r["top1_unconditional"])}|')
    text += ['', f'동일 공통 후보 시각의 top-1 균등 무작위 기대: {pct(baseline["chance_conditional"])}. '
             '자료 부족 사건의 점수를 0으로 둔 전체60 분모 성과는 서비스 범위를 포함한 보수적 지표이며 unknown을 정상 정답으로 간주한 것이 아니다.', '',
             'lin = 낮은 bbox/경로길이 비율의 상대 순위, activity = 낮은 log 경로량의 상대 순위, '
             'joint = activity × 중심점 이동의 상대 순위다. raw_lin은 원 lin_raw의 음수이며 같은 공통 후보에서만 비교했다.', '',
             '## 고정한 네 비교', '',
             '|비교|사건 수/선박 수|top-1 차이 %p|선박 bootstrap 98.75% 구간 %p|판정|',
             '|---|---:|---:|---|---|']
    for c in summary['primary_contrasts']:
        text.append(f'|{c["rule_a"]} − {c["rule_b"]}|{c["n_events"]}/{c["n_clusters"]}|{num(c["mean_difference"])}|'
                    f'[{num(c["ci_low"])}, {num(c["ci_high"])}]|{c["decision"]}|')
    text += ['', '네 비교의 다중성을 반영한 명목 구간이다(B=4000, seed=11052026). '
             '최소30사건과 구간 하한>0을 함께 요구했다. 동일 dev을 여러 라운드에서 사용한 선택 편향은 이 구간으로 보정되지 않는다.', '',
             '## 시간과 위치를 맞추면서 잃은 관측', '',
             '|집합|사건 수|±6h 원관측 없음|품질충족 창 없음|T 없음|L 없음|TL 없음|공통 후보 없음|',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, d in diagnostics.items():
        text.append('|' + '|'.join(str(v) for v in [name, d['total_events'], d['observed_near_zero'], d['quality_near_zero'],
                    d['T_near_zero'], d['L_near_zero'], d['TL_near_zero'], d['common_near_zero']]) + '|')
    text += ['', '이 표는 전체 사건을 분모로 한 사고 근처 가용성이다. 선박 전체의 100시각 요건과는 다르다. '
             '세부 제외 사유는 coverage_diagnostics.json, 시각별 실제 관측·유효행·중심점쌍·참조시각은 timestamp_scores.csv에 남겼다. '
             'TL은 재방문 이력이 부족한 새 장소를 unknown으로 만들 수 있으므로 이 실험의 미개선이 위치 정보의 무용성이나 표류 부재를 뜻하지 않는다.', '',
             '## 전체100 사건 보조 결과', '',
             '|점수|평가가능|조건부 top-1|전체100 분모 top-1|', '|---|---:|---:|---:|']
    for rule, r in summary['profiles']['all100']['rules'].items():
        text.append(f'|{rule}|{r["n_evaluable"]}|{pct(r["top1_conditional"])}|{pct(r["top1_unconditional"])}|')
    memory = json.loads((HERE / 'memory.json').read_text(encoding='utf-8'))
    text += ['', '## 표류 정의에 대한 판단', '',
        '이번 실험은 표류의 물리적 정답을 새로 만들지 않았다. 수색 계획의 표류는 물·바람 등 환경 외력에 따른 이동으로 설명된다'
        '([Canadian Coast Guard, 11.9.2](https://waves-vagues.dfo-mpo.gc.ca/Library/253768.pdf)). '
        '현재 항적에서 관찰한 상대 변화만으로 조종 의도·추진 상태를 식별할 수 없으므로 실제 표류·기관고장·정상 조업·예인 가능성을 구분해 둔다.', '',
        '이번 평가는 여러 사고유형을 포함한 사건집합에 대한 평가이며, 표류 사고만 골라 붙인 정답으로 평가한 것이 아니다. '
        '표본에서 두 방식 모두 적중0이면 차이 bootstrap 구간이[0,0]으로 나올 수 있지만 모집단 효과가 정확히0이라는 증명은 아니다.', '',
        '특히 joint가 양수라고 실제 이동이 계속됐다고 판정할 수 없다. 현재와 참조의 중심점 이동이 모두0이어도 중간순위는0.5여서 곱이 양수가 될 수 있다. '
        '이번 점수는 상대 저활동×중심점 이동 순위라는 가설을 그대로 시험했으며 결과를 본 뒤 양수 이동 조건을 추가하지 않았다. '
        'lin_raw 역시 시작·끝 순변위비가 아니라 시간행별 bbox_m/len_m 평균이다.', '',
        '기존 q10 저활동·고빈도 체류구역 밖·2시간 지속의 AND 규칙은 표류 정답으로 사용하지 않는다. '
        '이 실험의 비교 반경10km와 과거30일도 검증된 물리 경계가 아니며 다른 조건에 대한 결론은 별도 실험이 필요하다.', '',
        '시간대 조건은 조석 위상을 맞춘 것이 아니며 위치 조건은 창 마지막 시간행 중심점 한 점으로 대표했다. '
        '창 안의 넓은 공간 이동·바람·조류 차이는 여전히 남을 수 있다. 특징은 과거 이력만으로 계산했지만 '
        '전체 관측기간에서 top-1을 고르는 평가는 사후 국소화 평가다. 온라인 경보 임계값·오경보율·사전경보 시간을 검증한 것으로 해석하지 않는다.', '',
        '## 실행과 검증', '',
        f'실행 종료코드 {execution["exit_code"]}, 경과 {execution["elapsed_seconds"]:.1f}초. '
        f'입력 {summary["input_profile"]["scanned_rows"]:,}행을 청크 스캔하고 대상 {summary["input_profile"]["retained_rows"]:,}행을 선박별 순차 계산했다. '
        f'시각행 {summary["timestamp_score_rows"]:,}개, 사건·규칙 행 {summary["event_metric_rows"]:,}개를 저장했다.', '',
        f'계약 SHA256: `{summary["protocol_sha256"]}`. 실행 전 초기1.5GiB 계획은 메모리 여유가 부족해 보류했고 '
        '8192행 청크·512MiB 예상 peak로 줄였다. 단계별 RAM 확인은 memory.json에 기록했다. '
        f'확인된 최소 가용량은 {min(r["available_bytes"] for r in memory)/2**20:.1f}MiB다. '
        '단계별 RSS 표본은 peak 실측이나 고빈도 메모리 추적이 아니며 예상 peak와 구분한다.', '',
        '별도 검토자의 검증 범위와 수치 대조는 [AUDIT.md](AUDIT.md), audit.json을 따른다. '
        '합성 테스트는 시간 경계·결측·동률·참조 선택 검증이며 실제 데이터 평가는 별도 실행이다. 하드웨어 실험은 없다.', '',
        '## 이번 결정과 학습 질문', '',
        'lin_raw의 특징 후보 채택은 유지한다. 위 국소화 결과가 실제 표류 정답이나 단독 탐지기 성능을 확증한 것으로 바꾸어 읽지 않는다. '
        '이번 계약 수치를 사후 변경하지 않고 결과와 가용성 제한을 다음 설계의 근거로 남긴다.', '',
        '설명할 질문은 세 가지다. 같은 값도 위치·시간 조건에 따라 왜 다른 의미가 되는가? '
        '공통집합의 적중률과 전체 사건 분모의 적중률은 왜 다른가? '
        '정상 조업과 외력에 따른 이동을 구분하려면 현재 항적 외에 어떤 관측이 필요한가?', '',
        '재현: 이 폴더에서 `python -X utf8 test_experiment.py`, '
        '`python -X utf8 run_experiment.py --output-dir <새 출력 폴더>`, '
        '`python -X utf8 audit_round011.py --help`를 따른다. 실제 재실행 전 가용 RAM을 다시 확인한다.', '',
        '핵심 파일: PROTOCOL.md, run_experiment.py, test_experiment.py, summary.json, event_metrics.csv, '
        'timestamp_scores.csv, execution.json, memory.json, AUDIT.md, audit.json. 과거 라운드의 수치·보고서는 보존했다.',
    ]
    (HERE / 'ROUND011_실험결과보고_20261105.md').write_text('\n'.join(text) + '\n', encoding='utf-8')
    print(conclusion)


if __name__ == '__main__':
    main()
