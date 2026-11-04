from pathlib import Path
from urllib.parse import unquote
import json,hashlib,re,sys

root=Path(__file__).resolve().parents[1]
out=root/'outputs/competition_20261019'
report_path=out/'proposal_integration_verification.json'
manifest=json.loads((out/'archive_manifest.json').read_text(encoding='utf-8'))
attachment=json.loads((out/'proposal_attachment.json').read_text(encoding='utf-8'))
for record in manifest['files']:
    source=root/record['local_path']
    assert source.stat().st_size==record['bytes']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256']
assert hashlib.sha256(Path(manifest['archive']).read_bytes()).hexdigest()==manifest['archive_sha256']
original=Path(attachment['source']).read_bytes()
copy=(root/attachment['local_copy']).read_bytes()
assert original==copy and len(original)==attachment['bytes']
assert hashlib.sha256(original).hexdigest()==attachment['sha256']
assert attachment['pages']==10
report_path.write_text('{"status":"checking"}\n',encoding='utf-8')
files=[root/'2026 데이터 분석대회 데이터 분석 정리.md',*sorted((root/'docs/competition_20261019').glob('*.md')),root/'어선 항적 분석 소개.md',root/'어선 항적 통합 학습 가이드.md',root/'docs/fishing_execution_plan.md',out/'proposal_integration_evidence.md',out/'proposal_integration_decision.md',out/'proposal_integration_review.md']

def links_in(text):
    text=re.sub(r'^```[^\n]*\n.*?^```\s*$', '',text, flags=re.S|re.M)
    for match in re.finditer(r'\]\(',text):
        pos=match.end()
        start=pos
        depth=1
        while pos<len(text) and depth:
            c=text[pos]
            if c=='\\':
                pos+=2
                continue
            if c=='(':
                depth+=1
            if c==')':
                depth-=1
            pos+=1
        if depth==0:
            yield text[start:pos-1]

missing=[]
total=0
for path in files:
    if not path.exists():
        missing.append({'file':str(path.relative_to(root)),'target':'file pending'})
        continue
    text=path.read_text(encoding='utf-8')
    assert '\ufffd' not in text
    assert not re.search(r'[\u3040-\u30ff]',text)
    for href in links_in(text):
        if '://' in href or href.startswith('#'):
            continue
        href=href.strip('<>')
        target=unquote(href.split('#',1)[0])
        total+=1
        if not (path.parent/target).resolve().exists():
            missing.append({'file':str(path.relative_to(root)),'target':target})
profile=json.loads((out/'csv_profile.json').read_text(encoding='utf-8'))
assert profile['data_rows']==10 and profile['parts_total']==16 and profile['points_total']==246 and profile['adjacent_repeats_total']==158
assert hashlib.sha256((root/profile['source']).read_bytes()).hexdigest()==profile['sha256']
result={'status':'passed' if not missing else 'pending_or_failed','inspection_date':'2026-10-19','zip_member_sources_verified':len(manifest['files']),'additional_pdf_sources_verified':1,'total_preserved_member_and_additional_sources':len(manifest['files'])+1,'original_zip_hash_unchanged':True,'additional_pdf_byte_identity':True,'additional_pdf_sha256':attachment['sha256'],'additional_pdf_pages':10,'csv_source_hash_unchanged':True,'sample_profile_counts_unchanged':True,'markdown_files_checked':len(files),'local_links_checked':total,'missing_links':missing,'pdf_visual_review_scope':'body pages 3-10, including figures and final plan table; cover date checked in extracted text','model_training_or_external_collection_performed':False}
report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
if '--final' in sys.argv:
    assert not missing
