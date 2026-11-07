"""Check delivered counts, source statistics, PDF image identity and layout samples."""
from pathlib import Path
import csv, hashlib, json, gc
import numpy as np
import pandas as pd
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pymupdf as fitz
import build_panels as b

out=b.OUT
check=b.memory('final verification and sequential PDF raster checks',650)
summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
index=pd.read_csv(out/'panel_index.csv',dtype={'rfid_id':str})
assert len(index)==100 and index.rfid_id.nunique()==100
assert len(list(out.glob('panel_[0-9][0-9][0-9]_*.png')))==100
df=b.load()
for number,(ship,g) in enumerate(df.groupby('rfid_id',sort=True),1):
    expected=b.stats(g.reset_index(drop=True),number)
    actual=index[index.rfid_id==ship].iloc[0].to_dict()
    for k,v in expected.items():
        if isinstance(v,float): assert abs(actual[k]-v)<1e-14,(ship,k)
        else: assert actual[k]==v,(ship,k,actual[k],v)
    p=out/f'panel_{number:03d}_{ship}.png'
    with Image.open(p) as im: assert im.size==(1920,2880);im.verify()
assert summary['continuous_runs']==4205
assert summary['run_length_median_hours']==5
assert summary['vertices']==2706562
assert summary['score_sha256']==hashlib.sha256(b.SOURCE.read_bytes()).hexdigest()
for panel in summary['panels']:
    for m in panel['maps']:
        got=m['scale_bar_lon_span']*m['meters_per_lon_degree_at_bar']
        assert abs(got-m['scale_bar_m'])<1e-5

qa=out/'_qa';qa.mkdir(exist_ok=True)
doc=fitz.open(out/'testb_100_panels.pdf')
assert len(doc)==101 and len(doc.get_toc())==101
paths=[out/'panel_contents.png']+[out/f'panel_{r.순번:03d}_{r.rfid_id}.png' for r in index.itertuples()]
for i,p in enumerate(paths):
    images=doc[i].get_images(full=True);assert len(images)==1
    pix=fitz.Pixmap(doc,images[0][0])
    with Image.open(p) as im:
        rgb=im.convert('RGB')
        assert (pix.width,pix.height)==rgb.size
        assert hashlib.sha256(pix.samples).digest()==hashlib.sha256(rgb.tobytes()).digest(),i
    del pix,rgb

# Render PDF pages (not merely original PNGs) to catch PDF composition defects.
largest=int(index.loc[index['시간대행수'].idxmax(),'순번'])
smallest=int(index.loc[index['시간대행수'].idxmin(),'순번'])
pages=sorted(set([0,1,largest,smallest,100]))
for page in pages:
    pix=doc[page].get_pixmap(matrix=fitz.Matrix(1,1),alpha=False)
    pix.save(qa/f'pdf_page_{page+1:03d}.png');del pix
doc.close();gc.collect()

# Five overview sheets, all 100 delivered panels, one image loaded at a time.
font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',17)
for group in range(5):
    sheet=Image.new('RGB',(1500,1920),'#dce2ea');draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(paths[1+group*20:1+(group+1)*20]):
        x=(j%5)*300;y=(j//5)*480
        with Image.open(p) as im:
            thumb=im.convert('RGB');thumb.thumbnail((292,438))
            sheet.paste(thumb,(x+4,y+28))
        draw.text((x+8,y+5),p.stem.replace('panel_',''),fill='#17283f',font=font)
    sheet.save(qa/f'contact_{group+1}.jpg',quality=90)
    del sheet;gc.collect()
result=dict(status='passed',panels=100,index_rows=100,pdf_pages=101,
            png_dimensions=[1920,2880],pdf_images_pixel_identical=101,
            score_file_unchanged=True,continuous_runs=4205,run_length_median_hours=5,
            source_vertex_count=2706562,scale_bars_verified=300,
            pdf_pages_rendered=[p+1 for p in pages],memory_check=check,
            independent_review={'task':'/root/visual_review','role':'sol_review','model':'gpt-6.1-sol','effort':'high',
                                'evidence':'Explicit collaboration.spawn_agent configuration; read-only code review and panel_001 visual review returned no blocking issue',
                                'scope':'code and one sample image; not an independent review of every panel'})
(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
