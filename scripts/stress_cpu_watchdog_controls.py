"""Matched CPU controls after watchdog stress crashed; no simulator/model/GPU."""
import os,sys,json,subprocess,time
from pathlib import Path
r=Path(os.environ['RSI_RUNTIME_ROOT'])/'outputs/native-rpc-prepare-20261031-2110/cpu-watchdog-controls';r.mkdir(exist_ok=False)
prior=r.parent/'cpu-watchdog-stress';meta=json.loads((prior/'report.json').read_text());assert all(x['returncode']==-11 for x in meta['rows'])
base='''import faulthandler,time,threading,numpy as np,sys,traceback
from concurrent.futures import ThreadPoolExecutor
f=open("stacks.log","w");faulthandler.enable(file=f,all_threads=True)
{observer}
end=time.monotonic()+6
matrix=np.eye(64)
def work(i):return float(np.sum(matrix @ matrix))+i
while time.monotonic()<end:
 with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(work,range(48)))
print("finished")
'''
observer='''def observe():
 while True:
  for tid,frame in sys._current_frames().items():
   f.write(str(tid)+"\\n"+"".join(traceback.format_stack(frame)))
  f.flush();time.sleep(.05)
threading.Thread(target=observe,daemon=True).start()'''
rows=[];start=time.time()
for mode in ['no_periodic_dump','python_frame_observer']:
 for i in range(3):
  d=r/(mode+str(i));d.mkdir();env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
  with (d/'stdout.txt').open('w') as out:
   try:x=subprocess.run([sys.executable,'-c',base.format(observer=observer if mode=='python_frame_observer' else '')],cwd=d,env=env,stdout=out,stderr=out,timeout=12);code=x.returncode
   except subprocess.TimeoutExpired:code=124
  rows.append(dict(mode=mode,trial=i,returncode=code))
report=dict(classification='Matched CPU thread/numpy controls only; not SAPIEN qualification or cause of original RPC stall',rows=rows,elapsed_seconds=time.time()-start,model_calls=0,episodes=0,status='passed_limited_cpu_scope' if all(x['returncode']==0 for x in rows) else 'failed');(r/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
