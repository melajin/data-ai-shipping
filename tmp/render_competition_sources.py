from pathlib import Path
import pypdfium2 as pdfium
root=Path(__file__).resolve().parents[1]
source=root/'data/reference/competition_20261019/2026 데이터 분석대회'
out=root/'tmp/pdfs/competition_20261019'
out.mkdir(parents=True,exist_ok=True)
for file,page,name in [('어선항적과제_이해가이드.pdf',15,'guide_page16'),('15_어선항적_최종_제안서작성_가이드라인.pdf',2,'proposal_page3')]:
    doc=pdfium.PdfDocument(source/file)
    doc[page].render(scale=1.3).to_pil().save(out/(name+'.png'))
    print(name)
