"""Single retrospective feature check; no model inference or submission writes."""
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
FINAL = OUT.parent
# RAM checked 2026-11-06 06:12 KST: 3.6 GiB available; existing Python 88 MiB.
# Estimated peak <0.3 GiB: 99,677 rows, six projected columns, sequential groups.
can = pq.read_table(FINAL / 'round_004_20261105/execution_001/candidate_ledger.parquet',
    columns=['rfid_id', 'ts', 'source_ordinal', 'bbox_m', 'geometry_valid']).to_pandas()
can = can.sort_values(['rfid_id', 'ts', 'source_ordinal'])
assert not can.duplicated(['rfid_id', 'ts']).any(), 'Ambiguous hourly rows'
can = can[can.geometry_valid & np.isfinite(can.bbox_m) & (can.bbox_m >= 0)]
selected = []
for rfid, g in can.groupby('rfid_id', sort=False):
    g = g.copy()
    # Actual elapsed hours, not a six-row window; current hour excluded.
    s = pd.Series(g.bbox_m.to_numpy(), index=pd.to_timedelta(g.ts.to_numpy(), unit='h'))
    baseline = s.rolling('6h', closed='left', min_periods=3).median().to_numpy()
    # 1 m offset keeps zero-size boxes finite. Symmetric expansion/contraction.
    g['baseline_bbox_m'] = baseline
    g['feature'] = np.abs(np.log((g.bbox_m.to_numpy() + 1) / (baseline + 1)))
    g = g.dropna(subset=['feature'])
    if len(g):
        # Fixed top1 rule; earliest timestamp wins ties; no labels consulted.
        selected.append(g.sort_values(['feature', 'ts'], ascending=[False, True]).iloc[0])
pred = pd.DataFrame(selected)[['rfid_id', 'ts', 'bbox_m', 'baseline_bbox_m', 'feature']]
pos = pd.read_csv(FINAL.parent / '과거/round_008_linkage_audit_20261105/devset_positives.csv', dtype={'rfid_id': str})
ev = pos[['acc_id', 'rfid_id', 'tier', 'conflict', 'acc_ts']].merge(pred, on='rfid_id', how='left', validate='many_to_one')
assert len(ev) == 100
# Insufficient recent observations: retain event as a miss and infinite error.
ev['abs_error_h'] = (ev.ts - ev.acc_ts).abs().fillna(np.inf)
ev['hit6h'] = ev.abs_error_h <= 6
acc, prd = ev.acc_ts.to_numpy(float), ev.ts.to_numpy(float)
obs = ev.abs_error_h.median()
rng = np.random.default_rng(20261106)
# Same event-wise shuffle null as rejected check; lower median is better.
valid = np.isfinite(prd)
nulls = np.array([np.median(np.r_[np.abs(acc[valid] - rng.permutation(prd[valid])),
    np.full((~valid).sum(), np.inf)]) for _ in range(2000)])
p = (np.count_nonzero(nulls <= obs) + 1) / (len(nulls) + 1)
ev.to_csv(OUT / 'event_results.csv', index=False)
pd.DataFrame({'permutation_median_error_h': nulls}).to_csv(OUT / 'permutation_null.csv', index=False)
cause = '시간당 박스 크기의 급변이 사고보다 정상 조업·이동 전환에도 반응해 사고시각을 분리하지 못한 것으로 추정된다.'
line = f'6시간 bbox_m 로그비 급변량 / {obs:,.1f}h / {int(ev.hit6h.sum())}/100 / {p:.4f} / {cause}'
(OUT / 'result.txt').write_text(line + '\n', encoding='utf-8')
print(line)
