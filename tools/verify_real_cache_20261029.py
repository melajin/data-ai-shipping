"""Read-only independent comparison of repaired features against v1 SQLite."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'outputs/evaluation_cycle_20261028'
path = BASE/'vessel_features_v2.json'
blob = path.read_bytes()
features = json.loads(blob)
repair = json.loads((BASE/'cache_repair_audit.json').read_text(encoding='utf-8'))
assert hashlib.sha256(blob).hexdigest() == repair['vessel_features_v2_sha256']
connection = sqlite3.connect((BASE/'inspection_cache.sqlite3').as_uri()+'?mode=ro', uri=True)
old = {}
for row in connection.execute('SELECT file_ordinal,record_ordinal,vessel_hash,label_code,part_dt,feature_valid,feature_reason,feature_values_json,degree_control_values_json FROM feature_samples'):
    key = (row[0], row[1])
    assert key not in old
    old[key] = row[2:]
excluded = {(r['file_ordinal'], r['record_ordinal']) for r in repair['quarantine']}
seen, ships = set(), set()
classes, months, invalid = Counter(), Counter(), Counter()
for vessel in features['vessels']:
    assert vessel['vessel_hash'] not in ships
    ships.add(vessel['vessel_hash'])
    classes[vessel['label']] += 1
    per_file = Counter()
    for row in vessel['rows']:
        key = (row['file_ordinal'], row['record_ordinal'])
        assert key not in seen and key not in excluded and key in old
        seen.add(key)
        original = old[key]
        assert original[0] == vessel['vessel_hash'] and original[1] == vessel['label']
        assert row['month'] == int(original[2][5:7]) == row['file_ordinal']+1
        assert 0 <= row['file_ordinal'] <= 5
        assert row['valid'] == bool(original[3]) and row['reason'] == original[4]
        assert row['values'] == json.loads(original[5])
        assert row['degree_control_values'] == json.loads(original[6])
        per_file[row['file_ordinal']] += 1
        months[row['month']] += 1
        if not row['valid']:
            invalid[row['reason']] += 1
    assert all(count <= 4 for count in per_file.values()) and len(vessel['rows']) <= 24
assert seen == set(old)-excluded
connection.close()
result = {'status': 'passed', 'v2_sha256': hashlib.sha256(blob).hexdigest(),
          'vessels': len(ships), 'selected_rows': len(seen), 'excluded_structurally_invalid_rows': len(excluded),
          'class_vessels': dict(classes), 'month_selected_rows': dict(sorted(months.items())),
          'invalid_selected_row_reasons': dict(invalid),
          'month_matches_source_date_and_file': True, 'source_row_ownership_unique': True,
          'all_feature_values_unchanged': True, 'sample_bound_per_vessel_per_file': 4,
          'comparison_scope': 'All v2 selected rows against preserved v1 SQLite; no source CSV reread or full geometry validation.'}
out = ROOT/'outputs/real_cache_independent_audit_20261029.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
