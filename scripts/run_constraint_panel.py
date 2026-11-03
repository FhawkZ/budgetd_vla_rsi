"""New independently budgeted paired DEVELOPMENT pilot of one frozen Agent program.
Reuses collection/owner/single-seed helpers, NOT any historical run or allocation.
"""
import argparse,fcntl,json,os,signal,subprocess,sys,time,traceback
from pathlib import Path
import run_single_seed_panel as common
from run_vla_only_pilot import digest,save
ROOT=Path(__file__).resolve().parents[1]

def validate(c):
 assert c['status']=='frozen' and c['classification']=='constraint_program_paired_development'
 assert c['execution_host']=='lzgpu201' and c['execution_hostname']==os.uname().nodename
 assert c['max_episodes']==12 and c['max_vla_inferences_total']==288 and c['horizon']==1200
 assert c['max_vla_inferences_per_episode']==24 and c['qwen_calls']==0 and c['skill_updates']==0
 assert c['gpu']==1 and c['episode_wall_seconds']==1200 and c['total_wall_seconds']==7200
 cases=[]
 for task,seeds in [('stack_blocks_two',range(100000,100003)),('handover_block',range(100001,100004))]:
  for seed in seeds:
   pair=len(cases)//2;roles=['baseline','candidate'] if pair%2==0 else ['candidate','baseline']
   cases.extend({'task':task,'seed':seed,'role':role,'pair_index':pair,'instruction':None,'use_length':50} for role in roles)
 assert c['cases']==cases
 return c

def preflight(c,strict):
 import run_official_owner_panel as base
 runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
 for rel,h in c['code_sha256'].items():assert digest(ROOT/rel)==h,rel
 old=ROOT/c['reference_config'];assert digest(old)==c['reference_config_sha256']
 receipt=base.preflight(json.loads(old.read_text()),strict=strict)
 for role,row in c['programs'].items():
  p=runtime/row['path'];assert digest(p)==row['sha256']
  from physical_constraint_harness import validate_program
  rules=validate_program(json.loads(p.read_text()))['rules'];assert bool(rules)==(role=='candidate')
 q=runtime/c['proposal_report'];assert digest(q)==c['proposal_report_sha256'] and json.loads(q.read_text())['status']=='closed_candidate_ready'
 disk=os.statvfs(runtime);assert disk.f_bavail*disk.f_frsize>max(100*2**30,.2*disk.f_blocks*disk.f_frsize)+c['expected_output_max_bytes'] and disk.f_favail>100000
 receipt.update(free_bytes=disk.f_bavail*disk.f_frsize,free_inodes=disk.f_favail,projected_bytes=c['expected_output_max_bytes'])
 return receipt

def worker(c,index,out):
 # Keep source collector unchanged, disable its former typed native skill module.
 # New policy program is injected only inside our owned VLA server; same wrapper
 # and empty program for baseline. Every role remains fixed50.
 import typed_skill_patch
 from rpent.utils.daemon import ProcessDaemon
 class NoNativePatch:
  def __init__(self,*args,**kwargs):self.attempts=[]
  def before_vla(self,*args):return None
 original_patch=typed_skill_patch.TypedSkillPatch;typed_skill_patch.TypedSkillPatch=NoNativePatch
 original_start=ProcessDaemon.start
 def start(daemon):
  if daemon.name=='lingbot_vla_server':
   assert Path(daemon.cmd[1]).name=='vla_server.py'
   daemon.cmd[1]=str(ROOT/'scripts/run_constraint_vla_server.py')
   role=c['cases'][index]['role'];p=c['programs'][role]
   daemon.subprocess_env.update(RSI_CONSTRAINT_PROGRAM_FILE=str(Path(os.environ['RSI_RUNTIME_ROOT'])/p['path']),RSI_CONSTRAINT_PROGRAM_SHA256=p['sha256'],RSI_CONSTRAINT_VELOCITY_M=str(c['max_injected_xyz_velocity_m']),RSI_CONSTRAINT_TRACE=str(out/'program-trace.jsonl'))
   daemon.subprocess_env['PYTHONPATH']=str(ROOT/'scripts')+os.pathsep+daemon.subprocess_env.get('PYTHONPATH','')
  return original_start(daemon)
 ProcessDaemon.start=start
 try:common.worker(c,index,out)
 finally:
  ProcessDaemon.start=original_start;typed_skill_patch.TypedSkillPatch=original_patch
  p=out/'episode.json'
  if p.exists():
   e=json.loads(p.read_text());e.update(program_sha256=c['programs'][c['cases'][index]['role']]['sha256'],candidate_unaccepted=True,strict_rsi_rounds=0,limitation='Paired DEVELOPMENT test; same autonomous proposal reused across episodes. Native count not physics ticks; no acceptance or RSI claim. All typed native skill patches disabled.')
   save(p,e)

