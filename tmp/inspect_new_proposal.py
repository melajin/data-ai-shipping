from pathlib import Path
import hashlib,json
from pypdf import PdfReader
import pypdfium2 as pdfium

root=Path(__file__).resolve().parents[1]
source=Path('C:/Users/dlehs/Documents/카카오톡 받은 파일/IT종합설계프로젝트_제안서_C215192 최승빈.pdf')
dest=root/'data/reference/competition_20261019/additional'/source.name
dest.parent.mkdir(parents=True,exist_ok=True)
content=source.read_bytes()
if dest.exists() and dest.read_bytes()!=content:
    raise ValueError('refusing to replace different source')
dest.write_bytes(content)
reader=PdfReader(dest)
out=root/'outputs/competition_20261019'
parts=['## PAGE %d\n\n%s'%(i+1,page.extract_text() or '') for i,page in enumerate(reader.pages)]
(out/'proposal_attachment_text.txt').write_text('\n\n'.join(parts),encoding='utf-8')
report={'inspection_date':'2026-10-19','source':str(source),'local_copy':str(dest.relative_to(root)).replace('\\','/'),'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'pages':len(parts),'text_file':'outputs/competition_20261019/proposal_attachment_text.txt','original_modified':False}
(out/'proposal_attachment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
render=root/'tmp/pdfs/proposal_attachment'
render.mkdir(parents=True,exist_ok=True)
doc=pdfium.PdfDocument(dest)
for i in range(len(doc)):
    doc[i].render(scale=1.15).to_pil().save(render/('page_%02d.png'%(i+1)))
print(json.dumps(report,ensure_ascii=False,indent=2))
print('\n\n'.join(parts))
