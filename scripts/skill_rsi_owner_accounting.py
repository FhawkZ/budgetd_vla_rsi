"""Trusted owner accounting only; not a full runner, sandbox or C++ watchdog."""
import hashlib,math,subprocess,sys,time
from pathlib import Path
class ExecutionBudget(BaseException):pass

def proc_start(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]

class BoundSkill:
    def __init__(self,process,run_id,source):
        if not isinstance(process,subprocess.Popen) or process.poll() is not None:raise ValueError('bind live owned child before dispatch')
        if not isinstance(run_id,str) or not run_id:raise ValueError('run ID')
        self.process=process;self.pid=process.pid;self.starttime=proc_start(self.pid)
        self.run_id=run_id;self.source_sha256=hashlib.sha256(source.encode()).hexdigest()
        self.consumed=False
    def consume(self,process,run_id,source):
        if self.consumed:raise RuntimeError('receipt already consumed')
        self.consumed=True
        if process is not self.process or run_id!=self.run_id or hashlib.sha256(source.encode()).hexdigest()!=self.source_sha256:raise ValueError('bound run/source/process mismatch')
        code=process.poll()
        if code is None:
            if proc_start(self.pid)!=self.starttime:raise ValueError('PID identity mismatch')
            raise ValueError('child still active')
        if code!=0:raise ValueError('child exit not zero')
        return {'run_id':self.run_id,'source_sha256':self.source_sha256,'pid':self.pid,'starttime':self.starttime,'exit_code':code}

class ActiveWall:
    def __init__(self,seconds=240,clock=time.monotonic):
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0:raise ValueError('finite positive wall limit')
        self.limit=seconds;self.clock=clock;self.spent=0.;self.started=None
    def elapsed(self):
        return self.spent+(0 if self.started is None else self.clock()-self.started)
    def check(self):
        if self.elapsed()>=self.limit:raise ExecutionBudget('wall budget')
    def start(self):
        if self.started is not None:raise RuntimeError('wall already running')
        self.check();self.started=self.clock()
    def pause(self):
        if self.started is None:raise RuntimeError('wall not running')
        self.spent+=self.clock()-self.started;self.started=None;self.check()

class CodeLineBudget:
    def __init__(self,limit):
        if type(limit) is not int or limit<=0:raise ValueError('positive code line limit')
        self.limit=limit;self.n=0
    def tracer(self,frame,event,arg):
        if frame.f_code.co_filename!='<skills>':return None
        if event=='line':
            self.n+=1
            if self.n>self.limit:raise ExecutionBudget('code_lines')
        return self.tracer
    def run(self,fn,*args):
        previous=sys.gettrace();sys.settrace(self.tracer)
        try:return fn(*args)
        finally:sys.settrace(previous)
