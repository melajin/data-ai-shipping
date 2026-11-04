from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

folder = Path(__file__).resolve().parent
root = folder.parents[1]
paths = sorted(p for p in folder.iterdir() if p.is_file() and p.name != 'COMPLETION_MANIFEST.json')
paths += [root / 'docs/20261105_검증자료_PDF반영_기술진단_보강보고서.md']
paths += [root / f'rounds/round_003/verification_20261105/{name}' for name in (
 'VERIFICATION_REPORT.md','v1_integrity.json','v2_recompute.json',
 'v3_bootstrap_gate.json','v4_idhash.json','v4_idhash.py','v5_split_and_scores.json','v6_manifest.json')]
out = {'saved_at_utc': datetime.now(timezone.utc).isoformat(),
       'scope': 'Supplemental document review; no model experiment or shared round-state update',
       'files': [{'path':str(p.relative_to(root)), 'bytes':p.stat().st_size,
                  'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
(folder / 'COMPLETION_MANIFEST.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'manifest_files':len(paths),'scope':out['scope']}))