def run(c,path,h):
 assert digest(path)==h
 runtime=Path(os.environ['RSI_RUNTIME_ROOT']);lock=(runtime/'locks/gpu1.lock').open('a')
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);g=common.gpu_snapshot(1)
 assert g['memory_mib']<100 and not g['compute_pids']
 started=time.time();check=preflight(c,True)
 out=runtime/'outputs'/c['run_id'];out.mkdir(exist_ok=False)
 save(out/'protocol.json',c);(out/'code').mkdir()
 import shutil
 for rel in c['code_sha256']:shutil.copy2(ROOT/rel,out/'code'/Path(rel).name)
 report={'status':'running','started_unix':started,'protocol_sha256':h,'pid':os.getpid(),'gpu_before':g,'preflight':check,'episodes':[],'qwen_calls':0,'accepted_updates':0,'strict_rsi':0,'planned_episodes':12}
 save(out/'report.json',report);active=None;current=None
 def stop(*_):raise KeyboardInterrupt('external termination')
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  for i,case in enumerate(c['cases']):
   remaining=c['total_wall_seconds']-(time.time()-started);assert remaining>0
   current=out/f"{i:02d}-{case['task']}-s{case['seed']}";current.mkdir()
   env=dict(os.environ)
   for k in list(env):
    if any(x in k.upper() for x in ['API_KEY','ACCESS_TOKEN','AUTH_TOKEN','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']):env.pop(k,None)
   source=runtime/'vendor'/('RPent-'+common.RPENT_COMMIT)
   env.update(PYTHONPATH=str(ROOT/'scripts')+os.pathsep+str(source),RPENT_REPO_ROOT=str(source),RPENT_RLINF_ROOT=str(runtime/c['rlinf_relative_path']),CUDA_VISIBLE_DEVICES='1',CUDA_DEVICE_ORDER='PCI_BUS_ID',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',RSI_EXPECTED_GPU_PCI=g['pci_bus_id'],NO_PROXY='127.0.0.1,localhost',RSI_VLA_WORKER_PROTOCOL_SHA256=h)
   with (current/'worker.log').open('w') as log:
    active=subprocess.Popen([sys.executable,__file__,'--config',str(path),'--sha',h,'--worker',str(i),'--out',str(current)],env=env,stdout=log,stderr=log,start_new_session=True)
    try:code=active.wait(timeout=min(c['episode_wall_seconds'],remaining))
    except subprocess.TimeoutExpired:
     os.killpg(active.pid,signal.SIGTERM)
     try:active.wait(timeout=5)
     except subprocess.TimeoutExpired:os.killpg(active.pid,signal.SIGKILL);active.wait(timeout=5)
     code=124
   clean=common.cleanup_owned(current/'owned-daemons.jsonl');epfile=current/'episode.json'
   ep=json.loads(epfile.read_text()) if epfile.exists() else {'status':'missing'}
   invalid=False
   if code:
    from scene_validity import native_scene_invalid
    af=current/'seed-attempts.jsonl';attempts=[json.loads(x) for x in af.read_text().splitlines()] if af.exists() else []
    invalid=code!=124 and native_scene_invalid(ep,attempts) and not any(x['live'] for x in clean)
    ep.update(status='scene_invalid' if invalid else 'infrastructure_error',worker_exit_code=code);save(epfile,ep)
   report['episodes'].append({'case':case,'result':ep,'cleanup':clean});save(out/'report.json',report);active=None
   assert not any(x['live'] for x in clean),'owned daemon still live'
   if code and not invalid:raise RuntimeError('infrastructure failure stops pilot; no retries')
  report['status']='completed_with_censored' if any(x['result']['status']=='scene_invalid' for x in report['episodes']) else 'completed'
 except BaseException as e:report.update(status='closed_failed',error=repr(e),traceback=traceback.format_exc())
 finally:
  if active is not None and active.poll() is None:
   os.killpg(active.pid,signal.SIGTERM)
   try:active.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(active.pid,signal.SIGKILL);active.wait(timeout=5)
  if current is not None:
   report['final_cleanup']=common.cleanup_owned(current/'owned-daemons.jsonl')
   if not any(x['case']==c['cases'][int(current.name.split('-',1)[0])] for x in report['episodes']):
    epfile=current/'episode.json';ep=json.loads(epfile.read_text()) if epfile.exists() else {'status':'missing'}
    if ep.get('status')=='running':ep['status']='interrupted';save(epfile,ep)
    report['episodes'].append({'case':c['cases'][int(current.name.split('-',1)[0])],'result':ep})
  report.update(finished_unix=time.time(),gpu1_lock_interval_seconds=time.time()-started,total_vla_inferences=sum(x['result'].get('vla_inferences',0) for x in report['episodes']),native_actions=sum(x['result'].get('native_actions',0) for x in report['episodes']),unstarted_episodes=12-len(report['episodes']),gpu_after=common.gpu_snapshot(1))
  save(out/'report.json',report);save(out/'CLOSE.json',{'status':'CLOSED','outcome':report['status'],'max_vla':288,'used_vla':report['total_vla_inferences'],'unused_canceled':288-report['total_vla_inferences']});lock.close()
 print(json.dumps(report))
 return 0 if report['status'].startswith('completed') else 1

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--sha',required=True);p.add_argument('--run',action='store_true');p.add_argument('--worker',type=int);p.add_argument('--out',type=Path);a=p.parse_args()
 assert digest(a.config)==a.sha;c=validate(json.loads(a.config.read_text()))
 for rel,h in c['code_sha256'].items():assert digest(ROOT/rel)==h,rel
 if a.worker is not None:
  assert os.environ['RSI_VLA_WORKER_PROTOCOL_SHA256']==a.sha;worker(c,a.worker,a.out)
 elif a.run:sys.exit(run(c,a.config.resolve(),a.sha))
 else:print(json.dumps(preflight(c,False),indent=2))
