from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[3]
result_path = root / 'rounds' / 'round_007' / 'artifacts' / 'synthetic_pair_result.json'
result = json.loads(result_path.read_text(encoding='utf-8'))
npz_path = Path(result['outputs_path'])
if not npz_path.is_absolute():
    npz_path = root / npz_path
blob_sha = hashlib.sha256(npz_path.read_bytes()).hexdigest()
checks: dict[str, bool] = {}
def check(name: str, condition: object) -> None:
    checks[name] = bool(condition)
    if not checks[name]:
        raise AssertionError(name)

def array_sha(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes(order='C')).hexdigest()

check('result_status_complete', result.get('status') == 'SYNTHETIC_PAIR_COMPLETE')
check('result_stage_comparison_complete', result.get('stage') == 'comparison_complete')
check('approved_source_hash_used', result.get('source_at_entry_sha256', '').lower() == '67f74942b38c4c2ee42c6a0509c39997828c0e98658bc04adb2ca96850f445b3')
check('one_fit_and_two_predictions', result.get('checkpoint_fit_invocation_count') == 1 and result.get('fit_completed_count') == 1 and result.get('predict_proba_attempted_count') == 2 and result.get('predict_proba_completed_count') == 2)
check('adapter_restored', result.get('adapter_installed') is False and result.get('adapter_restored') is True and result.get('original_manager_reinstated') is True)
check('npz_sha256_matches_result', blob_sha == result.get('outputs_sha256'))

with np.load(npz_path, allow_pickle=False) as archive:
    expected_names = {'X_fit', 'y_fit', 'X_query', 'baseline_probabilities', 'chunked_probabilities'}
    check('npz_members_exact', set(archive.files) == expected_names)
    X_fit = archive['X_fit']
    y_fit = archive['y_fit']
    X_query = archive['X_query']
    p_base = archive['baseline_probabilities']
    p_chunk = archive['chunked_probabilities']

check('synthetic_shapes_and_dtypes', X_fit.shape == (32, 312) and X_fit.dtype == np.dtype('float32') and y_fit.shape == (32,) and y_fit.dtype == np.dtype('int64') and X_query.shape == (2, 312) and X_query.dtype == np.dtype('float32') and p_base.shape == (2, 4) and p_chunk.shape == (2, 4) and p_base.dtype == np.dtype('float32') and p_chunk.dtype == np.dtype('float32'))
check('expected_label_values', np.array_equal(y_fit, np.tile(np.arange(4), 8)))
rng = np.random.default_rng(20261105)
expected_fit = rng.normal(0.0, 1.0, size=(32, 312)).astype(np.float32)
expected_query = rng.normal(0.0, 1.0, size=(2, 312)).astype(np.float32)
check('expected_rng_arrays', np.array_equal(X_fit, expected_fit) and np.array_equal(X_query, expected_query))
inputs = result['inputs']
for name, array in [('X_fit', X_fit), ('y_fit', y_fit), ('X_query', X_query)]:
    metadata = inputs[name]
    check(f'{name}_result_shape_dtype_hash', metadata['shape'] == list(array.shape) and metadata['dtype'] == str(array.dtype) and metadata['sha256_c_order_bytes'] == array_sha(array))
expected_fingerprints = {
    'X_fit': {'shape': list(X_fit.shape), 'dtype': str(X_fit.dtype), 'sha256_c_order_bytes': array_sha(X_fit)},
    'y_fit': {'shape': list(y_fit.shape), 'dtype': str(y_fit.dtype), 'sha256_c_order_bytes': array_sha(y_fit)},
    'X_query': {'shape': list(X_query.shape), 'dtype': str(X_query.dtype), 'sha256_c_order_bytes': array_sha(X_query)},
}
for label in ('input_fingerprints_at_creation', 'baseline_pre_call_input_fingerprints', 'baseline_post_call_input_fingerprints', 'chunked_pre_call_input_fingerprints', 'chunked_post_call_input_fingerprints'):
    check(f'{label}_matches_npz', result.get(label) == expected_fingerprints)
check('json_probability_values_match_npz', np.array_equal(np.asarray(result['baseline_probability_check']['values'], dtype=np.float64), p_base.astype(np.float64)) and np.array_equal(np.asarray(result['chunked_probability_check']['values'], dtype=np.float64), p_chunk.astype(np.float64)))

def probability_gate(a: np.ndarray) -> tuple[bool, float]:
    finite = bool(np.isfinite(a).all())
    in_range = bool(np.all((a >= 0.0) & (a <= 1.0))) if finite else False
    error = float(np.max(np.abs(a.sum(axis=1) - 1.0))) if a.shape == (2, 4) and finite else float('inf')
    return bool(a.shape == (2, 4) and finite and in_range and error <= 1e-5), error
