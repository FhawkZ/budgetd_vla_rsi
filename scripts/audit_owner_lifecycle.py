"""Pinned AST lifecycle probe with fake task; zero native/model/GPU execution."""
import ast,json,os,sys,hashlib,threading,types
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from owner_thread_adapter import construct_on_owner
r=Path(os.environ['RSI_RUNTIME_ROOT']);out=r/'outputs/owner-lifecycle-audit-20261101-0220';out.mkdir(exist_ok=True)
source=r/'vendor/RPent-a744bd5f128ebef3cb8c6736cf7cd98adff681f1';site=Path(sys.prefix)/'lib/python3.11/site-packages';vf=site/'robotwin/envs/vector_env.py';tree=ast.parse(vf.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='VectorEnv');methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ['_init_envs','reset','get_obs','close']];events=[]
class Sub:
 def __init__(self,**kw):events.append(('create',threading.get_ident()))
 def setup_task(self):events.append(('setup',threading.get_ident()))
 def reset(self,env_seed=None):events.append(('reset',threading.get_ident()))
 def get_obs(self):events.append(('observe',threading.get_ident()));return {'unchanged':1}
 def close(self,clear_cache=True):events.append(('close',threading.get_ident()))
ns={'SubEnv':Sub,'gc':types.SimpleNamespace(collect=lambda:None),'torch':types.SimpleNamespace(cuda=types.SimpleNamespace(empty_cache=lambda:None))}
exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='V',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])),str(vf),'exec'),ns)
module=types.SimpleNamespace(ThreadPoolExecutor=ThreadPoolExecutor)
def factory():
 v=ns['V']();v.n_envs=1;v.envs=[];v.task_name='fake';v.args={};v.env_seeds=[100000];v.instruction_type='seen';v.global_lock=threading.Lock();v.env_thread_pool=module.ThreadPoolExecutor(max_workers=1);v._init_envs();return v
rows=[]
for adapted in [False,True]:
 events.clear();v=construct_on_owner(factory,module) if adapted else factory()
 def calls():v.reset(env_idx=[0],env_seeds=[100000]);assert v.get_obs()==[{'unchanged':1}];v.close()
 if adapted:calls()
 else:
  with ThreadPoolExecutor(1) as transport:transport.submit(calls).result(timeout=5)
 v.env_thread_pool.shutdown();rows.append(dict(mode='owner_inline' if adapted else 'native_topology',events=list(events),threads=len(set(t for _,t in events))))
assert rows[0]['threads']==3 and rows[1]['threads']==1
paths=[vf,source/'robots/robotwin/env_server.py',source/'robots/robotwin/rlinf_env.py',source/'rpent/utils/rpc/rpc_facade.py',source/'rpent/utils/rpc/main_thread_serve.py',source/'rpent/utils/rpc/http_rpc.py',r/'vendor/RLinf-2348ece3df113874671478be1360ae3115b346e3/rlinf/envs/sim/robotwin/robotwin_env.py']
report=dict(status='passed_cpu_scope',classification='exact pinned vector methods with fake task; no physics/thread safety conclusion',rows=rows,source_sha256={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},native_vector_method_lines={n.name:[n.lineno,n.end_lineno] for n in methods},facts=['Main construction invokes VectorEnv._init_envs/setup_task directly','VectorEnv.reset submits SubEnv.reset to pool; get_obs/close direct caller','RPent chunk_step directly takes sub_env.lock then task.take_action; does not use vector pool','Native HTTP workers vary across calls; RWLock serializes state mutations only','Pinned MainThreadServeMixin exists but calls _dispatch(session_id=...) whereas RoboTwin override omits keyword; candidate explicitly bridges only None session','Candidate main-thread facade alone insufficient: must keep reset inline too'],limitations=['Different thread identities do not prove SAPIEN requirement or explain original stall','CPU fake task proves routing and no nested-future deadlock only; no native qualification','Candidate adapts deployment for all methods, not method novelty'],model_calls=0,episodes=0)
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
