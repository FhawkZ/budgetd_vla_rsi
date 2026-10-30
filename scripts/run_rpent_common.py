"""Fresh bounded common-backend RPent CLI development reproduction, not RSI.
No archive execution. Unmodified tools, prior and task language; explicit local
model/transport/render/video adaptations, read-only telemetry and hard budgets.
"""
import argparse,fcntl,hashlib,json,os,shutil,signal,socket,subprocess,sys,time,traceback,urllib.request
from pathlib import Path
from run_vla_only_pilot import save,append,digest,proc_identity,cleanup_owned,gpu_snapshot,RENDER_BOOTSTRAP
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ['RSI_RUNTIME_ROOT'])

def check(cfg):
 assert cfg['status']=='frozen' and cfg['classification']=='common_backend_rpent_development'
 assert socket.gethostname()==cfg['hostname']
 assert cfg['qwen_calls_per_case']==32 and cfg['qwen_calls_total']==64
 assert cfg['horizon']==1200 and cfg['vla_calls_per_case']==24
 assert [(c['task'],c['seed']) for c in cfg['cases']]==[('stack_blocks_two',2026103011),('handover_block',2026103012)]
 for rel,sha in cfg['code_sha256'].items():assert digest(ROOT/rel)==sha,rel
 for rel,sha in cfg['vendor_sha256'].items():assert digest(RUNTIME/rel)==sha,rel
 for rel,sha in cfg['asset_manifests'].items():assert digest(ROOT/rel)==sha,rel
 assert digest(RUNTIME/cfg['input_manifest'])==cfg['input_manifest_sha256']
 manifest=json.loads((ROOT/'configs/rpent-memory-manifest.json').read_text())
 for row in manifest['files']:assert digest(RUNTIME/cfg['prior_root']/row['path'])==row['sha256'],row['path']
 assert len(manifest['files'])==107

def child(cfg,index,out):
 import numpy as np
 from PIL import Image
 import robots.robotwin.robot_spec as spec
 from robots.robotwin.env_client import RoboTwinEnvClient
 from robots.robotwin.primitives import RoboTwinPrimitives
 from rpent.utils.daemon import ProcessDaemon
 from rpent_local_compaction import install
 install(RUNTIME/'models/Qwen3-VL-8B-Instruct/tokenizer.json',out/'compaction.jsonl')
 case=cfg['cases'][index];report=dict(status='running',**case,vla_inferences=0,reset_calls=0,native_actions=0,native_success=None,accepted_updates=0)
 save(out/'episode.json',report);holder={}
 original_start=ProcessDaemon.start
 def start(daemon):
  if daemon.name=='robotwin_env_server':
   assets=RUNTIME/'assets/robotwin-c15cc97b';daemon.cwd=str(assets)
   bootstrap=out/'bootstrap';bootstrap.mkdir();(bootstrap/'sitecustomize.py').write_text(RENDER_BOOTSTRAP)
   daemon.subprocess_env.update(ROBOTWIN_ASSETS_ROOT=str(assets),ASSETS_PATH=str(assets),RSI_VLA_RENDER_CHILD='1')
   daemon.subprocess_env['PYTHONPATH']=str(bootstrap)+os.pathsep+daemon.subprocess_env.get('PYTHONPATH','')
  result=original_start(daemon)
  append(out/'owned-daemons.jsonl',dict(pid=daemon._proc.pid,starttime=proc_identity(daemon._proc.pid)[0],name=daemon.name,cmd=daemon.cmd))
  return result
 ProcessDaemon.start=start
 original_reset=RoboTwinEnvClient.reset
 def reset(env):
  report['reset_calls']+=1;save(out/'episode.json',report);assert report['reset_calls']<=1
  return original_reset(env)
 RoboTwinEnvClient.reset=reset
 original_runtime=spec._init_runtime
 def init(*args,**kwargs):
  result=original_runtime(*args,**kwargs);env=result[1]['env'];model=result[1]['model'];holder['env']=env
  status=env.last_info['episode_status'];assert status['actual_seed']==case['seed'] and status['step_lim']==1200 and status['take_action_cnt']==0
  instruction=env.get_task_language();assert instruction==case['instruction'],'native language mismatch'
  initial={'instruction':instruction,'robot_state':env.last_info['robot_state'],'images':{}}
  for camera in ('head','left_wrist','right_wrist'):
   path=out/f'initial-{camera}.png';Image.fromarray(np.asarray(env.render_camera(camera))).save(path);initial['images'][camera]=digest(path)
  raw=json.dumps(initial['robot_state'],sort_keys=True,separators=(',',':'),default=lambda x:x.tolist()).encode()
  initial['robot_state_sha256']=hashlib.sha256(raw).hexdigest()
  save(out/'initial.json',initial)
  report['initial_images_match']=initial['images']==case['initial_image_sha256']
  original_infer=model.infer
  def infer(observation):
   assert report['vla_inferences']<cfg['vla_calls_per_case'],'VLA budget exhausted before extra inference'
   report['vla_inferences']+=1;save(out/'episode.json',report)
   assert observation['task_language']==instruction
   prefix=out/f"vla-{report['vla_inferences']:03d}";record={'task_language':instruction,'robot_state':observation['robot_state'],'started_unix':time.time(),'images':{}}
   for camera,view in observation['views'].items():
    path=prefix.with_name(prefix.name+'-'+camera+'.png');Image.fromarray(np.asarray(view['rgb'])).save(path);record['images'][camera]=digest(path)
   save(prefix.with_suffix('.json'),record)
   try:
    actions=original_infer(observation);np.save(prefix.with_suffix('.npy'),actions);record.update(status='completed',action_sha256=digest(prefix.with_suffix('.npy')));return actions
   except BaseException as e:record.update(status='failed',error=repr(e));raise
   finally:record['elapsed_seconds']=time.time()-record['started_unix'];save(prefix.with_suffix('.json'),record)
  model.infer=infer;return result
 spec._init_runtime=init
 recording=RoboTwinPrimitives.start_recording
 def boundary(self):recording(self);self.stop_recording()
 RoboTwinPrimitives.start_recording=boundary
 from rpent.cli.main import main
 sys.argv=['rpent','--robot','robotwin','--planner','api','--model','openai-chat:qwen3-vl-8b-instruct','--base-url','http://127.0.0.1:18019/v1','--max-turns','32','--max-tokens','1024','--reasoning-effort','none','--planner-timeout-s','900','--memory-profile','local','--memory-dir',str(out/'prior'),'--output-dir',str(out/'cli'),'--task-name',case['task'],'--seed',str(case['seed']),'--task-config','demo_randomized','--max-episode-steps','1200','--robotwin-assets-path',str(RUNTIME/'assets/robotwin-c15cc97b'),'--vla-model-path',str(RUNTIME/'models/LingBot-VLA-RoboTwin-EEF-e727b46c'),'--cuda-device','1']
 try:
  code=main();report.update(status='completed' if code==0 else 'agent_failed',cli_returncode=code)
 except BaseException as e:report.update(status='failed',error=repr(e),traceback=traceback.format_exc());raise
 finally:
  if 'env' in holder:
   info=holder['env'].last_info;status=info.get('episode_status',{});report.update(native_episode_status=status,native_success=status.get('eval_success'),native_actions=status.get('take_action_cnt'),final_robot_state=info.get('robot_state'))
  save(out/'episode.json',report)
 return code

