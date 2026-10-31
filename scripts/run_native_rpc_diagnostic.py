"""One frozen cached-action replay for native RPC phase diagnosis; not Agent score."""
import argparse,fcntl,json,os,signal,socket,sys,time,traceback
from pathlib import Path
import numpy as np
from PIL import Image
from run_bounded_vla_pilot import ROOT,RENDER_BOOTSTRAP,digest,save,append,gpu_snapshot,proc_identity,cleanup_owned
p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);p.add_argument('--sha',required=True);a=p.parse_args();path=Path(a.protocol);cfg=json.loads(path.read_text());assert digest(path)==a.sha
r=Path(os.environ['RSI_RUNTIME_ROOT']);out=r/'outputs'/cfg['run_id'];assert not out.exists();assert socket.gethostname()==cfg['hostname'] and cfg['max_replays']==1 and cfg['max_chunks']==11
for rel,h in cfg['code_sha256'].items():assert digest(ROOT/rel)==h,rel
source=r/cfg['source_relative_path']
for rel,h in cfg['source_sha256'].items():assert digest(source/rel)==h,rel
assert digest(Path(sys.prefix)/cfg['native_task_relative_path'])==cfg['native_task_sha256']
for item in cfg['inputs']:
 assert digest(r/item['path'])==item['sha256']
 assert digest(r/item['observation_path'])==item['observation_sha256']
lock=(r/'locks/gpu1.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);gpu=gpu_snapshot(1);assert gpu['memory_mib']<100 and not gpu['compute_pids']
out.mkdir();save(out/'protocol.json',cfg);started=time.time();report=dict(status='running',classification=cfg['classification'],model_generations=0,vla_inferences=0,max_replays=1,completed_chunks=0,acknowledged_native_actions=0,started_unix=started,gpu_before=gpu,observation_matches=[]);save(out/'report.json',report)
from rpent.utils.daemon import ProcessDaemon
from rpent.dashboard.events import NullDashboardEventSink
from robots.robotwin.robot_spec import _init_runtime
from robots.robotwin.primitives import RoboTwinPrimitives
from robots.robotwin.env_client import RoboTwinEnvClient
old_start=ProcessDaemon.start;daemons=[]
def start(daemon):
 assert daemon.name=='robotwin_env_server','diagnostic must not start any model'
 bootstrap=out/'bootstrap';bootstrap.mkdir(exist_ok=True)
 (bootstrap/'sitecustomize.py').write_text(RENDER_BOOTSTRAP+'\nif os.environ.get("RSI_VLA_RENDER_CHILD")=="1":\n import native_phase_trace\n native_phase_trace.install()\n')
 daemon.cwd=str(r/cfg['assets_relative_path']);daemon.subprocess_env.update(PYTHONPATH=str(bootstrap)+os.pathsep+str(ROOT/'scripts')+os.pathsep+str(source),RSI_VLA_RENDER_CHILD='1',RSI_EXPECTED_GPU_PCI=gpu['pci_bus_id'],RSI_NATIVE_TRACE_DIR=str(out/'native-trace'),ROBOTWIN_ASSETS_ROOT=daemon.cwd,ASSETS_PATH=daemon.cwd)
 old_start(daemon);daemons.append(daemon);identity=proc_identity(daemon._proc.pid);append(out/'owned-daemons.jsonl',dict(pid=daemon._proc.pid,starttime=identity[0],name=daemon.name))
ProcessDaemon.start=start
old_reset=RoboTwinEnvClient.reset;resets=0
def reset(env):
 global resets
 resets+=1;assert resets==1
 return old_reset(env)
RoboTwinEnvClient.reset=reset

def alarm(*unused):raise TimeoutError('independent900second diagnostic wall limit')
signal.signal(signal.SIGALRM,alarm);signal.alarm(900)
try:
 args=argparse.Namespace(task_name=cfg['task'],seed=cfg['seed'],task_config='demo_randomized',max_episode_steps=1200,env_endpoint=None,vla_endpoint=None,robotwin_assets_path=str(r/cfg['assets_relative_path']),vla_model_path=None,lingbot_robot_config=None,cuda_device='1',env_cuda_device=None,vla_cuda_device=None)
 _,kw=_init_runtime(args,out,NullDashboardEventSink(),{'env'});env=kw['env'];primitives=RoboTwinPrimitives(**kw,model=None,check_cancelled=lambda:None)
 initial=primitives._build_lingbot_observation();assert initial['task_language']==cfg['instruction']
 # Match the initial harness observation and the first autonomous observe choice.
 primitives._build_lingbot_observation()
 for j,item in enumerate(cfg['inputs'],1):
  observation=primitives._build_lingbot_observation();images={}
  for name,v in observation['views'].items():
   f=out/f'chunk-{j:02d}-{name}.png';Image.fromarray(np.asarray(v['rgb'])).save(f);images[name]=digest(f)
  original=json.loads((r/item['observation_path']).read_text())
  state_equal=json.dumps(observation['robot_state'],sort_keys=True,default=lambda x:x.tolist())==json.dumps(original['robot_state'],sort_keys=True)
  image_equal=images=={k:v['sha256'] for k,v in original['images'].items()}
  report['observation_matches'].append(dict(chunk=j,state_equal=state_equal,images_equal=image_equal));save(out/'report.json',report)
  if j==1:assert state_equal and image_equal,'initial inputs differ; no replay retry'
  prediction=np.load(r/item['path']);assert prediction.shape==(50,16) and np.isfinite(prediction).all();selected=prediction[:25].copy()
  submitted=out/f'chunk-{j:02d}-submitted.npy';np.save(submitted,selected)
  append(out/'client-phases.jsonl',dict(event='chunk_enter',chunk=j,wall=time.time(),sha256=digest(submitted)))
  _,_,_,_,info=env.chunk_step(selected,action_type='ee',return_all_frames=False)
  report.update(completed_chunks=j,acknowledged_native_actions=int(info['episode_status']['take_action_cnt']));save(out/'report.json',report)
  append(out/'client-phases.jsonl',dict(event='chunk_exit',chunk=j,wall=time.time(),native_status=info['episode_status']))
  if info['episode_status']['eval_success']:break
 report['status']='completed_replay';report['native_status_for_infrastructure_only']=env.last_info['episode_status']
except BaseException as exc:
 report.update(status='diagnostic_interrupted',error=repr(exc),traceback=traceback.format_exc(),action_count_is_lower_bound=True)
 # Do not query a possibly blocked server for terminal images or success.
finally:
 signal.alarm(0)
 for daemon in reversed(daemons):
  try:daemon.stop(timeout=3)
  except Exception as exc:report.setdefault('cleanup_errors',[]).append(repr(exc))
 report['cleanup']=cleanup_owned(out/'owned-daemons.jsonl');report.update(finished_unix=time.time(),gpu_allocation_seconds=time.time()-started,gpu_after=gpu_snapshot(1),resets=resets)
 save(out/'report.json',report);save(out/'CLOSE.json',dict(status=report['status'],allowance='closed;no retry',agent_score=False));lock.close()
print(json.dumps(report,indent=2))
