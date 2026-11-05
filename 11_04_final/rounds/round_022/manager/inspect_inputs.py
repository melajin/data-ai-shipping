import datetime,hashlib,json,os
from pathlib import Path
import psutil
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
source=ROOT.parent/'26_11_2/work/재식별_투트랙_001r1/s3_hourly.parquet'
vm=psutil.virtual_memory();expected=256*2**20
other=[]
for p in psutil.process_iter(['pid','name','cmdline','memory_info']):
 try:
  if 'python' in (p.info['name'] or '').lower():other.append(dict(pid=p.pid,argv=p.info['cmdline'],rss=p.info['memory_info'].rss))
 except(psutil.NoSuchProcess,psutil.AccessDenied):pass
pre=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),available_bytes=vm.available,expected_peak_bytes=expected,basis='pyarrow import + parquet footer only + streamed SHA256; no table materialization',other_python=other)
(R/'logs/metadata_preflight.json').write_text(json.dumps(pre,indent=2)+'\n',encoding='utf8')
assert vm.available>=max(1.5*2**30,expected+2**30)
import pyarrow,pyarrow.parquet as pq
pf=pq.ParquetFile(source)
with source.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source=str(source),bytes=source.stat().st_size,sha256=h,schema=str(pf.schema_arrow),row_count=pf.metadata.num_rows,row_groups=[dict(rows=pf.metadata.row_group(i).num_rows,uncompressed_bytes=pf.metadata.row_group(i).total_byte_size) for i in range(pf.metadata.num_row_groups)],row_values_read=False,pyarrow_version=pyarrow.__version__,rss_bytes=psutil.Process().memory_info().rss)
(R/'manager/s3_metadata.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(out,ensure_ascii=False))
