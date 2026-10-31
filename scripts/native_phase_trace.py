"""Read-only method timing and Python stack watchdog, opt-in for diagnostics."""
import functools,json,os,time,threading,faulthandler
from pathlib import Path
_stream=None
_guard=threading.Lock()
def wrap(cls,name,emit):
    original=getattr(cls,name)
    @functools.wraps(original)
    def traced(self,*args,**kwargs):
        event={'phase':cls.__name__+'.'+name,'thread':threading.get_ident(),'start_ns':time.monotonic_ns()}
        if hasattr(self,'take_action_cnt'):event['native_counter']=int(self.take_action_cnt)
        emit({**event,'event':'enter'})
        try:
            result=original(self,*args,**kwargs)
        except BaseException as exc:
            emit({**event,'event':'error','error_type':type(exc).__name__});raise
        emit({**event,'event':'exit','elapsed_ns':time.monotonic_ns()-event['start_ns']})
        return result
    setattr(cls,name,traced)
    return original

def install():
    global _stream
    out=Path(os.environ['RSI_NATIVE_TRACE_DIR']);out.mkdir(exist_ok=True,parents=True)
    _stream=(out/'python-stacks.log').open('w')
    faulthandler.enable(file=_stream,all_threads=True)
    faulthandler.dump_traceback_later(45,repeat=True,file=_stream)
    log=(out/'phases.jsonl').open('a',buffering=1)
    def emit(row):
        with _guard:log.write(json.dumps(row)+'\n')
    from robotwin.envs._base_task import Base_Task
    from robots.robotwin.rlinf_env import RoboTwinAgentEnv
    for cls,names in [(Base_Task,['take_action','get_obs','_update_render']),(RoboTwinAgentEnv,['chunk_step','_robot_state'])]:
        for name in names:wrap(cls,name,emit)
    emit({'event':'installed','pid':os.getpid(),'wall':time.time()})
