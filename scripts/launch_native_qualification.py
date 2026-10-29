"""Own local-only bounded namespace qualification or full native development pilot.
Separate new protocol/ledger/processes for each mode. No automatic retries.
"""
import argparse,fcntl,hashlib,json,os,signal,socket,subprocess,sys,time
from pathlib import Path
import run_roborsi_native_pilot as pilot
ROOT=pilot.ROOT;RUNTIME=pilot.RUNTIME

def child_namespace(state):
 pilot.clean_environment(state)
 from roborsi.agents.sessions import persistent_agent as pa
 pa._REPO=Path(state['workspace'])
 path=Path(state['workspace'])/'namespace-fixture.txt'
 result={'classification':'real Qwen namespace read-tool qualification, no task','model_call_cap':2}
 try:
  answer=pa.run('planner','namespace_canary','Read the entire file '+str(path)+' using the read_text tool. Then report its marker exactly. Do not inspect any other file.',system_prompt='Local transport qualification. Use exactly one read_text call, then a final answer with the marker. Do not guess file content or use any other tool.',model=pilot.ROLE_MODEL)
  rows=[json.loads(x) for x in (Path(state['run_root'])/'mcp-audit.jsonl').read_text().splitlines()]
  assert len(rows)==1 and rows[0]['tool']=='read_text' and rows[0]['path']==str(path)
  assert 'NAMESPACE-4829' in answer
  ledger=pilot.get(state['budget_url']+'/health')['ledger'];assert ledger['backend_attempts']==2
  result.update(status='passed',answer=answer,ledger=ledger)
 except Exception as e:result.update(status='failed',error=repr(e))
 pilot.write(Path(state['run_root'])/'namespace-report.json',result)
 return 0 if result['status']=='passed' else 1

