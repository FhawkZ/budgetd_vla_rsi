"""Verify archived code and pinned source contracts without any model or GPU call."""
import hashlib,json,os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
archive=json.loads((root/'archive/manifest.json').read_text())
for path,expected in archive['files'].items():assert sha(root/path)==expected,path
sources=json.loads((root/'configs/sources.json').read_text())
checks=json.loads((root/'configs/source-checks.json').read_text())
for row in checks:
 spec=sources[row['source']];path=runtime/'vendor'/(row['source']+'-'+spec['commit'])/row['path']
 assert sha(path)==row['sha256'],str(path)
print(json.dumps({'archive_files':len(archive['files']),'source_contract_files':len(checks),'passed':True,'model_calls':0}))
