from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ledger = ROOT / 'testB/final/round_004_20261105/execution_001/candidate_ledger.parquet'
truth = ROOT / 'testB/과거/round_008_linkage_audit_20261105/devset_positives.csv'
pos = pd.read_csv(truth, encoding='utf-8-sig', dtype={'rfid_id': str}, usecols=['acc_id', 'rfid_id', 'acc_ts'])
d = pq.read_table(ledger, columns=['rfid_id','ts','cen_lon','cen_lat','geometry_valid']).to_pandas()
d = d.sort_values(['rfid_id','ts'], kind='stable').reset_index(drop=True)
g = d.groupby('rfid_id', sort=False)
dt = g.ts.diff()
lon1 = np.radians(g.cen_lon.shift()); lat1 = np.radians(g.cen_lat.shift())
lon2 = np.radians(d.cen_lon); lat2 = np.radians(d.cen_lat)
dl = lon2-lon1
y = np.sin(dl)*np.cos(lat2)
x = np.cos(lat1)*np.sin(lat2)-np.sin(lat1)*np.cos(lat2)*np.cos(dl)
a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dl/2)**2
km = 12742*np.arcsin(np.sqrt(np.clip(a, 0, 1)))
valid = (dt == 1) & d.geometry_valid.fillna(False) & g.geometry_valid.shift().fillna(False) & np.isfinite(km) & (km >= 0.01)
d['speed'] = km.where(valid)
d['s'] = (y / np.hypot(x,y)).where(valid)
d['c'] = (x / np.hypot(x,y)).where(valid)
# A missing hour, invalid geometry or indeterminate heading breaks the series.
for col in ['s','c','speed']:
    d[f'cur_{col}'] = d[col].rolling(6, min_periods=6).mean()
    d[f'base_{col}'] = d[col].shift(6).rolling(12, min_periods=12).mean()
d['cur_var'] = 1 - np.hypot(d.cur_s, d.cur_c)
d['base_var'] = 1 - np.hypot(d.base_s, d.base_c)
# Low speed is relative to the vessel's immediately preceding 12-hour history.
ratio = d.cur_speed / d.base_speed
d['score'] = ((d.cur_var - d.base_var) / (1 + ratio)).where(ratio <= 1)
# An event receives its vessel's highest scoring eligible candidate; no candidate is persisted.
eligible = d.dropna(subset=['score']).sort_values(['rfid_id','score','ts'], ascending=[True,False,True], kind='stable')
selected = eligible.drop_duplicates('rfid_id')[['rfid_id','ts']]
ev = pos.merge(selected, on='rfid_id', how='left')
ev = ev.dropna(subset=['ts'])
acc = ev.acc_ts.to_numpy(dtype=float); pred = ev.ts.to_numpy(dtype=float)
error = np.abs(acc-pred); obs = np.median(error)
rng = np.random.default_rng(20261106)
nulls = np.array([np.median(np.abs(acc-rng.permutation(pred))) for _ in range(2000)])
text = (f'피처명: 저속 조건 방향 분산 증가 (최근 6h vs 이전 12h)\n'
        f'오차중앙값(h): {obs:.1f}\n±6h 적중 수: {(error <= 6).sum()}/{len(pos)} (후보 존재 {len(ev)}/{len(pos)})\n'
        f'순열검정 p: {(nulls <= obs).mean():.4f}\n'
        f'순열 중앙값(h): {np.median(nulls):.1f}\n'
        f'후보 선박: {selected.rfid_id.nunique()}/{pos.rfid_id.nunique()}\n')
print(text)
(OUT / 'metrics.txt').write_text(text, encoding='utf-8')


