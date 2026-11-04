from pathlib import Path
import pypdfium2 as pdfium

folder = Path(__file__).resolve().parent
doc = pdfium.PdfDocument(r'C:\Users\dlehs\Downloads\선박 업종 분류 정확도 0.70 달성을 위한 기술 진단 및 종합 실행 로드맵.pdf')
for i in range(len(doc)):
    page = doc[i]
    bitmap = page.render(scale=1.25)
    bitmap.to_pil().save(folder / f'pdf_page_{i+1}.png')
    bitmap.close()
    page.close()
doc.close()
print('Rendered 5 pages')
