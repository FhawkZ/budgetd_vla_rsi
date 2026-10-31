"""Explicit single-owner candidate server. Requires a separately frozen protocol."""
import json, os, threading, functools, atexit
from pathlib import Path
from owner_thread_adapter import install
from robots.robotwin import env_server
from robotwin.envs import vector_env
from robotwin.envs._base_task import Base_Task
from rpent.utils.rpc.main_thread_serve import MainThreadServeMixin

if os.environ.get('RSI_OWNER_QUALIFIED_LAUNCH') != 'candidate_lifecycle_v1':
    raise RuntimeError('No explicit candidate qualification launch marker')
owner = threading.get_ident()
counts = {}
out = Path(os.environ['RSI_OWNER_AUDIT_FILE'])
def receipt():
    out.write_text(json.dumps({'owner':owner,'phase_counts':counts,'status':'process_exit','scope':'thread checks only'},indent=2)+'\n')
atexit.register(receipt)
for name in ['_init_task_env_','get_obs','take_action','close_env','_update_render']:
    original = getattr(Base_Task,name)
    def wrap(fn, key):
        @functools.wraps(fn)
        def call(*a, **k):
            if threading.get_ident() != owner:
                raise RuntimeError('Native method outside owner: '+key)
            counts[key]=counts.get(key,0)+1
            return fn(*a, **k)
        return call
    setattr(Base_Task,name,wrap(original,name))
install(env_server,vector_env,MainThreadServeMixin)
env_server.main()
