"""Bounded CPU-only watchdog stress; does NOT qualify SAPIEN signal safety."""
import os,sys,json,subprocess,time
from pathlib import Path
r=Path(os.environ['RSI_RUNTIME_ROOT'])/'outputs/native-rpc-prepare-20261031-2110/cpu-watchdog-stress';r.mkdir(exist_ok=False)
child='''import faulthandler,time,threading,numpy as np
from concurrent.futures import ThreadPoolExecutor
f=open("stacks.log","w");faulthandler.enable(file=f,all_threads=True);faulthandler.dump_traceback_later(.05,repeat=True,file=f)
end=time.monotonic()+6
matrix=np.eye(64)
def work(i):return float(np.sum(matrix @ matrix))+i
while time.monotonic()<end:
 with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(work,range(48)))
faulthandler.cancel_dump_traceback_later()
print("finished")
'''
rows=[];start=time.time()
for i in range(3):
 d=r/str(i);d.mkdir();env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 with (d/'stdout.txt').open('w') as out:
  try:x=subprocess.run([sys.executable,'-c',child],cwd=d,env=env,stdout=out,stderr=out,timeout=12);code=x.returncode
  except subprocess.TimeoutExpired:code=124
 text=(d/'stacks.log').read_text(errors='replace') if (d/'stacks.log').exists() else ''
 rows.append(dict(trial=i,returncode=code,watchdog_dumps=text.count('Timeout ('),unexpected_frame_marker='???' in text))
report=dict(classification='CPU-only threads/numpy/watchdog stress, no simulator or GPU; cannot prove SAPIEN-safe',rows=rows,elapsed_seconds=time.time()-start,model_calls=0,episodes=0,status='passed_limited_cpu_scope' if all(x['returncode']==0 for x in rows) else 'failed')
(r/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
