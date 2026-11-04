from pathlib import Path
from urllib.parse import unquote,quote
import re,json,hashlib
root = Path(__file__).resolve().parents[1]
out = root/'outputs/competition_20261019'
manifest = json.loads((out/'archive_manifest.json').read_text(encoding='utf-8'))
checked = 0
for record in manifest['files']:
    path = root/record['local_path']
    assert path.stat().st_size == record['bytes']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    checked += 1
assert hashlib.sha256(Path(manifest['archive']).read_bytes()).hexdigest() == manifest['archive_sha256']
files = [root/'2026 데이터 분석대회 데이터 분석 정리.md', *sorted((root/'docs/competition_20261019').glob('*.md'))]
missing=[]
links=0
for path in files:
    text=path.read_text(encoding='utf-8')
    fixed=text.replace(quote('01_데이터구조와_실측집계.md',safe='/._-'),quote('01_데이터구조와_직접집계.md',safe='/._-'))
    if fixed!=text:
        path.write_text(fixed,encoding='utf-8')
        text=fixed
    assert '\ufffd' not in text
    assert text.startswith('---\n')
    for href in re.findall(r'\[[^\]]*\]\(([^\n)]*)\)', text):
        if '://' in href or href.startswith('#'):
            continue
        links += 1
        target = unquote(href.split('#',1)[0])
        if not (path.parent/target).resolve().exists():
            missing.append({'file':str(path.relative_to(root)), 'target':target})
result={'checked_source_files':checked, 'archive_hash_unchanged':True,'notes_checked':len(files),'links_checked':links,'missing_links':missing,'encoding_replacement_characters':0}
(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
assert not missing
