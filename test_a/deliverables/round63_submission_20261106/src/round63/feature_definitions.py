"""Geometry and state definitions used in Round63;no fitting or I/O."""
import numpy as np
import pandas as pd
import shapely

NAMES=['length_km', 'extent_km', 'linearity', 'n_points', 'n_parts', 'zero_step_fraction', 'axis_strength', 'direction_strength', 'turn_abs', 'turn_reversal', 'short_step_fraction', 'long_step_fraction', 'center_lon', 'center_lat', 'width_km', 'height_km']
SIZES=[100,500,2000]
CELLSPACE=2**40
VIEWS=["full"]

def row_features(wkts):
    wkts=np.where(pd.isna(wkts),None,wkts)
    g=shapely.from_wkt(wkts,on_invalid='ignore');n=len(g)
    parts,gi=shapely.get_parts(g,return_index=True)
    xy,pi=shapely.get_coordinates(parts,return_index=True)
    out=np.zeros((n,len(NAMES)),dtype=np.float32)
    bounds=shapely.bounds(g)
    out[:,12:14]=np.column_stack(((bounds[:,0]+bounds[:,2])/2,(bounds[:,1]+bounds[:,3])/2))
    out[:,14]=(bounds[:,2]-bounds[:,0])*111.32*np.cos(np.deg2rad(out[:,13]))
    out[:,15]=(bounds[:,3]-bounds[:,1])*110.574
    out[:,1]=np.hypot(out[:,14],out[:,15])
    out[:,3]=shapely.get_num_coordinates(g);out[:,4]=shapely.get_num_geometries(g)
    if len(xy)<2:
        missing=~np.isfinite(out[:,12]);out[missing]=np.nan
        return out,int(np.sum(missing))
    valid=pi[:-1]==pi[1:];src=np.flatnonzero(valid);rr=gi[pi[src]]
    dx=(xy[src+1,0]-xy[src,0])*111.32*np.cos(np.deg2rad((xy[src+1,1]+xy[src,1])/2))
    dy=(xy[src+1,1]-xy[src,1])*110.574; dist=np.hypot(dx,dy)
    def bc(v): return np.bincount(rr,weights=v,minlength=n)
    cnt=np.bincount(rr,minlength=n);den=np.maximum(cnt,1)
    length=bc(dist);out[:,0]=length
    out[:,5]=bc(dist<.001)/den;out[:,10]=bc(dist<.01)/den;out[:,11]=bc(dist>1)/den
    theta=np.arctan2(dy,dx);moving=dist>.001
    out[:,6]=np.hypot(bc(np.cos(2*theta)*dist),bc(np.sin(2*theta)*dist))/np.maximum(length,1e-6)
    out[:,7]=np.hypot(bc(dx),bc(dy))/np.maximum(length,1e-6)
    # Net distance of each actual LineString; never bridge disconnected parts.
    cp=shapely.get_num_coordinates(parts);end=np.cumsum(cp)-1;start=np.r_[0,end[:-1]+1];nz=cp>0
    vx=(xy[end[nz],0]-xy[start[nz],0])*111.32*np.cos(np.deg2rad((xy[end[nz],1]+xy[start[nz],1])/2))
    vy=(xy[end[nz],1]-xy[start[nz],1])*110.574
    out[:,2]=np.bincount(gi[nz],weights=np.hypot(vx,vy),minlength=n)/np.maximum(length,1e-6)
    adj=(src[1:]==src[:-1]+1)&(rr[1:]==rr[:-1])&(pi[src[1:]]==pi[src[:-1]])&moving[:-1]&moving[1:]
    a=np.flatnonzero(adj);dt=np.abs(np.arctan2(np.sin(theta[a+1]-theta[a]),np.cos(theta[a+1]-theta[a])))
    tc=np.maximum(np.bincount(rr[a],minlength=n),1)
    out[:,8]=np.bincount(rr[a],weights=dt,minlength=n)/tc
    out[:,9]=np.bincount(rr[a],weights=dt>2.3,minlength=n)/tc
    missing=shapely.is_missing(g);out[missing]=np.nan
    return out,int(np.sum(missing))

