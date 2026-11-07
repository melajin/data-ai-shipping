from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
ledger = ROOT / 'round_004_20261105/execution_001/candidate_ledger.parquet'
labels = next(ROOT.parent.glob('*/round_008_linkage_audit_20261105/devset_positives.csv'))
cols = ['rfid_id', 'ts', 'cen_lon', 'cen_lat', 'previous_gap_reason', 'next_gap_reason']
d = pq.read_table(ledger, columns=cols).to_pandas().sort_values(['rfid_id', 'ts']).reset_index(drop=True)
pos = pd.read_csv(labels, dtype={'rfid_id': str}, usecols=['acc_id', 'rfid_id', 'acc_ts'])

g = d.groupby('rfid_id', sort=False)
prev_ts = g.ts.shift()
dt = d.ts - prev_ts
plon = g.cen_lon.shift()
plat = g.cen_lat.shift()
lon1, lat1, lon2, lat2 = (np.radians(x) for x in (plon, plat, d.cen_lon, d.cen_lat))
a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
distance = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
valid_coords = (d.cen_lon.between(-180, 180) & d.cen_lat.between(-90, 90)
                & plon.between(-180, 180) & plat.between(-90, 90))
previous_next_reason = g.next_gap_reason.shift()
normal = (dt.eq(1) & valid_coords & d.previous_gap_reason.eq('ok') & previous_next_reason.eq('ok'))
speed = (distance / dt).where(normal)
# Last 48 normal one-hour transitions preceding the gap, not last 48 hours.
# Compute only observed normal transitions, then carry the median forward.
baseline = pd.Series(np.nan, index=d.index, dtype=float)
baseline.loc[normal] = speed.loc[normal].groupby(d.loc[normal, 'rfid_id'], sort=False).transform(
    lambda s: s.rolling(48, min_periods=8).median())
baseline = baseline.groupby(d.rfid_id, sort=False).ffill().groupby(d.rfid_id, sort=False).shift(1)
gap = (dt.gt(1) & valid_coords & d.previous_gap_reason.eq('missing_observation')
       & previous_next_reason.eq('missing_observation'))
eligible = gap & baseline.ge(0.1) & np.isfinite(distance)
ratio = distance / (dt * baseline)
score = np.abs(np.log(ratio.clip(lower=0.01)))
c = pd.DataFrame({'rfid_id': d.rfid_id, 'ts': d.ts, 'score': score})[eligible]
c = c.sort_values(['rfid_id', 'score', 'ts'], ascending=[True, False, True])
best = c.drop_duplicates('rfid_id')
ev = pos.merge(best, on='rfid_id', how='left', validate='many_to_one')
valid = ev.dropna(subset=['ts'])
acc = valid.acc_ts.to_numpy(float)
selected = valid.ts.to_numpy(float)
errors = np.abs(acc - selected)
rng = np.random.default_rng(20261106)
null = np.array([np.median(np.abs(acc - rng.permutation(selected))) for _ in range(2000)])
summary = {'feature': 'gap_jump_speed_ratio_abs_log', 'n_events_total': len(ev),
           'n_events_scored': len(valid), 'n_gap_pairs': int(gap.sum()),
           'n_eligible_gap_pairs': len(c), 'n_scored_vessels': int(c.rfid_id.nunique()),
           'median_abs_error_hours': float(np.median(errors)) if len(errors) else None,
           'hit_within_6h': int((errors <= 6).sum()), 'permutation_p': float((null <= np.median(errors)).mean()),
           'null_median_hours': float(np.median(null)), 'permutations': 2000, 'seed': 20261106}
print(json.dumps(summary, ensure_ascii=False, indent=2))
(OUT / 'metrics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
ev['abs_error_h'] = (ev.ts - ev.acc_ts).abs()
ev['hit6h'] = ev.abs_error_h.le(6) & ev.ts.notna()
ev[['acc_id', 'abs_error_h', 'hit6h']].to_csv(OUT / 'event_errors.csv', index=False, encoding='utf-8-sig')
