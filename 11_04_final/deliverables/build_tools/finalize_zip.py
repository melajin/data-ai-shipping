from pathlib import Path
import hashlib
import json
import shutil
import zipfile

root = Path(__file__).resolve().parents[2]
package = root / 'deliverables/rounds_001_002_team_package'
review = root / 'delivery_review'
assert (review / 'REVIEW.md').is_file()
assert (package / 'validation/model_replay.json').is_file()
assert json.loads((package / 'validation/model_replay.json').read_text())['status'] == 'PASS'
(package / 'delivery_review').mkdir(exist_ok=True)
for name in ('REVIEW.md', 'review.json'):
    shutil.copy2(review / name, package / 'delivery_review' / name)
archive = root / 'deliverables/선박조업분류_1차_2차_결과보고서_팀원전달.zip'
assert not archive.exists(), 'Refusing to overwrite an existing delivery archive'
files = sorted(p for p in package.rglob('*') if p.is_file())
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in files:
        z.write(p, (Path(package.name) / p.relative_to(package)).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.infolist()) == len(files)
    for p in files:
        name = (Path(package.name) / p.relative_to(package)).as_posix()
        assert hashlib.sha256(z.read(name)).digest() == hashlib.sha256(p.read_bytes()).digest(), name
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
receipt = {'status': 'PASS', 'archive_name': archive.name, 'bytes': archive.stat().st_size,
           'sha256': digest, 'file_count': len(files), 'uncompressed_bytes': sum(p.stat().st_size for p in files),
           'zip_crc_test': 'PASS', 'each_zip_member_sha256_matches_staging': True,
           'staging_model_replay_status': 'PASS', 'training_started': False, 'round003_started': False}
(root / 'deliverables/ZIP_VERIFICATION.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=True, indent=2))
