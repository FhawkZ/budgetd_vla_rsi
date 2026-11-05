import subprocess,os,time,json,signal,shutil
from pathlib import Path
ROOT=Path('/root/autodl-tmp/qian/budgeted-vla-rsi'); LOG=Path('/root/autodl-tmp/qian/budgeted-vla-rsi-migration')
SOFT=Path('/root/autodl-tmp/qian/.dex_env/agent-rsi-standalone/software'); RAM=Path('/dev/shm/agent-rsi-lzgpu301-20261105')
UV='/home/lzgpu301/.local/bin/uv'; start=time.time(); env=os.environ.copy()
env.update(UV_PYTHON_INSTALL_DIR=str(SOFT/'python'),UV_CACHE_DIR=str(RAM/'uv-cache'),TMPDIR=str(SOFT/'tmp'),CUDA_VISIBLE_DEVICES='',UV_LINK_MODE='copy',UV_HTTP_TIMEOUT='120')
for p in [SOFT/'tmp',SOFT/'envs',RAM/'uv-cache']:p.mkdir(parents=True,exist_ok=True)
s={'status':'starting','started_unix':start,'pid':os.getpid(),'max_seconds':7200,'storage_exception_user_approved':True,'max_software_bytes':11*1024**3,'model_calls':0,'robot_episodes':0,'automatic_robot_launch':False,'steps':[]}
def save():
 p=LOG/'sim-env-v3-status.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(s,indent=2));t.replace(p)
def run(name,args):
 s.update(status='running',phase=name);save()
 with (LOG/('sim-env-v3-'+name+'.log')).open('wb') as f:
  p=subprocess.Popen(args,env=env,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   while p.poll() is None:
    if time.time()-start>7200:raise TimeoutError('environment deployment wall cap')
    used=int(subprocess.check_output(['du','-sb',str(SOFT)],text=True).split()[0])
    if used>s['max_software_bytes']:raise RuntimeError('authorized approximate11GiB environment cap reached')
    s.update(child_pid=p.pid,software_bytes=used,updated_unix=time.time());save();time.sleep(5)
   s['steps'].append({'name':name,'returncode':p.returncode});save()
   if p.returncode:raise RuntimeError(name+' nonzero '+str(p.returncode))
  finally:
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(5)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(5)
try:
 run('python',[UV,'python','install','3.11.17'])
 py=SOFT/'python/cpython-3.11.17-linux-x86_64-gnu/bin/python'; ve=SOFT/'envs/robotwin'
 assert (ve/'bin/python').exists(), 'reuse already-created uv environment'
 run('pinned-packages',[UV,'pip','install','--python',str(ve/'bin/python'),'--no-deps','--prerelease','allow','--index-url','https://pypi.tuna.tsinghua.edu.cn/simple','-r',str(ROOT/'requirements/skillrsi-native-py311-301.lock')])
 s['status']='base_installed_pending_curobo_clip_and_verification'
except BaseException as e:s.update(status='failed',error=repr(e))
finally:s.update(finished_unix=time.time());save()
