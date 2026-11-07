"""Read-only ZIP intake; compare small XLSX bytes and CSV size/header only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import time
import zipfile


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def checked_member(name):
    relative = PurePosixPath(name.replace('\\', '/'))
    if relative.is_absolute() or '..' in relative.parts or any(':' in p for p in relative.parts):
        raise ValueError('Unsafe ZIP member path')
    return relative


def header_info(stream):
    data = stream.readline(8192)
    return {'first_physical_line_sha256': hashlib.sha256(data).hexdigest(),
            'first_physical_line_bytes': len(data),
            'line_complete_within_limit': data.endswith(b'\n')}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--old-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    old_root = args.old_root.resolve(strict=True)
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError('Output must be a new directory')
    if output == old_root or old_root in output.parents or output == archive.parent:
        raise ValueError('Use a separate project output directory')
    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    before = archive.stat()
    sha_before = file_hash(archive)
    entries, extracted = [], []
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            relative = checked_member(entry.filename)
            old_path = old_root.joinpath(*relative.parts)
            row = {'name': entry.filename, 'is_directory': entry.is_dir(),
                   'uncompressed_bytes': entry.file_size, 'compressed_bytes': entry.compress_size,
                   'zip_crc32': f'{entry.CRC:08x}', 'zip_member_datetime': entry.date_time,
                   'old_exact_path': str(old_path), 'old_exact_path_exists': old_path.exists()}
            if entry.is_dir():
                entries.append(row)
                continue
            if old_path.is_file():
                row['old_bytes'] = old_path.stat().st_size
                row['same_size'] = old_path.stat().st_size == entry.file_size
            suffix = relative.suffix.lower()
            if suffix == '.xlsx':
                if entry.file_size > 50 * 1024 * 1024:
                    raise ValueError('XLSX too large for small-file intake')
                data = zipped.read(entry)
                row['new_sha256'] = hashlib.sha256(data).hexdigest()
                small_path = output / f'reference_{len(extracted) + 1:02d}_{relative.name}'
                with small_path.open('xb') as stream:
                    stream.write(data)
                row['extracted_reference_path'] = str(small_path)
                if old_path.is_file():
                    row['old_sha256'] = file_hash(old_path)
                    row['byte_identical_to_old'] = row['new_sha256'] == row['old_sha256']
                extracted.append(row['name'])
            elif suffix == '.csv':
                with zipped.open(entry) as stream:
                    row['new_header'] = header_info(stream)
                if old_path.is_file():
                    with old_path.open('rb') as stream:
                        row['old_header'] = header_info(stream)
                    row['header_identical_to_old'] = row['new_header'] == row['old_header']
                row['full_content_identity_verified'] = False
            entries.append(row)
    after = archive.stat()
    sha_after = file_hash(archive)
    unchanged = (before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns and sha_before == sha_after)
    csvs = [r for r in entries if r['name'].lower().endswith('.csv')]
    xlsxs = [r for r in entries if r['name'].lower().endswith('.xlsx')]
    manifest = {'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                'archive_path': str(archive), 'archive_bytes': before.st_size,
                'archive_sha256_before': sha_before, 'archive_sha256_after': sha_after,
                'archive_unchanged': unchanged, 'archive_entry_count': len(entries),
                'regular_file_count': sum(not r['is_directory'] for r in entries),
                'total_uncompressed_file_bytes': sum(r['uncompressed_bytes'] for r in entries),
                'csv_count': len(csvs), 'xlsx_count': len(xlsxs),
                'csv_exact_old_path_count': sum(r['old_exact_path_exists'] for r in csvs),
                'csv_same_size_count': sum(r.get('same_size', False) for r in csvs),
                'csv_same_header_count': sum(r.get('header_identical_to_old', False) for r in csvs),
                'csv_full_content_identity_verified': False,
                'xlsx_byte_identical_count': sum(r.get('byte_identical_to_old', False) for r in xlsxs),
                'small_references_extracted': extracted,
                'full_archive_extracted': False,
                'script_sha256': file_hash(Path(__file__)),
                'elapsed_seconds': time.perf_counter() - timer,
                'entries': entries}
    (output / 'archive_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in manifest.items() if key not in ('entries', 'small_references_extracted', 'archive_path')}, ensure_ascii=True))
    if not unchanged:
        raise RuntimeError('Input archive changed during intake')


if __name__ == '__main__':
    main()
