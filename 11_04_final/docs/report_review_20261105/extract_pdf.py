from pathlib import Path
import json,hashlib,importlib.util
from pypdf import PdfReader
p=Path('C:/Users/dlehs/Downloads/선박 업종 분류 정확도 0.70 달성을 위한 기술 진단 및 종합 실행 로드맵.pdf')
o=Path('docs/report_review_20261105');r=PdfReader(p)
t='\n\n'.join(f'=== PAGE {i+1} ===\n'+(x.extract_text() or '') for i,x in enumerate(r.pages))
(o/'pdf_text.txt').write_text(t,encoding='utf-8')
meta={'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pages':len(r.pages),'chars':len(t),'pymupdf':bool(importlib.util.find_spec('fitz')),'pypdfium2':bool(importlib.util.find_spec('pypdfium2'))}
(o/'pdf_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(meta,ensure_ascii=False))
