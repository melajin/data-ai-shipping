"""Read-only, package-relative verification. Never trains or opens raw/holdout data."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', action='store_true', help='Also reload all 21 models and replay OUTER predictions plus CSV precision variants')
    parser.add_argument('--hash-only', action='store_true', help='Standard-library-only file integrity check')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        path = (root / item['path']).resolve()
        assert path.is_relative_to(root), item['path']
        assert path.stat().st_size == item['bytes'], item['path']
        assert digest(path) == item['sha256'], item['path']
    out = {'status': 'PASS', 'files_verified': len(manifest['files']), 'training_performed': False,
           'scope': 'Repeatedly exposed development OUTER, not independent or official evaluation'}
    if args.hash_only:
        print(json.dumps(out, indent=2)); return
    import numpy as np

    def load(p):
        with np.load(p, allow_pickle=False) as z:
            return {k: z[k] for k in z.files}

    def metrics(y, prob):
        assert prob.shape == (len(y), 4)
        assert np.isfinite(prob).all()
        assert np.max(np.abs(prob.sum(axis=1) - 1)) < 1e-5
        pred = prob.argmax(axis=1)
        cm = np.zeros((4, 4), dtype=int)
        np.add.at(cm, (y, pred), 1)
        f1 = np.divide(2 * cm.diagonal(), cm.sum(0) + cm.sum(1), out=np.zeros(4), where=(cm.sum(0) + cm.sum(1)) != 0)
        recall = np.divide(cm.diagonal(), cm.sum(1), out=np.zeros(4), where=cm.sum(1) != 0)
        return {'n': len(y), 'correct': int((pred == y).sum()), 'micro_f1': float((pred == y).mean()),
                'macro_f1': float(f1.mean()), 'class_recall': recall.tolist(), 'confusion_matrix': cm.tolist()}

    res = json.loads((root / 'rounds/round_002/artifacts/result.json').read_text(encoding='utf-8'))
    config = json.loads((root / 'rounds/round_002/configs/experiment.json').read_text(encoding='utf-8'))
    feature_sets = {}
    old_y, old_probs, all_ids = [], [], []
    round2 = {k: [[], []] for k in ('baseline', 'candidate', 'blend')}
    probdir = root / 'rounds/round_002/artifacts/probabilities'
    models = root / 'rounds/round_002/artifacts/models'
    aliases = {'baseline': 'baseline_lightgbm', 'candidate': 'candidate_catboost', 'blend': 'blend'}
    model_checks, csv_checks = [], []
    if args.models:
        import lightgbm as lgb
        import catboost as cb
        import pandas as pd
        assert pd.__version__ == '2.2.3', 'CSV precision replay requires original round001 pandas==2.2.3; round002 pandas3.1.0 uses different default parsing'
        out['verification_environment'] = {'python': sys.version, 'numpy': np.__version__, 'pandas': pd.__version__, 'lightgbm': lgb.__version__, 'catboost': cb.__version__}
    for fold in range(3):
        input_path = root / f'inputs/development/fold_{fold}_features.npz'
        assert digest(input_path) == config['input']['fold_sha256'][str(fold)]
        z = load(input_path)
        assert z['X'].shape == (5897, 304)
        assert set(z['roles']) == {'FIT', 'INNER', 'OUTER'}
        outer = z['roles'] == 'OUTER'
        ids, y, x = z['rfid_ids'][outer], z['y'][outer], z['X'][outer]
        assert len(ids) == [1966, 1966, 1965][fold]
        feature_sets[fold] = z
        all_ids.extend(ids.tolist())
        historic = []
        csv_default_probs, csv_rt_probs = [], []
        if args.models:
            columns = z['feature_names'][156:166].tolist()
            csvpath = root / f'inputs/t5/fold_{fold}_t5.csv'
            default = pd.read_csv(csvpath, dtype={'rfid_id': str}).set_index('rfid_id').loc[z['rfid_ids'], columns].to_numpy(dtype=float)
            rt = pd.read_csv(csvpath, dtype={'rfid_id': str}, float_precision='round_trip').set_index('rfid_id').loc[z['rfid_ids'], columns].to_numpy(dtype=float)
            assert np.array_equal(default, z['X'][:, 156:166], equal_nan=True)
            rt_x = x.copy(); rt_x[:, 156:166] = rt[outer]
        for seed in (1, 7, 42, 2024, 2026):
            saved = load(root / f'historical_baseline/seed_predictions/fold_{fold}_seed_{seed}.npz')
            assert np.array_equal(saved['outer_ids'], ids)
            historic.append(saved['outer_probs'])
            if args.models:
                model = lgb.Booster(model_file=str(root / f'historical_baseline/models/fold_{fold}_seed_{seed}.txt'))
                pred = model.predict(x, num_threads=3)
                delta = float(np.max(np.abs(pred - saved['outer_probs'])))
                assert delta <= 1e-12
                model_checks.append({'round': 1, 'fold': fold, 'seed': seed, 'max_abs_delta': delta})
                csv_default_probs.append(pred)
                csv_rt_probs.append(model.predict(rt_x, num_threads=3))
        old_y.append(y); old_probs.append(np.mean(historic, axis=0))
        if args.models:
            p0, p1 = np.mean(csv_default_probs, axis=0), np.mean(csv_rt_probs, axis=0)
            assert np.array_equal(p0.argmax(1), p1.argmax(1))
            csv_checks.append({'fold': fold, 'default_t5_equals_npz': True,
                               'outer_probability_max_abs_delta': float(np.max(np.abs(p0-p1))),
                               'changed_argmax': int(np.sum(p0.argmax(1) != p1.argmax(1)))})
        saved2 = {}
        for key, alias in aliases.items():
            p = load(probdir / f'fold_{fold}_{alias}_outer.npz')
            assert np.array_equal(p['ids'], ids) and np.array_equal(p['y_true'], y)
            assert np.array_equal(p['predictions'], p['probabilities'].argmax(1))
            saved2[key] = p['probabilities']
            round2[key][0].append(y); round2[key][1].append(p['probabilities'])
        alpha = res['alpha_selection']['folds'][str(fold)]['chosen_alpha']
        a = load(probdir / f'fold_{fold}_baseline_lightgbm_inner_select.npz')
        b = load(probdir / f'fold_{fold}_candidate_catboost_inner_select.npz')
        assert np.array_equal(a['ids'], b['ids']) and np.array_equal(a['y_true'], b['y_true'])
        options = config['blend_selection']['alpha_candidates']
        scores = [int((((1-v)*a['probabilities']+v*b['probabilities']).argmax(1) == a['y_true']).sum()) for v in options]
        assert alpha == options[int(np.argmax(scores))]
        assert np.max(np.abs(saved2['blend'] - ((1-alpha)*saved2['baseline']+alpha*saved2['candidate']))) <= 1e-12
        if args.models:
            baseline = lgb.Booster(model_file=str(models / f'fold_{fold}_baseline_lightgbm.txt'))
            candidate = cb.CatBoostClassifier(); candidate.load_model(str(models / f'fold_{fold}_candidate_catboost.cbm'))
            preds = {'baseline': baseline.predict(x, num_threads=3),
                     'candidate': candidate.predict_proba(cb.Pool(x, feature_names=z['feature_names'].tolist()), thread_count=3)}
            for key, pred in preds.items():
                delta = float(np.max(np.abs(pred-saved2[key])))
                assert delta <= 1e-12
                model_checks.append({'round': 2, 'fold': fold, 'model': key, 'max_abs_delta': delta})
    assert len(all_ids) == len(set(all_ids)) == 5897
    old = metrics(np.concatenate(old_y), np.concatenate(old_probs))
    assert old['correct'] == 3497 and abs(old['macro_f1'] - 0.5252719738966167) < 1e-12
    out['round001_saved_five_seed_replay'] = old
    out['round002'] = {}
    for key, (ys, ps) in round2.items():
        got = metrics(np.concatenate(ys), np.concatenate(ps))
        expected = res['pooled_development_outer'][key]
        for metric in ('n', 'correct', 'micro_f1', 'macro_f1', 'class_recall', 'confusion_matrix'):
            assert np.allclose(got[metric], expected[metric], atol=1e-12, rtol=0), (key, metric)
        out['round002'][key] = got
    out['frozen_alphas_verified'] = [1.0, 0.0, 0.5]
    out['model_replay_checks'] = model_checks
    out['csv_precision_checks'] = csv_checks
    out['bootstrap_recomputed'] = False
    print(json.dumps(out, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
