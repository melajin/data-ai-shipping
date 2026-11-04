"""Read-only supporting workbook audit; no vessel identifiers in output."""
from pathlib import Path
from collections import Counter
import datetime
import hashlib
import json
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('F:/문제 데이터_수정_1027')
out = {'source_root': str(SOURCE), 'inspection': 'all workbook rows, structural aggregates only', 'files': []}
for path in sorted(SOURCE.rglob('*.xlsx')):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    entry = {'path': str(path), 'bytes': path.stat().st_size,
             'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'sheets': []}
    for sheet in workbook:
        rows = list(sheet.iter_rows(values_only=True))
        headers = [str(x) if x is not None else None for x in rows[0]]
        columns = []
        for i, header in enumerate(headers):
            values = [r[i] for r in rows[1:] if i < len(r) and r[i] is not None]
            item = {'column_1based': i+1, 'header': header, 'nonempty': len(values),
                    'types': dict(Counter(type(v).__name__ for v in values))}
            if header == '발생일시' and values:
                dates = [v.isoformat() for v in values if isinstance(v, (datetime.datetime, datetime.date))]
                item['date_min'] = min(dates) if dates else None
                item['date_max'] = max(dates) if dates else None
            if header in ('사고시각', '시각1', '시각2', '시각3') or (header is None and sheet.title == '테스트B'):
                item['year_prefix_counts'] = dict(Counter(str(v)[:4] for v in values))
            columns.append(item)
        entry['sheets'].append({'sheet': sheet.title, 'data_rows': len(rows)-1,
                                'columns': columns, 'headers': headers})
    workbook.close()
    out['files'].append(entry)
target = ROOT/'outputs'/'real_support_audit_20261028.json'
target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=True))
