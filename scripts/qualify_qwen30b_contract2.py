"""Independent three-generation qualification; never executes robot tools.
Two frozen development inputs + one free-text canary, then hard budget refusal.
"""
import argparse,fcntl,json,os,signal,socket,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
from run_vla_only_pilot import digest,save,gpu_snapshot
ROOT=Path(__file__).resolve().parents[1];RUNTIME=Path(os.environ['RSI_RUNTIME_ROOT'])

def main():
 p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);p.add_argument('--sha',required=True);a=p.parse_args();path=Path(a.protocol);cfg=json.loads(path.read_text());assert digest(path)==a.sha
 assert cfg['status']=='frozen' and cfg['max_calls']==2 and cfg['execution_host']==socket.gethostname()
 for rel,sha in cfg['code_sha256'].items():assert digest(ROOT/rel)==sha
 receipt=RUNTIME/cfg['cpu_receipt'];assert digest(receipt)==cfg['cpu_receipt_sha256'];assert json.loads(receipt.read_text())['status']=='passed'
 assert cfg['code_sha256']['scripts/structured_qwen.py']==json.loads(receipt.read_text())['adapter_sha256']
 asset_receipt=RUNTIME/cfg['asset_receipt'];assert digest(asset_receipt)==cfg['asset_receipt_sha256'];assert json.loads(asset_receipt.read_text())['status']=='passed'
 for f in json.loads(asset_receipt.read_text())['files']:
  asset=RUNTIME/'models/Qwen3-VL-30B-A3B-Instruct'/f['path'];assert asset.stat().st_size==f['bytes'] and asset.stat().st_mtime_ns==f['mtime_ns']
 out=RUNTIME/'outputs'/cfg['run_id'];assert not out.exists()
 lock=(RUNTIME/'locks/gpu0.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);gpu=gpu_snapshot(0);assert gpu['memory_mib']<100 and not gpu['compute_pids']
 for port in (8020,18029):
  s=socket.socket();s.bind(('127.0.0.1',port));s.close()
 out.mkdir();save(out/'protocol.json',cfg)
 env=dict(os.environ)
 for key in list(env):
  if any(x in key.upper() for x in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')):env.pop(key,None)
 env.update(CUDA_VISIBLE_DEVICES='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='4',NO_PROXY='127.0.0.1,localhost')
 procs=[];logs=[];report=dict(status='running',started_unix=time.time(),protocol_sha256=a.sha,gpu_before=gpu,model_calls_cap=2,robot_tools_executed=0,episodes=0,results=[])
 save(out/'report.json',report)
 def spawn(name,cmd):
  log=(out/(name+'.log')).open('w');logs.append(log);proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True);procs.append(proc);return proc
 def health(url,proc,seconds):
  end=time.time()+seconds
  while time.time()<end:
   if proc.poll() is not None:raise RuntimeError('service exited')
   try:
    with urllib.request.urlopen(url,timeout=2) as f:return json.load(f)
   except Exception:time.sleep(.5)
  raise TimeoutError('health')
 def request(body):
  req=urllib.request.Request('http://127.0.0.1:18029/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=180) as f:return json.load(f)
 def alarm(*args):raise TimeoutError('qualification wall limit')
 signal.signal(signal.SIGALRM,alarm);signal.alarm(600)
 try:
  raw=spawn('server',[sys.executable,str(ROOT/'scripts/serve_qwen_structured30b.py'),'--port','8020','--model',str(RUNTIME/'models/Qwen3-VL-30B-A3B-Instruct'),'--output',str(out/'server'),'--max-calls','2']);assert health('http://127.0.0.1:8020/health',raw,150)['model']==cfg['model_id']
  proxy=spawn('proxy',[sys.executable,str(ROOT/'scripts/budget_proxy30b.py'),'--port','18029','--upstream','http://127.0.0.1:8020','--output',str(out/'ledger'),'--max-calls','2']);health('http://127.0.0.1:18029/health',proxy,15)
  from structured_qwen import validate_output
  for fixture in cfg['inputs']:
   source=RUNTIME/fixture['path'];assert digest(source)==fixture['sha256'];body=json.loads(source.read_text())
   response=request(body);message=response['choices'][0]['message'];calls=message.get('tool_calls',[])
   valid=False
   if fixture['kind']=='historical_schema_boundary':
    assert len(calls)==1 and calls[0]['function']['name']=='sample_world_xyz','qualification did not exercise target boundary'
    value=calls[0]['function'];validate_output('<tool_call>'+json.dumps({'name':value['name'],'arguments':json.loads(value['arguments'])})+'</tool_call>',body['tools']);args=json.loads(value['arguments']);assert args['view']=='head' and args['pixels']==[[16,24],[32,48]],'explicit serialization fixture mismatch'
    valid=True
   else:
    assert not calls and message.get('content','').strip()=='qualification-ok'
    assert response['usage']['prompt_tokens']==31744,'32K combined input/output reservation not exercised'
    valid=True
   report['results'].append(dict(kind=fixture['kind'],source_sha256=fixture['sha256'],valid=valid,response=response));save(out/'report.json',report)
  try:request(body);raise AssertionError('budget allowed third request')
  except urllib.error.HTTPError as e:
   payload=e.read().decode();assert e.code==400 and 'budget exhausted' in payload;report['hard_budget_rejection_verified']=True
  report['status']='passed'
 except BaseException as exc:report.update(status='failed',error=repr(exc))
 finally:
  signal.alarm(0)
  for proc in reversed(procs):
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
  for log in logs:log.close()
  gens=[json.loads(p.read_text()) for p in (out/'server').glob('*-generation.json')]
  report['memory']={'peak_allocated_bytes':max((g.get('peak_allocated_bytes',0) for g in gens),default=0),'peak_reserved_bytes':max((g.get('peak_reserved_bytes',0) for g in gens),default=0)}
  report['usage']=dict(generations=len(gens),prompt_tokens=sum(g['usage']['prompt_tokens'] for g in gens),completion_tokens=sum(g['usage']['completion_tokens'] for g in gens),generation_seconds=sum(g['generation_seconds'] for g in gens))
  if (out/'ledger/ledger.json').exists():
   report['ledger']=json.loads((out/'ledger/ledger.json').read_text());report['token_ledger_match']=all(report['ledger'][key]==report['usage'][key] for key in ['prompt_tokens','completion_tokens'])
   if not report['token_ledger_match']:report['status']='failed'
  report.update(finished_unix=time.time(),gpu_allocation_seconds=time.time()-report['started_unix'],gpu_after=gpu_snapshot(0),unused_allowance='canceled')
  save(out/'report.json',report);save(out/'CLOSE.json',dict(status=report['status'],unused_allowance='canceled',time=time.time()));lock.close()
 print(json.dumps(report,indent=2));return 0 if report['status']=='passed' else 1
if __name__=='__main__':sys.exit(main())
