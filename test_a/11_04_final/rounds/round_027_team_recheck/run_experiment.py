"""Probability-only, fold-local SELECT recheck experiment; see ROUND_PLAN.md."""
from __future__ import annotations

import os
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '1'
import csv
import gc
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
if any((HERE / name).exists() for name in ('predictions_frozen.npz', 'selection_frozen.json', 'results.json')):
    raise RuntimeError('Frozen outputs already exist: preserve this run; use a separately planned attempt directory.')
ROOT = HERE.parents[1]
R2 = ROOT / 'rounds/round_002/artifacts/probabilities'
A = ROOT / 'rounds/round_027_fallback_ovr/worker_a_ovr_models/worker_a_probabilities.npz'
T3 = ROOT / 'rounds/round_026/track3_ensemble/probabilities_track3.npz'
REPO = Path(r'D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\artifacts\exp01\sqrt_macro')
TAB = ROOT.parent / '29-30일 모델 심층 분석/31일/팀원자료/TabICLv2_F156_공유자료/evaluation/seed_42'
INPUTS = set()
RESOURCE = []


def dump(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def guard(stage, entry=False):
    proc = psutil.Process()
    if os.name == 'nt':
        proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    v = psutil.virtual_memory()
    r = dict(time=datetime.now(timezone.utc).isoformat(), stage=stage,
             available_gib=v.available / 2**30, rss_gib=proc.memory_info().rss / 2**30,
             expected_peak_gib=.35, estimate='small probability arrays + sklearn/scipy imports + <=394x16 logistic fits',
             other_python=[dict(pid=p.pid, name=p.info['name']) for p in psutil.process_iter(['name'])
                           if p.info['name'] and 'python' in p.info['name'].lower() and p.pid != proc.pid])
    RESOURCE.append(r)
    dump('resource_checks.json', RESOURCE)
    if r['available_gib'] < (1.5 if entry else 1.0) or r['rss_gib'] > .75:
        raise RuntimeError('RAM gate: defer calculation; see resource_checks.json')


guard('entry_before_numeric_import', entry=True)
import numpy as np
import scipy
import sklearn
from scipy.stats import binomtest
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CANDIDATES = ['baseline', 'singleton_trust', 'singleton_recheck', 'empty_zero', 'empty_recheck',
              'pair01_hard_base', 'pair01_recheck', 'pair02_recheck', 'combined_hard', 'combined_soft']
ALPHA = np.array([1.033, 1., .983, 1.5])


def npz(path):
    INPUTS.add(Path(path))
    return np.load(path, allow_pickle=False)


def csv_probs(path, keys, inner=False):
    INPUTS.add(Path(path))
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        rows = csv.DictReader(f)
        d = {}
        for r in rows:
            k = (int(r['fold']), str(r['rfid_id'])) if inner else str(r['rfid_id'])
            if k in d:
                raise ValueError(f'duplicate probability key in {path}')
            d[k] = [float(r[f'p{c}']) for c in range(4)]
    return np.asarray([d[k] for k in keys], dtype=np.float64)


def metrics(y, pred):
    cm = np.bincount(y * 4 + pred, minlength=16).reshape(4, 4)
    tp = cm.diagonal()
    support, predicted = cm.sum(1), cm.sum(0)
    f1 = np.divide(2 * tp, support + predicted, out=np.zeros(4), where=(support + predicted) > 0)
    return dict(n=len(y), correct=int(tp.sum()), micro_f1=float(tp.sum() / max(1, len(y))),
                macro_f1=float(f1.mean()), tp=tp.tolist(), fp=(predicted - tp).tolist(),
                support=support.tolist(), predicted=predicted.tolist(), f1=f1.tolist(),
                precision=np.divide(tp, predicted, out=np.zeros(4), where=predicted > 0).tolist(),
                recall=np.divide(tp, support, out=np.zeros(4), where=support > 0).tolist(), cm=cm.tolist())


def tag_groups(scores):
    tags = scores >= .5
    count = tags.sum(1)
    return tags, dict(singleton=count == 1, empty=count == 0,
                      pair01=tags[:, 0] & tags[:, 1],
                      pair02=(count == 2) & tags[:, 0] & tags[:, 2])


def features(base, scores, m123):
    tags, _ = tag_groups(scores)
    return np.column_stack([base, scores, m123, tags.astype(float), tags.sum(1)])


def fit_models(x, y):
    models = []
    for classes in (None, (0, 1), (0, 2)):
        mask = np.ones(len(y), dtype=bool) if classes is None else np.isin(y, classes)
        if len(np.unique(y[mask])) < (4 if classes is None else 2):
            models.append(None)
            continue
        model = make_pipeline(StandardScaler(), LogisticRegression(C=.3, max_iter=400, random_state=2705))
        model.fit(x[mask], y[mask])
        models.append(model)
    return models


def infer(models, x, base):
    out = []
    for model in models:
        if model is None:
            out.append(base.copy())
        else:
            p = np.zeros((len(x), 4))
            p[:, model[-1].classes_] = model.predict_proba(x)
            out.append(p)
    return out


def candidates(base, scores, rechecks):
    tags, group = tag_groups(scores)
    b = base.argmax(1)
    full, pair01, pair02 = [p.argmax(1) for p in rechecks]
    pred = {name: b.copy() for name in CANDIDATES}
    pred['singleton_trust'][group['singleton']] = tags[group['singleton']].argmax(1)
    pred['singleton_recheck'][group['singleton']] = full[group['singleton']]
    pred['empty_zero'][group['empty']] = 0
    pred['empty_recheck'][group['empty']] = full[group['empty']]
    hard01 = np.asarray([0, 1])[base[:, [0, 1]].argmax(1)]
    pred['pair01_hard_base'][group['pair01']] = hard01[group['pair01']]
    pred['pair01_recheck'][group['pair01']] = pair01[group['pair01']]
    pred['pair02_recheck'][group['pair02']] = pair02[group['pair02']]
    for group_name, name in [('singleton', 'singleton_recheck'), ('empty', 'empty_zero'),
                             ('pair01', 'pair01_recheck'), ('pair02', 'pair02_recheck')]:
        m = group[group_name]
        pred['combined_hard'][m] = pred[name][m]
    target = np.logical_or.reduce(list(group.values()))
    q = rechecks[0]
    row = np.arange(len(base))
    margin = q[row, full] - q[row, b]
    change = target & (margin >= .15)
    pred['combined_soft'][change] = full[change]
    return pred


def choose(y, oof):
    scores = {name: metrics(y, p) for name, p in oof.items()}
    ref = scores['baseline']['tp']
    eligible = [name for name in CANDIDATES if scores[name]['tp'][0] >= ref[0]
                and scores[name]['tp'][3] >= ref[3]]
    selected = max(eligible, key=lambda n: (scores[n]['correct'], scores[n]['macro_f1'], -CANDIDATES.index(n)))
    return selected, dict(selected=selected, eligible=eligible, oof_metrics=scores,
                          protection_reference_tp=ref, label_source='same original fold INNER_SELECT only')


def serialize_models(models):
    saved = []
    for m in models:
        saved.append(None if m is None else dict(mean=m[0].mean_.tolist(), scale=m[0].scale_.tolist(),
                     classes=m[-1].classes_.tolist(), coef=m[-1].coef_.tolist(), intercept=m[-1].intercept_.tolist()))
    return saved


def paired(y, ref, pred):
    b, c = ref == y, pred == y
    gain, loss = int((~b & c).sum()), int((b & ~c).sum())
    rng = np.random.default_rng(2705)
    samples = rng.multinomial(len(y), [gain / len(y), loss / len(y), 1 - (gain + loss) / len(y)], size=2000)
    ci = np.quantile(samples[:, 0] - samples[:, 1], [.025, .975]).tolist()
    per_class = {}
    for k in range(4):
        m = y == k
        g, l = int((~b & c & m).sum()), int((b & ~c & m).sum())
        per_class[str(k)] = dict(gain=g, loss=l, net=g-l)
    return dict(gain=gain, loss=loss, net=gain-loss, ci95_correct_count=ci,
                mcnemar_p=float(binomtest(gain, gain + loss, .5).pvalue) if gain+loss else 1.,
                per_true_class=per_class, transition=np.bincount(ref*4+pred, minlength=16).reshape(4,4).tolist())


def group_report(y, base, scores, pred):
    tags, groups = tag_groups(scores)
    masks = (tags * (1 << np.arange(4))).sum(1)
    groups.update({f'pattern_{v:04b}': masks == v for v in range(16)})
    result = {}
    for name, m in groups.items():
        n = int(m.sum())
        if not n:
            result[name] = dict(n=0)
            continue
        yy = y[m]
        result[name] = dict(n=n, true_counts=np.bincount(yy, minlength=4).tolist(),
                            true_tag_present=int(tags[m][np.arange(n), yy].sum()),
                            singleton_trust_correct=int((tags[m].argmax(1) == yy).sum()) if name == 'singleton' else None,
                            baseline_correct=int((base[m] == yy).sum()), selected_correct=int((pred[m] == yy).sum()),
                            selected_metrics=metrics(yy, pred[m]))
    return result


def run():
    guard('load_small_probabilities')
    INPUTS.update([A.with_name('run_worker_a_ovr.py'), REPO.parent / 'fixed_split_roster.csv',
                   Path(r'D:\repos\fishing-track-classification\coach\gpt\rank1_experiments_20261104\configs\exp01\experiment.json')])
    inner, outer = [], []
    pc_in, pc_out = [], []
    p42_out = []
    for f in range(3):
        for role, suffix in [('ES', 'inner_es'), ('SELECT', 'inner_select')]:
            with npz(R2 / f'fold_{f}_baseline_lightgbm_{suffix}.npz') as z:
                reference_ids = z['ids'].astype(str)
                inner.extend((f, role, str(i), int(y)) for i,y in zip(reference_ids, z['y_true']))
            with npz(R2 / f'fold_{f}_candidate_catboost_{suffix}.npz') as z:
                assert np.array_equal(z['ids'].astype(str), reference_ids)
                pc_in.append(z['probabilities'])
        with npz(R2 / f'fold_{f}_baseline_lightgbm_outer.npz') as z:
            reference_ids = z['ids'].astype(str)
            outer.extend((f, str(i)) for i in reference_ids)  # intentionally do not access y_true yet
            p42_out.append(z['probabilities'])
        with npz(R2 / f'fold_{f}_candidate_catboost_outer.npz') as z:
            assert np.array_equal(z['ids'].astype(str), reference_ids)
            pc_out.append(z['probabilities'])
    ik = [(f,i) for f,_,i,_ in inner]
    ok = [i for _,i in outer]
    assert len(set(ik)) == len(ik) == 2361
    assert len(set(ok)) == len(ok) == 5897
    iy = np.array([r[3] for r in inner])
    fi = np.array([r[0] for r in inner]); fo = np.array([r[0] for r in outer])
    is_select = np.array([r[1] == 'SELECT' for r in inner])
    for f in range(3):
        # Only metadata members, never X or y from these feature archives.
        with npz(REPO.parent / f'fold_{f}_features.npz') as z:
            ids, roles = z['rfid_ids'].astype(str), z['roles'].astype(str)
        fit_ids = set(ids[roles == 'FIT'])
        inner_ids = set(ids[roles == 'INNER'])
        outer_ids = ids[roles == 'OUTER']
        canonical_in = [i for ff,i in ik if ff == f]
        canonical_out = [i for ff,i in outer if ff == f]
        assert len(set(canonical_in)) == len(canonical_in)
        assert set(canonical_in) == inner_ids
        assert not fit_ids & inner_ids and not fit_ids & set(outer_ids) and not inner_ids & set(outer_ids)
        assert np.array_equal(outer_ids, np.array(canonical_out)), 'Worker A assumes source OUTER order; mismatch aborts'
    lgb_in = csv_probs(REPO / 'inner_predictions.csv', ik, inner=True)
    lgb_out = csv_probs(REPO / 'outer_predictions.csv', ok)
    tab_in_list = []
    for f in range(3):
        keys = [i for ff,i in ik if ff == f]
        tab_in_list.append(csv_probs(TAB / f'fold_{f}/inner_predictions.csv', keys))
    tab_out = csv_probs(TAB / 'original_oof_predictions.csv', ok)
    base_in = (.45*lgb_in + .45*np.concatenate(tab_in_list) + .10*np.concatenate(pc_in)) * ALPHA
    base_out = (.45*lgb_out + .45*tab_out + .10*np.concatenate(pc_out)) * ALPHA
    base_in /= base_in.sum(1, keepdims=True); base_out /= base_out.sum(1, keepdims=True)
    with npz(A) as z:
        assert np.array_equal(z['y_inner'], iy)
        scores_in = np.column_stack([1-z['p_spec_gate_in'], z['p_ovr_std_in']])
        scores_out = np.column_stack([1-z['p_spec_gate_out'], z['p_ovr_std_out']])
        m123_in, m123_out = z['p_m123_std_in'], z['p_m123_std_out']
    for array in [base_in, base_out, scores_in, scores_out, m123_in, m123_out]:
        assert np.isfinite(array).all() and np.all((array >= 0) & (array <= 1))
    x_in = features(base_in, scores_in, m123_in)
    x_out = features(base_out, scores_out, m123_out)
    all_out = {name: np.empty(len(outer), dtype=np.int64) for name in CANDIDATES}
    selected_out = np.empty(len(outer), dtype=np.int64)
    selected_oof = []
    fold_decisions = []
    for f in range(3):
        guard(f'fold{f}_select_crossfit')
        ii = np.flatnonzero((fi == f) & is_select)
        oo = np.flatnonzero(fo == f)
        assert not (set(ik[i][1] for i in ii) & set(ok[i] for i in oo))
        x, y = x_in[ii], iy[ii]
        cv = StratifiedKFold(3, shuffle=True, random_state=2705)
        oof = {name: np.empty(len(y), dtype=np.int64) for name in CANDIDATES}
        splits = []
        for tr, va in cv.split(x, y):
            assert not set(tr) & set(va)
            models = fit_models(x[tr], y[tr])
            r = infer(models, x[va], base_in[ii[va]])
            p = candidates(base_in[ii[va]], scores_in[ii[va]], r)
            for name in CANDIDATES:
                oof[name][va] = p[name]
            splits.append(dict(train_ids=[ik[ii[j]][1] for j in tr], valid_ids=[ik[ii[j]][1] for j in va],
                               missing_models=[j for j,m in enumerate(models) if m is None]))
            del models
        winner, decision = choose(y, oof)
        decision.update(fold=f, select_n=len(y), splits=splits)
        fold_decisions.append(decision)
        selected_oof.append(dict(fold=f, y=y.tolist(), predictions={n:p.tolist() for n,p in oof.items()}))
        models = fit_models(x, y)
        decision['final_missing_models'] = [j for j,m in enumerate(models) if m is None]
        dump(f'model_fold_{f}.json', serialize_models(models))
        output = candidates(base_out[oo], scores_out[oo], infer(models, x_out[oo], base_out[oo]))
        for name in CANDIDATES:
            all_out[name][oo] = output[name]
        selected_out[oo] = output[winner]
        print(f'fold {f}: SELECT={len(y)}, OOF selected={winner}, correct={decision["oof_metrics"][winner]["correct"]}', flush=True)
        del models
        gc.collect()
    # Complete all choices and predictions BEFORE reading OUTER labels.
    np.savez_compressed(HERE / 'predictions_frozen.npz', ids=np.array(ok), folds=fo,
                        selected=selected_out, scores=scores_out, base_prob=base_out,
                        **{f'pred_{n}':p for n,p in all_out.items()})
    dump('selection_frozen.json', dict(time=datetime.now(timezone.utc).isoformat(), folds=fold_decisions,
         candidates=CANDIDATES, outer_labels_read=False, purpose='development diagnostic, no independent test claim'))
    dump('select_oof_predictions.json', selected_oof)
    guard('evaluate_after_predictions_frozen')
    oy_list = []
    for f in range(3):
        with npz(R2 / f'fold_{f}_baseline_lightgbm_outer.npz') as z:
            oy_list.extend(z['y_true'].tolist())
    oy = np.asarray(oy_list, dtype=np.int64)
    with npz(A) as z:
        assert np.array_equal(z['y_outer'], oy)
    historical = {}
    with npz(T3) as z:
        assert np.array_equal(z['outer_ids'].astype(str), np.array(ok))
        assert np.array_equal(z['outer_y'], oy)
        for k in ['pred_b2_trio', 'pred_grand_fusion']:
            historical[k] = metrics(oy, z[k])
    bm = all_out['baseline']
    refs = dict(same_condition_baseline=bm, seed42=np.concatenate(p42_out).argmax(1), five_seed=lgb_out.argmax(1))
    results = dict(time=datetime.now(timezone.utc).isoformat(), selected=metrics(oy, selected_out),
                   baseline=metrics(oy,bm), candidates={n:metrics(oy,p) for n,p in all_out.items()},
                   selected_vs={n:paired(oy,p,selected_out) for n,p in refs.items()},
                   candidate_vs_same_baseline={n:paired(oy,bm,p) for n,p in all_out.items()},
                   references={n:metrics(oy,p) for n,p in refs.items()}, historical=historical,
                   groups=group_report(oy,bm,scores_out,selected_out),
                   fold_results=[dict(fold=f, selected=metrics(oy[fo==f],selected_out[fo==f]),
                                      baseline=metrics(oy[fo==f],bm[fo==f])) for f in range(3)],
                   adoption=False, independent_evaluation=False, observation_day_subgroups='not available in probability-only inputs')
    tp = results['selected']['tp']
    results['protection'] = dict(single_seed_reference_pass=tp[0]>=2389 and tp[3]>=90,
                                 historical_five_seed_reference_pass=tp[0]>=2381 and tp[3]>=92,
                                 selected_vs_same_baseline_tp0_tp3_no_drop=tp[0]>=results['baseline']['tp'][0] and tp[3]>=results['baseline']['tp'][3])
    for name in ['pair01','pair02']:
        g=results['groups'][name]
        counts=g.get('true_counts',[0]*4)
        g['forced_exclusion_true_outside_pair']=sum(counts[c] for c in ((2,3) if name=='pair01' else (1,3)))
    dump('results.json', results)
    with (HERE / 'predictions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['rfid_id','fold','y_true','selected']+CANDIDATES)
        w.writerows([ok[i],int(fo[i]),int(oy[i]),int(selected_out[i])]+[int(all_out[n][i]) for n in CANDIDATES] for i in range(len(oy)))
    INPUTS.update([HERE/'ROUND_PLAN.md', Path(__file__)])
    manifest=[]
    for path in sorted(INPUTS):
        h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024), b''):
                h.update(chunk)
        manifest.append(dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest()))
    dump('input_manifest.json',manifest)
    dump('environment.json',dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
         scipy=scipy.__version__, sklearn=sklearn.__version__, pid=os.getpid(), threads=1,
         priority=str(psutil.Process().nice()), actual_parent_model='not asserted; session model not changed by config',
         auxiliary_request='gpt-6-luna/xhigh; collaboration spawn_agent task team_label_evidence'))
    guard('complete')
    print(json.dumps(dict(selected=results['selected'],baseline=results['baseline'],protection=results['protection']),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    run()