base_gate, base_sum_error = probability_gate(p_base)
chunk_gate, chunk_sum_error = probability_gate(p_chunk)
diff = np.abs(p_base.astype(np.float64) - p_chunk.astype(np.float64))
max_diff = float(diff.max())
base_argmax = np.argmax(p_base.astype(np.float64), axis=1).astype(int).tolist()
chunk_argmax = np.argmax(p_chunk.astype(np.float64), axis=1).astype(int).tolist()
comparison = result['comparison']
check('probability_gates', base_gate and chunk_gate and result['baseline_probability_check']['gate_pass'] is True and result['chunked_probability_check']['gate_pass'] is True)
check('max_row_sum_errors_match_json', abs(base_sum_error - result['baseline_probability_check']['max_abs_row_sum_error']) <= 1e-15 and abs(chunk_sum_error - result['chunked_probability_check']['max_abs_row_sum_error']) <= 1e-15)
check('difference_and_exact_equality_match_json', max_diff == comparison['max_abs_probability_difference'] and bool(np.array_equal(p_base, p_chunk)) == comparison['exact_numeric_equal'] and bool(np.array_equal(p_base, p_chunk)))
check('argmax_matches_json', base_argmax == comparison['argmax_baseline'] and chunk_argmax == comparison['argmax_chunked'] and base_argmax == chunk_argmax and comparison['argmax_equal'] is True)
check('comparison_gate_pass', comparison['within_tolerance_and_argmax_gate_pass'] is True and max_diff <= 1e-5)

calls = [e for e in result.get('adapter_events', []) if e.get('event') == 'column_chunk_call_started']
check('eight_column_calls', len(calls) == 8 and [e.get('call_id') for e in calls] == list(range(8)))
for call in calls:
    cid = call['call_id']
    check(f'call_{cid}_shape_contract', call.get('feature_shape') == [1, 316, 34, 3] and call.get('column_axis') == 1 and call.get('column_count') == 316 and call.get('sequence_length_preserved') == 34 and call.get('feature_group_size_preserved') == 3 and call.get('train_size_shared') == 32 and call.get('embed_with_test_shared') is False and call.get('output_repeat_preserved') == 1)
    starts = sorted((e for e in result['adapter_events'] if e.get('event') == 'column_chunk_started' and e.get('call_id') == cid), key=lambda e: e['chunk_index'])
    completes = [e for e in result['adapter_events'] if e.get('event') == 'column_chunk_completed' and e.get('call_id') == cid]
    spans = [(e['column_start'], e['column_stop_exclusive']) for e in starts]
    expected_spans = [(start, min(start + 16, 316)) for start in range(0, 316, 16)]
    check(f'call_{cid}_twenty_contiguous_chunks', len(starts) == 20 and len(completes) == 20 and spans == expected_spans)
    check(f'call_{cid}_output_reassembled_shape', any(e.get('event') == 'column_chunk_call_completed' and e.get('call_id') == cid and e.get('output_shape') == [1, 316, 34, 128] and e.get('max_chunk_columns') == 16 and e.get('chunk_count') == 20 for e in result['adapter_events']))
check('runtime_managers_unchanged', result.get('baseline_runtime_manager_state') == result.get('chunked_runtime_manager_state') and result.get('chunked_runtime_manager_state_unchanged') is True)

verification = {
    'schema': 'round007_synthetic_artifact_verification.v1',
    'verification_completed_utc': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    'method': 'independent NumPy-only artifact check; imported only NumPy, JSON, hashlib, pathlib, datetime; did not import Torch/TabICL or load a checkpoint',
    'result_path': str(result_path),
    'npz_path': str(npz_path),
    'npz_sha256': blob_sha,
    'result_status': result['status'],
    'source_at_entry_sha256': result['source_at_entry_sha256'],
    'input_shapes': {'X_fit': list(X_fit.shape), 'y_fit': list(y_fit.shape), 'X_query': list(X_query.shape)},
    'input_sha256': {name: expected_fingerprints[name]['sha256_c_order_bytes'] for name in expected_fingerprints},
    'prediction': {
        'baseline_gate_pass': base_gate,
        'chunked_gate_pass': chunk_gate,
        'baseline_max_abs_row_sum_error': base_sum_error,
        'chunked_max_abs_row_sum_error': chunk_sum_error,
        'max_abs_probability_difference': max_diff,
        'exact_numeric_equal': bool(np.array_equal(p_base, p_chunk)),
        'argmax_baseline': base_argmax,
        'argmax_chunked': chunk_argmax,
        'overall_probability_and_argmax_gate_pass': comparison['within_tolerance_and_argmax_gate_pass'],
    },
    'adapter_events': {'column_calls': len(calls), 'columns_per_call': 316, 'chunk_width': 16, 'chunks_per_call': 20, 'last_chunk_width': 12, 'output_shape_per_call': [1, 316, 34, 128]},
    'check_count': len(checks),
    'checks': checks,
    'all_checks_pass': all(checks.values()),
    'limits': 'Synthetic pair only: two synthetic query rows; does not establish actual-data replay equivalence, F1, full-context memory reduction, holdout/Test2025 performance, or hardware behavior.',
}
verification_path = root / 'rounds' / 'round_007' / 'review' / 'synthetic_artifact_verification.json'
verification_path.write_text(json.dumps(verification, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({k: verification[k] for k in ('all_checks_pass', 'check_count', 'npz_sha256', 'prediction', 'adapter_events')}, indent=2))
