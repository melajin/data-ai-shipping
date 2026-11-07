"""Read-only, privacy-limited views used by the recorded live demo."""
import csv
import importlib.metadata
import json
from pathlib import Path
import sys

mode = sys.argv[1]
result = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('results/demo_run')
if mode == 'environment':
    print('Python ' + sys.version.split()[0])
    print('Compute: CPU (numpy / pandas / scipy); no GPU runtime')
    print('\nrequirements.txt / installed version')
    for line in Path('requirements.txt').read_text().splitlines():
        name, required = line.split('==')
        actual = importlib.metadata.version(name)
        print(f'  {name:10} required={required:8} installed={actual:8} match={required == actual}')
        assert required == actual
    print('\nFrozen baseline reproduction / no training')
else:
    summary = json.loads((result / 'summary.json').read_text(encoding='utf-8'))
    if mode == 'outputs':
        print('New output directory: ' + result.as_posix())
        for name in ('scored_rows.parquet', 'candidates.csv', 'summary.json'):
            p = result / name
            print(f'  {name:24} {p.stat().st_size:>10,} bytes')
        print('\nsummary.json')
        print('  status: ' + summary['status'])
        print('  counts: ' + json.dumps(summary['counts']))
        print('\ntelemetry (this run, from summary.json)')
        for name in ('elapsed_seconds', 'process_peak_mib'):
            print(f'  {name}: {summary["telemetry"][name]}')
    elif mode == 'parity':
        print('summary.json -> parity (complete block; compact nested objects)\n')
        print('{')
        for i, (key, value) in enumerate(summary['parity'].items()):
            suffix = ',' if i + 1 < len(summary['parity']) else ''
            if isinstance(value, dict):
                print(f'  "{key}":')
                print('    ' + json.dumps(value) + suffix)
            else:
                print(f'  "{key}": {json.dumps(value)}{suffix}')
        print('}')
        assert summary['parity']['all_checks_passed']
    elif mode == 'candidate':
        case = next(c for c in summary['sample_cases'] if c['case_type'] == 'median_peak_rank')
        with (result / 'candidates.csv').open(encoding='utf-8-sig', newline='') as stream:
            row = next(r for r in csv.DictReader(stream) if r['rfid_id'] == case['rfid_id'])
        print('candidates.csv -> median_peak_rank sample')
        print('Vessel identifier omitted from display (privacy).\n')
        for key in ('rank_by_peak', 'lead_label', 'score', 's_zone', 's_change', 's_gap',
                    'component_count', 'prior_observation_count', 'n_observations'):
            print(f'  {key:25} {row[key] or "missing"}')
        print('\nSelection: full-period maximum for this vessel (retrospective).')
        print('Score = mean of finite components; not an accident probability.')
        print('Candidate time is not confirmed accident time; timezone unconfirmed.')
    else:
        raise ValueError('Unknown view')
