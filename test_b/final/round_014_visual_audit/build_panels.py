"""Offline visual audit: stored scores and original WKT, without inference."""
from pathlib import Path
from datetime import datetime
import argparse, gc, hashlib, json, math, re, sqlite3, sys, time
import numpy as np
import pandas as pd
import psutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, FuncFormatter
from matplotlib.font_manager import fontManager
import fitz

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
SOURCE=ROOT/'testB/과거/first_results/hourly_scores.parquet'
fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
plt.rcParams.update({'font.family':'Malgun Gothic','font.size':10,'axes.unicode_minus':False,
                     'path.simplify':False,'agg.path.chunksize':0,'axes.titleweight':'bold'})
COLORS=['#243b76','#008f91','#ed8b23','#bb3e91']
LABELS=['00-05시 새벽','06-11시 오전','12-17시 오후','18-23시 저녁']
WARNING='이 그림은 점검용이다. 이상점수는 사고 확률이 아니며,\n표시된 최고점 시각이 사고라는 뜻이 아니다.'
MEM=[]

def memory(stage, estimate=500):
    available=psutil.virtual_memory().available/2**20
    rec=dict(time=datetime.now().astimezone().isoformat(),stage=stage,available_mib=round(available,1),
             estimated_peak_mib=estimate,current_process_mib=round(psutil.Process().memory_info().rss/2**20,1),
             basis='One vessel at a time; max 3,413 hourly rows; 1920x2880 RGBA canvas ~22 MiB; raw coordinate arrays and matplotlib collections; no parallel data jobs')
    MEM.append(rec)
    current=psutil.Process().memory_info().rss/2**20
    if available < max(100,estimate-current)+180:
        raise MemoryError(f'RAM insufficient at {stage}: {available:.0f} MiB available')
    return rec

def parse_wkt(s):
    if not s.strip().upper().startswith('MULTILINESTRING'):
        raise ValueError('Expected MULTILINESTRING')
    parts=[]
    for text in re.findall(r'\(([^()]*)\)',s):
        points=[]
        for point in text.split(','):
            values=point.split()
            if len(values)!=2: raise ValueError('Expected two-dimensional WKT')
            points.append([float(values[0]),float(values[1])])
        a=np.asarray(points,dtype=float)
        if len(a)<2 or not np.isfinite(a).all(): raise ValueError('Invalid part')
        if np.any(np.abs(a[:,0])>180) or np.any(np.abs(a[:,1])>90): raise ValueError('Invalid lon/lat')
        parts.append(a)
    if not parts: raise ValueError('Empty WKT')
    return parts

