"""Fetch exact official commits into external runtime; record archive hashes."""
import argparse,hashlib,json,os,tarfile,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--runtime',default=os.environ.get('RSI_RUNTIME_ROOT','/root/autodl-tmp/Dex_runtime/agent-rsi'));a=p.parse_args()
root=Path(a.runtime);vendor=root/'vendor';vendor.mkdir(parents=True,exist_ok=True)
config=json.loads((Path(__file__).resolve().parents[1]/'configs/sources.json').read_text())
receipts=[]
for name,spec in config.items():
 target=vendor/(name+'-'+spec['commit']);archive=vendor/(name+'-'+spec['commit']+'.tar.gz')
 if target.exists():
  receipt=target/'.source-receipt.json'
  if not receipt.exists():raise RuntimeError(f'Unverified existing source: {target}')
  receipts.append(json.loads(receipt.read_text()));continue
 url=spec['url'].removesuffix('.git').replace('https://github.com/','https://codeload.github.com/')+'/tar.gz/'+spec['commit']
 temporary=archive.with_suffix('.part')
 with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as out:
  size=0
  while chunk:=response.read(1024*1024):
   size+=len(chunk)
   if size>256*1024*1024:raise RuntimeError('source archive unexpectedly large')
   out.write(chunk)
 assert hashlib.sha256(temporary.read_bytes()).hexdigest()==spec['archive_sha256'], 'source archive hash mismatch'
 temporary.rename(archive)
 staging=vendor/(name+'-extract');staging.mkdir(exist_ok=False)
 with tarfile.open(archive) as tar:tar.extractall(staging,filter='data')
 directories=list(staging.iterdir());assert len(directories)==1 and directories[0].is_dir()
 directories[0].rename(target);staging.rmdir()
 receipt={**spec,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'archive_bytes':archive.stat().st_size,'path':str(target)}
 (target/'.source-receipt.json').write_text(json.dumps(receipt,indent=2));receipts.append(receipt)
 print(json.dumps(receipt),flush=True)
(root/'source-receipts.json').write_text(json.dumps(receipts,indent=2))
