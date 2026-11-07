"""Read-only audit of existing top candidates; no score/policy changes."""
from pathlib import Path
from datetime import datetime
import json, hashlib, sys, math
import psutil

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PKG = ROOT / 'deliverables/testb_system_20261106'
PANELS = ROOT / 'testB/final/round_014_visual_audit'
memory = []
def gate(stage, estimate=450):
    v = psutil.virtual_memory()
    proc=[]
    for p in psutil.process_iter(['name','memory_info']):
        try: proc.append((p.info['name'], round(p.info['memory_info'].rss/2**20,1)))
        except (psutil.NoSuchProcess,psutil.AccessDenied): pass
    rec=dict(time=datetime.now().astimezone().isoformat(),stage=stage,available_mib=v.available/2**20,
             estimated_peak_mib=estimate,basis='3.62MB parquet; two 31MB reference arrays; sequential 1920x2880 panel decoding and one contact sheet; two other small analysis workers',
             largest_processes=sorted(proc,key=lambda a:-a[1])[:8])
    memory.append(rec)
    if v.available/2**20 < estimate+400: raise MemoryError(rec)

gate('numeric audit')
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import pymupdf
sys.path.insert(0,str(PKG/'src'))
from frozen_baseline import haversine_m

c=pd.read_csv(PKG/'results/reproduction_001/candidates.csv',dtype={'rfid_id':str})
d=pd.read_parquet(PKG/'results/reproduction_001/scored_rows.parquet')
idx=pd.read_csv(PANELS/'panel_index.csv',dtype={'rfid_id':str}).set_index('rfid_id')
dom=c[c.s_gap.eq(c[['s_zone','s_change','s_gap']].max(axis=1))].copy()
refg=np.sort(np.load(PKG/'references/gap_reference.npy',allow_pickle=False))
refg=refg[~np.isnan(refg)]
refj=np.sort(np.load(PKG/'references/jump_reference.npy',allow_pickle=False))
refj=refj[~np.isnan(refj)]
def cdf(a,v): return float(np.searchsorted(a,v,side='right')/len(a))
def dt(t): return pd.to_datetime(t,unit='h').strftime('%Y-%m-%d %H:00')
records=[]
for r in dom.itertuples():
    g=d[d.rfid_id==r.rfid_id].sort_values(['ts','source_ordinal']).reset_index(drop=True)
    i=int(np.flatnonzero(g.source_ordinal.to_numpy()==r.source_ordinal)[0]); assert i>0
    peak=g.iloc[i]; prev=g.iloc[i-1]
    delta=int(peak.ts-prev.ts); jump=haversine_m(prev.cen_lon,prev.cen_lat,peak.cen_lon,peak.cen_lat)
    p=idx.loc[r.rfid_id]; n=int(p['순번'])
    assert pd.Timestamp(p['최고점시각'])==pd.to_datetime(r.lead_ts,unit='h')
    assert abs(p['최고점수']-r.score)<1e-12
    # Last actual interruption ending at or before the selected peak. Distinct from its immediate predecessor.
    breaks=np.flatnonzero(np.diff(g.ts.to_numpy()[:i+1])>1)+1
    b=int(breaks[-1]) if len(breaks) else None
    actual=None if b is None else g.iloc[b]
    before=None if b is None else g.iloc[b-1]
    row=dict(rfid_id=r.rfid_id,panel_number=n,pdf_page=n+1,panel_file=f'panel_{n:03d}_{r.rfid_id}.png',
      peak_time=dt(peak.ts),prior_observation_count=i,score=float(peak.score),s_zone=float(peak.s_zone),
      s_change=float(peak.s_change),s_gap=float(peak.s_gap),previous_time=dt(prev.ts),
      predecessor_interval_h=delta,missing_hour_bins=delta-1,centroid_separation_m=jump,
      gap_cdf=cdf(refg,delta),jump_cdf=cdf(refj,jump),previous_score=float(prev.score),
      score_increase=float(peak.score-prev.score),previous_s_gap=float(prev.s_gap),
      s_gap_increase=float(peak.s_gap-prev.s_gap),
      at_gap_end=delta>1,rise_at_gap_end=delta>1 and peak.score>prev.score,
      classification='gap_end_rise' if delta>1 and peak.score>prev.score else ('gap_end_tie' if delta>1 else 'continuous_hour'),
      last_actual_gap_end=None if b is None else dt(actual.ts),
      last_actual_gap_interval_h=None if b is None else int(actual.ts-before.ts),
      last_actual_gap_missing_bins=None if b is None else int(actual.ts-before.ts)-1,
      last_actual_gap_centroid_m=None if b is None else haversine_m(before.cen_lon,before.cen_lat,actual.cen_lon,actual.cen_lat),
      hours_since_last_gap_end=None if b is None else int(peak.ts-actual.ts),
      next_interval_h=None if i+1==len(g) else int(g.iloc[i+1].ts-peak.ts),
      next_score=None if i+1==len(g) else float(g.iloc[i+1].score),
      next_score_drop=None if i+1==len(g) else float(peak.score-g.iloc[i+1].score))
    assert abs(row['s_gap']-(row['gap_cdf']+row['jump_cdf'])/2)<1e-12
    records.append(row)
