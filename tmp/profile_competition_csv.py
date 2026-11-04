from pathlib import Path
import csv, io, json, hashlib, collections, datetime, math, sys, re

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
from inspect_data import _validate_geometry
source = root / 'data/reference/competition_20261019/2026 데이터 분석대회/공지사항/어선 과제 샘플데이터.csv'
content = source.read_bytes()
text = content.decode('utf-8-sig')
records = list(csv.reader(io.StringIO(text, newline='')))
header, rows = records[0], records[1:]
expected = ['part_dt','rfid_id','rfid_time','geom','fishing_code']
vessel_alias = {}
detail = []
points_all = []
for number, values in enumerate(rows, start=2):
    assert len(values) == len(header)
    row = dict(zip(expected, values[:5]))
    vessel_alias.setdefault(row['rfid_id'], 'V%02d' % (len(vessel_alias)+1))
    validation = _validate_geometry(row['geom'])
    assert validation.state == 'structured_nonempty' and validation.issue_code is None
    parts = [[tuple(float(n) for n in pair.split()) for pair in part.split(',')] for part in re.findall(r'\(([^()]+)\)', row['geom'])]
    assert tuple(map(len,parts)) == validation.part_point_counts
    counts = [len(p) for p in parts]
    points = [tuple(p) for part in parts for p in part]
    points_all.extend(points)
    detail.append({'csv_line': number, 'vessel_alias': vessel_alias[row['rfid_id']], 'date': row['part_dt'], 'hour': int(row['rfid_time']), 'label': row['fishing_code'], 'parts':len(parts), 'points':sum(counts), 'part_point_counts':counts, 'unique_points':len(set(points)), 'adjacent_repeats':sum(a==b for part in parts for a,b in zip(part,part[1:])), 'closed_parts':sum(part[0]==part[-1] for part in parts), 'finite_xy':all(len(p)==2 and all(math.isfinite(x) for x in p) for p in points), 'lonlat_bounds_if_assumed':all(-180<=p[0]<=180 and -90<=p[1]<=90 for p in points), 'valid_yyyymmdd': datetime.datetime.strptime(row['part_dt'],'%Y%m%d').strftime('%Y%m%d')==row['part_dt'], 'hour_0_23':0<=int(row['rfid_time'])<=23})

def distribution(values):
    return dict(collections.Counter(values))
keys = [tuple(r[:3]) for r in rows]
blanks = {name:sum(r[i].strip()=='' for r in rows) for i,name in enumerate(expected)}
report = {
    'source': str(source.relative_to(root)).replace('\\','/'),
    'sha256': hashlib.sha256(content).hexdigest(), 'bytes':len(content),
    'encoding':'UTF-8-SIG compatible' if content.startswith(b'\xef\xbb\xbf') else 'UTF-8, no BOM',
    'delimiter':',', 'data_rows':len(rows), 'columns_physical':len(header), 'named_columns':expected,
    'unnamed_columns_1based':[i+1 for i,n in enumerate(header) if not n],
    'unnamed_all_blank':all(r[i]=='' for r in rows for i,n in enumerate(header) if not n),
    'row_widths':distribution(len(r) for r in rows), 'blank_counts':blanks,
    'vessels':len(vessel_alias),'dates':distribution(r[0] for r in rows),
    'hours':distribution(r[2] for r in rows),'labels':distribution(r[4] for r in rows),
    'exact_duplicate_rows':len(rows)-len(set(tuple(r) for r in rows)),
    'duplicate_key_excess_rows':len(keys)-len(set(keys)),
    'geometry_types':{'MultiLineString':len(detail)},
    'parts_total':sum(r['parts'] for r in detail),'points_total':sum(r['points'] for r in detail),
    'unique_xy_dataset':len(set(points_all)),
    'adjacent_repeats_total':sum(r['adjacent_repeats'] for r in detail),
    'per_row':detail,
    'scope':'Entire sole CSV in supplied archive; no model training, no distance/speed calculation. Vessel aliases are local inspection labels, not original identifiers.'
}
out = root / 'outputs/competition_20261019/csv_profile.json'
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
