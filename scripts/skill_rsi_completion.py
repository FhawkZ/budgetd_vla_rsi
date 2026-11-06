"""Trusted evaluator gate, not a public robot API or runnable experiment.
Receipts must be built by the owner from process/transport state, never model text.
An outer supervisor must enforce the evaluation deadline and kill owned children.
"""
from dataclasses import dataclass
import json,math,threading,time
from pathlib import Path

@dataclass(frozen=True)
class OwnerCompletion:
    child_exit_code:int
    child_alive:bool
    pending_api:bool
    transport_failed:bool
    deadline_exceeded:bool
    render_error:bool
    outcome:str

class CompletionGate:
    def __init__(self,session,private_output,settle,score,clock=time.monotonic):
        self.session=session;self.path=Path(private_output);self.settle=settle;self.score=score
        self.clock=clock;self.used=False;self.thread=threading.get_ident()
        if self.path.exists():raise FileExistsError(self.path)
    def finish(self,receipt,deadline):
        # Consumes the attempt even on refusal: never retry unknown operations.
        if self.used:raise RuntimeError('completion already consumed')
        self.used=True
        record={'status':'refused','success':None,'settle_steps':None,'robot_qualified':False}
        try:
            s=self.session
            if type(receipt) is not OwnerCompletion:raise ValueError('owner receipt required')
            if threading.get_ident()!=self.thread or threading.get_ident()!=s.thread:raise ValueError('thread identity')
            if s.closed or s.poisoned or s.report['status']!='ready':raise ValueError('session not ready')
            if type(receipt.child_exit_code) is not int or receipt.child_exit_code!=0:raise ValueError('child exit')
            flags=[receipt.child_alive,receipt.pending_api,receipt.transport_failed,receipt.deadline_exceeded,receipt.render_error]
            if any(type(f) is not bool for f in flags) or any(flags):raise ValueError('incomplete or failed execution')
            if receipt.outcome!='returned':raise ValueError('no normal execution return')
            if not isinstance(deadline,(int,float)) or not math.isfinite(deadline) or self.clock()>=deadline:raise ValueError('evaluation deadline')
            record['status']='settling'
            # Original order: settle then native scorer; never infer score from API bool.
            record['settle_steps']=self.settle(s.task,2)
            if self.clock()>=deadline:raise TimeoutError('deadline after settle; do not score')
            record['status']='scoring';value=self.score(s.task)
            if self.clock()>=deadline:raise TimeoutError('score returned after deadline')
            record.update(status='evaluated',success=bool(value))
        except BaseException as e:
            self.session.poisoned=True;record.update(status='evaluation_refused_or_error',success=None,error_class=type(e).__name__,error=str(e))
            raise
        finally:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.path.open('x') as f:json.dump(record,f,indent=2,allow_nan=False)
        return {'status':'completion_recorded'} # No score returned to policy-facing consumer.
