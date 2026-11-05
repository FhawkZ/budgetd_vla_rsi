"""Bounded CPU migration finalizer. Never loads a model or starts a robot."""
import ast,hashlib,json,os,subprocess,time,urllib.request,zipfile,shutil
from pathlib import Path
ROOT=Path('/root/autodl-tmp/qian/budgeted-vla-rsi')
R=Path('/dev/shm/agent-rsi-lzgpu301-20261105/runtime')
OUT=Path('/root/autodl-tmp/qian/budgeted-vla-rsi-migration')
started=time.time();status={'status':'waiting_assets','pid':os.getpid(),'started_unix':started,'max_seconds':8500,'model_calls':0,'robot_episodes':0,'automatic_robot_launch':False}
def save():
 status['updated_unix']=time.time();p=OUT/'stage-owner-status.json';q=p.with_suffix('.tmp');q.write_text(json.dumps(status,indent=2));q.replace(p)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def clip():
 source=R/'vendor/CLIP-d05afc436d78f1c48dc0dbf8e5980a9d471f35f6/clip/clip.py'
 tree=ast.parse(source.read_text());models=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_MODELS' for t in n.targets))
 url=models['ViT-B/32'];sha='40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af';assert sha in url
 dest=R/'models/CLIP-ViT-B-32/ViT-B-32.pt';dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists() and dest.stat().st_size==353976522 and digest(dest)==sha:return
 part=dest.with_suffix('.pt.partial');count=0;deadline=time.monotonic()+600
 with urllib.request.urlopen(url,timeout=60) as response,part.open('wb') as f:
  while b:=response.read(1<<20):
   count+=len(b)
   if count>353976522 or time.monotonic()>deadline:raise TimeoutError('CLIP transfer bound')
   f.write(b)
 assert count==353976522 and digest(part)==sha
 part.replace(dest);status['clip_verified']=True;save()
try:
 save()
 try:clip()
 except Exception as e:status['clip_error']=repr(e);save()
 while time.time()-started<8500:
  statuses={}
  for label,n in [('qwen','qwen30b-migration-lzgpu301-20261105'),('assets','robotwin-migration-lzgpu301-v2-20261105')]:
   p=R/'outputs'/n/'status.json'
   if p.exists():
    value=json.loads(p.read_text());statuses[label]=value
    (OUT/(label+'-status-mirror.json')).write_text(json.dumps(value,indent=2))
  status['downloads']={k:{n:v.get(n) for n in ['status','pid','current_file','current_file_chunks_ready','error']} for k,v in statuses.items()};save()
  if any(v.get('status')=='failed' for v in statuses.values()):raise RuntimeError('bounded download failed; no automatic retry')
  if len(statuses)==2 and all(v.get('status')=='complete' for v in statuses.values()):break
  time.sleep(30)
 else:raise TimeoutError('migration finalizer deadline')
 status['status']='verifying_and_extracting';save()
 manifest=json.loads((ROOT/'configs/robotwin-assets.json').read_text());dest=R/'assets/robotwin-c15cc97b/assets'
 assert not dest.exists();dest.mkdir(parents=True)
 expanded=0
 for row in manifest['files']:
  p=R/'downloads/robotwin-assets'/row['path'];assert p.stat().st_size==row['bytes'] and digest(p)==row['sha256']
  with zipfile.ZipFile(p) as z:
   expanded+=sum(i.file_size for i in z.infolist());free=shutil.disk_usage(R).free
   assert free>max(100*2**30,.2*shutil.disk_usage(R).total)+sum(i.file_size for i in z.infolist())+2*2**30
   for item in z.infolist():
    name=Path(item.filename);assert not name.is_absolute() and '..' not in name.parts and (item.external_attr>>16)&0o170000!=0o120000
   z.extractall(dest)
 (dest.parent/'.robotwin-assets.json').write_text(json.dumps({'repository':manifest['repository'],'revision':manifest['revision'],'archives':{x['path']:x['sha256'] for x in manifest['files']}},indent=2))
 native=R/'vendor/robotwin-official-6dde571';old='/root/autodl-tmp/Dex_runtime/agent-rsi';changes=[]
 for p in native.rglob('*'):
  if p.is_symlink():
   link=os.readlink(p)
   if link.startswith(old+'/'):
    target=str(R)+link[len(old):];p.unlink();p.symlink_to(target);changes.append({'path':str(p),'old_target':link,'new_target':target})
 for name in ['curobo_left.yml','curobo_right.yml']:
  p=native/'assets/embodiments/aloha-agilex'/name;s=p.read_text()
  if old in s:
   before=digest(p);p.write_text(s.replace(old,str(R)));changes.append({'path':str(p),'old_sha256':before,'new_sha256':digest(p),'change':'absolute path relocation only'})
 (OUT/'path-relocations.json').write_text(json.dumps(changes,indent=2))
 status.update(status='assets_ready_pending_sim_environment_and_protocol_freeze',expanded_asset_bytes=expanded,path_changes=len(changes),model_calls=0,robot_episodes=0);save()
except BaseException as e:status.update(status='blocked_deployment',error=repr(e));save()
finally:status['finished_unix']=time.time();save()
