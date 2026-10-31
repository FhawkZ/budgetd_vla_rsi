import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bounded_vla import BoundedVLA,BudgetExceeded
class Env:
 def __init__(self):self.last_info={'episode_status':{'take_action_cnt':0,'eval_success':False}};self.executed=[]
 def get_task_language(self):return 'frozen native language'
 def chunk_step(self,a,**kw):
  assert kw==dict(action_type='ee',return_all_frames=False)
  self.executed.append(a.copy());self.last_info['episode_status']['take_action_cnt']+=len(a)
  return None,None,None,None,dict(executed_actions=len(a))
class Model:
 def __init__(self):self.seen=[];self.fail=False
 def infer(self,o):
  self.seen.append(o['robot_state']);
  if self.fail:raise RuntimeError('inference failed')
  return np.arange(800,dtype=np.float32).reshape(50,16)+o['robot_state']
def make(**kw):
 e=Env();m=Model();h=BoundedVLA(e,m,lambda:dict(task_language=e.get_task_language(),robot_state=e.last_info['episode_status']['take_action_cnt'],views={}),**kw);return e,m,h
class Contract(unittest.TestCase):
 def test_schedule_changes_next_real_observation_and_selected_prefix(self):
  for length in [25,50]:
   e,m,h=make()
   for _ in range(2):h.dispatch(dict(action='execute_vla_chunk',use_length=length))
   self.assertEqual(m.seen,[0,length]);self.assertEqual(len(e.executed[0]),length)
   np.testing.assert_array_equal(e.executed[0],np.arange(800,dtype=np.float32).reshape(50,16)[:length])
 def test_native50_equivalence_no_extra_inference_or_observation(self):
  e,m,h=make();h.dispatch(dict(action='execute_vla_chunk',use_length=50))
  self.assertEqual(m.seen,[0]);np.testing.assert_array_equal(e.executed[0],np.arange(800,dtype=np.float32).reshape(50,16))
 def test_observe_and_stop_never_execute(self):
  e,m,h=make();h.dispatch(dict(action='observe'));h.dispatch(dict(action='stop'))
  self.assertEqual(m.seen,[]);self.assertEqual(e.executed,[])
  with self.assertRaises(BudgetExceeded):h.dispatch(dict(action='execute_vla_chunk',use_length=50))
 def test_failures_and_invalid_requests_cannot_bypass_caps(self):
  e,m,h=make(max_inferences=1,max_requests=4);m.fail=True
  with self.assertRaises(RuntimeError):h.dispatch(dict(action='execute_vla_chunk',use_length=50))
  self.assertEqual(h.inferences,1)
  with self.assertRaises(BudgetExceeded):h.dispatch(dict(action='execute_vla_chunk',use_length=50))
  for r in [dict(action='execute_vla_chunk',use_length=True),dict(action='execute_vla_chunk',use_length=50,prompt='rescue')]:
   with self.assertRaises(ValueError):h.dispatch(r)
  with self.assertRaises(BudgetExceeded):h.dispatch(dict(action='observe'))
  self.assertEqual(e.executed,[])
 def test_horizon_clips_only_tail_and_terminal_stops_before_inference(self):
  e,m,h=make(horizon=60);h.dispatch(dict(action='execute_vla_chunk',use_length=50));h.dispatch(dict(action='execute_vla_chunk',use_length=25))
  self.assertEqual([len(x) for x in e.executed],[50,10])
  with self.assertRaises(BudgetExceeded):h.dispatch(dict(action='execute_vla_chunk',use_length=25))
  self.assertEqual(len(m.seen),2)
 def test_language_binding_is_immutable(self):
  e,m,h=make();e.get_task_language=lambda:'changed'
  with self.assertRaises(ValueError):h.dispatch(dict(action='execute_vla_chunk',use_length=50))
  self.assertEqual(m.seen,[])
if __name__=='__main__':unittest.main()
