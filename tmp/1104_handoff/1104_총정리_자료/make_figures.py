from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
RUN=ROOT/'TabICLv2_투트랙_6_10차_20261104'
OUT=HERE/'그림';OUT.mkdir(exist_ok=True)
font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,
                     'font.size':11,'axes.spines.top':False,'axes.spines.right':False,
                     'figure.facecolor':'#f7f9fc','axes.facecolor':'white','savefig.facecolor':'#f7f9fc'})
rows=[json.loads((RUN/f'{i}차 시도/result.json').read_text(encoding='utf-8')) for i in range(6,11)]
met=[r['metrics']['outer'] for r in rows]
fig,ax=plt.subplots(figsize=(10,4.6),layout='constrained')
series=[('전체',[v['micro_f1'] for v in met],'#1f4b99'),
        ('기존 ID',[v['groups']['known_by_ref_id']['micro_f1'] for v in met],'#00857d'),
        ('신규 ID',[v['groups']['novel_by_ref_id']['micro_f1'] for v in met],'#c35b26')]
for name,vals,color in series:
    ax.plot(range(6,11),vals,'o-',color=color,lw=2.5,label=name)
    for x,y in zip(range(6,11),vals):ax.annotate(f'{y:.3f}',(x,y),xytext=(0,8),textcoords='offset points',ha='center',color=color)
ax.set(xticks=range(6,11),xticklabels=[f'{i}차' for i in range(6,11)],ylim=(.42,.95),ylabel='Micro-F1',
       title='높아진 전체 성적과 남아 있는 신규 선박 격차')
ax.grid(axis='y',alpha=.18);ax.legend(ncol=3,loc='upper left')
fig.savefig(OUT/'01_기존신규_성적.png',dpi=160);plt.close(fig)

fig,axs=plt.subplots(1,2,figsize=(11,4.6),layout='constrained')
for ax,key,title in zip(axs,['known_by_ref_id','novel_by_ref_id'],['기존 ID 5,835척','신규 ID 691척']):
    cm=np.asarray(met[-1]['groups'][key]['confusion'])
    ratio=cm/cm.sum(1,keepdims=True)
    im=ax.imshow(ratio,vmin=0,vmax=1,cmap='Blues')
    for i in range(4):
        for j in range(4):ax.text(j,i,f'{cm[i,j]:,}\n({ratio[i,j]:.0%})',ha='center',va='center',color='white' if ratio[i,j]>.6 else '#182333',fontsize=10)
    ticks=['연안복합','자망','통발','채낚기·연승']
    ax.set(xticks=range(4),yticks=range(4),xticklabels=ticks,yticklabels=ticks,xlabel='예측 업종',ylabel='실제 업종',title=title)
fig.suptitle('10차 혼동행렬 — 괄호는 같은 실제 업종 안에서의 비율',fontsize=14)
fig.savefig(OUT/'02_10차_집단별혼동.png',dpi=160);plt.close(fig)

c=json.loads((HERE/'component_analysis.json').read_text(encoding='utf-8'))['component_only']
names=['TabICLv2 전역 경로','TabICLv2 지역 경로','두 TabICLv2 경로 혼합','검색 1등 업종만','최종 10차']
keys=['TabICL_global','TabICL_local','TabICL_blend','retrieval_top1','final10']
vals=[c[k]['micro_f1'] for k in keys]
fig,ax=plt.subplots(figsize=(10,4.6),layout='constrained')
ax.barh(names[::-1],vals[::-1],color=['#1f4b99','#00857d','#a8b7cd','#a8b7cd','#a8b7cd'])
for y,v in enumerate(vals[::-1]):ax.text(v+.008,y,f'{v:.4f}',va='center')
ax.set(xlim=(0,1),xlabel='같은 OUTER 6,526척의 Micro-F1',title='고성능의 중심은 세밀한 항적 검색 경로')
ax.grid(axis='x',alpha=.18)
fig.savefig(OUT/'03_구성요소_분해.png',dpi=160);plt.close(fig)
print('three figures saved')
