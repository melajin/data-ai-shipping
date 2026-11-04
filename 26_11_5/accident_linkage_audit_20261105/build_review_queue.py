"""Derive review queues from saved linkage evidence; no learning or new matching."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd


def fingerprint(path):
    return {'path': str(path.resolve()), 'size_bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.input_dir.resolve(), args.output_dir.resolve()
    if output.exists():
        raise FileExistsError('Use a new output directory')
    inputs = [source / 'event_audit.csv', source / 'candidate_vessels.csv']
    before = [fingerprint(path) for path in inputs]
    events = pd.read_csv(inputs[0], encoding='utf-8-sig')
    candidates = pd.read_csv(inputs[1], encoding='utf-8-sig', dtype={'rfid_id': str})
    conditions = [(h, r) for h in (0, 1, 2) for r in (1000, 3000, 5000)]
    relation = {
        key: set(group.rfid_id)
        for key, group in candidates.groupby(['event_id', 'hour_bucket_radius', 'spatial_radius_m'])
    }
    queue = events.copy()
    detail = []
    for event in events.itertuples(index=False):
        base = relation.get((event.event_id, 1, 5000), set())
        narrow = relation.get((event.event_id, 0, 1000), set())
        wide = relation.get((event.event_id, 2, 5000), set())
        stable = len(base) == 1 and all(relation.get((event.event_id, h, r), set()) == base for h, r in conditions)
        if not event.metadata_valid:
            category = 'invalid_metadata'
        elif not base:
            category = 'baseline_none_wider_candidate' if wide else 'no_candidate_all_conditions'
        elif len(base) > 1:
            category = 'baseline_multiple_candidates'
        elif event.single_candidate_does_not_cover_reported_multi_vessel_event:
            category = 'baseline_single_but_multi_vessel_accident'
        elif stable:
            category = 'same_single_candidate_all_nine_conditions'
        else:
            category = 'baseline_single_condition_sensitive'
        detail.append({
            'event_id': event.event_id,
            'review_category': category,
            'baseline_candidate_ids': '|'.join(sorted(base)),
            'narrowest_candidate_count': len(narrow),
            'widest_candidate_count': len(wide),
            'same_single_candidate_all_nine_conditions': stable,
            'baseline_single_becomes_multiple_when_time_widened': len(base) == 1 and len(wide) > 1,
            'baseline_single_present_in_narrowest_condition': len(base) == 1 and base.issubset(narrow),
            'confirmed_accident_vessel': False,
            'eligible_as_confirmed_training_label': False,
        })
    queue = queue.merge(pd.DataFrame(detail), on='event_id', how='left', validate='one_to_one')
    base_rows = candidates[(candidates.hour_bucket_radius == 1) & (candidates.spatial_radius_m == 5000)]
    singles = queue[queue.baseline_candidate_vessel_count == 1].copy()
    single_base_rows = base_rows[base_rows.event_id.isin(singles.event_id)]
    singles = singles.merge(single_base_rows, on='event_id', how='left', validate='one_to_one', suffixes=('', '_candidate'))
    repeated = base_rows.groupby('rfid_id').agg(
        candidate_event_count=('event_id', 'nunique'),
        event_ids=('event_id', lambda values: '|'.join(sorted(set(values)))),
    ).reset_index()
    repeated = repeated[repeated.candidate_event_count > 1].sort_values(
        ['candidate_event_count', 'rfid_id'], ascending=[False, True])
    no_candidates = queue[queue.baseline_candidate_vessel_count == 0]
    counts = queue.review_category.value_counts().to_dict()
    summary = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Derived evidence organization only; no confirmed identity or accident labels',
        'all_events': len(queue),
        'category_counts': {key: int(value) for key, value in counts.items()},
        'baseline_single_count': len(singles),
        'same_single_candidate_all_nine_conditions': int(queue.same_single_candidate_all_nine_conditions.sum()),
        'baseline_single_present_in_narrowest_condition': int(queue.baseline_single_present_in_narrowest_condition.sum()),
        'baseline_single_becomes_multiple_when_time_widened': int(queue.baseline_single_becomes_multiple_when_time_widened.sum()),
        'baseline_none_recovered_only_by_wider_condition': int((no_candidates.widest_candidate_count > 0).sum()),
        'baseline_distinct_candidate_vessels': int(base_rows.rfid_id.nunique()),
        'baseline_candidate_vessels_linked_to_multiple_events': len(repeated),
        'maximum_candidate_events_per_vessel': int(repeated.candidate_event_count.max()) if len(repeated) else 1,
        'widest_distinct_candidate_vessels': int(candidates.rfid_id.nunique()),
        'all_condition_event_vessel_associations': len(candidates),
        'stable_single_event_ids': queue.loc[queue.same_single_candidate_all_nine_conditions, 'event_id'].tolist(),
        'single_but_multi_vessel_event_ids': queue.loc[queue.single_candidate_does_not_cover_reported_multi_vessel_event, 'event_id'].tolist(),
        'baseline_single_distance_quantiles_m': {
            str(q): float(singles.minimum_distance_row__centroid_distance_m.quantile(q)) for q in (0, 0.25, 0.5, 0.75, 1)
        },
        'baseline_single_minimum_distance_row_start_abs_residual_over_60min': int(
            (singles.minimum_distance_row__track_hour_start_minus_accident_minutes.abs() > 60).sum()),
        'input_pre': before,
        'script': fingerprint(Path(__file__)),
        'command_argv': [sys.executable, *sys.argv],
    }
    assert len(queue) == events.event_id.nunique()
    assert sum(summary['category_counts'].values()) == len(queue)
    assert len(singles) == int((events.baseline_candidate_vessel_count == 1).sum())
    after = [fingerprint(path) for path in inputs]
    assert before == after
    output.mkdir(parents=True, exist_ok=False)
    queue.to_csv(output / 'review_queue.csv', index=False, encoding='utf-8-sig')
    singles.to_csv(output / 'baseline_single_review.csv', index=False, encoding='utf-8-sig')
    repeated.to_csv(output / 'repeated_candidate_vessels.csv', index=False, encoding='utf-8-sig')
    summary['input_post'] = after
    summary['input_unchanged'] = before == after
    summary['outputs'] = [fingerprint(path) for path in sorted(output.glob('*.csv'))]
    (output / 'review_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key not in ('input_pre', 'input_post', 'outputs', 'script', 'command_argv')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