def run(cfg,path,sha):
 assert digest(path)==sha;check(cfg)
 out=RUNTIME/'outputs'/cfg['run_id'];assert not out.exists()
 locks=[]
 for gpu in (0,1):
  lock=(RUNTIME/f'locks/gpu{gpu}.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(lock)
 before={str(i):gpu_snapshot(i) for i in (0,1)}
 assert all(x['memory_mib']<100 and not x['compute_pids'] for x in before.values()),before
 for port in (8018,18019):
  s=socket.socket();s.bind(('127.0.0.1',port));s.close()
 out.mkdir();save(out/'protocol.json',cfg)
 (out/'code').mkdir()
 for rel in cfg['code_sha256']:shutil.copy2(ROOT/rel,out/'code'/Path(rel).name)
 report=dict(status='running',started_unix=time.time(),protocol_sha256=sha,gpu_before=before,cases=[],accepted_updates=0,forgetting=None,strict_rsi_rounds=0)
 save(out/'report.json',report)
 base=dict(os.environ)
 for key in list(base):
  if any(x in key.upper() for x in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')):base.pop(key,None)
 base.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',NO_PROXY='127.0.0.1,localhost',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',RPENT_REPO_ROOT=str(RUNTIME/'vendor'/cfg['rpent_directory']),RPENT_RLINF_ROOT=str(RUNTIME/'vendor/RLinf-2348ece3df113874671478be1360ae3115b346e3'),PYTHONPATH=str(RUNTIME/'vendor'/cfg['rpent_directory'])+':'+str(ROOT/'scripts'),OPENAI_API_KEY='local-only',RSI_EXPECTED_GPU_PCI=before['1']['pci_bus_id'])
 processes=[];logs=[]
 def spawn(name,cmd,where,env):
  log=(where/(name+'.log')).open('w');logs.append(log);p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True);processes.append(p);append(out/'owner-processes.jsonl',dict(name=name,pid=p.pid,starttime=proc_identity(p.pid)[0]));return p
 def stop(p):
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
 def health(url,p,seconds):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   if p.poll() is not None:raise RuntimeError('service exited: '+str(p.args))
   try:
    with urllib.request.urlopen(url,timeout=2) as response:return json.load(response)
   except Exception:time.sleep(.5)
  raise TimeoutError(url)
 def timeout(*_):raise TimeoutError('independent total wall budget exhausted')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(cfg['total_wall_seconds'])
 active=None
 try:
  qwen=spawn('qwen',[str(RUNTIME/'software/envs/qwen/bin/python'),str(ROOT/'scripts/serve_qwen.py'),'--model',str(RUNTIME/'models/Qwen3-VL-8B-Instruct'),'--output',str(out/'server'),'--port','8018','--max-calls','64'],out,dict(base,CUDA_VISIBLE_DEVICES='0'))
  health('http://127.0.0.1:8018/health',qwen,150)
  for index,case in enumerate(cfg['cases']):
   active=out/case['task'];active.mkdir();shutil.copytree(RUNTIME/cfg['prior_root']/'robotwin',active/'prior')
   aliases=[]
   for suffix in ('.json','_recipe.jsonl'):
    src=active/'prior'/'task-specific'/f"{case['task']}_s0{suffix}";dst=active/'prior'/'task-specific'/f"robotwin_{case['task']}_demo_randomized_s0{suffix}"
    shutil.copy2(src,dst);assert digest(src)==digest(dst);aliases.append(dict(source=src.name,target=dst.name,sha256=digest(dst)))
   save(active/'prior-aliases.json',aliases)
   proxy=spawn('proxy',[sys.executable,str(ROOT/'scripts/budget_proxy.py'),'--upstream','http://127.0.0.1:8018','--port','18019','--output',str(active/'ledger'),'--max-calls','32'],active,base)
   health('http://127.0.0.1:18019/health',proxy,15);t=time.time()
   worker=spawn('agent',[sys.executable,str(Path(__file__).resolve()),'--protocol',str(path),'--child',str(index),'--output',str(active)],active,dict(base,CUDA_VISIBLE_DEVICES='1'))
   try:code=worker.wait(timeout=cfg['case_wall_seconds'])
   except subprocess.TimeoutExpired:stop(worker);code=-9
   cleaned=cleanup_owned(active/'owned-daemons.jsonl');stop(proxy)
   assert not any(x['live'] for x in cleaned),'owned daemon still live'
   item=dict(task=case['task'],returncode=code,allocation_seconds=time.time()-t,cleanup=cleaned)
   if (active/'episode.json').exists():item['episode']=json.loads((active/'episode.json').read_text())
   item['ledger']=json.loads((active/'ledger/ledger.json').read_text());save(active/'CLOSE.json',dict(unused_allowance='canceled',time=time.time(),ledger=item['ledger']))
   report['cases'].append(item);save(out/'report.json',report)
   if not (active/'initial.json').exists():raise RuntimeError('infrastructure/init failure; second case canceled')
  report['status']='closed'
 except BaseException as e:report.update(status='failed',error=repr(e),traceback=traceback.format_exc())
 finally:
  signal.alarm(0)
  for p in reversed(processes):stop(p)
  if active:report['last_cleanup']=cleanup_owned(active/'owned-daemons.jsonl')
  for log in logs:log.close()
  gens=[json.loads(p.read_text()) for p in (out/'server').glob('*-generation.json')]
  report['usage']=dict(generations=len(gens),prompt_tokens=sum(g['usage']['prompt_tokens'] for g in gens),completion_tokens=sum(g['usage']['completion_tokens'] for g in gens),generation_seconds=sum(g['generation_seconds'] for g in gens))
  report.update(finished_unix=time.time(),GPU0_allocation_seconds=time.time()-report['started_unix'],unused_allowance='canceled',gpu_after={str(i):gpu_snapshot(i) for i in (0,1)})
  save(out/'report.json',report);save(out/'CLOSE.json',dict(time=time.time(),unused_allowance='canceled',generations=len(gens),max_calls=64))
  for lock in locks:lock.close()
 return 0 if report['status']=='closed' else 1

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);p.add_argument('--sha');p.add_argument('--run',action='store_true');p.add_argument('--child',type=int);p.add_argument('--output');a=p.parse_args();cfg=json.loads(Path(a.protocol).read_text())
 if a.child is not None:sys.exit(child(cfg,a.child,Path(a.output)))
 if a.run:sys.exit(run(cfg,Path(a.protocol),a.sha))
 check(cfg);print('CPU protocol checks passed; no model/simulator execution')
