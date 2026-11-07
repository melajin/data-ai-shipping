import pandas as pd, glob, os, numpy as np, ast
rng = np.random.default_rng(20261106)
def first(s):
    try:
        v = ast.literal_eval(str(s))
        return float(v[0]) if isinstance(v, list) and v else np.nan
    except Exception:
        return np.nan
print('%-6s %-10s %5s %5s %9s %9s %7s %6s' % ('round','meth','n','pred','obs_med','null_med','p_med','hit6h'))
for f in sorted(glob.glob('round_0*/execution_001/event_results.csv')):
    r = f.replace(os.sep,'/').split('/')[0][6:9]
    d = pd.read_csv(f, encoding='utf-8-sig'); d = d[d.k == 1].copy()
    d['pred'] = d.predicted_times.map(first)
    for m, g0 in d.groupby('method'):
        g = g0.dropna(subset=['pred'])
        acc = g.acc_ts.values.astype(float); pr = g.pred.values.astype(float)
        if len(g) < 5: 
            print('%-6s %-10s %5d %5d  (too few)' % (r, m, len(g0), len(g))); continue
        err = np.abs(acc - pr); obs = np.median(err)
        nulls = np.array([np.median(np.abs(acc - rng.permutation(pr))) for _ in range(2000)])
        print('%-6s %-10s %5d %5d %9.0f %9.0f %7.3f %6d' % (
            r, m, len(g0), len(g), obs, np.median(nulls), (nulls <= obs).mean(), int((err <= 6).sum())))
