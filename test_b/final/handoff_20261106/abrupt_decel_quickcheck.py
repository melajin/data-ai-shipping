import pyarrow.parquet as pq
import pandas as pd, numpy as np

can = pq.read_table('round_004_20261105/execution_001/candidate_ledger.parquet',
                     columns=['rfid_id','ts','cen_lon','cen_lat','geometry_valid']).to_pandas()
can = can[can.geometry_valid].sort_values(['rfid_id','ts']).reset_index(drop=True)

pos = pd.read_csv('../과거/round_008_linkage_audit_20261105/devset_positives.csv', dtype={'rfid_id':str})
pos = pos[['acc_id','rfid_id','tier','conflict','acc_ts']]

def haversine_km(lon1, lat1, lon2, lat2):
    R = 6371.0
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1; dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2*R*np.arcsin(np.sqrt(a))

rows = []
for rfid, g in can.groupby('rfid_id', sort=False):
    g = g.reset_index(drop=True)
    if len(g) < 5:
        continue
    dt = g.ts.diff()
    dist = haversine_km(g.cen_lon.shift(), g.cen_lat.shift(), g.cen_lon, g.cen_lat)
    speed = dist / dt.replace(0, np.nan)
    g = g.assign(dt_h=dt, speed_kmh=speed)
    # rolling baseline speed (own history, backward-looking median over up to 48 prior obs)
    baseline = g.speed_kmh.rolling(48, min_periods=8).median().shift(1)
    drop = baseline - g.speed_kmh  # large positive = sudden deceleration from own normal pace
    g = g.assign(baseline_speed=baseline, decel=drop)
    rows.append(g)

full = pd.concat(rows, ignore_index=True)
full = full.dropna(subset=['decel'])

pred = (full.sort_values('decel', ascending=False)
            .groupby('rfid_id', as_index=False).first()[['rfid_id','ts','decel','speed_kmh','baseline_speed']])

ev = pos.merge(pred, on='rfid_id', how='left')
ev['abs_error_h'] = (ev.ts - ev.acc_ts).abs()
ev['hit6h'] = ev.abs_error_h <= 6

print('matched events with a prediction:', ev.ts.notna().sum(), '/', len(ev))
print('median abs error (h):', ev.abs_error_h.median())
print('mean abs error (h):', ev.abs_error_h.mean())
print('hit <=6h:', int(ev.hit6h.sum()), '/', len(ev))
print()
print('Tier01 only:')
t01 = ev[ev.tier <= 1]
print('n=', len(t01), 'median err', t01.abs_error_h.median(), 'hit6h', int(t01.hit6h.sum()))

# permutation null for this feature, same scheme as before
rng = np.random.default_rng(20261106)
evv = ev.dropna(subset=['ts'])
acc = evv.acc_ts.values.astype(float); prd = evv.ts.values.astype(float)
obs = np.median(np.abs(acc - prd))
nulls = np.array([np.median(np.abs(acc - rng.permutation(prd))) for _ in range(2000)])
print()
print('obs median:', obs, 'null median:', np.median(nulls), 'p:', (nulls <= obs).mean())

ev.to_csv('handoff_20261106/abrupt_decel_quickcheck.csv', index=False)