x=pd.DataFrame(records).sort_values('panel_number').reset_index(drop=True)
x.to_csv(OUT/'gap_candidates.csv',index=False,encoding='utf-8-sig')
summ={'count':len(x),'strict_max_count':int((dom.s_gap>dom[['s_zone','s_change']].max(axis=1)).sum()),
      'class_counts':x.classification.value_counts().to_dict(),'cdf_gap_1h':cdf(refg,1),
      'cdf_gap_values':{str(t):cdf(refg,t) for t in [1,2,6,12,24,48,168,720]},
      'all_row_gap_dominant_count':int(d.s_gap.eq(d[['s_zone','s_change','s_gap']].max(axis=1)).sum()),
      'gap_cdf_reference_count':len(refg),'jump_cdf_reference_count':len(refj),
      'group_stats':{},'pdf_png_match_count':0,'visual_contact_sheets':[]}
for label,sub in x.groupby('classification'):
    summ['group_stats'][label]={'count':len(sub),'coldstart_count':int((sub.prior_observation_count<24).sum()),
      'next_contiguous_drop_count':int(((sub.next_interval_h==1)&(sub.next_score_drop>0)).sum()),
      'stats':sub[['predecessor_interval_h','missing_hour_bins','centroid_separation_m','score','score_increase','s_gap','s_gap_increase']].describe().to_dict()}
del refg,refj,d
gate('sequential panel/PDF visual crosscheck',450)
(OUT/'visual_review').mkdir(exist_ok=True)
pdf=pymupdf.open(PANELS/'testb_100_panels.pdf')
assert len(pdf)==101
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
for start in range(0,len(x),8):
    sheet=Image.new('RGB',(1800,2240),'#e5e7eb');draw=ImageDraw.Draw(sheet)
    for pos,r in enumerate(x.iloc[start:start+8].itertuples()):
        with Image.open(PANELS/r.panel_file) as im:
            im=im.convert('RGB')
            page=pdf[r.panel_number]
            imgs=page.get_images(full=True); assert len(imgs)==1
            px=pymupdf.Pixmap(pdf,imgs[0][0]); assert (px.width,px.height)==im.size
            assert hashlib.sha256(px.samples).digest()==hashlib.sha256(im.tobytes()).digest()
            summ['pdf_png_match_count']+=1
            left=(pos%2)*900; top=(pos//2)*560
            # Display full peak-day map and full timeline, with an added exact numeric label.
            draw.rectangle((left,top,left+899,top+559),fill='white',outline='#888888')
            draw.text((left+10,top+5),f'{r.panel_number:03d} / {r.rfid_id}  {r.classification}',font=font,fill='black')
            draw.text((left+10,top+31),f'dt={r.predecessor_interval_h}h  jump={r.centroid_separation_m/1000:.3f}km  dScore={r.score_increase:.4f}',font=font,fill='black')
            mapcrop=im.crop((80,1770,1880,2400)).resize((900,315))
            timeline=im.crop((80,2410,1880,2780)).resize((900,185))
            sheet.paste(mapcrop,(left,top+59));sheet.paste(timeline,(left,top+374))
            del px
    name=f'visual_review/sheet_{start//8+1:02d}.jpg'
    sheet.save(OUT/name,quality=92);summ['visual_contact_sheets'].append(name)
pdf.close()
summ['memory_checks']=memory
summ['source_sha256']={str(p.relative_to(ROOT)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in [PKG/'results/reproduction_001/candidates.csv',PKG/'results/reproduction_001/scored_rows.parquet',PANELS/'panel_index.csv',PANELS/'testb_100_panels.pdf',PKG/'src/frozen_baseline.py',PKG/'references/gap_reference.npy',PKG/'references/jump_reference.npy']}
(OUT/'gap_summary.json').write_text(json.dumps(summ,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summ,ensure_ascii=False,indent=2))
