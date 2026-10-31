"""Own one finite local service and ledger; cleanup only child process groups."""
import contextlib,fcntl,json,os,signal,socket,subprocess,time,urllib.request
from pathlib import Path
from run_vla_only_pilot import digest,save,gpu_snapshot
ROOT=Path(__file__).resolve().parents[1]
@contextlib.contextmanager
def service(cfg):
 r=Path(os.environ['RSI_RUNTIME_ROOT']);out=r/'outputs'/(cfg['run_id']+'-qwen');assert not out.exists()
 for rel,sha in cfg['controller_code_sha256'].items():assert digest(ROOT/rel)==sha,rel
 receipt=r/cfg['qualification_report'];assert digest(receipt)==cfg['qualification_report_sha256'];assert json.loads(receipt.read_text())['status']=='passed'
 assets=r/cfg['qwen_asset_receipt'];assert digest(assets)==cfg['qwen_asset_receipt_sha256']
 for f in json.loads(assets.read_text())['files']:
  p=r/'models/Qwen3-VL-30B-A3B-Instruct'/f['path'];assert p.stat().st_size==f['bytes'] and p.stat().st_mtime_ns==f['mtime_ns']
 lock=(r/'locks/gpu0.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);before=gpu_snapshot(0);assert before['memory_mib']<100 and not before['compute_pids']
 for port in (8020,18029):
  s=socket.socket();s.bind(('127.0.0.1',port));s.close()
 out.mkdir();started=time.time();procs=[];logs=[];report=dict(status='running',started_unix=started,model_id=cfg['model_id'],max_calls=cfg['max_qwen_calls_total'],gpu_before=before);save(out/'report.json',report)
 env=dict(os.environ)
 for k in list(env):
  if any(x in k.upper() for x in ['API_KEY','ACCESS_TOKEN','AUTH_TOKEN','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']):env.pop(k,None)
 env.update(CUDA_VISIBLE_DEVICES='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='4',NO_PROXY='127.0.0.1,localhost')
 python=str(r/'software/envs/qwen/bin/python')
 def start(name,args,port):
  f=(out/(name+'.log')).open('w');logs.append(f);p=subprocess.Popen([python,*args],cwd=ROOT,env=env,stdout=f,stderr=f,start_new_session=True);procs.append(p);deadline=time.time()+180
  while time.time()<deadline:
   if p.poll() is not None:raise RuntimeError(name+' exited')
   try:
    with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=2) as response:return json.load(response)
   except Exception:time.sleep(.5)
  raise TimeoutError(name+' health')
 try:
  cap=str(cfg['max_qwen_calls_total'])
  h=start('server',[str(ROOT/'scripts/serve_qwen_structured30b.py'),'--port','8020','--model',str(r/'models/Qwen3-VL-30B-A3B-Instruct'),'--output',str(out/'server'),'--max-calls',cap],8020);assert h['model']==cfg['model_id']
  start('proxy',[str(ROOT/'scripts/budget_proxy30b.py'),'--port','18029','--upstream','http://127.0.0.1:8020','--output',str(out/'ledger'),'--max-calls',cap],18029)
  yield out
  report['status']='closed'
 except BaseException as e:report.update(status='closed_failed',error=repr(e));raise
 finally:
  for p in reversed(procs):
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
  for f in logs:f.close()
  gens=[json.loads(p.read_text()) for p in (out/'server').glob('*-generation.json')]
  report['usage']=dict(generations=len(gens),prompt_tokens=sum(g['usage']['prompt_tokens'] for g in gens),completion_tokens=sum(g['usage']['completion_tokens'] for g in gens),generation_seconds=sum(g['generation_seconds'] for g in gens))
  if (out/'ledger/ledger.json').exists():
   ledger=json.loads((out/'ledger/ledger.json').read_text());report['ledger']=ledger;report['token_ledger_match']=all(ledger[k]==report['usage'][k] for k in ['prompt_tokens','completion_tokens'])
  report.update(finished_unix=time.time(),gpu_allocation_seconds=time.time()-started,gpu_after=gpu_snapshot(0),unused_allowance_canceled=cfg['max_qwen_calls_total']-len(gens))
  save(out/'report.json',report);save(out/'CLOSE.json',dict(status=report['status'],unused_allowance='canceled'));lock.close()
