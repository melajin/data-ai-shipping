from pathlib import Path
import zipfile, hashlib, json, collections

root = Path(__file__).resolve().parents[1]
archive = Path('C:/Users/dlehs/Documents/카카오톡 받은 파일/2026 데이터 분석대회.zip')
dest = root / 'data/reference/competition_20261019'
out = root / 'outputs/competition_20261019'
dest.mkdir(parents=True, exist_ok=True)
out.mkdir(parents=True, exist_ok=True)
records = []
with zipfile.ZipFile(archive) as z:
    for item in z.infolist():
        if item.is_dir():
            continue
        target = (dest / item.filename).resolve()
        if not target.is_relative_to(dest.resolve()) or item.file_size > 100_000_000:
            raise ValueError('unsafe or unexpectedly large entry')
        content = z.read(item)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise ValueError('refusing to overwrite different file')
        target.write_bytes(content)
        records.append({'member': item.filename, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'local_path': str(target.relative_to(root)).replace('\\','/')})
manifest = {'inspection_date': '2026-10-19', 'archive': str(archive), 'archive_bytes': archive.stat().st_size, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': records, 'extensions': dict(collections.Counter(Path(r['member']).suffix.lower() for r in records))}
(out / 'archive_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if k != 'files'},ensure_ascii=False,indent=2))

from pypdf import PdfReader
texts = out / 'extracted_text'
texts.mkdir(exist_ok=True)
for record in records:
    path = root / record['local_path']
    if path.suffix.lower() == '.pdf':
        reader = PdfReader(path)
        pages = ['\n\n## PAGE %d\n\n%s' % (i+1, p.extract_text() or '') for i,p in enumerate(reader.pages)]
        (texts / (path.stem + '.txt')).write_text(''.join(pages), encoding='utf-8')
        print(path.name, 'pages=', len(pages), 'chars=', sum(map(len,pages)))
