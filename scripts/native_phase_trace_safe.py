"""Candidate Python-thread sampler; full module not qualified or enabled in simulator.
Only the sampling mechanism passed bounded CPU controls, not SAPIEN.
Avoids timer/signal-driven faulthandler dumping, which crashed local CPU stress.
Sampling still changes timing; apply identically in any future comparison.
"""
import json,os,sys,threading,time,traceback
from pathlib import Path
from native_phase_trace import wrap

def install(interval=45):
    out=Path(os.environ['RSI_NATIVE_TRACE_DIR']);out.mkdir(exist_ok=True,parents=True)
    log=(out/'phases.jsonl').open('a',buffering=1);guard=threading.Lock()
    def emit(row):
        with guard:log.write(json.dumps(row)+'\n')
    def sample():
        with (out/'python-thread-stacks.log').open('w',buffering=1) as f:
            while True:
                time.sleep(interval)
                frames=sys._current_frames()
                for tid,frame in frames.items():
                    f.write('thread '+str(tid)+' wall '+str(time.time())+'\n'+''.join(traceback.format_stack(frame)))
                del frames,frame
    threading.Thread(target=sample,daemon=True,name='rsi-python-stack-observer').start()
    from robotwin.envs._base_task import Base_Task
    from robots.robotwin.rlinf_env import RoboTwinAgentEnv
    for cls,names in [(Base_Task,['take_action','get_obs','_update_render']),(RoboTwinAgentEnv,['chunk_step','_robot_state'])]:
        for name in names:wrap(cls,name,emit)
    emit({'event':'installed_candidate_python_observer','pid':os.getpid(),'wall':time.time()})