def load():
    df=pd.read_parquet(SOURCE)
    df['rfid_id']=df.rfid_id.astype(str)
    df['dt']=pd.to_datetime(df.part_dt.astype(str),format='%Y%m%d')+pd.to_timedelta(df.rfid_time,unit='h')
    assert not df.duplicated(['rfid_id','ts']).any()
    assert np.array_equal(df.dt.astype('int64').to_numpy()//3_600_000_000_000,df.ts.to_numpy())
    assert len(df)==46705 and df.rfid_id.nunique()==100
    assert df.score.notna().all() and df.score.between(0,1).all()
    return df.sort_values(['rfid_id','ts']).reset_index(drop=True)

def run_slices(g):
    cuts=np.r_[0,np.flatnonzero(np.diff(g.ts.to_numpy())!=1)+1,len(g)]
    return [slice(int(a),int(b)) for a,b in zip(cuts[:-1],cuts[1:])]

def stats(g,number):
    runs=run_slices(g); sizes=[s.stop-s.start for s in runs]
    peak=g.iloc[int(np.argmax(g.score.to_numpy()))]
    t=int(peak.ts); hours=set(g.ts.astype(int))
    return {'rfid_id':str(peak.rfid_id),'순번':number,'관측일수':int(g.part_dt.nunique()),'시간대행수':len(g),
            '시작일':g.dt.min().strftime('%Y-%m-%d'),'종료일':g.dt.max().strftime('%Y-%m-%d'),
            '연속구간수':len(sizes),'구간길이중앙값':float(np.median(sizes)),'최장구간':max(sizes),
            '최고점수':float(peak.score),'최고점시각':peak["dt"].strftime('%Y-%m-%d %H:00'),
            '최고점당일행수':int((g.part_dt==peak.part_dt).sum()),
            '최고점_직전3h_관측수':sum(t-h in hours for h in [1,2,3]),
            '최고점_직후3h_관측수':sum(t+h in hours for h in [1,2,3]),'좌표출처':'원본 WKT'}

def geometry(g):
    con=sqlite3.connect(f'file:{(OUT/"raw_geometry.sqlite").as_posix()}?mode=ro',uri=True)
    rows=con.execute('SELECT day,hour,ordinal,wkt FROM geom WHERE ship=?',(str(g.rfid_id.iloc[0]),)).fetchall()
    con.close()
    lookup={(int(d),int(h)):(o,w) for d,h,o,w in rows}
    result=[]; mismatches=[]
    for r in g.itertuples():
        ordinal,wkt=lookup[(int(r.part_dt),int(r.rfid_time))]
        assert ordinal==int(r.source_ordinal)
        parts=parse_wkt(wkt); a=np.concatenate(parts)
        assert len(a)==r.n_coords, (r.rfid_id,r.ts,len(a),r.n_coords)
        center=a.mean(axis=0)
        if not np.allclose(center,[r.cen_lon,r.cen_lat],rtol=0,atol=1e-8):
            mismatches.append(int(r.ts))
        result.append(parts)
    assert not mismatches, f'WKT vertex-mean center mismatch: {mismatches[:5]}'
    return result

def degree_m(lat):
    # WGS84 meridional and prime-vertical radii, meters per degree.
    rad=np.deg2rad(lat); a=6378137.; e2=6.6943799901413165e-3
    w=np.sqrt(1-e2*np.sin(rad)**2)
    return np.pi/180*a*np.cos(rad)/w,np.pi/180*a*(1-e2)/w**3

def bounds(points,quantile=False):
    if quantile:
        low,high=np.quantile(points,[.005,.995],axis=0)
    else: low,high=points.min(axis=0),points.max(axis=0)
    return np.array([low[0],high[0],low[1],high[1]],float)

def setup_map(ax,box,title):
    cx=(box[0]+box[1])/2; cy=(box[2]+box[3])/2
    mx,my=degree_m(cy)
    # Fixed panel dimensions with equal physical-distance scaling at panel center.
    ratio=(.87*12)/(.18*18)
    dx=max((box[1]-box[0])*1.10,60/mx)
    dy=max((box[3]-box[2])*1.10,60/my)
    dx=max(dx,dy*my/mx*ratio); dy=max(dy,dx*mx/my/ratio)
    ax.set_xlim(cx-dx/2,cx+dx/2);ax.set_ylim(cy-dy/2,cy+dy/2)
    ax.set_aspect(my/mx,adjustable='box')
    ax.set_title(title,loc='left',fontsize=12,pad=14)
    ax.set_facecolor('#fafbfc');ax.grid(True,color='#d7dce2',lw=.45,zorder=0)
    ax.xaxis.set_major_locator(MaxNLocator(6));ax.yaxis.set_major_locator(MaxNLocator(4))
    fmt=FuncFormatter(lambda v,p:f'{v:.4f}°' if max(dx,dy)<.08 else f'{v:.2f}°')
    ax.xaxis.set_major_formatter(fmt);ax.yaxis.set_major_formatter(fmt);ax.tick_params(labelsize=8)
    ax.set_ylabel('위도',fontsize=9)
    ax.text(1.0,-.10,'경도',ha='right',va='top',transform=ax.transAxes,fontsize=8)
    ax.annotate('N',xy=(.955,.91),xytext=(.955,.73),xycoords='axes fraction',
                ha='center',va='center',fontsize=11,fontweight='bold',
                arrowprops={'arrowstyle':'-|>','color':'#25334a','lw':1.4})
    x0=cx-dx*.44; y0=cy-dy*.40
    bar_mx,_=degree_m(y0)
    target=dx*bar_mx*.19
    power=10**math.floor(math.log10(target)); m=max(v*power for v in [1,2,5,10] if v*power<=target)
    x1=x0+m/bar_mx
    ax.plot([x0,x1],[y0,y0],color='#152434',lw=2,zorder=20)
    for x in [x0,x1]:ax.plot([x,x],[y0-dy*.009,y0+dy*.009],color='#152434',lw=1,zorder=20)
    label=f'{m/1000:g} km' if m>=1000 else f'{m:g} m'
    ax.text((x0+x1)/2,y0+dy*.025,label,ha='center',fontsize=8,zorder=21,
            bbox={'facecolor':'white','edgecolor':'none','alpha':.88,'pad':1})
    ax.text(.985,.025,'실제 축척 · 지형 배경 미포함',ha='right',va='bottom',transform=ax.transAxes,
            fontsize=7.5,zorder=25,bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':2})
    return {'center_lat':cy,'scale_bar_lat':y0,'scale_bar_m':m,'scale_bar_lon_span':x1-x0,
            'meters_per_lon_degree_at_bar':bar_mx,'aspect':my/mx,'xlim':list(ax.get_xlim()),'ylim':list(ax.get_ylim())}

def draw_parts(ax,parts,color,lw=.45,alpha=.7,point_size=.5,z=2):
    if not parts:return
    ax.add_collection(LineCollection(parts,colors=color,linewidths=lw,alpha=alpha,zorder=z))
    a=np.concatenate(parts)
    ax.scatter(a[:,0],a[:,1],s=max(point_size,12) if len(a)<=20 else point_size,
               c=color,alpha=alpha,linewidths=0,zorder=z+.1)

def make_panel(g,number):
    rec=stats(g,number); geom=geometry(g); peak_i=int(np.argmax(g.score.to_numpy())); peak=g.iloc[peak_i]
    daymask=(g.part_dt.to_numpy()==peak.part_dt)
    allparts=[a for parts in geom for a in parts]
    dayparts=[a for i,parts in enumerate(geom) if daymask[i] for a in parts]
    allpts=np.concatenate(allparts); daypts=np.concatenate(dayparts)
    qb=bounds(allpts,True)
    joint=np.mean((allpts[:,0]>=qb[0])&(allpts[:,0]<=qb[1])&(allpts[:,1]>=qb[2])&(allpts[:,1]<=qb[3]))
    gap_i=np.flatnonzero(np.diff(g.ts.to_numpy())!=1)
    marks=[];markrows=[]
    for i in gap_i:
        for j,end in [(i,-1),(i+1,0)]:
            for part in geom[j]: marks.append(part[end]);markrows.append(j)
    marks=np.asarray(marks).reshape(-1,2);markrows=np.asarray(markrows,dtype=int)
    fig=plt.figure(figsize=(12,18),facecolor='white')
    fig.text(.075,.971,f'{number:03d}  선박 {rec["rfid_id"]} · 항적 점검',fontsize=21,fontweight='bold',color='#18283e')
    fig.text(.075,.948,f'관측일 {rec["관측일수"]}일 · 시간대 행 {len(g):,}개 · {rec["시작일"]} ~ {rec["종료일"]}',fontsize=11)
    fig.text(.075,.927,f'최고점 {peak.score:.4f} · {peak["dt"]:%Y-%m-%d %H}시',fontsize=13,color='#bf302f',fontweight='bold')
    fig.text(.075,.907,f'연속 관측 구간 {rec["연속구간수"]:,}개 / 구간 길이 중앙값 {rec["구간길이중앙값"]:g}시간 / 최장 {rec["최장구간"]}시간',fontsize=10.5)
    fig.text(.075,.874,WARNING,fontsize=11,fontweight='bold',color='#293342',linespacing=1.45)
    fig.text(.075,.854,'좌표 출처: 원본 WKT · 모든 꼭짓점 표시 · 부분선과 시간대 행 사이를 임의로 연결하지 않음',fontsize=9,color='#4a5665')
    ax1=fig.add_axes([.085,.645,.87,.18]);ax2=fig.add_axes([.085,.415,.87,.18]);ax3=fig.add_axes([.085,.185,.87,.18])
    maps=[]
    titles=['전체 관측 기간 · 모든 좌표',
            f'밀집 범위 확대 · 좌표 99% 포함',
            f'최고점 당일 확대 · {peak["dt"]:%Y-%m-%d} · {int(daymask.sum())}개']
    for ax,box,title in zip([ax1,ax2,ax3],[bounds(allpts),qb,bounds(daypts)],titles):maps.append(setup_map(ax,box,title))
    ax2.text(0,1.018,f'경·위도 각각 0.5~99.5% 분위 · 두 조건 동시 포함 {joint*100:.2f}% (축척 유지용 여백 별도)',
             transform=ax2.transAxes,fontsize=7.5,color='#586473')
    for ax in [ax1,ax2]:
        draw_parts(ax,allparts,'#808994',lw=.4,alpha=.48,point_size=.35)
        draw_parts(ax,dayparts,COLORS[2],lw=.8,alpha=.88,point_size=1,z=4)
    for b,color in enumerate(COLORS):
        parts=[a for i,p in enumerate(geom) if daymask[i] and int(g.rfid_time.iloc[i])//6==b for a in p]
        draw_parts(ax3,parts,color,lw=.7,alpha=.85,point_size=2,z=3)
    for ax in [ax1,ax2,ax3]:
        m=marks if ax is not ax3 else marks[daymask[markrows]]
        if len(m):ax.scatter(m[:,0],m[:,1],marker='x',s=13,c='#28313b',linewidths=.65,alpha=.8,zorder=10)
    legend=[Line2D([0],[0],color='#808994',lw=1,label='전체 기간'),Line2D([0],[0],color=COLORS[2],lw=2,label='최고점 당일'),
            Line2D([0],[0],marker='x',color='#28313b',linestyle='none',markersize=5,label='× 관측 끊김')]
    ax1.legend(handles=legend,loc='upper left',fontsize=8,ncol=3,framealpha=.93)
    ax3.legend(handles=[Line2D([0],[0],color=c,lw=2,label=l) for c,l in zip(COLORS,LABELS)],
               loc='upper left',fontsize=8,ncol=4,framealpha=.93)
    ax=fig.add_axes([.085,.075,.87,.068])
    times=g.dt.to_numpy()
    for i in gap_i:ax.axvspan(g.dt.iloc[i]+pd.Timedelta(hours=1),g.dt.iloc[i+1],color='#c4c8ce',alpha=.50,lw=0)
    comp_colors=['#5792ca','#c39758','#8b76b6']
    for name,color in zip(['s_zone','s_change','s_gap'],comp_colors):
        for j,s in enumerate(run_slices(g)):
            ax.plot(times[s],g[name].to_numpy()[s],color=color,alpha=.42,lw=.8,marker='.',markersize=1.6,label=name if j==0 else None)
    ax.scatter(times,g.score,s=5,c='#243349',alpha=.8,label='score',zorder=4)
    ax.scatter([peak["dt"]],[peak.score],s=54,marker='D',c='#c73235',edgecolors='white',lw=.5,label='최고점',zorder=6,clip_on=False)
    ax.set_ylim(0,1.04);ax.set_yticks([0,.5,1]);ax.set_ylabel('score',fontsize=8);ax.tick_params(labelsize=7.5)
    if g.dt.min()==g.dt.max(): ax.set_xlim(g.dt.min()-pd.Timedelta(minutes=30),g.dt.max()+pd.Timedelta(minutes=30))
    else:ax.set_xlim(g.dt.min(),g.dt.max()+pd.Timedelta(hours=1))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3,maxticks=7))
    short=(g.dt.max()-g.dt.min())<pd.Timedelta(days=3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M' if short else '%Y-%m-%d'))
    ax.grid(axis='y',alpha=.2);ax.legend(loc='upper left',bbox_to_anchor=(.34,1.43),ncol=5,fontsize=7.5,frameon=False)
    ax.set_title('이상점수 타임라인 · 회색 배경 = 관측 없는 시간',loc='left',fontsize=9,pad=12)
    fig.text(.075,.046,'빈 구간은 연결하지 않았다. 색은 기록 시간대이며 속도·위험도가 아니다.',fontsize=8.5)
    fig.text(.075,.033,'좌표 출처: 원본 WKT  |  최고점은 전체 기간 최대값이며 사고 판정이 아니다.',fontsize=8.5)
    ties=int((g.score==peak.score).sum())
    fig.text(.075,.020,f'×는 공백 양옆 기록의 부분선 끝점 · 축척은 막대 위도의 WGS84 거리(광역 지도는 국지 근사) · 최고점 동률 {ties}개: 첫 시각 표시',fontsize=7.3,color='#596575')
    path=OUT/f'panel_{number:03d}_{rec["rfid_id"]}.png'
    fig.savefig(path,dpi=160,facecolor='white');plt.close(fig)
    details=dict(rfid_id=rec['rfid_id'],number=number,coordinate_source='원본 WKT',filename=path.name,
                 vertices=len(allpts),parts=len(allparts),hourly_rows=len(g),gap_count=len(gap_i),gap_markers=len(marks),
                 coordinate_count_matches=True,vertex_mean_centers_match=True,peak_ties=ties,
                 marginal_quantile_box=qb.tolist(),joint_fraction_in_quantile_box=float(joint),maps=maps,
                 line_policy='Only consecutive vertices in each original WKT part; no cross-part or cross-hour interpolation')
    del fig,geom,allparts,dayparts,allpts,daypts
    gc.collect()
    return rec,details

def index_image(records):
    fig=plt.figure(figsize=(12,16),facecolor='white')
    fig.text(.06,.955,'Test B 100척 · 항적 점검 목차',fontsize=24,fontweight='bold',color='#18283e')
    fig.text(.06,.927,'선박 ID 오름차순 · PDF 첫 장은 목차 / 패널 PDF 쪽 = 순번 + 1',fontsize=12)
    fig.text(.06,.902,'좌표 출처: 원본 WKT · 저장된 score만 표시 · 사용자가 직접 점검하고 판단',fontsize=11,color='#b63433')
    for col in range(4):
        x=.06+col*.235
        fig.text(x,.862,'순번   선박 ID        PDF 쪽',fontsize=10,fontweight='bold')
        for j,r in enumerate(records[col*25:(col+1)*25]):
            y=.833-j*.0295
            fig.text(x,y,f'{r["순번"]:03d}   {r["rfid_id"]}       {r["순번"]+1:3d}',fontsize=11,color='#26374e')
    fig.text(.06,.06,'이 그림은 점검용이다. 이상점수는 사고 확률이 아니며, 최고점 시각이 사고라는 뜻이 아니다.',fontsize=10,fontweight='bold')
    fig.text(.06,.039,'정렬 가능한 상세 요약: panel_index.csv  |  원본 좌표와 부분선 보존 / 공백 연결 없음',fontsize=10)
    p=OUT/'panel_contents.png';fig.savefig(p,dpi=160);plt.close(fig);gc.collect();return p

def make_pdf(records,index):
    memory('PDF assembly',650)
    doc=fitz.open()
    paths=[index]+[OUT/f'panel_{r["순번"]:03d}_{r["rfid_id"]}.png' for r in records]
    for i,p in enumerate(paths):
        # Embed the delivered PNG itself: PDF and individual image are identical.
        # Compress each page before adding it to the combined PDF: bounded RAM.
        one=fitz.open()
        page=one.new_page(width=864,height=1152 if i==0 else 1296)
        page.insert_image(page.rect,filename=str(p))
        packed=one.tobytes(deflate=True);one.close()
        with fitz.open(stream=packed,filetype='pdf') as compressed:
            doc.insert_pdf(compressed)
        del packed,page,one
    doc.set_toc([[1,'목차',1]]+[[1,f'{r["순번"]:03d} 선박 {r["rfid_id"]}',r['순번']+1] for r in records])
    doc.set_metadata({'title':'Test B 100척 항적 점검','subject':'원본 WKT / 기존 이상점수 / 사고 판정 아님','author':'Visual audit'})
    doc.save(OUT/'testb_100_panels.pdf',deflate=True,garbage=3);doc.close();gc.collect()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sample',action='store_true');parser.add_argument('--all',action='store_true')
    args=parser.parse_args();print(json.dumps(memory('load scores',450),ensure_ascii=False),flush=True)
    before=hashlib.sha256(SOURCE.read_bytes()).hexdigest();df=load();records=[];details=[];failures=[]
    groups=list(df.groupby('rfid_id',sort=True))
    if args.sample:groups=groups[:1]
    for number,(ship,g) in enumerate(groups,1):
        memory(f'panel {number:03d}',500)
        try:
            rec,detail=make_panel(g.reset_index(drop=True),number)
            records.append(rec);details.append(detail)
            print(f'PANEL {number:03d} {ship} rows={len(g)} vertices={detail["vertices"]}',flush=True)
        except MemoryError: raise
        except Exception as e:
            failures.append({'rfid_id':ship,'reason':repr(e)});print(f'FAILED {ship}: {e!r}',flush=True)
    if args.sample:
        (OUT/'sample_check.json').write_text(json.dumps({'panels':details,'failures':failures,'memory_checks':MEM},ensure_ascii=False,indent=2),encoding='utf-8')
        if failures:raise RuntimeError(failures)
        return
    assert not failures and len(records)==100, failures
    pd.DataFrame(records).to_csv(OUT/'panel_index.csv',index=False,encoding='utf-8-sig')
    index=index_image(records);make_pdf(records,index)
    runs=[s.stop-s.start for _,g in df.groupby('rfid_id') for s in run_slices(g)]
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==before
    summary=dict(coordinate_source='원본 WKT',score_source=str(SOURCE),score_sha256=before,
                 score_unchanged=True,new_models_predictions_labels=False,network_used=False,
                 generated_panels=len(records),failed_vessels=failures,contents_pages=1,pdf_pages=101,
                 hourly_rows=len(df),vertices=sum(d['vertices'] for d in details),
                 continuous_runs=len(runs),run_length_median_hours=float(np.median(runs)),
                 run_length_max_hours=max(runs),vessels_one_hour=int((df.groupby('rfid_id').size()==1).sum()),
                 missing_component_counts=df[['s_zone','s_change','s_gap']].isna().sum().to_dict(),
                 source_details=json.loads((OUT/'source_summary.json').read_text(encoding='utf-8')),
                 panels=details,memory_checks=MEM,
                 review_agent={'task':'visual_review','requested_model':'gpt-6.1-sol','requested_effort':'high','spawn_role':'sol_review'},
                 notes=['No speed or accident judgment inferred.','All vertices retained, no resampling.',
                        'Temporal run length is count of consecutive hourly bins; not subhour position timing.',
                        'Missing-hour shading is [previous timestamp + 1h, next timestamp).',
                        'The nominal 99% map uses per-axis quantiles; actual joint inclusion is printed.',
                        'Each WKT part and each hourly row remains a separate path.',
                        'Stored cen_lon/cen_lat match the arithmetic mean of WKT vertices, not generally a bounding-box center; raw WKT is used throughout.'])
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['panels','source_details','memory_checks']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
