from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# 2026-11-06 06:29 KST: 2,782,432 KiB available; largest other processes
# checked via Get-Process. Estimated peak <512 MiB for 99,677 rows, selected
# columns, one sequential process and a 2,000-element permutation array.
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ledger = ROOT / 'testB/final/round_004_20261105/execution_001/candidate_ledger.parquet'
positive_files = list((ROOT / 'testB').glob('*/round_008_linkage_audit_20261105/devset_positives.csv'))
assert len(positive_files) == 1
cols = ['rfid_id', 'ts', 'cen_lon', 'cen_lat', 'previous_gap_reason', 'next_gap_reason']
d = pq.read_table(ledger, columns=cols).to_pandas().sort_values(['rfid_id', 'ts'], kind='stable')
assert not d.duplicated(['rfid_id', 'ts']).any()
g = d.groupby('rfid_id', sort=False)
for c in ['ts', 'cen_lon', 'cen_lat', 'next_gap_reason']:
    d['prior_' + c] = g[c].shift()
d['gap_interval_h'] = d.ts - d.prior_ts
# Missing endpoints are never bridged. A gap must have observations on both sides.
gap = d[(d.previous_gap_reason == 'missing_observation') &
        (d.prior_next_gap_reason == 'missing_observation') &
        (d.gap_interval_h > 1)].copy()
lat1, lat2 = np.radians(gap.prior_cen_lat), np.radians(gap.cen_lat)
dlon = np.radians(gap.cen_lon - gap.prior_cen_lon)
dlat = lat2 - lat1
a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
valid = (gap.prior_cen_lat.abs() <= 90) & (gap.cen_lat.abs() <= 90) & (gap.prior_cen_lon.abs() <= 180) & (gap.cen_lon.abs() <= 180)
gap['endpoint_center_distance_km'] = np.where(valid, 12742 * np.arcsin(np.sqrt(np.clip(a, 0, 1))), np.nan)
gap[['rfid_id', 'prior_ts', 'ts', 'gap_interval_h', 'endpoint_center_distance_km']].to_parquet(OUT / 'gap_features.parquet', index=False)

# One deterministic feature: longest gap per vessel; earliest resumption breaks ties.
# Distance is retained as a feature, not used to resolve ties or tuned on labels.
chosen = (gap.sort_values(['rfid_id', 'gap_interval_h', 'ts'], ascending=[True, False, True], kind='stable')
          .drop_duplicates('rfid_id'))[['rfid_id', 'ts']]
pos = pd.read_csv(positive_files[0], dtype={'rfid_id': str})
ev = pos.merge(chosen, on='rfid_id', how='left', validate='many_to_one')
ev = ev.dropna(subset=['ts', 'acc_ts'])
acc, pred = ev.acc_ts.to_numpy(float), ev.ts.to_numpy(float)
assert len(acc) >= 5
err = np.abs(acc - pred)
obs = np.median(err)
rng = np.random.default_rng(20261106)
nulls = np.array([np.median(np.abs(acc - rng.permutation(pred))) for _ in range(2000)])
line = (f'최장 관측 공백 재개 시각 / {obs:g}h / {int((err <= 6).sum())}/{len(acc)} '
        f'/ {(nulls <= obs).mean():.3f} / 관측 공백은 통신 장애뿐 아니라 자료 누락과 '
        '수집 조건에서도 생길 수 있어 사고와의 연결이 불확실하다.')
(OUT / 'result.txt').write_text(line + '\n', encoding='utf-8')
print(line)
print(f'positive_rows={len(pos)} candidate_gaps={len(gap)} matched={len(ev)} missing_distance={gap.endpoint_center_distance_km.isna().sum()}')
