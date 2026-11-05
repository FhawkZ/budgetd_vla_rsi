import json,os,subprocess,time
from pathlib import Path
B=Path('/root/autodl-tmp/qian/budgeted-vla-rsi-migration');SOFT=Path('/root/autodl-tmp/qian/.dex_env/agent-rsi-standalone/software');RAM=Path('/dev/shm/agent-rsi-lzgpu301-20261105');ROOT=Path('/root/autodl-tmp/qian/budgeted-vla-rsi');PY=SOFT/'envs/robotwin/bin/python';UV='/home/lzgpu301/.local/bin/uv';start=time.time()
s={'status':'waiting_base_environment','pid':os.getpid(),'started_unix':start,'max_seconds':7800,'model_calls':0,'robot_episodes':0,'automatic_robot_launch':False}
def save():
 p=B/'sim-post-status.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(s,indent=2));t.replace(p)
def run(name,args):
 s.update(status='running',phase=name);save()
 with (B/('sim-post-'+name+'.log')).open('wb') as f:
  p=subprocess.run(args,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
  if p.returncode:raise RuntimeError(name+' failed')
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',UV_CACHE_DIR=str(RAM/'uv-cache'),TMPDIR=str(SOFT/'tmp'),UV_LINK_MODE='copy',LD_LIBRARY_PATH=str(SOFT/'system/usr/lib/x86_64-linux-gnu'))
try:
 save()
 while time.time()-start<7200:
  p=B/'sim-env-v3-status.json'
  if p.exists():
   status=json.loads(p.read_text())
   if status['status']=='failed':raise RuntimeError('base install failed; no retry')
   if status['status']=='base_installed_pending_curobo_clip_and_verification':break
  time.sleep(15)
 else:raise TimeoutError('base install deadline')
 run('curobo',[UV,'pip','install','--python',str(PY),'--no-deps',str(B/'nvidia_curobo-0.7.8-cp311-cp311-linux_x86_64.whl')])
 run('clip',[UV,'pip','install','--python',str(PY),'--no-deps','--no-build-isolation',str(RAM/'runtime/vendor/CLIP-d05afc436d78f1c48dc0dbf8e5980a9d471f35f6')])
 run('check',[UV,'pip','check','--python',str(PY)])
 run('imports',[str(PY),'-c','import torch,torchvision,sapien,mplib,open3d,clip,ftfy; print(torch.__version__); print("CPU imports only; cuRobo CUDA import deliberately deferred")'])
 # Alias skillrsi to this dedicated complete uv environment. Other project envs are not modified.
 alias=SOFT/'envs/skillrsi'
 if not alias.exists():alias.symlink_to(SOFT/'envs/robotwin',target_is_directory=True)
 s.update(status='environment_ready_pending_source_asset_protocol_verification',interpreter=str(PY),software_bytes=int(subprocess.check_output(['du','-sb',str(SOFT)],text=True).split()[0]))
except BaseException as e:s.update(status='failed',error=repr(e))
finally:s['finished_unix']=time.time();save()
