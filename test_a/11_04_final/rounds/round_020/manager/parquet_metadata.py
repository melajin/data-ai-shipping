import datetime,hashlib,json,sys
from pathlib import Path
import psutil
out=Path(__file__).resolve().parent
available=psutil.virtual_memory().available
assert available>=2*2**30
import pyarrow
import pyarrow.parquet as pq
p=Path('D:/obsidian/claude/obsidian_export/DATA AI SHIPPING/26_11_2/work/재식별_투트랙_001r1/s6_fingerprint_grid.parquet')
f=pq.ParquetFile(p)
r=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=sys.executable,pyarrow_version=pyarrow.__version__,path=str(p),bytes=p.stat().st_size,sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),schema=str(f.schema_arrow),num_rows=f.metadata.num_rows,num_row_groups=f.metadata.num_row_groups,row_groups=[dict(rows=f.metadata.row_group(i).num_rows,total_uncompressed_bytes=f.metadata.row_group(i).total_byte_size) for i in range(f.metadata.num_row_groups)],row_values_read=False,available_bytes_before_import=available,expected_peak_bytes=256*2**20,estimate_basis='pyarrow import and footer metadata only; no table materialization',rss_bytes_after=psutil.Process().memory_info().rss)
(out/'round021_parquet_metadata.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(r,ensure_ascii=False))
