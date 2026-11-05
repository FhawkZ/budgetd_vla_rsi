import ast,concurrent.futures,hashlib,json,os,time,urllib.request
from pathlib import Path
R=Path('/dev/shm/agent-rsi-lzgpu301-20261105/runtime');out=Path('/root/autodl-tmp/qian/budgeted-vla-rsi-migration');start=time.time();status={'status':'running','pid':os.getpid(),'started_unix':start,'max_seconds':600,'reason':'CDN plain URL returned partial body; explicit range cache keys with exact Content-Range','model_calls':0}
def save():
 p=out/'clip-range-status.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(status,indent=2));t.replace(p)
tree=ast.parse((R/'vendor/CLIP-d05afc436d78f1c48dc0dbf8e5980a9d471f35f6/clip/clip.py').read_text());m=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_MODELS' for t in n.targets));url=m['ViT-B/32'];size=353976522;expected='40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af';parts=R/'models/CLIP-ViT-B-32/range-parts';parts.mkdir(exist_ok=True);chunk=8<<20
def one(a):
 b=min(a+chunk,size)-1;req=urllib.request.Request(url+'?rsi_range='+str(a),headers={'Range':f'bytes={a}-{b}'})
 with urllib.request.urlopen(req,timeout=60) as x:
  assert x.status==206 and x.headers.get('Content-Range')==f'bytes {a}-{b}/{size}'
  p=parts/str(a)
  with p.open('wb') as f:
   total=0
   while data:=x.read(1<<20):
    total+=len(data);assert total<=b-a+1 and time.time()-start<600;f.write(data)
  assert total==b-a+1
 return a
try:
 save()
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  for f in concurrent.futures.as_completed([ex.submit(one,a) for a in range(0,size,chunk)]):f.result();status['complete_chunks']=status.get('complete_chunks',0)+1;save()
 dest=parts.parent/'ViT-B-32.pt.verified-part';h=hashlib.sha256()
 with dest.open('wb') as f:
  for a in range(0,size,chunk):
   data=(parts/str(a)).read_bytes();h.update(data);f.write(data)
 assert h.hexdigest()==expected;dest.replace(parts.parent/'ViT-B-32.pt');status.update(status='complete',sha256=expected,bytes=size)
except BaseException as e:status.update(status='failed',error=repr(e))
finally:status['finished_unix']=time.time();save()
