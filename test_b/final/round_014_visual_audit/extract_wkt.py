"""Read-only, bounded-memory extraction of the existing Test B score rows."""
from pathlib import Path
import csv, json, sqlite3, sys, time
from datetime import datetime
import pandas as pd
import psutil

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = ROOT / 'testB/과거/first_results/hourly_scores.parquet'
RAW = Path('F:/문제 데이터_수정_1103_v2/테스트셋 및 결과제출 샘플/테스트셋')

def memory(stage, estimate_mb):
    v = psutil.virtual_memory()
    rec = dict(time=datetime.now().astimezone().isoformat(), stage=stage,
               available_mib=round(v.available/2**20, 1), estimated_peak_mib=estimate_mb,
               basis='CSV one record at a time; 46,705 score keys; SQLite cache 8 MiB; no parallel rendering')
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    if v.available < (estimate_mb + 200)*2**20:
        raise MemoryError('Insufficient RAM; defer this stage instead of forcing execution')
    return rec

def main():
    started=time.time()
    mem=memory('raw extraction',350)
    df=pd.read_parquet(SOURCE)
    assert len(df)==46705 and df.rfid_id.nunique()==100
    df.rfid_id=df.rfid_id.astype(str)
    assert not df.duplicated(['rfid_id','ts']).any()
    dbpath=OUT/'raw_geometry.sqlite'
    con=sqlite3.connect(dbpath)
    con.execute('PRAGMA cache_size=-8192')
    con.execute('CREATE TABLE IF NOT EXISTS geom (idx INTEGER, ship TEXT, day INTEGER, hour INTEGER, ordinal INTEGER, wkt TEXT, PRIMARY KEY(ship,day,hour))')
    if con.execute('SELECT COUNT(*) FROM geom').fetchone()[0]:
        raise RuntimeError('Existing extraction database is nonempty; refusing to append duplicate run')
    stats=[]; offset=0
    csv.field_size_limit(50_000_000)
    ships=set(df.rfid_id)
    for month in range(1,7):
        p=RAW/f'vpass_{month}월 데이터.csv'
        sub=df[df.source_month==month]
        keys={(str(r.rfid_id),int(r.part_dt),int(r.rfid_time)): (int(r.row_index),int(r.source_ordinal)) for r in sub.itertuples()}
        found=set(); relevant=0; ordinal_mismatch=0; duplicates=0
        before=p.stat()
        with p.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            assert reader.fieldnames==['part_dt','rfid_id','rfid_time','geom']
            for ordinal,row in enumerate(reader):
                if row['rfid_id'] not in ships: continue
                relevant+=1
                key=(row['rfid_id'],int(row['part_dt']),int(row['rfid_time']))
                if key not in keys: continue
                if key in found:
                    duplicates+=1
                    raise RuntimeError(f'Duplicate raw key: {key}')
                idx,expected_ordinal=keys[key]
                ordinal_mismatch+=int(ordinal+offset!=expected_ordinal or ordinal!=idx)
                con.execute('INSERT INTO geom VALUES (?,?,?,?,?,?)',(idx,*key,ordinal+offset,row['geom']))
                found.add(key)
        con.commit()
        after=p.stat()
        assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
        rec=dict(path=str(p),size_bytes=before.st_size,mtime_ns=before.st_mtime_ns,
                 expected_rows=len(keys),matched_rows=len(found),all_rows_for_100_ships=relevant,
                 unmatched_score_rows=len(keys)-len(found),ordinal_mismatches=ordinal_mismatch,
                 duplicate_keys=duplicates,source_ordinal_offset=offset,total_csv_rows=ordinal+1)
        stats.append(rec); print(json.dumps(rec,ensure_ascii=False),flush=True)
        assert len(found)==len(keys), rec
        assert ordinal_mismatch==0, rec
        offset+=ordinal+1
    con.execute('CREATE INDEX IF NOT EXISTS ship_idx ON geom(ship)'); con.commit();con.close()
    result=dict(coordinate_source='원본 WKT',raw_directory=str(RAW),score_source=str(SOURCE),
                search_drives=['C:','D:','E:','F:'],search_note='rg --files --hidden --no-ignore vpass filename search; inaccessible OS directories excluded by filesystem permissions',
                selected_reason='2025 Test CSVs; match all score keys and source ordinals; do not use 2026 reference CSVs',
                sources=stats,memory_check=mem,elapsed_seconds=round(time.time()-started,2))
    (OUT/'source_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('EXTRACTION COMPLETE',flush=True)

if __name__=='__main__': main()
