"""Label-free target-bundle features,matching Round63's 337-column schema."""
import io
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from .feature_definitions import (
    NAMES,SIZES,CELLSPACE,row_features,summaries,layout_features,state_codes,extract,
)


def _round_like_source(frame,digits):
    """Preserve the original intermediate CSV rounding before float32 inference."""
    return pd.read_csv(io.StringIO(frame.to_csv(float_format=f'%.{digits}g')),index_col='id')


def build_features(input_dir,target_ids,schema,output,chunk_size=50000):
    """Read only supplied target IDs;no labels,split creation or outside history."""
    started=time.perf_counter();ids=np.sort(np.asarray(target_ids,dtype=np.int64))
    if len(np.unique(ids))!=len(ids):raise ValueError('Duplicate target rfid_id')
    wanted={f'{i:08d}' for i in ids};files=sorted(Path(input_dir).glob('*.csv'))
    if not files:raise FileNotFoundError(f'No CSV input in {input_dir}')
    projector=Transformer.from_crs('EPSG:4326','EPSG:5179',always_xy=True)
    day_hulls={};grids={('full',size):{} for size in SIZES};rows=[]
    counts={'input_rows_scanned':0,'target_rows':0,'invalid_target_metadata':0,'missing_geometry_rows':0}
    for path in files:
        for part in pd.read_csv(path,usecols=['part_dt','rfid_id','rfid_time','geom'],
                dtype=str,chunksize=chunk_size,encoding='utf-8-sig'):
            counts['input_rows_scanned']+=len(part)
            part=part.loc[part.rfid_id.isin(wanted)].copy()
            if part.empty:continue
            dates=pd.to_datetime(part.part_dt,format='%Y%m%d',errors='coerce')
            hours=pd.to_numeric(part.rfid_time,errors='coerce')
            valid=dates.notna() & hours.between(0,23) & hours.eq(hours.round())
            counts['invalid_target_metadata']+=int((~valid).sum());part=part.loc[valid]
            if part.empty:continue
            x,_=row_features(part.geom.to_numpy())
            x[~np.isfinite(x[:,12])]=np.nan
            frame=pd.DataFrame(x,columns=NAMES)
            frame['id']=part.rfid_id.to_numpy(dtype=np.int64)
            frame['date']=part.part_dt.to_numpy(dtype=np.int32)
            frame['hour']=part.rfid_time.to_numpy(dtype=np.int8)
            rows.append(frame);counts['target_rows']+=len(frame)
            counts['missing_geometry_rows']+=int((~np.isfinite(x[:,12])).sum())
            rid=frame.id.to_numpy();date=frame.date.to_numpy();pos=np.searchsorted(ids,rid)
            geometry=shapely.from_wkt(np.where(part.geom.isna(),None,part.geom),on_invalid='ignore')
            coordinates,row=shapely.get_coordinates(geometry,return_index=True)
            good=np.isfinite(coordinates).all(axis=1)&(np.abs(coordinates[:,0])<=180)&(np.abs(coordinates[:,1])<=90)
            coordinates=coordinates[good];row=row[good]
            if not len(row):continue
            px,py=projector.transform(coordinates[:,0],coordinates[:,1]);xy=np.column_stack([px,py])
            good=np.isfinite(xy).all(axis=1);xy=xy[good];row=row[good]
            if not len(row):continue
            keys=pos[row]*100000000+date[row]
            unique,inverse=np.unique(keys,return_inverse=True);order=np.argsort(inverse,kind='stable')
            hulls=shapely.convex_hull(shapely.multipoints(xy[order],indices=inverse[order]))
            for key,hull in zip(unique,hulls):
                key=int(key)
                day_hulls[key]=shapely.convex_hull(shapely.union(day_hulls[key],hull)) if key in day_hulls else hull
            for size in SIZES:
                gx=np.floor(xy[:,0]/size).astype(np.int64);gy=np.floor(xy[:,1]/size).astype(np.int64)
                if not ((np.abs(gx)<2**19).all() and (np.abs(gy)<2**19).all()):
                    raise ValueError('Projected grid coordinates exceed the original packing range')
                packed=np.unique(row.astype(np.int64)*CELLSPACE+(gx&(2**20-1))*2**20+(gy&(2**20-1)))
                local_row=packed//CELLSPACE;cell=packed%CELLSPACE
                keys,visits=np.unique(pos[local_row]*CELLSPACE+cell,return_counts=True)
                table=grids[('full',size)]
                for key,count in zip(keys,visits):table[int(key)]=table.get(int(key),0)+int(count)
        print(json.dumps({'phase':'features','file':path.name,**counts,
            'elapsed_seconds':round(time.perf_counter()-started,2)},ensure_ascii=False),flush=True)
    if not rows:raise ValueError('No target observations were found')
    data=pd.concat(rows,ignore_index=True);del rows
    missing_ids=set(ids)-set(data.id)
    if missing_ids:raise ValueError(f'Missing target boats: {sorted(missing_ids)}')
    data['ordinal_hour']=pd.to_datetime(data.date.astype(str),format='%Y%m%d').to_numpy().astype('datetime64[h]').astype(np.int64)+data.hour.to_numpy()
    if data.duplicated(['id','ordinal_hour']).any():raise ValueError('Duplicate actual vessel/hour rows;inspect source rather than joining tracks')
    data['state']=state_codes(data.length_km.to_numpy(),data.linearity.to_numpy(),
        np.isfinite(data[['length_km','linearity','center_lon','center_lat']]).all(axis=1).to_numpy())
    basic=_round_like_source(summaries(data,ids),8)
    keys=np.array(sorted(day_hulls),dtype=np.int64)
    hulls=np.array([day_hulls[int(key)] for key in keys],dtype=object)
    meta=data[['id','date','hour']].copy();meta['geometry_missing']=~np.isfinite(data.center_lon.to_numpy())
    layout=_round_like_source(layout_features(ids,np.full((len(ids),1),99999999,dtype=np.int64),meta,keys,hulls,grids),9)
    states,details=extract(data,ids);states=_round_like_source(states,9)
    combined=basic.join(layout).join(states)
    if list(combined.columns)!=schema['columns']:raise ValueError('Feature column names/order differ from the fixed model schema')
    combined=combined.reindex(np.asarray(target_ids,dtype=np.int64))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    combined.to_csv(output,float_format='%.17g')
    audit={**counts,'boats':len(combined),'features':combined.shape[1],
        'label_columns_read':False,'provided_target_bundle_only':True,
        'elapsed_seconds':time.perf_counter()-started,'state_details':details,
        'csv_rounding':{'basic':8,'layout':9,'state':9}}
    output.with_suffix('.audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    return combined
