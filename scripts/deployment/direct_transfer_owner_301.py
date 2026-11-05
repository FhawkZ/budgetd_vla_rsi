import os,subprocess,signal,json,hashlib,shlex,time
from pathlib import Path
R=Path('/dev/shm/agent-rsi-lzgpu301-20261105/runtime');B=Path('/root/autodl-tmp/qian/budgeted-vla-rsi-migration');SOFT=Path('/root/autodl-tmp/qian/.dex_env/agent-rsi-standalone/software');CODE=Path('/root/autodl-tmp/qian/budgeted-vla-rsi');SRC='/root/autodl-tmp/Dex_runtime/agent-rsi';start=time.time()
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(B/'source-known-hosts'),'-p','53051','lzgpu201@connect.westd.seetacloud.com']
s={'status':'running','pid':os.getpid(),'started_unix':start,'max_seconds':5400,'model_calls':0,'robot_episodes':0,'automatic_robot_launch':False,'steps':[]}
def save():
 p=B/'direct-transfer-status.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(s,indent=2));t.replace(p)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(8<<20),b''):h.update(x)
 return h.hexdigest()
def transfer(name,root,paths,dest):
 s.update(phase=name);save();t=time.time();dest.mkdir(parents=True,exist_ok=True)
 command='tar -cf - -C '+shlex.quote(root)+' '+' '.join(shlex.quote(p) for p in paths)
 with (B/(name+'-source.log')).open('wb') as log,(B/(name+'-dest.log')).open('wb') as log2:
  a=subprocess.Popen(SSH+[command],stdout=subprocess.PIPE,stderr=log,start_new_session=True)
  b=subprocess.Popen(['tar','-xpf','-','-C',str(dest)],stdin=a.stdout,stdout=log2,stderr=subprocess.STDOUT,start_new_session=True);a.stdout.close()
  try:
   while a.poll() is None or b.poll() is None:
    if time.time()-start>5400:raise TimeoutError('direct migration deadline')
    if a.poll() not in (None,0) or b.poll() not in (None,0):raise RuntimeError('tar/ssh transfer failed')
    s.update(source_pid=a.pid,destination_pid=b.pid,updated_unix=time.time());save();time.sleep(2)
   if a.returncode or b.returncode:raise RuntimeError('nonzero transfer')
  finally:
   for p in [a,b]:
    if p.poll() is None:
     os.killpg(p.pid,signal.SIGTERM)
     try:p.wait(5)
     except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(5)
 s['steps'].append({'name':name,'seconds':time.time()-t,'returncodes':[a.returncode,b.returncode]});save()
try:
 save()
 # Restore original uv-managed packages, not freshly rebuilt alternative wheels.
 transfer('frozen-environment',SRC+'/software',['envs/robotwin/lib','envs/skillrsi/lib'],SOFT)
 assert int(subprocess.check_output(['du','-sb',str(SOFT)],text=True).split()[0])<11*2**30,'approved software cap'
 transfer('fixed-assets',SRC,['assets/robotwin-c15cc97b'],R)
 manifest=json.loads((CODE/'configs/qwen30b-candidate-model-files.json').read_text());rows=manifest['files'];missing=[]
 for f in rows:
  p=R/'models/Qwen3-VL-30B-A3B-Instruct'/f['path']
  if not(p.exists() and p.stat().st_size==f['bytes'] and sha(p)==f['sha256']):missing.append('models/Qwen3-VL-30B-A3B-Instruct/'+f['path'])
 if missing:transfer('remaining-qwen',SRC,missing,R)
 s.update(phase='verifying_frozen_sources');save()
 # Compare full restored environment/assets against contemporaneous source tree hashes.
 verify_script="""import pathlib,json,hashlib,sys
root=pathlib.Path('/root/autodl-tmp/Dex_runtime/agent-rsi');result=[]
for rel in ['assets/robotwin-c15cc97b','software/envs/robotwin/lib','software/envs/skillrsi/lib']:
 for p in sorted((root/rel).rglob('*')):
  if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
  h=hashlib.sha256()
  with p.open('rb') as f:
   for x in iter(lambda:f.read(8<<20),b''):h.update(x)
  result.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
print(json.dumps(result))
"""
 q=subprocess.run(SSH+[SRC+'/software/envs/robotwin/bin/python -'],input=verify_script,text=True,capture_output=True,timeout=900);q.check_returncode();source=json.loads(q.stdout);(B/'source-file-manifest.json').write_text(q.stdout)
 for f in source:
  p=(SOFT/f['path'][9:]) if f['path'].startswith('software/') else R/f['path']
  assert p.stat().st_size==f['bytes'] and sha(p)==f['sha256'],f['path']
 verified=[]
 for f in rows:
  p=R/'models/Qwen3-VL-30B-A3B-Instruct'/f['path'];assert p.stat().st_size==f['bytes'] and sha(p)==f['sha256'];verified.append(dict(f,mtime_ns=p.stat().st_mtime_ns))
 (B/'qwen-assets-verified.json').write_text(json.dumps({'files':verified,'verified_unix':time.time()},indent=2))
 assert sha(R/'models/CLIP-ViT-B-32/ViT-B-32.pt')=='40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af'
 (B/'restored-files-audit.json').write_text(json.dumps({'verified_files':len(source),'verified_bytes':sum(f['bytes'] for f in source),'source_manifest_sha256':sha(B/'source-file-manifest.json'),'qwen_files':len(verified),'qwen_bytes':sum(f['bytes'] for f in verified),'status':'exact_bytes_before_host_path_relocation'},indent=2))
 s.update(status='transferred_verified_pending_environment_path_binding_and_protocol_freeze',verified_source_files=len(source),qwen_verified_files=len(verified))
except BaseException as e:s.update(status='failed',error=repr(e))
finally:s['finished_unix']=time.time();save()
