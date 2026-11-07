"""Coordinator check of applicability of static-review warning to this fixed run."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
EXEC = HERE / 'execution_001'
cols = ['score'] + [f'd{i}_ok' for i in range(5)]
frame = pq.read_table(EXEC / 'candidate_ledger.parquet', columns=cols).to_pandas()
pred = pd.read_csv(EXEC / 'predictions.csv')
out = {
 'rows': len(frame),
 'finite_legacy_scores': int(np.isfinite(frame['score']).sum()),
 'd0_true': int(frame.d0_ok.sum()),
 'subset_violations': {f'd{i}_outside_d{i-1}': int((frame[f'd{i}_ok'] & ~frame[f'd{i-1}_ok']).sum()) for i in range(1,5)},
 'prediction_rows': len(pred),
 'all_primary_prediction_scores_finite': bool(np.isfinite(pred['method_score']).all()),
 'scope': 'fixed execution_001 only; does not prove API safe for invalid-score inputs',
}
out['fixed_input_warning_manifested'] = bool(out['finite_legacy_scores'] != out['rows'] or out['d0_true'] != out['rows'] or any(out['subset_violations'].values()))
(EXEC / 'ACTUAL_MASK_CHECK.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
