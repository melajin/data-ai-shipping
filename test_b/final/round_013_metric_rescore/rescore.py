"""Rescore saved top1 results only; run with Python from any directory."""
from pathlib import Path
import ast, hashlib, json, sys
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
import pandas as pd
import scipy
from scipy.stats import wilcoxon

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
rows, audit = [], []
for r in range(1, 12):
    files = sorted(ROOT.glob(f'round_{r:03d}_*/execution_*/event_results.csv'))
    if not files:
        rows.append(dict(round=r, execution='—', method='저장 CSV 없음', median=None, p=None))
    for f in files:
        d = pd.read_csv(f, encoding='utf-8-sig').query('k == 1').copy()
        assert not d.duplicated(['method', 'acc_id']).any()
        col = 'abs_error_hours' if 'abs_error_hours' in d else 'abs_error'
        d['err'] = pd.to_numeric(d[col], errors='raise')
        d['pred'] = d.predicted_times.map(lambda s: ast.literal_eval(s))
        d['valid'] = d.pred.map(bool) & np.isfinite(d.err)
        valid = d[d.valid]
        assert (valid.err >= 0).all()
        assert np.allclose(valid.err, [abs(float(a)-float(p[0])) for a,p in zip(valid.acc_ts,valid.pred)])
        base = 'B0' if 'B0' in set(d.method) else 'B0_full'
        b = valid[valid.method == base].set_index('acc_id')
        for m, g in d.groupby('method', sort=True):
            v = g[g.valid].set_index('acc_id').sort_index()
            ids = b.index.intersection(v.index).sort_values()
            assert np.array_equal(b.loc[ids,'acc_ts'], v.loc[ids,'acc_ts'])
            delta = v.loc[ids,'err'].to_numpy() - b.loc[ids,'err'].to_numpy()
            p = None if m == base or not len(ids) else (float(wilcoxon(delta, alternative='two-sided', zero_method='wilcox', method='auto').pvalue) if np.any(delta != 0) else 1.0)
            row = dict(round=r, execution=f.parent.name, method=m, median=float(v.err.median()) if len(v) else None, p=p,
                       n=len(g), valid_n=len(v), paired_n=len(ids), baseline=base,
                       invalid=(r == 2 and f.parent.name == 'execution_001' and m in ('C', 'U')))
            rows.append(row)
            # Diagnostic shuffle of EXISTING timestamps; never write predictions or labels.
            rng = np.random.default_rng(20261106)
            acc = v.acc_ts.to_numpy(float)
            pred = np.array([float(p[0]) for p in v.pred])
            null = np.array([np.median(np.abs(acc-rng.permutation(pred))) for _ in range(2000)]) if len(v) else np.array([])
            audit.append(dict(**row, source=str(f.relative_to(ROOT)), sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                              null_median=float(np.median(null)) if len(null) else None,
                              permutation_p=float((1+np.sum(null <= row['median']))/2001) if len(null) else None))

tests = sorted([x for x in rows if x['p'] is not None and not x.get('invalid')], key=lambda x:x['p'])
running = 0.0
for i, row in enumerate(tests):
    running = max(running, min(1.0, (len(tests)-i)*row['p']))
    row['holm_p'] = running
    row['survives'] = running <= .05

lines = [
    '내부 선택 지표: k=1의 저장 abs_error 중앙값(h), 작을수록 좋음. 공식 F1 점수가 아니다.',
    f'B0 대비 양측 paired Wilcoxon, zero_method=wilcox, method=auto; 전체 {len(tests)}개 비교에 Holm step-down, α=0.05.',
    'R2 기준은 B0_full이며 B0_common도 비교 대상이다. 실행본을 합치거나 유리한 실행을 선택하지 않았다. 중복 실행도 보수적으로 별도 비교에 포함했다.',
    '중앙값은 유효 예측 행 기준, 검정은 같은 acc_id의 양쪽 유효 예측만 사용한다. 결측은 0으로 대체하지 않았다. R2 B0_common은 98/100행으로 다른 방법의 100행 중앙값과 직접 순위 비교에 주의한다.',
    '', '| 회차/실행 | 방법 | 오차중앙값(h) | B0대비 Wilcoxon p | Holm보정 후 생존여부 |',
    '|---|---|---:|---:|---|'
]
for row in rows:
    median = '—' if row['median'] is None else f"{row['median']:.1f}"
    p = '—' if row['p'] is None else f"{row['p']:.6g}"
    status = ('예' if row['survives'] else '아니오') + f" (p_adj={row['holm_p']:.6g})" if 'holm_p' in row else ('기준선' if row.get('baseline') == row['method'] else '산출 불가')
    if row.get('invalid'):
        status = '제외: 기존 실행 무효(C/U 정렬 오류)'
    lines.append(f"| R{row['round']}/{row['execution']} | {row['method']} | {median} | {p} | {status} |")
lines += ['', 'R1·R3·R7·R10은 저장 event_results.csv가 없어 산출 불가. R8 synthetic_execution은 합성 검증이므로 제외했다.',
          'R2 execution_001 C/U는 같은 폴더 INVALID_COMPARISON.md에서 무효로 판정된 실행이다. 오차·p는 기록 검산용이며 Holm 및 가설 판단에서 제외했다. 생존은 양측 차이의 유의성을 뜻하며 새 방법의 유효성 또는 공식 성능을 입증하지 않는다.',
          '검증: 저장 오차와 저장 top1 시각의 차이 일치, 사건 키 중복 없음, 짝의 사고시각 일치 확인. /3600 변환 없음.',
          '1차 remeasure.py는 R2의 B0 별칭을 건너뛰고 결측·중복을 명시하지 않으며 Holm이 없다. null.py는 execution_001만 다루고 Monte Carlo p에 +1 보정이 없다. 여기서는 모든 실행을 검사하고 (b+1)/(2000+1)을 사용했다.',
          '순열검정은 사건 간 저장 예측시각의 교환가능성을 가정한 진단이며 B0 대비 개선 검정이 아니다. 후보 가용성·선박별 시간분포를 보존하지 않으므로 공식 성능 근거로 사용하지 않는다. 진단 수치는 audit.json에 기록했다.',
          '재현: python testB/final/round_013_metric_rescore/rescore.py']
(OUT/'RESCORE.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
(OUT/'audit.json').write_text(json.dumps(dict(scipy=scipy.__version__, numpy=np.__version__, holm_family_size=len(tests), rows=rows, permutation_diagnostics=audit), ensure_ascii=False, indent=2), encoding='utf-8')
print('\n'.join(lines))