def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['namespace','native','reviewer','reviewer-scoped'],required=True);p.add_argument('--output');p.add_argument('--state');p.add_argument('--namespace-receipt');p.add_argument('--closed-evidence');p.add_argument('--reviewer-receipt');p.add_argument('--public-language-manifest');p.add_argument('--task',choices=['stack_blocks_two','handover_block'],default='stack_blocks_two');p.add_argument('--child',action='store_true');a=p.parse_args()
 if a.child:
  state=json.loads(Path(a.state).read_text())
  if a.mode in ('reviewer','reviewer-scoped'):
   from reviewer_contract import child
   return child(state)
  return child_namespace(state)
 if a.mode=='native':
  if not a.public_language_manifest:raise ValueError('New native protocols require explicit public language manifest; old no-language runs are closed')
  from task_language_contract import load
  language_rows=load(a.public_language_manifest,RUNTIME/'backends/robotwin-ae507381-c15cc97b')
  assert a.task in language_rows
  vision=json.loads((RUNTIME/'outputs/native-vision-qualification-20261029-2355/report.json').read_text());assert vision['status']=='passed'
  assert vision['vision_manifest_sha256']==pilot.sha(ROOT/'configs/native-vision-models.json')
  receipt=json.loads(Path(a.reviewer_receipt or a.namespace_receipt).read_text());assert receipt['status']=='passed'
  if a.reviewer_receipt:
   assert receipt['mode']=='reviewer-scoped' and receipt['detail']['status']=='passed'
   assert (Path(a.reviewer_receipt).parent/'CLOSE.json').exists()
  assert receipt['script_hashes']['scripts/responses_adapter.py']==pilot.sha(ROOT/'scripts/responses_adapter.py')
 state=pilot.prepare(a.output,'http://127.0.0.1:18019','http://127.0.0.1:18020','http://127.0.0.1:18021','http://127.0.0.1:8181')
 r=Path(a.output);calls={'namespace':2,'reviewer':4,'reviewer-scoped':4,'native':64}[a.mode]
 if a.mode in ('reviewer','reviewer-scoped'):
  from reviewer_contract import prepare
  prepare(state,a.closed_evidence)
  state['tool_profile']='role-evidence' if a.mode=='reviewer-scoped' else 'original'
  pilot.write(r/'state.json',state)
 if a.mode=='native':
  import shutil
  shutil.copy2(a.public_language_manifest,r/'public-language.json')
  state['public_language_manifest']=str(r/'public-language.json')
  state['public_language_manifest_sha256']=pilot.sha(r/'public-language.json')
  state['script_hashes']['scripts/task_language_contract.py']=pilot.sha(ROOT/'scripts/task_language_contract.py')
  pilot.write(r/'state.json',state)
 if a.mode=='native' and a.reviewer_receipt:
  state['tool_profile']='role-evidence';state['reviewer_contract']='explicit-evidence-v1'
  state['script_hashes']['scripts/reviewer_contract.py']=pilot.sha(ROOT/'scripts/reviewer_contract.py')
  pilot.write(r/'state.json',state)
 if a.mode=='namespace':(Path(state['workspace'])/'namespace-fixture.txt').write_text('NAMESPACE-4829\n')
 protocol=json.loads((ROOT/'configs/roborsi-native-pilot-draft.json').read_text())
 protocol.update(status='FROZEN',max_model_calls=calls,state_sha256=pilot.sha(r/'state.json'),qualification_mode=a.mode,wall_seconds=360 if a.mode!='native' else 1800,namespace_receipt=a.namespace_receipt,owner_sha256=pilot.sha(__file__),tool_profile=state.get('tool_profile','original'))
 if a.mode!='native':protocol.update(classification=a.mode+'_deployment_qualification',tasks=[],tool_budget=0,max_physics_steps=0)
 if a.mode=='native':
  protocol['tasks']=[{'task':a.task,'seed':42}]
  protocol['reviewer_receipt']=a.reviewer_receipt
  protocol['public_language_manifest_sha256']=state['public_language_manifest_sha256']
  protocol['explicit_adaptations'] += ['Public task description pinned by source SHA, explicitly bound to HTTP environment instruction; language binding not yet online qualified. All common-backend comparisons must receive identical text.']
  if a.reviewer_receipt:protocol['explicit_adaptations'] += ['Persistent role tools restricted to4explicit evidence readers; actual Reviewer file paths supplied; max3evidence reads requested before verdict. Not a learned update; old closed run remains failed.']
 pilot.write(r/'protocol.json',protocol)
 # Freeze ALL service/runner code before allocating GPU.
 hashes={str(x.relative_to(ROOT)):pilot.sha(x) for x in [ROOT/'scripts/serve_qwen.py',ROOT/'scripts/budget_proxy.py',ROOT/'scripts/responses_adapter.py',Path(__file__)]}
 hashes.update(state['script_hashes']);hashes['scripts/qualify_native_vision.py']=pilot.sha(ROOT/'scripts/qualify_native_vision.py');pilot.write(r/'code-manifest.json',hashes)
 (r/'code').mkdir()
 import shutil
 for filename in hashes:shutil.copy2(ROOT/filename,r/'code'/Path(filename).name)
 lock=(RUNTIME/'locks/gpu0.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert int(subprocess.check_output(['nvidia-smi','-i','0','--query-gpu=memory.used','--format=csv,noheader,nounits']))<100
 assert not subprocess.check_output(['nvidia-smi','-i','0','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
 for port in [8018,18019,18020,18021,8181]:
  probe=socket.socket();probe.bind(('127.0.0.1',port));probe.close()
 base=dict(os.environ);base.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',NO_PROXY='127.0.0.1,localhost',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4')
 for key in list(base):
  if any(x in key.upper() for x in ['API_KEY','ACCESS_TOKEN','AUTH_TOKEN','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']):base.pop(key,None)
 procs=[];logs=[];started=time.time();report={'status':'running','pid':os.getpid(),'mode':a.mode,'started_unix':started,'script_hashes':hashes,'protocol_sha256':pilot.sha(r/'protocol.json'),'model_call_cap':calls,'accepted_updates':0,'strict_rsi_rounds':0}
 pilot.write(r/'owner-report.json',report)
 def start(name,cmd,env=base):
  log=(r/(name+'.log')).open('w');logs.append(log);proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True);procs.append(proc);report[name+'_pid']=proc.pid;pilot.write(r/'owner-report.json',report);return proc
 def health(url,proc,seconds):
  deadline=time.monotonic()+seconds
  while time.monotonic()<deadline:
   if proc.poll() is not None:raise RuntimeError('service exited: '+str(proc.args))
   try:pilot.get(url);return
   except Exception:time.sleep(.5)
  raise TimeoutError('service not healthy: '+url)
 def timeout(sig,frame):raise TimeoutError('owner wall limit')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(protocol['wall_seconds'])
 try:
  qenv=dict(base,CUDA_VISIBLE_DEVICES='0');qpython=str(RUNTIME/'software/envs/qwen/bin/python')
  raw=start('qwen',[qpython,str(ROOT/'scripts/serve_qwen.py'),'--model',str(RUNTIME/'models/Qwen3-VL-8B-Instruct'),'--output',str(r/'server'),'--port','8018','--max-calls',str(calls)],qenv);health('http://127.0.0.1:8018/health',raw,150)
  budget=start('budget',[sys.executable,str(ROOT/'scripts/budget_proxy.py'),'--upstream','http://127.0.0.1:8018','--port','18019','--output',str(r/'ledger'),'--max-calls',str(calls)]);health(state['budget_url']+'/health',budget,15)
  adapter=start('adapter',[sys.executable,str(ROOT/'scripts/responses_adapter.py'),'--upstream',state['budget_url'],'--port','18020','--output',str(r/'adapter'),'--tool-profile',state.get('tool_profile','original')]);health(state['adapter_url']+'/health',adapter,15)
  if a.mode!='native':
   child=start(a.mode,[sys.executable,str(Path(__file__).resolve()),'--mode',a.mode,'--state',str(r/'state.json'),'--child'])
  else:
   cap=start('cap',[sys.executable,str(ROOT/'scripts/run_roborsi_native_pilot.py'),'cap-bridge','--state',str(r/'state.json'),'--output',str(r/'cap')]);health(state['cap_url']+'/health',cap,15)
   rpc=start('rpc',[sys.executable,str(ROOT/'scripts/run_roborsi_native_pilot.py'),'rpc','--state',str(r/'state.json'),'--protocol',str(r/'protocol.json')]);health(state['rpc_url']+'/healthz',rpc,120)
   child=start('native',[sys.executable,str(ROOT/'scripts/run_roborsi_native_pilot.py'),'run','--state',str(r/'state.json'),'--protocol',str(r/'protocol.json')])
  code=child.wait(timeout=max(1,protocol['wall_seconds']-(time.time()-started)))
  report['child_returncode']=code
  detail=json.loads((r/(('reviewer' if a.mode.startswith('reviewer') else a.mode)+'-report.json' if a.mode!='native' else 'pilot-report.json')).read_text())
  report['detail']=detail;report['status']='passed' if detail['status'] in ['passed','finished_bounded_attempts'] else 'failed'
 except Exception as e:report.update(status='failed',error=repr(e))
 finally:
  signal.alarm(0)
  for proc in reversed(procs):
   try:os.killpg(proc.pid,signal.SIGTERM)
   except ProcessLookupError:pass
  for proc in reversed(procs):
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:
    os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
  for log in logs:log.close()
  report.update(finished_unix=time.time(),GPU0_allocation_seconds=time.time()-started,owned_children_exited=all(x.poll() is not None for x in procs),remaining_budget='canceled')
  if (r/'ledger/ledger.json').exists():report['ledger']=json.loads((r/'ledger/ledger.json').read_text())
  generations=[json.loads(x.read_text()) for x in (r/'server').glob('*-generation.json')]
  report['server_generation_usage']={'generations':len(generations),'prompt_tokens':sum(x['usage']['prompt_tokens'] for x in generations),'completion_tokens':sum(x['usage']['completion_tokens'] for x in generations),'generation_seconds':sum(x['generation_seconds'] for x in generations)}
  pilot.write(r/'owner-report.json',report);pilot.write(r/'CLOSE.json',{'time':time.time(),'unused_allowance':'canceled','max_calls':calls});lock.close()
 return 0 if report['status']=='passed' else 1
if __name__=='__main__':sys.exit(main())
