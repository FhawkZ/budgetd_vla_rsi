"""One tiny tensor operation under a physical-GPU lock. Not an Agent experiment."""
import argparse,fcntl,json,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--gpu',type=int,choices=[0,1],required=True);p.add_argument('--output',required=True);a=p.parse_args()
root=Path(os.environ.get('RSI_RUNTIME_ROOT','/root/autodl-tmp/Dex_runtime/agent-rsi'));locks=root/'locks';locks.mkdir(parents=True,exist_ok=True)
with (locks/f'gpu{a.gpu}.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 inv=subprocess.check_output(['nvidia-smi','-i',str(a.gpu),'--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'],text=True).strip().split(',')
 procs=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader'],text=True)
 if inv[0].strip() in procs or int(inv[1])>=100:raise RuntimeError('GPU not idle; no allocation')
 os.environ['CUDA_VISIBLE_DEVICES']=str(a.gpu)
 import torch
 start=time.monotonic();x=torch.arange(1024,device='cuda',dtype=torch.float32);v=float((x*x).sum().cpu());assert v==357389824.0
 torch.cuda.synchronize()
 r={'gpu':a.gpu,'name':torch.cuda.get_device_name(0),'torch':torch.__version__,'cuda':torch.version.cuda,'compute_capability':torch.cuda.get_device_capability(0),'elapsed_seconds':time.monotonic()-start,'passed':True,'model_calls':0,'native_robot_actions':0}
 Path(a.output).write_text(json.dumps(r,indent=2));print(json.dumps(r))
