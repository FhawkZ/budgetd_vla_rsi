"""Frozen two-reset native/owner deployment qualification. No policy actions."""
import argparse,json,os,sys,time,subprocess,signal,fcntl,socket,traceback
from pathlib import Path
from run_bounded_vla_pilot import ROOT,RENDER_BOOTSTRAP,save,digest,gpu_snapshot,proc_identity,append,cleanup_owned

def worker(cfg,mode,out):
 import numpy as np
 from PIL import Image
 from rpent.utils.daemon import ProcessDaemon
 from rpent.dashboard.events import NullDashboardEventSink
 from robots.robotwin.robot_spec import _init_runtime
 from robots.robotwin.primitives import RoboTwinPrimitives
 from robots.robotwin.env_client import RoboTwinEnvClient
 r=Path(os.environ['RSI_RUNTIME_ROOT']);source=r/cfg['source'];daemons=[];start=ProcessDaemon.start;reset=RoboTwinEnvClient.reset
 report=dict(mode=mode,status='running',resets=0,model_calls=0,vla_inferences=0,policy_actions=0)
 def spawn(d):
  assert d.name=='robotwin_env_server','no model service allowed'
  bootstrap=out/'bootstrap';bootstrap.mkdir();(bootstrap/'sitecustomize.py').write_text(RENDER_BOOTSTRAP)
  d.cwd=str(r/cfg['assets']);d.subprocess_env.update(PYTHONPATH=str(bootstrap)+os.pathsep+str(ROOT/'scripts')+os.pathsep+str(source),RSI_VLA_RENDER_CHILD='1',RSI_EXPECTED_GPU_PCI=os.environ['RSI_EXPECTED_GPU_PCI'],ROBOTWIN_ASSETS_ROOT=d.cwd,ASSETS_PATH=d.cwd)
  if mode=='owner':
   assert Path(d.cmd[1]).name=='env_server.py';d.cmd[1]=str(ROOT/'scripts/run_owner_env_server.py');d.subprocess_env.update(RSI_OWNER_QUALIFIED_LAUNCH='candidate_lifecycle_v1',RSI_OWNER_AUDIT_FILE=str(out/'owner-audit.json'))
  start(d);daemons.append(d);ident=proc_identity(d._proc.pid);append(out/'owned.jsonl',dict(pid=d._proc.pid,starttime=ident[0],name=d.name))
 ProcessDaemon.start=spawn
 def once(e):
  report['resets']+=1;assert report['resets']==1;return reset(e)
 RoboTwinEnvClient.reset=once
 try:
  args=argparse.Namespace(task_name=cfg['task'],seed=cfg['seed'],task_config='demo_randomized',max_episode_steps=1200,env_endpoint=None,vla_endpoint=None,robotwin_assets_path=str(r/cfg['assets']),vla_model_path=None,lingbot_robot_config=None,cuda_device='1',env_cuda_device=None,vla_cuda_device=None)
  _,kw=_init_runtime(args,out,NullDashboardEventSink(),{'env'});env=kw['env'];primitives=RoboTwinPrimitives(**kw,model=None,check_cancelled=lambda:None)
  obs=primitives._build_lingbot_observation();assert obs['task_language']==cfg['instruction'];assert env.last_info['episode_status']['actual_seed']==cfg['seed'];assert env.last_info['episode_status']['take_action_cnt']==0
  images={}
  for name,v in obs['views'].items():
   f=out/(name+'.png');Image.fromarray(np.asarray(v['rgb'])).save(f);images[name]=digest(f)
  report.update(status='completed',robot_state=obs['robot_state'],image_sha256=images,instruction=obs['task_language'],native_status=env.last_info['episode_status'])
 except BaseException as exc:report.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
 finally:
  report['daemon_before_cleanup']=[dict(pid=d._proc.pid,returncode=d.poll()) for d in daemons]
  for d in reversed(daemons):d.stop(timeout=15)
  report['daemon_after_cleanup']=[dict(pid=d._proc.pid,returncode=d.poll()) for d in daemons]
  report['cleanup']=cleanup_owned(out/'owned.jsonl');save(out/'result.json',report)
 if report['status']!='completed' or any(d['returncode']!=0 for d in report['daemon_after_cleanup']):raise RuntimeError('Lifecycle qualification failed')

