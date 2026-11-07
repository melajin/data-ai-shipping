"""Read Parquet footers and input hashes; does not load data tables."""
from pathlib import Path
import hashlib, json
from datetime import datetime, timezone
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).with_name('input_metadata.json')
FILES = [
 'testB/과거/round_008_linkage_audit_20261105/dev_hourly_scores.parquet',
 'testB/과거/round_008_linkage_audit_20261105/additional_hourly_scores.parquet',
 'testB/과거/round_008_linkage_audit_20261105/devset_positives.csv',
 'testB/과거/first_results/hourly_scores.parquet',
]
out = {'created_utc': datetime.now(timezone.utc).isoformat(), 'metadata_only': True, 'files': []}
for rel in FILES:
    p = ROOT / rel
    sha = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha.update(chunk)
    row = {'path': rel, 'bytes': p.stat().st_size, 'sha256': sha.hexdigest()}
    if p.suffix == '.parquet':
        pf = pq.ParquetFile(p)
        row.update(rows=pf.metadata.num_rows, row_groups=pf.metadata.num_row_groups,
                   schema=str(pf.schema_arrow),
                   total_row_group_bytes=sum(pf.metadata.row_group(i).total_byte_size for i in range(pf.metadata.num_row_groups)))
    out['files'].append(row)
OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=False, indent=2))
