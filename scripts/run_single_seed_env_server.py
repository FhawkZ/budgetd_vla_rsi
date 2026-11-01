"""New opt-in single-owner/single-seed server, separate from frozen launchers."""
import atexit
import functools
import json
import os
import threading
from pathlib import Path

from owner_thread_adapter import install as install_owner
from single_seed_adapter import install as install_seed
from robots.robotwin import env_server
from robotwin.envs import vector_env
from robotwin.envs._base_task import Base_Task
from rpent.utils.rpc.main_thread_serve import MainThreadServeMixin

if os.environ.get('RSI_SINGLE_SEED_LAUNCH') != 'single_seed_v1':
    raise RuntimeError('No explicit single-seed qualification marker')
owner=threading.get_ident();counts={}
out=Path(os.environ['RSI_OWNER_AUDIT_FILE'])
attempts=Path(os.environ['RSI_SEED_ATTEMPTS_FILE'])
def record(row):
    with attempts.open('a') as f:
        f.write(json.dumps(row)+'\n');f.flush()
def receipt():
    out.write_text(json.dumps(dict(owner=owner,phase_counts=counts,status='process_exit',scope='thread checks only'),indent=2)+'\n')
atexit.register(receipt)
for name in ['_init_task_env_','get_obs','take_action','close_env','_update_render']:
    original=getattr(Base_Task,name)
    def wrap(fn,key):
        @functools.wraps(fn)
        def call(*a,**k):
            if threading.get_ident()!=owner:raise RuntimeError('Native method outside owner: '+key)
            counts[key]=counts.get(key,0)+1
            if key=='_init_task_env_' and counts[key]>2:raise RuntimeError('Native initialization entry budget exhausted')
            return fn(*a,**k)
        return call
    setattr(Base_Task,name,wrap(original,name))
install_seed(vector_env,record,max_attempts=2)
install_owner(env_server,vector_env,MainThreadServeMixin)
env_server.main()
