from __future__ import annotations
import csv, hashlib, json, warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(r'D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\11_04_final')
REPO = Path(r'D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104')
EXP = REPO / 'artifacts' / 'exp01'
P = Path(r'D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\29-30일 모델 심층 분석\31일\팀원자료\TabICLv2_F156_공유자료')
RESULT_PATH = ROOT / 'rounds' / 'round_004' / 'lineage' / 'result.json'
OUT = ROOT / 'rounds' / 'round_004' / 'review' / 'independent_lineage_check.json'

def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def read_csv(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

result = read_json(RESULT_PATH)
config_path = ROOT / 'rounds' / 'round_002' / 'configs' / 'experiment.json'
config = read_json(config_path)
columns_path = P / 'metadata' / 'feature_columns.json'
p_names = [str(x) for x in read_json(columns_path)]
dictionary_path = P / 'metadata' / 'F156_feature_dictionary.csv'
dictionary = read_csv(dictionary_path)
dict_names = [r['feature'] for r in dictionary]
positions = [int(r['position_0based']) for r in dictionary]
roster = read_csv(EXP / 'fixed_split_roster.csv')
p_roles = read_csv(P / 'splits' / 'development_roles_long.csv')

assert len(p_names) == len(dictionary) == 156
assert positions == list(range(156))
assert p_names == dict_names
assert all(r.get('definition_ko', '').strip() and r.get('group', '').strip() for r in dictionary)
assert sha_file(config_path) == result['source_contracts']['round002_config_sha256']

fold_reports = {}
median_reports = {}
tensor_reports = {}
source_hashes = {'round002_config': sha_file(config_path), 'P_feature_columns': sha_file(columns_path), 'P_F156_dictionary': sha_file(dictionary_path)}

for fold in range(3):
    npz_path = EXP / f'fold_{fold}_features.npz'
    expected_npz_hash = config['input']['fold_sha256'][str(fold)]
    actual_npz_hash = sha_file(npz_path)
    assert actual_npz_hash == expected_npz_hash == result['folds'][str(fold)]['npz_sha256']
    with np.load(npz_path, allow_pickle=False) as z:
        ids = z['rfid_ids'].astype(str)
        y = z['y'].astype(np.int64)
        roles = z['roles'].astype(str)
        x = z['X']
        names = z['feature_names'].astype(str).tolist()
        fold_value = int(z['fold'])
    assert fold_value == fold
    assert x.shape == (5897, 304)
    assert names[:156] == p_names
    roster_fold = [r for r in roster if int(r['fold']) == fold]
    roles_fold = [r for r in p_roles if int(r['outer_fold']) == fold]
    roster_ids = [r['rfid_id'] for r in roster_fold]
    p_role_ids = [r['rfid_id'] for r in roles_fold]
    roster_roles = [r['role'].upper() for r in roster_fold]
    p_role_values = [r['role'].upper() for r in roles_fold]
    assert ids.tolist() == roster_ids == p_role_ids
    assert roles.tolist() == roster_roles == p_role_values
    assert y.tolist() == [int(r['y_true']) for r in roster_fold]
    counts = {role: int(np.sum(roles == role)) for role in ('FIT', 'INNER', 'OUTER')}
    assert counts == {'FIT': 3145 if fold == 2 else 3144, 'INNER': 787, 'OUTER': 1966 if fold < 2 else 1965}
    assert not np.isinf(x[:, :156]).any()
    fit_mask = roles == 'FIT'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        npz_median = np.nanmedian(x[fit_mask, :156].astype(np.float64, copy=False), axis=0)
    fold_reports[str(fold)] = {
        'npz_sha256': actual_npz_hash,
        'npz_shape': list(x.shape),
        'first156_names_equal_dictionary_order': True,
        'npz_row_order_equal_development_roster_and_P_role_table': True,
        'roles_equal': True,
        'labels_equal_roster_y_true': True,
        'role_counts': counts,
        'original_fit_id_order_recorded_in_training_json': False,
    }
    vocab_path = P / 'metadata' / f'fold_{fold}' / 'vocabulary_state.json'
    vocab = read_json(vocab_path)['provenance']
    sorted_fit_ids = sorted(set(ids[fit_mask].astype(str).tolist()))
    fit_ids_digest = sha_bytes(json.dumps(sorted_fit_ids, sort_keys=True, ensure_ascii=False).encode('utf-8'))
    base_path = next((P / 'code' / 'historical' / 'TinyTabM').glob('*/fishing_tiny_tabm.py'))
    vocab_code_path = next((P / 'code' / 'historical' / 'TabM').glob('*/vocabulary_features.py'))
    assert fit_ids_digest == vocab['fit_ids_sha256']
    assert vocab['fit_id_count'] == int(fit_mask.sum())
    assert sha_file(vocab_code_path) == vocab['module_sha256']
    assert sha_file(base_path) == vocab['baseline_implementation_sha256']
    for seed in (42, 2026):
        prep_path = P / 'evaluation' / f'seed_{seed}' / f'fold_{fold}' / 'preprocessor.json'
        prep = read_json(prep_path)
        saved_median = np.asarray(prep['median'], dtype=np.float64)
        assert prep['kind'] == 'fit_median_and_raw_missing_flags'
        assert saved_median.shape == (156,)
        delta = np.abs(npz_median - saved_median)
        assert np.isfinite(delta).all()
        assert float(delta.max()) <= 1e-10
        median_reports[f'{seed}/{fold}'] = {
            'saved_median_count': int(saved_median.size),
            'npz_fit_rows': int(fit_mask.sum()),
            'max_abs_delta': float(delta.max()),
            'mismatch_count_at_1e-10': int(np.sum(delta > 1e-10)),
        }
        for role_name, mask in (('FIT', fit_mask), ('INNER_QUERY', roles == 'INNER')):
            raw = np.asarray(x[mask, :156], dtype=np.float64).copy()
            raw[~np.isfinite(raw)] = np.nan
            missing = ~np.isfinite(raw)
            transformed = np.c_[np.where(missing, saved_median, raw), missing.astype(float)].astype('float32')
            row_ids = ids[mask].astype(str).tolist()
            tensor_hash = sha_bytes(transformed.tobytes(order='C'))
            row_hash = sha_bytes(json.dumps(row_ids, sort_keys=True, ensure_ascii=False).encode('utf-8'))
            key = f'{seed}/{fold}/{role_name}'
            recorded = result['transformed_input_hashes'][key]
            assert tensor_hash == recorded['sha256_C_order_float32_bytes']
            assert row_hash == recorded['row_ids_order_sha256']
            assert list(transformed.shape) == recorded['shape']
            assert str(transformed.dtype) == recorded['dtype'] == 'float32'
            assert np.isfinite(transformed).all()
            tensor_reports[key] = {
                'shape': list(transformed.shape),
                'dtype': str(transformed.dtype),
                'tensor_sha256_matches_result': True,
                'row_order_sha256_matches_result': True,
                'row_count': int(len(row_ids)),
                'input_is_original_saved_model_replay': False,
            }

# Role membership digest confirms a sorted set, not the original training sequence.
training_order_fields = []
for seed in (42, 2026):
    for fold in range(3):
        t = read_json(P / 'evaluation' / f'seed_{seed}' / f'fold_{fold}' / 'training.json')
        training_order_fields.append({'seed': seed, 'fold': fold, 'fit_ids_order_recorded': 'fit_ids' in t, 'inner_ids_order_recorded': 'inner_ids' in t})
assert not any(x['fit_ids_order_recorded'] or x['inner_ids_order_recorded'] for x in training_order_fields)

out = {
    'schema': 'round004_independent_lineage_check.v1',
    'status': 'PASS_WITH_LIMITATIONS',
    'checked_at_utc': datetime.now(timezone.utc).isoformat(),
    'reviewer_code_sha256': sha_file(Path(__file__).resolve()),
    'scope': {
        'inputs': 'Only three already-approved development fold NPZs, development rosters, round002 config, F156 metadata, six saved preprocessors, six training metadata files, and three vocabulary metadata states/source files.',
        'protected_rows_read': 0,
        'model_loaded': False,
        'training_or_inference': False,
        'F1_or_accuracy': False,
        'exact_original_F156_array_comparison': False,
        'original_fit_or_inner_sequence_available': False,
    },
    'feature_metadata': {
        'columns': len(p_names),
        'dictionary_rows': len(dictionary),
        'positions_sequential': positions == list(range(156)),
        'dictionary_names_equal_metadata_order': p_names == dict_names,
        'definitions_and_groups_nonempty': True,
        'group_counts': {g: sum(r['group'] == g for r in dictionary) for g in sorted({r['group'] for r in dictionary})},
        'semantic_source_value_validation': False,
    },
    'folds': fold_reports,
    'fit_medians': median_reports,
    'transformed_tensor_hashes': tensor_reports,
    'vocabulary_fit_membership': {
        'fit_id_membership_hash_matches_state_metadata_each_fold': True,
        'source_module_hash_matches_state_metadata': True,
        'baseline_source_hash_matches_state_metadata': True,
        'hash_semantics': 'sorted FIT ID set; confirms membership, not original FIT row order',
        'vocabulary_feature_values_regenerated': False,
    },
    'training_order_metadata': training_order_fields,
    'result_json_sha256': sha_file(RESULT_PATH),
    'source_sha256': source_hashes,
}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': out['status'], 'folds': len(fold_reports), 'median_comparisons': len(median_reports), 'transformed_hashes': len(tensor_reports), 'original_fit_sequence_available': False, 'output': str(OUT)}, ensure_ascii=False))