def summaries(a,ids):
    g=a.groupby('id',sort=True);f=g[NAMES].agg(['mean','std','median','max']);f.columns=['%s__%s'%c for c in f.columns]
    e=g.agg(n_rows=('date','size'),n_days=('date','nunique'),length_sum_km=('length_km','sum'),lon_min=('center_lon','min'),lon_max=('center_lon','max'),lat_min=('center_lat','min'),lat_max=('center_lat','max'))
    b=a.assign(night=((a.hour<6)|(a.hour>=18)).astype(float),h_sin=np.sin(a.hour*2*np.pi/24),h_cos=np.cos(a.hour*2*np.pi/24));h=b.groupby('id')[['night','h_sin','h_cos']].mean()
    active=a.loc[a.length_km>.05].groupby('id')[['length_km','extent_km','linearity','axis_strength','direction_strength','turn_abs','turn_reversal','short_step_fraction']].agg(['mean','std','median']);active.columns=['active_%s__%s'%c for c in active.columns]
    return f.join(e).join(h).join(active).reindex(ids)

def geom_features(h,prefix):
    area=shapely.area(h);perimeter=shapely.length(h);mrr=shapely.minimum_rotated_rectangle(h);ra=shapely.area(mrr);out=[]
    for geom,rect,a,p,r in zip(h,mrr,area,perimeter,ra):
        c=shapely.get_coordinates(rect)
        if len(c)>=4:
            edges=np.linalg.norm(np.diff(c,axis=0),axis=1);long=edges.max();short=edges.min()
        elif len(c)==2:long=float(np.linalg.norm(c[1]-c[0]));short=0.
        else:long=short=0.
        if shapely.is_empty(geom):
            out.append([np.nan]*7+[0,1])
        else:
            out.append([a/1e6,p/1000,long/1000,short/1000,short/long if long>0 else np.nan,a/r if r>0 else np.nan,4*np.pi*a/(p*p) if p>0 else np.nan,int(a==0),0])
    return pd.DataFrame(out,columns=[prefix+c for c in ['area_km2','perimeter_km','long_axis_km','short_axis_km','axis_ratio','mrr_fill','compactness','degenerate','empty']])

