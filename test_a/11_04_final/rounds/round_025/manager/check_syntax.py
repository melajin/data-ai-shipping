"""Parse round scripts without importing features, models or data."""
import ast
import datetime
import json
from pathlib import Path

r = Path(__file__).resolve().parents[1]
paths = sorted([*r.joinpath('code').glob('*.py'),
                *r.joinpath('review').glob('*.py'),
                *r.joinpath('code_author').glob('*.py'),
                r / 'manager/launch.py', r / 'manager/freeze_stage.py'])
for path in paths:
    ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
out = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
           syntax='pass', count=len(paths),
           scope='ast.parse only; no feature/model imports or data evaluation',
           files=[str(p.relative_to(r)) for p in paths])
(r / 'manager/syntax_check.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out))
