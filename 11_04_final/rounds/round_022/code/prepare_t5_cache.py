"""Bounded exact legacy label-free harbor restoration; FIT2026 queries only.

Test2025 geometry is used solely for the already-established shared-harbor
aggregate. No test label, individual output, prediction or cross-year profile.
"""
import datetime,hashlib,json,math,sqlite3,time
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
import pyarrow.dataset as ds
import pyarrow as pa
from scipy.spatial import cKDTree
from t5_rebuild import FIELDS,roster_hash
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
SOURCE=ROOT.parent/'29-30일 모델 심층 분석/분석 결과/outputs/remeasure_20261031'
BASE=Path('D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104/artifacts/exp01/fold_0_features.npz')
EARTH_R=6371000.0
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def hav(lon,lat,lo,la):
 p=np.radians(lat);p2=np.radians(la);dp=p2-p;dl=np.radians(lo-lon)
 a=np.sin(dp/2)**2+np.cos(p)*np.cos(p2)*np.sin(dl/2)**2
 return 2*EARTH_R*np.arcsin(np.sqrt(np.clip(a,0,1)))
def batches(path,cols,predicate):
 scanner=ds.dataset(str(path),format='parquet').scanner(columns=cols,filter=predicate,batch_size=32768,use_threads=False,batch_readahead=1,fragment_readahead=1)
 for b in scanner.to_batches():yield b.to_pydict()
