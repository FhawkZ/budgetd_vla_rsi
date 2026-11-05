"""Synthetic CPU backend, never a robot task or capability result."""
import time
from skill_rsi_native_lifecycle import NativeBudget,NativeSafety,NativeInfrastructure
class Budget(BaseException):pass
class Safety(BaseException):pass
class SimTimeout(BaseException):pass
class Infrastructure(BaseException):pass
class FakeTask:
 def __init__(self):self.scored=0;self.closed=0
 def check_success(self):self.scored+=1;return True
class FakeAPI:
 def __init__(self,hooks,detect,spec):self.hooks,self.detect,self.spec=hooks,detect,spec
 def task_spec(self):return dict(self.spec,criterion_source='SECRET')
 def observe(self):
  import numpy as np
  result=self.detect(np.ones((4,4,3),dtype=np.uint8),np.ones((4,4),dtype=np.uint16),{'K':[[1,0,0],[0,1,0],[0,0,1]],'extrinsic_cv':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]})
  return {'ok':True,'components':result[0],'table_z_estimate':result[1]}
 def move_pose(self,arm,pose):self.hooks.calls.append('move_pose');return False
 def gripper(self,arm,value):return True
 def ee_pose(self,arm):return [0,0,0,1,0,0,0]
 def gripper_state(self,arm):return {'commanded':0,'measured':None}
 def wait(self,seconds):
  self.hooks.calls.append('wait')
  if self.hooks.mode=='sim_timeout':raise SimTimeout()
  if self.hooks.mode=='budget':raise Budget()
  if self.hooks.mode=='unknown':raise RuntimeError('BudgetExhausted')
  if self.hooks.mode=='blocking':time.sleep(3)
  return True
class FakeHooks:
 exception_map=[(Budget,NativeBudget,'native_primitive_budget'),(SimTimeout,NativeBudget,'native_sim_timeout'),(Safety,NativeSafety,'native_safety_stop'),(Infrastructure,NativeInfrastructure,'native_infrastructure')]
 def __init__(self,mode='ok'):self.mode=mode;self.calls=[];self.task=FakeTask();self.restored=False
 def prepare(self):self.calls.append('prepare')
 def setup(self,task,seed):
  self.calls.append(('setup',task,seed))
  if self.mode=='setup_error':raise Infrastructure('synthetic init failure')
  return self.task
 def task_spec(self,t,card):return {'instruction':'synthetic only','roles':{'toy':'toy'},'criterion_source':'SECRET','layout':{'truth':1}}
 def attach_monitor(self,t):
  if self.mode=='monitor_error':raise Infrastructure('synthetic monitor failure')
  return None
 def make_api(self,t,detect,spec):return FakeAPI(self,detect,spec)
 def close_task(self,t):t.closed+=1;self.calls.append('close')
 def restore(self):self.restored=True;self.calls.append('restore')
CONFIG={'task':'synthetic','seed':7,'task_card':{}}
PERCEPTION='def detect(rgb, depth_mm, calibration):\n    return [], 0.74\n'
