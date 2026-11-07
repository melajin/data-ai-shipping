import pandas as pd, glob, os, numpy as np
from scipy import stats
def load(f):
    d = pd.read_csv(f, encoding='utf-8-sig'); d = d[d.k == 1].copy()
    d['err_h'] = d.abs_error_hours.astype(float) if 'abs_error_hours' in d else d.abs_error.astype(float)
    return d
def tag(f):
    p = f.replace(os.sep, '/').split('/')
    return p[0][6:9] + '/e' + p[1][-1]
fs = sorted(glob.glob('round_0*/execution_00*/event_results.csv'))
print('%-10s %-4s %4s %9s %9s' % ('round', 'meth', 'n', 'median_h', 'mean_h'))
for f in fs:
    for m, g in load(f).groupby('method'):
        print('%-10s %-4s %4d %9.1f %9.1f' % (tag(f), m, len(g), g.err_h.median(), g.err_h.mean()))
print('\n--- paired vs B0 (same events, k=1) ---')
for f in fs:
    d = load(f)
    if 'B0' not in set(d.method): continue
    b = d[d.method == 'B0'].groupby('acc_id').err_h.first()
    for m in sorted(set(d.method) - {'B0'}):
        v = d[d.method == m].groupby('acc_id').err_h.first()
        i = b.index.intersection(v.index); x, y = b[i], v[i]; diff = y - x
        nz = diff[diff != 0]
        p = stats.wilcoxon(x, y).pvalue if len(nz) > 0 else 1.0
        print('%-10s %-4s n=%3d changed=%3d median(var-B0)=%+7.1fh p=%.3f' % (tag(f), m, len(i), len(nz), diff.median(), p))
