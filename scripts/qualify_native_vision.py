"""One cached-image native DINO/SAM qualification; no robot or LLM calls."""
import argparse,fcntl,hashlib,importlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ['RSI_RUNTIME_ROOT'])
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_models():
 manifest=json.loads((ROOT/'configs/native-vision-models.json').read_text());verified={}
 for name,model in manifest['models'].items():
  directory=RUNTIME/'models'/model['destination_folder']
  for row in model['siblings']:
   p=directory/row['rfilename'];assert p.stat().st_size==row['size'],p
   h=hashlib.sha256() if 'lfs' in row else hashlib.sha1(b'blob '+str(row['size']).encode()+b'\0')
   with p.open('rb') as f:
    for b in iter(lambda:f.read(8<<20),b''):h.update(b)
   assert h.hexdigest()==(row['lfs']['sha256'] if 'lfs' in row else row['blobId']),p
  verified[name]={'directory':str(directory),'revision':model['sha'],'files':len(model['siblings'])}
 return verified

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--image',required=True);a=ap.parse_args()
 out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
 frozen={'classification':'cached-image native perception deployment qualification','image':str(Path(a.image).resolve()),'image_sha256':sha(a.image),'code_sha256':sha(__file__),'vision_manifest_sha256':sha(ROOT/'configs/native-vision-models.json'),'query':'block','max_dino_forwards':1,'max_sam_forwards':1,'max_wall_seconds':300,'physical_gpu':1,'robot_actions':0,'LLM_calls':0,'task_episodes':0}
 (out/'protocol.json').write_text(json.dumps(frozen,indent=2));report=dict(frozen,status='started',started_unix=time.time())
 def save():(out/'report.json').write_text(json.dumps(report,indent=2))
 lock=(RUNTIME/'locks/gpu1.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert int(subprocess.check_output(['nvidia-smi','-i','1','--query-gpu=memory.used','--format=csv,noheader,nounits']))<100
 assert not subprocess.check_output(['nvidia-smi','-i','1','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
 def timeout(sig,frame):raise TimeoutError('300 second qualification limit')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(300)
 try:
  report['verified_models']=verify_models();save()
  os.environ.update(CUDA_VISIBLE_DEVICES='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',ROBORSI_PERCEPTION_DEVICE='cuda:0',ROBORSI_GROUNDING_DINO_MODEL=report['verified_models']['dino']['directory'],ROBORSI_POINT_SAM_MODEL=report['verified_models']['sam']['directory'])
  import torch,numpy as np
  from PIL import Image
  torch.set_num_threads(4)
  m=importlib.import_module('roborsi.embodied.skills.base.detect_object.robotwin.policy')
  start=time.monotonic();gdp,gdm,sp,sm=m._load();torch.cuda.synchronize();report['load_seconds']=time.monotonic()-start
  counts={'dino':0,'sam':0}
  for name,model in [('dino',gdm),('sam',sm)]:
   original=model.forward
   def limited(*args,_fn=original,_name=name,**kwargs):
    counts[_name]+=1;assert counts[_name]<=1;return _fn(*args,**kwargs)
   model.forward=limited
  rgb=np.asarray(Image.open(a.image).convert('RGB'));start=time.monotonic()
  found=m.detect(rgb,'block');torch.cuda.synchronize()
  report['detections']=[{'bbox':list(x.bbox),'score':float(x.score),'centroid':list(x.centroid),'mask_pixels':int(x.mask.sum())} for x in found]
  if counts['sam']==0:
   # Explicit deployment fallback to exercise SAM weights once, not an Agent action.
   h,w=rgb.shape[:2];inputs=sp(images=Image.fromarray(rgb),input_points=[[[w/2,h/2]]],return_tensors='pt').to('cuda:0')
   with torch.inference_mode():pred=sm(**inputs)
   assert torch.isfinite(pred.pred_masks).all();report['sam_probe']='single image-center point; deployment only'
  report.update(status='passed',forwards=counts,inference_seconds=time.monotonic()-start,max_memory_allocated_bytes=torch.cuda.max_memory_allocated(),GPU_allocation_seconds=time.time()-report['started_unix'])
 except Exception as e:
  report.update(status='failed',error=repr(e));raise
 finally:
  report['finished_unix']=time.time();save();signal.alarm(0);lock.close()
if __name__=='__main__':main()
