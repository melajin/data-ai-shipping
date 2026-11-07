"""Independent saved-prediction arithmetic verification; no model refit/import."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / 'results.json').read_text(encoding='utf-8'))
    selection = json.loads((HERE / 'selection_frozen.json').read_text(encoding='utf-8'))
    names = selection['candidates']
    names_plus = ['selected'] + names
    cms = {n: [[0]*4 for _ in range(4)] for n in names_plus}
    ids = set()
    folds = {d['fold']:d for d in selection['folds']}
    changes = {n: [0,0] for n in names}
    for d in folds.values():
        b = d['oof_metrics']['baseline']['tp']
        eligible = [n for n in names if d['oof_metrics'][n]['tp'][0] >= b[0]
                    and d['oof_metrics'][n]['tp'][3] >= b[3]]
        expected = max(eligible,key=lambda n:(d['oof_metrics'][n]['correct'],d['oof_metrics'][n]['macro_f1'],-names.index(n)))
        assert d['selected'] == expected
        train_valid = set()
        for s in d['splits']:
            assert len(set(s['train_ids'])) == len(s['train_ids'])
            assert len(set(s['valid_ids'])) == len(s['valid_ids'])
            assert not set(s['train_ids']) & set(s['valid_ids'])
            assert not train_valid & set(s['valid_ids'])
            train_valid.update(s['valid_ids'])
        assert len(train_valid) == d['select_n']
    with (HERE / 'predictions.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            vid, fold, y = r['rfid_id'], int(r['fold']), int(r['y_true'])
            assert vid not in ids
            ids.add(vid)
            assert r['selected'] == r[folds[fold]['selected']]
            base = int(r['baseline'])
            for n in names_plus:
                p=int(r[n]); assert 0<=p<4
                cms[n][y][p] += 1
            for n in names:
                p=int(r[n]); changes[n][0] += base != y and p == y
                changes[n][1] += base == y and p != y
    assert len(ids) == 5897
    for n in names_plus:
        cm=cms[n]
        m=result['selected'] if n=='selected' else result['candidates'][n]
        assert cm == m['cm']
        correct=sum(cm[c][c] for c in range(4))
        f1=[]
        for c in range(4):
            den=sum(cm[c])+sum(row[c] for row in cm)
            f1.append(2*cm[c][c]/den if den else 0)
        assert correct == m['correct']
        assert abs(correct/5897-m['micro_f1']) < 1e-12
        assert abs(sum(f1)/4-m['macro_f1']) < 1e-12
        if n != 'selected':
            p=result['candidate_vs_same_baseline'][n]
            assert changes[n] == [p['gain'],p['loss']]
    manifest=json.loads((HERE/'input_manifest.json').read_text(encoding='utf-8'))
    for r in manifest:
        h=hashlib.sha256()
        with Path(r['path']).open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        assert h.hexdigest() == r['sha256']
    out=dict(passed=True, rows=len(ids), candidate_metrics_checked=len(names_plus),
             input_hashes_checked=len(manifest), selection_rule_recomputed=True,
             split_disjointness_checked=True, scope='saved prediction arithmetic; no independent generalization or hardware test')
    (HERE/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    main()