p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);p.add_argument('--sha',required=True);p.add_argument('--worker',choices=['native','owner']);p.add_argument('--out');a=p.parse_args();cp=Path(a.protocol).resolve();assert digest(cp)==a.sha;cfg=json.loads(cp.read_text());r=Path(os.environ['RSI_RUNTIME_ROOT'])
assert socket.gethostname()==cfg['hostname'] and cfg['max_resets']==2 and cfg['model_calls']==0 and cfg['policy_actions']==0
for rel,h in cfg['code_sha256'].items():assert digest(ROOT/rel)==h
for rel,h in cfg['source_sha256'].items():assert digest(r/rel)==h
if a.worker:
 worker(cfg,a.worker,Path(a.out));sys.exit(0)
out=r/'outputs'/cfg['run_id'];assert not out.exists();lock=(r/'locks/gpu1.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);gpu=gpu_snapshot(1);assert gpu['memory_mib']<100 and not gpu['compute_pids'];out.mkdir();save(out/'protocol.json',cfg);start=time.time();report=dict(status='running',classification='deployment lifecycle qualification only; no autonomous task or replay',gpu_before=gpu,protocol_sha256=a.sha,rows=[],model_calls=0,vla_inferences=0,policy_actions=0);active=None;folder=None
try:
 for mode in ['native','owner']:
  folder=out/mode;folder.mkdir();env=dict(os.environ,PYTHONPATH=str(r/cfg['source']),RPENT_REPO_ROOT=str(r/cfg['source']),RPENT_RLINF_ROOT=str(r/cfg['rlinf']),CUDA_VISIBLE_DEVICES='1',CUDA_DEVICE_ORDER='PCI_BUS_ID',RSI_EXPECTED_GPU_PCI=gpu['pci_bus_id'],NO_PROXY='127.0.0.1,localhost',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
  with (folder/'worker.log').open('w') as log:
   active=subprocess.Popen([sys.executable,__file__,'--protocol',str(cp),'--sha',a.sha,'--worker',mode,'--out',str(folder)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:rc=active.wait(timeout=cfg['per_worker_wall_seconds'])
   except subprocess.TimeoutExpired:
    os.killpg(active.pid,signal.SIGTERM)
    try:active.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(active.pid,signal.SIGKILL);active.wait(timeout=5)
    rc=124
  cleanup=cleanup_owned(folder/'owned.jsonl');row=json.loads((folder/'result.json').read_text()) if (folder/'result.json').exists() else {'status':'no_result'};row.update(worker_returncode=rc,supervisor_cleanup=cleanup);report['rows'].append(row);save(out/'report.json',report);active=None
  if rc!=0:raise RuntimeError(mode+' lifecycle failed; no retry')
 left,right=report['rows'];assert left['robot_state']==right['robot_state'];assert left['image_sha256']==right['image_sha256'];assert left['instruction']==right['instruction'];audit=json.loads((out/'owner/owner-audit.json').read_text());assert audit['phase_counts'].get('get_obs',0)>0 and audit['phase_counts'].get('close_env',0)>0 and audit['phase_counts'].get('take_action',0)==0
 report.update(status='passed_reset_render_teardown_only',paired_initial_state_equal=True,paired_initial_images_equal=True,owner_audit=audit)
except BaseException as exc:report.update(status='closed_failed',error=repr(exc),traceback=traceback.format_exc())
finally:
 if active is not None and active.poll() is None:
  os.killpg(active.pid,signal.SIGKILL);active.wait(timeout=5)
 if folder is not None:report['final_cleanup']=cleanup_owned(folder/'owned.jsonl')
 report.update(gpu_allocation_seconds=time.time()-start,gpu_after=gpu_snapshot(1),accepted_updates=0,strict_rsi_rounds=0);save(out/'report.json',report);save(out/'CLOSE.json',dict(status=report['status'],unused_allowance='canceled; no retries',not_agent_score=True));lock.close()
print(json.dumps(report,indent=2))
