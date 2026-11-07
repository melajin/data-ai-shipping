"""Assemble source evidence and a checked local archive; never uploads it."""
from pathlib import Path
from datetime import datetime
import hashlib
import importlib.metadata
import json
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'deliverables/testb_system_20261106'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    sources = []
    def copy(source, relative):
        source = ROOT / source
        destination = PACKAGE / relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        sources.append({'original':source.relative_to(ROOT).as_posix(),
                        'copy':relative,'sha256':sha(destination)})
    official = 'data/reference/competition_20261019/2026 데이터 분석대회/공지사항/'
    for name in ['공지-문제 과제.png','공지-문제개요.png','공지-데이터 설명.png','공지-평가기준.png']:
        copy(official+name,'sources/official/'+name)
    mapping = {
        '26_11_5/20261105_분석종합과_TestB_실행계획.md':'sources/official/recorded_organizer_answers.md',
        'testB/final/CURRENT_STATUS.md':'sources/experiments/testb_status.md',
        'testB/final/round_013_gap_signal/result.txt':'sources/experiments/gap_signal.txt',
        'testB/final/round_013_drift/결과.md':'sources/experiments/drift.md',
        'testB/final/round_013_gap_jump_ratio/metrics.json':'sources/experiments/gap_jump_ratio.json',
        'testB/final/round_013_fleet_simultaneity/results.json':'sources/experiments/fleet_results.json',
        'testB/final/round_013_fleet_simultaneity/결과.md':'sources/experiments/fleet_notes.md',
        'testB/final/round_013_offhours_weight/results.json':'sources/experiments/offhours_results.json',
        'testB/final/round_013_offhours_weight/event_results.csv':'sources/experiments/offhours_events.csv',
        'testB/final/round_013_offhours_weight/결과.md':'sources/experiments/offhours_notes.md',
        'testB/final/round_013_metric_rescore/RESCORE.md':'sources/experiments/development_rescore.md',
        '11_04_final/rounds/round_029_domain_features_dtype_correction/ROUND_REPORT.md':'sources/experiments/testa_round029.md',
        'tools/build_testb_report.py':'reports/build_report.py',
    }
    for a,b in mapping.items(): copy(a,b)
    (PACKAGE/'sources/copy_manifest.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.path.insert(0,str(ROOT/'tmp/pdf_deps'))
    report_deps=['reportlab','matplotlib','pillow','psutil']
    (PACKAGE/'reports/requirements.txt').write_text(''.join(f'{x}=={importlib.metadata.version(x)}\n' for x in report_deps),encoding='utf-8')
    summary=json.loads((PACKAGE/'results/reproduction_001/summary.json').read_text(encoding='utf-8'))
    assert summary['parity']['all_checks_passed']
    validation={
        'completed_at':datetime.now().astimezone().isoformat(),
        'scope':'Test B fixed-baseline executable reproduction and Korean report',
        'numeric_parity':summary['parity'],
        'baseline_focused_tests':{'count':4,'exit_code':0,'source':'worker execution and independent source review'},
        'portable_causal_tests':{'count':26,'exit_code':0,'source':'parent execution from package/support'},
        'pdf_visual_qa':{'pages':20,'renderer':'PyMuPDF','all_pages_text_and_bounds_inspected':True,
                         'max_content_bottom_pt':786.6,'page_height_pt':841.9,'bottom_margin_pt':45,
                         'visually_rendered_pages':[1,7,13,16],
                         'fixed':'U+2212 minus rendered as notdef in the registered TTF; replaced with ASCII hyphen and rebuilt',
                         'note':'2026-11-06 revision adds the judgement procedure, two-axis measurement and Round014-021 update log'},
        'independent_review':'no blocking issue; source functions, metrics, artifact hashes and metadata correction verified',
        'official_f1':None,'live_detection_validated':False,'external_submission':False,
    }
    (PACKAGE/'reports/verification.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
    files=sorted(p for p in PACKAGE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.json')
    manifest={'created_at':datetime.now().astimezone().isoformat(),
              'files':[{'path':p.relative_to(PACKAGE).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]}
    (PACKAGE/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=PACKAGE.with_suffix('.zip')
    if archive.exists(): raise FileExistsError(f'Archive already exists: {archive}')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files+[PACKAGE/'MANIFEST.json']:
            z.write(p,arcname=PACKAGE.name+'/'+p.relative_to(PACKAGE).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    print(json.dumps({'archive':str(archive),'archive_bytes':archive.stat().st_size,
                      'files':len(files)+1,'sha256':sha(archive)},ensure_ascii=False))


if __name__ == '__main__':main()
