from pathlib import Path
import glob, json
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[2]
ledger = root / 'final/round_004_20261105/execution_001/candidate_ledger.parquet'
labels = Path(glob.glob(str(root / '*/round_008_linkage_audit_20261105/devset_positives.csv'))[0])
out = Path(__file__).resolve().parent
cols = ['rfid_id', 'ts', 'source_ordinal', 'score', 'stage0_ok']
d = pd.read_parquet(ledger, columns=cols)
d = d[d.stage0_ok & np.isfinite(d.score)].copy()
d['rfid_id'] = d.rfid_id.astype(str)
assert not d.duplicated(['rfid_id', 'ts']).any()
# Fixed exploratory rule, chosen before inspecting outcomes: vessel-specific top 10%;
# reject if >=20% of at least 5 observed OTHER vessels also exceed their 90th percentile.
d['q90'] = d.groupby('rfid_id').score.transform(lambda x: x.quantile(.9))
d['high'] = d.score > d.q90
g = d.groupby('ts').high
n = g.transform('size') - 1
high = g.transform('sum') - d.high.astype(int)
d['peer_n'] = n
d['peer_high'] = high
d['rejected'] = (n >= 5) & (high / n.where(n > 0) >= .2)
labels_df = pd.read_csv(labels, dtype={'rfid_id': str}, encoding='utf-8-sig')
assert labels_df.acc_id.is_unique
ranked = d.sort_values(['rfid_id', 'score', 'ts', 'source_ordinal'], ascending=[True, False, True, True], kind='stable')
rng = np.random.default_rng(20261106)
results = []
for name, rows in [('score', ranked), ('score + peer filter', ranked[~ranked.rejected])]:
    top = rows.drop_duplicates('rfid_id').set_index('rfid_id').ts
    e = labels_df[['acc_id','rfid_id','acc_ts']].copy()
    e['pred'] = e.rfid_id.map(top)
    valid = e.dropna(subset=['pred'])
    acc = valid.acc_ts.to_numpy(dtype=float)
    pred = valid.pred.to_numpy(dtype=float)
    err = abs(acc-pred)
    obs = float(np.median(err))
    null = np.array([np.median(np.abs(acc-rng.permutation(pred))) for _ in range(2000)])
    results.append(dict(feature=name, events=int(len(e)), evaluated=int(len(valid)), missing=int(e.pred.isna().sum()), median_error_h=obs, hits_6h=int((err<=6).sum()), permutation_p=float((null<=obs).mean()), null_median_h=float(np.median(null))))
summary = {'rule': 'score > vessel q90 marks high; reject when >=20% of >=5 observed other vessels are high at exact integer hour', 'quantile':.9,'peer_fraction_threshold':.2,'minimum_peers':5,'missing_peer_policy':'retain','rows':int(len(d)),'vessels':int(d.rfid_id.nunique()),'excluded_rows':int(d.rejected.sum()),'excluded_fraction':float(d.rejected.mean()),'hours_with_exclusion':int(d.loc[d.rejected,'ts'].nunique()),'events':results,'seed':20261106,'permutations':2000,'null':'shuffle event-level selected times against accident times, median absolute error, <= observed; shared RNG in row order','labels':str(labels.relative_to(root))}
(out/'results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))