def layout_features(ids, cuts, meta, keys, geoms, grids):
    pos = keys // 100000000
    date = keys % 100000000
    spec = []
    meta['ordinal_hour'] = pd.to_datetime(meta.date.astype(str), format='%Y%m%d').to_numpy().astype('datetime64[h]').astype(np.int64) + meta.hour
    for j, v in enumerate(VIEWS):
        keep = date <= cuts[pos, j]
        kk = keys[keep]
        hh = geoms[keep]
        pp = pos[keep]
        dd = date[keep]
        hulls = []
        dailyrows = []
        for k in range(len(ids)):
            local = hh[pp == k]
            coords = shapely.get_coordinates(local)
            hull = shapely.convex_hull(shapely.multipoints(coords)) if len(coords) else shapely.GeometryCollection()
            hulls.append(hull)
            areas = shapely.area(local) / 1000000.0
            perimeters = shapely.length(local) / 1000
            area = shapely.area(hull) / 1000000.0
            if len(local) > 1:
                intersect = shapely.area(shapely.intersection(local[:-1], local[1:]))
                union = shapely.area(local[:-1]) + shapely.area(local[1:]) - intersect
                overlap = np.divide(intersect, union, out=np.full_like(intersect, np.nan), where=union > 0)
                cx = shapely.get_x(shapely.centroid(local))
                cy = shapely.get_y(shapely.centroid(local))
                shift = np.hypot(np.diff(cx), np.diff(cy)) / 1000
            else:
                overlap = np.array([np.nan])
                shift = np.array([np.nan])

            def mean(z):
                return float(np.mean(z[np.isfinite(z)])) if np.isfinite(z).any() else np.nan
            dailyrows.append([np.median(areas) if len(areas) else np.nan, np.quantile(areas, 0.9) if len(areas) else np.nan, mean(areas) / area if area > 0 else np.nan, mean(perimeters), mean(overlap), mean(shift), int(len(local) > 1)])
        f = geom_features(np.array(hulls, dtype=object), 'hull_')
        f.index = ids
        f.index.name = 'id'
        f[[f'dayhull_{c}' for c in ['area_median_km2', 'area_q90_km2', 'area_to_full_fraction', 'perimeter_mean_km', 'consecutive_observed_overlap', 'center_shift_km', 'multiple_days_available']]] = dailyrows
        center = shapely.centroid(np.array(hulls, dtype=object))
        f['loc_hull_x_m'] = shapely.get_x(center)
        f['loc_hull_y_m'] = shapely.get_y(center)
        for size in SIZES:
            table = grids[v, size]
            if isinstance(table, tuple):
                keys1, vis = table
            else:
                keys1 = np.fromiter(table.keys(), dtype=np.int64)
                vis = np.fromiter(table.values(), dtype=np.int64)
            g = pd.DataFrame({'position': keys1 // CELLSPACE, 'visits': vis})
            total = g.groupby('position').visits.transform('sum')
            g['share'] = g.visits / total
            stats = g.groupby('position').agg(cells=('visits', 'size'), observed_interval_cell_count=('visits', 'sum'), max_share=('share', 'max'), repeated_observation_cell_fraction=('visits', lambda z: float((z > 1).mean())), interval_count_median=('visits', 'median'), interval_count_q90=('visits', lambda z: float(z.quantile(0.9))))
            stats['entropy'] = -(g.share * np.log(g.share)).groupby(g.position).sum()
            stats['effective_cells'] = 1 / (g.share * g.share).groupby(g.position).sum()
            stats = stats.reindex(range(len(ids)))
            stats.index = ids
            stats.columns = [f'grid_{size}m_' + c for c in stats.columns]
            f = f.join(stats)
        m = meta.loc[meta.date.to_numpy() <= cuts[np.searchsorted(ids, meta.id), j]]
        temp = []
        for boat, obs in m.groupby('id', sort=True):
            hours = np.unique(obs.ordinal_hour)
            gaps = np.diff(hours)
            dates1 = np.unique(hours // 24)
            daygap = np.diff(dates1)
            span = int(hours[-1] - hours[0] + 1)
            day_span = int(dates1[-1] - dates1[0] + 1)
            temp.append({'id': boat, 'calendar_span_days': day_span, 'gap_unrecorded_days_inside_span': day_span - len(dates1), 'gap_unrecorded_hours_inside_span': span - len(hours), 'gap_hour_coverage_inside_endpoints': len(hours) / span, 'gap_observed_hour_interval_median': float(np.median(gaps)) if len(gaps) else np.nan, 'gap_observed_hour_interval_q90': float(np.quantile(gaps, 0.9)) if len(gaps) else np.nan, 'gap_max_unrecorded_hours': int(max(gaps.max() - 1, 0)) if len(gaps) else 0, 'gap_max_unrecorded_days': int(max(daygap.max() - 1, 0)) if len(daygap) else 0, 'geometry_missing_row_fraction': float(obs.geometry_missing.mean()), 'gap_intervals_available': int(len(gaps) > 0)})
        f = f.join(pd.DataFrame(temp).set_index('id')).reindex(ids)
    return f

def state_codes(length,linearity,valid):
    out=np.searchsorted([.05,1.,5.],length,side='right')*2+(linearity>=.5).astype(int)
    return np.where(valid,out,-1)

def adjacent_pairs(ids,hours,states):
    return (ids[1:]==ids[:-1])&(hours[1:]-hours[:-1]==1)&(states[:-1]>=0)&(states[1:]>=0)

def extract(a,ids):
    a=a.sort_values(['id','ordinal_hour']).reset_index(drop=True);n=len(ids);pos=np.searchsorted(ids,a.id.to_numpy());st=a.state.to_numpy();valid=st>=0
    coverage=np.bincount(pos,minlength=n);count=np.bincount(pos[valid],minlength=n);den=np.maximum(count,1)
    def hist(codes,size,mask=valid,normalizer=den):
        values=np.bincount(pos[mask]*size+codes[mask],minlength=n*size).reshape(n,size)
        return values/np.maximum(normalizer[:,None],1)
    sf=hist(st,8);out={f'state_fraction_{i}':sf[:,i] for i in range(8)}
    hs=hist((a.hour.to_numpy()//4)*8+st,48)
    out.update({f'hour_state_{i}':hs[:,i] for i in range(48)})
    pairs=adjacent_pairs(a.id.to_numpy(),a.ordinal_hour.to_numpy(),st)
    pcount=np.bincount(pos[1:][pairs],minlength=n)
    tr=np.bincount(pos[1:][pairs]*64+st[:-1][pairs]*8+st[1:][pairs],minlength=n*64).reshape(n,64)/np.maximum(pcount[:,None],1)
    out.update({f'adjacent_hour_transition_{i}':tr[:,i] for i in range(64)})
    out['valid_geometry_fraction']=count/coverage;out['adjacent_pair_count']=pcount;out['adjacent_pair_fraction']=pcount/np.maximum(coverage-1,1)
    assert np.allclose(sf.sum(1)[count>0],1) and np.allclose(hs.sum(1)[count>0],1) and np.allclose(tr.sum(1)[pcount>0],1)
    # One run stops at every actual timestamp gap; it is not duration of a latent action.
    continue_run=np.r_[False,pairs&(st[1:]==st[:-1])]
    run_id=np.cumsum(~continue_run)
    runs=a.assign(run_id=run_id).loc[valid].groupby(['id','state','run_id']).size().rename('rows').reset_index()
    runq=runs.groupby(['id','state']).rows.quantile([.5,.9]).unstack(['state',-1]).reindex(index=ids,columns=pd.MultiIndex.from_product([range(8),[.5,.9]]))
    runq.columns=[f'state_{k}_observed_run_q{int(q*100)}' for k,q in runq.columns]
    # State-conditioned shape, and state location relative to this same target's mean center.
    validrows=a.loc[valid].copy();means=validrows.groupby('id')[['center_lon','center_lat']].mean()
    validrows['relative_east_km']=(validrows.center_lon.to_numpy()-means.loc[validrows.id,'center_lon'].to_numpy())*111.32*np.cos(np.deg2rad(means.loc[validrows.id,'center_lat'].to_numpy()))
    validrows['relative_north_km']=(validrows.center_lat.to_numpy()-means.loc[validrows.id,'center_lat'].to_numpy())*110.574
    cols=['turn_abs','axis_strength','relative_east_km','relative_north_km']
    shape=validrows.groupby(['id','state'])[cols].mean().unstack('state').reindex(index=ids,columns=pd.MultiIndex.from_product([cols,range(8)]))
    shape.columns=[f'state_{k}_{c}' for c,k in shape.columns]
    # Variation of state mixtures across the observed days, with absent states as real zeros.
    day=validrows.groupby(['id','date','state']).size().unstack(fill_value=0).reindex(columns=range(8),fill_value=0)
    day=day.div(day.sum(axis=1),axis=0)
    daily=day.groupby(level='id').agg(['std','max']).reindex(ids)
    daily.columns=[f'day_state_{k}_{stat}' for k,stat in daily.columns]
    result=pd.DataFrame(out,index=pd.Index(ids,name='id')).join(runq).join(shape).join(daily)
    assert result.shape==(n,187) and not np.isinf(result.to_numpy()).any()
    return result,{'rows':len(a),'valid_geometry_rows':int(count.sum()),'adjacent_hour_pairs':int(pcount.sum()),'max_ordinal_hour_gap_in_used_pairs':1,'histograms_normalized':True}
