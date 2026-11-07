"""Retrospective reranking of existing candidates; no inference or new labels."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
FINAL = OUT.parent
ledger = pq.read_table(FINAL / 'round_004_20261105/execution_001/candidate_ledger.parquet',
    columns=['rfid_id', 'ts', 'source_ordinal', 'score', 'stage0_ok']).to_pandas()
assert not ledger.duplicated(['rfid_id', 'ts']).any()
ledger = ledger[ledger.stage0_ok & np.isfinite(ledger.score)].copy()
assert (ledger.score >= 0).all()
# Hour modulo 24 is enough for within-vessel rarity; no timezone is assumed.
# Count observed candidate hours, excluding the entire candidate day. This is an
# activity-observation proxy, not a verified fishing schedule. Full-period
# retrospective reference includes future days and may reflect reporting gaps.
ledger['day'] = ledger.ts // 24
ledger['hour'] = ledger.ts % 24
ledger['weight'] = 1.0
for _, indices in ledger.groupby('rfid_id', sort=False).groups.items():
    g = ledger.loc[indices]
    total = np.bincount(g.hour.to_numpy(), minlength=24)
    for _, day_idx in g.groupby('day', sort=False).groups.items():
        hours = ledger.loc[day_idx, 'hour'].to_numpy()
        reference = total - np.bincount(hours, minlength=24)
        if reference.max() > 0:
            ledger.loc[day_idx, 'weight'] = 2 - reference[hours] / reference.max()
ledger['weighted_score'] = ledger.score * ledger.weight
assert ledger.weight.between(1, 2).all()

pos_path = next(FINAL.parent.glob('*/round_008_linkage_audit_20261105/devset_positives.csv'))
pos = pd.read_csv(pos_path, dtype={'rfid_id': str})
assert len(pos) == 100 and pos.acc_id.is_unique
ev = pos[['acc_id', 'rfid_id', 'tier', 'conflict', 'acc_ts']].copy()
for name, field in [('before', 'score'), ('after', 'weighted_score')]:
    top = (ledger.sort_values(['rfid_id', field, 'ts', 'source_ordinal'],
             ascending=[True, False, True, True]).drop_duplicates('rfid_id'))
    top = top[['rfid_id', 'ts', 'score', 'weight', 'weighted_score']].rename(
        columns={c: f'{name}_{c}' for c in ['ts', 'score', 'weight', 'weighted_score']})
    ev = ev.merge(top, on='rfid_id', how='left', validate='many_to_one')
    ev[f'{name}_error_h'] = (ev[f'{name}_ts'] - ev.acc_ts).abs()
    ev[f'{name}_hit6h'] = ev[f'{name}_error_h'] <= 6

assert ev.before_ts.notna().all() and ev.after_ts.notna().all()
results = {}
null_frame = {}
for name in ['before', 'after']:
    acc = ev.acc_ts.to_numpy(float)
    pred = ev[f'{name}_ts'].to_numpy(float)
    obs = np.median(np.abs(acc - pred))
    rng = np.random.default_rng(20261106)
    null = np.array([np.median(np.abs(acc - rng.permutation(pred))) for _ in range(2000)])
    null_frame[name] = null
    results[name] = {'n': len(ev), 'median_error_h': float(obs),
        'hit6h': int(ev[f'{name}_hit6h'].sum()), 'null_median_h': float(np.median(null)),
        'permutation_p': float((null <= obs).mean())}
results['changed_events'] = int((ev.before_ts != ev.after_ts).sum())
results['reference'] = 'same vessel observed candidate hours, excluding candidate day; full-period retrospective'
results['weight'] = '2 - count(hour)/max_24_hour_count; 1 when no other day'
results['permutation'] = '2000 shuffles of selected timestamps across events, seed 20261106, proportion null median <= observed median'
ev.to_csv(OUT / 'event_results.csv', index=False, encoding='utf-8-sig')
pd.DataFrame(null_frame).to_csv(OUT / 'permutation_null.csv', index=False)
(OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