def id_filter(path,ids):
 typ=ds.dataset(str(path),format='parquet').schema.field('rfid_id').type
 values=[int(v) for v in ids] if pa.types.is_integer(typ) else [str(v) for v in ids]
 return ds.field('rfid_id').isin(values)
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
 start=time.monotonic();artifact=R/'artifacts/t5_fishing_profiles.npz'
 assert not artifact.exists(),'No overwrite/retry of completed cache'
 with np.load(BASE,allow_pickle=False) as z:
  assert str(z['feature_names'][165])=='t5_log1p_fishing_rows'
  fit=z['roles'].astype(str)=='FIT';ids=z['rfid_ids'].astype(str)[fit];target=z['X'][fit,165].astype(float)
 assert len(ids)==3144 and len(set(ids))==3144
 idmap={int(v):i for i,v in enumerate(ids)}
 dbpath=R/'tmp/harbor_distinct.sqlite';assert not dbpath.exists()
 con=sqlite3.connect(dbpath);con.execute('PRAGMA cache_size=-32768');con.execute('PRAGMA temp_store=FILE');con.execute('PRAGMA secure_delete=ON')
 con.execute('CREATE TABLE d (x INTEGER,y INTEGER,v INTEGER,PRIMARY KEY(x,y,v)) WITHOUT ROWID')
 own=defaultdict(Counter);lat_sum=0.;nstop=0;input_manifest=[]
 # Same key-valid and WKT-valid population as legacy _load_year_arrays.
 valid=(ds.field('key_valid')==True)&(ds.field('wkt_valid')==True)
 stop=valid&(ds.field('len_m')<=50.)&(ds.field('bbox_m')<=100.)
 for dataset in ('train','test'):
  for month in range(1,7):
   p=SOURCE/f'rows_{dataset}_{month}.parquet'
   input_manifest.append(dict(path=str(p),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=sha(p)))
   cols=['rfid_id','cen_lon','cen_lat']
   for b in batches(p,cols,stop):
    lo=np.asarray(b['cen_lon'],float);la=np.asarray(b['cen_lat'],float)
    if not(np.isfinite(lo).all() and np.isfinite(la).all()):raise ValueError('Nonfinite valid stop geometry')
    ix=np.floor(lo/.005).astype(np.int64);iy=np.floor(la/.005).astype(np.int64)
    rid=[int(v) for v in b['rfid_id']]
    con.executemany('INSERT OR IGNORE INTO d VALUES (?,?,?)',((int(x),int(y),v) for x,y,v in zip(ix,iy,rid)))
    lat_sum+=float(la.sum());nstop+=len(la)
   if dataset=='train':
    for b in batches(p,['rfid_id','cen_lon','cen_lat','rfid_time'],stop&id_filter(p,ids)):
     for v,lo,la,h in zip(b['rfid_id'],b['cen_lon'],b['cen_lat'],b['rfid_time']):
      if int(h) in (20,21,22,23,0,1,2,3):own[int(v)][(int(np.floor(lo/.005)),int(np.floor(la/.005)))]+=1
   con.commit();print(json.dumps(dict(stage='shared_harbor_aggregate',dataset=dataset,month=month)),flush=True)
 candidates=set(con.execute('SELECT x,y FROM d GROUP BY x,y HAVING COUNT(*)>=20').fetchall())
 ref_lat=lat_sum/nstop if nstop else 36.;mx=111320.*math.cos(math.radians(ref_lat));my=110540.
 visited=set();centers=[]
 for cell in candidates:
  if cell in visited:continue
  stack=[cell];comp=[];visited.add(cell)
  while stack:
   x,y=stack.pop();comp.append((x,y))
   for dx in (-1,0,1):
    for dy in (-1,0,1):
     nb=(x+dx,y+dy)
     if nb!=(x,y) and nb in candidates and nb not in visited:visited.add(nb);stack.append(nb)
  centers.append((float(np.mean([(x+.5)*.005 for x,y in comp])),float(np.mean([(y+.5)*.005 for x,y in comp]))))
 centers=np.asarray(centers,float).reshape(-1,2)
 tree=cKDTree(centers*np.asarray([mx,my])) if len(centers) else None
 moors={v:[((x+.5)*.005,(y+.5)*.005) for (x,y),n in sorted(c.items(),key=lambda kv:-kv[1])[:3]] for v,c in own.items()}
 del own,candidates,visited
 con.execute('DROP TABLE d');con.commit();con.execute('VACUUM');con.execute('CREATE TABLE profiles (r INTEGER,m INTEGER,fx INTEGER,fy INTEGER,cx INTEGER,cy INTEGER,n INTEGER,PRIMARY KEY(r,m,fx,fy,cx,cy)) WITHOUT ROWID');con.commit()
 counts=np.zeros(len(ids),dtype=np.int64);queried_rows=0
 for month in range(1,7):
  p=SOURCE/f'rows_train_{month}.parquet'
  for b in batches(p,['rfid_id','part_dt','cen_lon','cen_lat'],valid&(ds.field('len_m')>50.)&id_filter(p,ids)):
   sel=[i for i,v in enumerate(b['rfid_id']) if int(v) in idmap]
   if not sel:continue
   rid=np.asarray([int(b['rfid_id'][i]) for i in sel],dtype=np.int64)
   lo=np.asarray(b['cen_lon'],float)[sel];la=np.asarray(b['cen_lat'],float)[sel]
   dates=np.asarray(b['part_dt'],dtype=np.int64)[sel];months=(dates//100%100).astype(int)
   if np.any(dates//10000!=2026) or np.any(months!=month):raise ValueError('Query period mismatch')
   if not(np.isfinite(lo).all() and np.isfinite(la).all()):raise ValueError('Nonfinite query geometry')
   queried_rows+=len(lo)
   if tree is None:hd=np.full(len(lo),np.inf)
   else:
    _,ci=tree.query(np.column_stack([lo*mx,la*my]),k=1)
    hd=hav(lo,la,centers[ci,0],centers[ci,1])
   od=np.full(len(lo),np.inf)
   for v in np.unique(rid):
    ii=np.flatnonzero(rid==v)
    for mlon,mlat in moors.get(int(v),[]):od[ii]=np.minimum(od[ii],hav(lo[ii],la[ii],mlon,mlat))
   good=(hd>1000.)&(od>1000.)
   rr=np.asarray([idmap[int(v)] for v in rid[good]],int);lm=lo[good];lt=la[good]
   np.add.at(counts,rr,1)
   cols=np.column_stack([rr,months[good],np.floor(lm/.01).astype(int),np.floor(lt/.01).astype(int),np.floor(lm/.05).astype(int),np.floor(lt/.05).astype(int)])
   unique,nn=np.unique(cols,axis=0,return_counts=True)
   con.executemany('INSERT INTO profiles VALUES (?,?,?,?,?,?,?) ON CONFLICT(r,m,fx,fy,cx,cy) DO UPDATE SET n=n+excluded.n',(tuple(map(int,row))+(int(n),) for row,n in zip(unique,nn)))
  con.commit();print(json.dumps(dict(stage='FIT2026_fishing_profiles',month=month)),flush=True)
 expected=np.where(counts>0,np.log1p(counts),np.nan)
 match=np.array_equal(np.isnan(expected),np.isnan(target)) and np.allclose(expected,target,rtol=0,atol=1e-6,equal_nan=True)
 audit=dict(legacy_log1p_count_matches=bool(match),max_abs_log_count_delta=float(np.nanmax(np.abs(expected-target))),current_fit_rows=len(ids),fishing_rows=int(counts.sum()),active_query_rows=queried_rows,shared_harbors=len(centers),shared_stop_records=nstop,shared_ref_lat=ref_lat)
 save(R/'artifacts/t5_mask_equivalence.json',audit)
 if not match:raise RuntimeError('Legacy T5 fishing-row count equivalence failed: no training allowed')
 nprofiles=con.execute('SELECT COUNT(*) FROM profiles').fetchone()[0]
 columns=[np.empty(nprofiles,dtype=np.int64) for _ in FIELDS]
 for i,row in enumerate(con.execute('SELECT r,m,fx,fy,cx,cy,n FROM profiles ORDER BY r,m,fx,fy,cx,cy')):
  for j,x in enumerate(row):columns[j][i]=x
 con.close();np.savez_compressed(artifact,**dict(zip(FIELDS,columns)))
 for entry in input_manifest:
  if sha(Path(entry['path']))!=entry['sha256']:raise RuntimeError('Input source changed during preparation')
 save(artifact.with_suffix('.manifest.json'),dict(roster_sha256=roster_hash(ids),year=2026,fishing_row_count_equivalence_verified=True,pointwise_mask_equivalence_verified=False,equivalence_basis='same legacy algorithm plus all3144 log1p_fishing_rows equality within1e-6; not pointwise independently saved mask comparison',test2025_query_rows_materialized=0,test2025_geometry_rows_read_for_harbor_reference=True,test2025_labels_read=False,test2025_individual_outputs_retained=False,holdout_geometry_scope='shared stop-location aggregate only; own-mooring and active query scanners filter FIT before materialization',labels_used=False,sha256=sha(artifact),input_files=input_manifest,baseline_sha256=sha(BASE),nprofiles=nprofiles,elapsed_seconds=time.monotonic()-start,query_scope='fold0 FIT 2026 only',test_scope='unlabeled shared-harbor aggregate only; no individual test outputs',projected_test_columns=['rfid_id','cen_lon','cen_lat'],test_filter_columns=['key_valid','wkt_valid','len_m','bbox_m'],**audit))
 print(json.dumps(dict(status='ready',profiles=nprofiles,elapsed_seconds=time.monotonic()-start)),flush=True)
if __name__=='__main__':main()
