"""Independently check frozen source hashes, split construction and row lineage."""
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'outputs/evaluation_cycle_20261028'
RUN = BASE/'model_cycle'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
fingerprint = lambda obj: hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
freeze = read(RUN/'freeze.json')
manifest = read(RUN/'split_manifest.json')
features = read(BASE/'vessel_features_v2.json')
predictions = read(RUN/'final_predictions.json')
assert fingerprint(manifest) == freeze['split_manifest_hash']
assert fingerprint(read(RUN/'protocol.json')) == freeze['protocol_hash']
source_hashes = {}
for name, expected in freeze['source_file_hashes'].items():
    current = ROOT/('docs' if name.endswith('.md') else 'fishing_demo')/name
    snapshot = RUN/'source_snapshot'/name
    assert hashlib.sha256(current.read_bytes()).hexdigest() == expected
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == expected
    source_hashes[name] = expected
by_hash = {v['vessel_hash']: v for v in features['vessels']}
assert len(by_hash) == len(features['vessels'])
rank = lambda seed, label, h: hashlib.sha256(f'{seed}\0{label}\0{h}'.encode('utf-8')).hexdigest()
expected_final, remaining = set(), {}
for label in manifest['class_names']:
    hashes = [h for h, v in by_hash.items() if v['label'] == label]
    ordered = sorted(hashes, key=lambda h: (rank(20261028, label, h), h))
    count = max(2, math.floor(.2*len(ordered)))
    expected_final.update(ordered[:count])
    remaining[label] = ordered[count:]
assert expected_final == set(manifest['final'])
for seed, observed in manifest['development'].items():
    expected = {k: set() for k in ('train', 'validation', 'calibration')}
    for label, hashes in remaining.items():
        ordered = sorted(hashes, key=lambda h: (rank(int(seed), label, h), h))
        n = len(ordered)
        nv = max(2, math.floor(.15*n))
        nc = max(2, n-math.floor(.7*n)-nv)
        nt = n-nv-nc
        expected['train'].update(ordered[:nt])
        expected['validation'].update(ordered[nt:nt+nv])
        expected['calibration'].update(ordered[nt+nv:])
    for role, values in expected.items():
        assert values == set(observed[role])
    assert set.union(*expected.values()) == set(by_hash)-expected_final
source_rows = 0
for pred in predictions:
    original = by_hash[pred['vessel_hash']]
    assert pred['label'] == original['label']
    expected = [(r['file_ordinal'], r['record_ordinal']) for r in original['rows']]
    assert expected == [(r['file_ordinal'], r['record_ordinal']) for r in pred['source_rows']]
    assert (pred['status'] == 'ok') == any(r['valid'] for r in original['rows'])
    source_rows += len(expected)
result = {'status': 'passed', 'source_snapshot_and_current_hashes_match': source_hashes,
          'frozen_protocol_and_split_hashes_match': True, 'seeded_split_reconstruction_matches': True,
          'development_and_final_cover_entire_roster': True, 'final_prediction_row_lineage_matches': True,
          'final_vessels': len(predictions), 'selected_final_source_rows': source_rows,
          'abstentions_match_fixed_feature_validity': True}
(ROOT/'outputs/real_provenance_independent_audit_20261029.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
