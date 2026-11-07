import hashlib, importlib.metadata as md, json, pathlib, platform, sys, zipfile
from datetime import datetime, timezone
root=pathlib.Path(__file__).resolve().parents[3]
out=root/'rounds/round_004/environment'
records=[]
for dist in sorted(md.distributions(),key=lambda d:d.metadata['Name'].lower()):
    license_files=[]
    for f in dist.files or []:
        if 'dist-info' in str(f) and any(w in str(f).lower() for w in ['license','copying','notice']):
            p=dist.locate_file(f)
            if p.is_file():
                raw=p.read_bytes(); target=out/'licenses'/dist.metadata['Name']/str(f).split('.dist-info/',1)[-1]
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                license_files.append({'source':str(p),'copy':str(target.relative_to(root)),'sha256':hashlib.sha256(raw).hexdigest()})
    records.append({'name':dist.metadata['Name'],'version':dist.version,'license':dist.metadata.get('License'),'license_expression':dist.metadata.get('License-Expression'),'home_page':dist.metadata.get('Home-page'),'project_urls':dist.metadata.get_all('Project-URL'),'requires_python':dist.metadata.get('Requires-Python'),'license_files':license_files})
data={'utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'packages':records,'torch_tabicl_imported':False}
(out/'installed_metadata.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'packages':len(records),'python':sys.version,'metadata_output':str(out/'installed_metadata.json')}))
