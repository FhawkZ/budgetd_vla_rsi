"""Fetch fixed native DINO/SAM weights with a 30-minute bound and per-file hashes."""
import argparse, concurrent.futures, fcntl, hashlib, json, os, shutil, signal, threading, time
from pathlib import Path
from huggingface_hub import hf_hub_download

root=Path(__file__).resolve().parents[1];runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
parser=argparse.ArgumentParser();parser.add_argument('--model',required=True,choices=['dino','sam']);args=parser.parse_args()
manifest=json.loads((root/'configs/native-vision-models.json').read_text())['models'][args.model]
assert len(manifest['sha'])==40
dest=runtime/'models'/manifest['destination_folder']
out=runtime/'outputs/native-vision-deploy-20261029'/args.model;out.mkdir(parents=True,exist_ok=True)
lock=(runtime/('locks/native-vision-'+args.model+'.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(runtime).free>(5<<30)
state={'status':'running','pid':os.getpid(),'started_unix':time.time(),'repository':manifest['id'],'revision':manifest['sha'],'workers':4,'wall_limit_seconds':1800,'model_calls':0,'gpu_jobs':0,'files':{},'verified_files':0,'verified_bytes':0}
mutex=threading.Lock()
def save():
 state['updated_unix']=time.time();p=out/'status.json';t=p.with_name(f'status.{os.getpid()}.{threading.get_ident()}.tmp');t.write_text(json.dumps(state,indent=2));t.replace(p)
def interrupted(sig,frame):
 state.update(status='interrupted',error=f'signal {sig}; HF resume cache retained');save();os._exit(128+sig)
signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGALRM,interrupted);signal.alarm(1800)
def fetch(row):
 name=row['rfilename']
 with mutex:state['files'][name]={'status':'downloading'};save()
 try:
  path=Path(hf_hub_download(repo_id=manifest['id'],revision=manifest['sha'],filename=name,local_dir=dest,endpoint='https://hf-mirror.com',token=False))
  assert path.stat().st_size==row['size'],name
  h=hashlib.sha256() if 'lfs' in row else hashlib.sha1(b'blob '+str(row['size']).encode()+b'\0')
  with path.open('rb') as f:
   for b in iter(lambda:f.read(8<<20),b''):h.update(b)
  expected=row['lfs']['sha256'] if 'lfs' in row else row['blobId'];assert h.hexdigest()==expected,name
  with mutex:
   state['files'][name]={'status':'verified','bytes':row['size'],'hash':expected,'hash_type':'sha256' if 'lfs' in row else 'git_blob_sha1'};state['verified_files']+=1;state['verified_bytes']+=row['size'];save()
 except Exception as exc:
  with mutex:state['files'][name]={'status':'failed','error':repr(exc)};save()
  raise
save()
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,manifest['siblings']))
 state.update(status='complete',finished_unix=time.time(),destination=str(dest));save()
except Exception as exc:state.update(status='failed',error=repr(exc));save();raise
