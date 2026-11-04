"""Independent vessel-level final audit; no project metric functions imported."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def metrics(labels, probs, classes):
    labels = np.asarray(labels, dtype=int)
    probs = np.asarray(probs, dtype=float)
    if probs.shape != (len(labels), classes) or not len(labels):
        raise ValueError('empty or incompatible probability dimensions')
    if not np.isfinite(probs).all() or np.any(probs < 0) or np.any(probs > 1):
        raise ValueError('invalid probabilities')
    if not np.allclose(probs.sum(axis=1), 1, rtol=0, atol=1e-10):
        raise ValueError('probability rows do not sum to one')
    if np.any(labels < 0) or np.any(labels >= classes):
        raise ValueError('invalid labels')
    predicted = probs.argmax(axis=1)
    matrix = np.bincount(labels * classes + predicted, minlength=classes**2).reshape(classes, classes)
    tp = matrix.diagonal().astype(float)
    denom = matrix.sum(axis=0) + matrix.sum(axis=1)
    f1 = np.divide(2*tp, denom, out=np.zeros(classes), where=denom > 0)
    truth = np.eye(classes)[labels]
    return {'n': len(labels), 'accuracy': float(tp.sum()/len(labels)),
            'macro_f1': float(f1.mean()), 'class_f1': f1.tolist(),
            'nll': float(-np.log(np.maximum(probs[np.arange(len(labels)), labels], np.finfo(float).tiny)).mean()),
            'brier': float(np.sum((probs-truth)**2, axis=1).mean()),
            'confusion': matrix.tolist(), 'support': matrix.sum(axis=1).tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=ROOT/'outputs/evaluation_cycle_20261028/model_cycle')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/real_evaluation_independent_audit_20261028.json')
    args = parser.parse_args()
    predpath = args.input_dir/'final_predictions.json'
    splitpath = args.input_dir/'split_manifest.json'
    rows = json.loads(predpath.read_text(encoding='utf-8'))
    split = json.loads(splitpath.read_text(encoding='utf-8'))
    names = split['class_names']
    final = split['final']
    if len(final) != len(set(final)):
        raise ValueError('duplicate final vessels')
    counts = {}
    for seed, dev in split['development'].items():
        seen = set(final)
        counts[seed] = {}
        for part in ('train', 'validation', 'calibration'):
            values = dev[part]
            if len(values) != len(set(values)) or seen.intersection(values):
                raise ValueError('vessel overlap inside a development/final split')
            seen.update(values)
            counts[seed][part] = len(values)
    ids = [r['vessel_hash'] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(final):
        raise ValueError('final prediction coverage does not match manifest')
    if any(r['label'] != names[r['true_index']] for r in rows):
        raise ValueError('label ordering mismatch')
    if any(r['status'] not in ('ok', 'abstained') for r in rows):
        raise ValueError('unknown final prediction status')
    abstained = [r for r in rows if r['status'] == 'abstained']
    if any(r['baseline_probabilities'] is not None or r['candidate_probabilities'] is not None for r in abstained):
        raise ValueError('abstained row must have null probabilities for both models')
    all_support = np.bincount([r['true_index'] for r in rows], minlength=len(names)).tolist()
    rows = [r for r in rows if r['status'] == 'ok']
    labels = np.array([r['true_index'] for r in rows])
    base = np.array([r['baseline_probabilities'] for r in rows])
    candidate = np.array([r['candidate_probabilities'] for r in rows])
    bm, cm = metrics(labels, base, len(names)), metrics(labels, candidate, len(names))
    bm['full_roster_accuracy'] = bm['accuracy']*len(rows)/len(final)
    cm['full_roster_accuracy'] = cm['accuracy']*len(rows)/len(final)
    groups = [np.flatnonzero(labels == i) for i in range(len(names))]
    if any(len(g) == 0 for g in groups):
        raise ValueError('final set lacks a declared class')
    rng = np.random.default_rng(20261028)
    deltas = []
    for _ in range(2000):
        selected = np.concatenate([rng.choice(g, len(g), replace=True) for g in groups])
        deltas.append(metrics(labels[selected], candidate[selected], len(names))['macro_f1'] - metrics(labels[selected], base[selected], len(names))['macro_f1'])
    ci = np.quantile(deltas, [.025, .975]).tolist()
    reported_path = args.input_dir/'results.json'
    reported = json.loads(reported_path.read_text(encoding='utf-8'))['final']
    differences = []
    for independent, key in ((bm, 'baseline_metrics'), (cm, 'candidate_metrics')):
        for metric in ('accuracy', 'macro_f1', 'nll', 'brier', 'full_roster_accuracy'):
            differences.append(abs(independent[metric]-reported[key][metric]))
        assert independent['support'] == reported[key]['support']
        reported_confusion = np.array(reported[key]['confusion_with_abstain_column'])
        assert np.array_equal(np.array(independent['confusion']), reported_confusion[:, :len(names)])
    assert len(abstained) == reported['abstained_vessels']
    assert len(rows) == reported['scorable_vessels']
    reported_ci = reported['paired_bootstrap']['macro_f1_delta_ci95']
    ci_error = float(np.max(np.abs(np.asarray(ci)-reported_ci)))
    assert max(differences) <= 1e-12 and ci_error <= 1e-12
    result = {'audit_type': 'independent_recalculation_from_saved_vessel_predictions',
              'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (predpath, splitpath, reported_path)},
              'class_names': names, 'split_counts': counts, 'final_vessels': len(final),
              'vessel_split_disjoint': True, 'prediction_manifest_coverage_complete': True,
              'evaluable_vessels': len(rows), 'abstained_vessels': len(abstained),
              'evaluated_fraction': len(rows)/len(final), 'all_final_class_support': all_support,
              'baseline': bm, 'candidate': cm,
              'delta': {k: cm[k]-bm[k] for k in ('accuracy','macro_f1','nll','brier')},
              'macro_f1_paired_stratified_bootstrap': {'replicates': 2000,'seed': 20261028,'ci95': ci},
              'reported_metrics_max_absolute_error': max(differences),
              'reported_bootstrap_ci_max_absolute_error': ci_error,
              'reported_confusion_support_coverage_match': True,
              'limitations': ['Checks saved predictions and split IDs; does not prove absence of upstream feature leakage.',
                              'Confidence interval conditions on the observed class support and sampled vessels.']}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
