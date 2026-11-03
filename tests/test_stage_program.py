import copy,hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np
from stage_program import StageProgram,adapted_infer,persist,validate,visible_frame

P={'version':1,'rationale':'test fixture only','routes':[{'task':'handover_block','evidence_case':'fixture','boundary_hypothesis':'consumer readiness may differ','stages':[{'focus':'prepare object','done_when':'object visible','next_ready_when':'receiver visible'},{'focus':'complete placement','done_when':'placed','next_ready_when':'not applicable'}]}]}
def observation():return {'task_language':'Pass block then place it.','views':{k:{'rgb':np.zeros((2,3,3),dtype=np.uint8)} for k in ['head','left_wrist','right_wrist']},'robot_state':{'left_eef_pose':[0,0,1,0,0,0,1],'right_eef_pose':[1,0,1,0,0,0,1],'left_gripper':0,'scorer':True},'success':True}
def decision(c,f,ready='yes'):return {'frame_sha256':f['frame_sha256'],'stage_index':c.stage_index,'completed':'yes','successor_ready':ready,'evidence':'synthetic fixture'}
class Tests(unittest.TestCase):
 def test_real_native_client_payload_and_unchanged_observation(self):
  from robots.robotwin.vla_client import LingBotVLAClient
  o=observation();o['robot_state']['right_gripper']=1;c=StageProgram(P,'handover_block',o['task_language']);client=object.__new__(LingBotVLAClient);seen=[]
  def pred(payload):seen.append(payload);return {'action':np.zeros((50,16))}
  # Invoke the exact upstream infer body with fake transport base predict.
  from unittest.mock import patch
  from rpent.robots.components.vla_client_base import BaseVLAClient
  logs=[]
  with patch.object(BaseVLAClient,'predict',side_effect=pred):result=adapted_infer(client.infer,o,c,lambda s:10,lambda r:logs.append(copy.deepcopy(r)))
  self.assertEqual(seen[0]['task'],c.effective_language());self.assertIs(seen[0]['observation.images.cam_high'],o['views']['head']['rgb']);self.assertEqual(o['task_language'],'Pass block then place it.');self.assertEqual(result.shape,(50,16));self.assertEqual(logs[-1]['status'],'completed')
 def test_unknown_holds_and_both_conditions_required(self):
  c=StageProgram(P,'handover_block','goal');f=visible_frame(observation());c.complete_vla_call()
  self.assertFalse(c.apply_decision(decision(c,f,'unknown'),f,2)['advanced']);c.complete_vla_call();self.assertTrue(c.apply_decision(decision(c,f),f,4)['advanced'])
 def test_antecedent_mode_control_differs_only_readiness(self):
  a=StageProgram(P,'handover_block','goal','postcondition_only');b=StageProgram(P,'handover_block','goal');f=visible_frame(observation())
  for c in [a,b]:c.complete_vla_call()
  self.assertTrue(a.apply_decision(decision(a,f,'no'),f,2)['advanced']);self.assertFalse(b.apply_decision(decision(b,f,'no'),f,2)['advanced'])
 def test_stale_duplicate_before_action_rejected(self):
  c=StageProgram(P,'handover_block','goal');f=visible_frame(observation());d=decision(c,f)
  with self.assertRaises(ValueError):c.apply_decision(d,f,2)
  c.complete_vla_call();d['frame_sha256']='old'
  with self.assertRaises(ValueError):c.apply_decision(d,f,2)
  c.apply_decision(decision(c,f,'no'),f,2)
  with self.assertRaises(ValueError):c.apply_decision(decision(c,f,'no'),f,2)
 def test_native_unchanged_and_oversize_fails_before_inference(self):
  o=observation();c=StageProgram(P,'handover_block',o['task_language'],'native');seen=[]
  adapted_infer(lambda x:seen.append(x['task_language']),o,c,lambda s:72,lambda r:None);self.assertEqual(seen,[o['task_language']])
  with self.assertRaises(ValueError):adapted_infer(lambda x:self.fail('called'),o,c,lambda s:73,lambda r:None)
 def test_no_scoring_or_command_fields_and_immutable_persistence(self):
  o=observation();f=visible_frame(o);o['success']=False;o['robot_state']['left_gripper']=1;self.assertEqual(f,visible_frame(o))
  with tempfile.TemporaryDirectory() as t:
   sha,p=persist(t,P,{'fixture':True});self.assertEqual(sha,hashlib.sha256(p.read_bytes()).hexdigest());c=StageProgram(P,'handover_block','goal');c.complete_vla_call();c.apply_decision(decision(c,f),f,2);self.assertEqual(sha,hashlib.sha256(p.read_bytes()).hexdigest());self.assertEqual(json.loads(p.with_name(sha+'.proposal.json').read_text())['status'],'proposed_unaccepted')
 def test_schema_rejects_code_or_duplicate_route(self):
  p=copy.deepcopy(P);p['code']='eval()'
  with self.assertRaises(Exception):validate(p)
  p=copy.deepcopy(P);p['routes']*=2
  with self.assertRaises(ValueError):validate(p)
if __name__=='__main__':unittest.main()
