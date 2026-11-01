import copy,types,unittest
from typed_skill_patch import TypedSkillPatch,validate_patch,PatchError
RULE={'arm':'left','min_vla_calls':1,'gripper_min':0.,'gripper_max':.5,'operation':'move_relative','delta_xyz':[0.,0.,.04],'gripper_target':0.}
class TestPatch(unittest.TestCase):
 def setup_env(self,fail=False):
  e=types.SimpleNamespace(last_info={'robot_state':{'left_gripper':.2,'left_eef_pose':[.2,.3,.4,1,0,0,0]},'episode_status':{'eval_success':False,'take_action_cnt':100}})
  calls=[]
  def move(**kw):
   calls.append(kw)
   if not fail:e.last_info['episode_status']['take_action_cnt']+=10
   return types.SimpleNamespace(data={'plan_status':'Fail' if fail else 'Success'})
  return e,types.SimpleNamespace(move_to=move,set_gripper=move),calls
 def test_real_observed_target_and_once(self):
  e,p,c=self.setup_env();a=TypedSkillPatch({'rules':[RULE]},e,p)
  self.assertIsNone(a.before_vla(0));r=a.before_vla(1)
  self.assertEqual(c[0]['xyz'],[.2,.3,.44]);self.assertEqual(r['native_actions'],10);self.assertIsNone(a.before_vla(2))
 def test_failed_plan_charged_no_retry(self):
  e,p,c=self.setup_env(True);a=TypedSkillPatch({'rules':[RULE]},e,p);r=a.before_vla(1)
  self.assertTrue(r['planning_failure']);self.assertEqual(a.attempts,1);self.assertIsNone(a.before_vla(2));self.assertEqual(len(c),1)
 def test_remaining_budget(self):
  e,p,c=self.setup_env();e.last_info['episode_status']['take_action_cnt']=1191
  self.assertIsNone(TypedSkillPatch({'rules':[RULE]},e,p).before_vla(1));self.assertFalse(c)
 def test_closed(self):
  e,p,c=self.setup_env();e.last_info['episode_status']['eval_success']=True
  self.assertIsNone(TypedSkillPatch({'rules':[RULE]},e,p).before_vla(1))
 def test_no_match(self):
  e,p,c=self.setup_env();e.last_info['robot_state']['left_gripper']=1
  self.assertIsNone(TypedSkillPatch({'rules':[RULE]},e,p).before_vla(1));self.assertFalse(c)
 def test_no_extra_permissions(self):
  for edit in ({'code':'print(1)'},{'operation':'execute_python'},{'delta_xyz':[.5,0,0]},{'delta_xyz':[float('nan'),0,0]},{'min_vla_calls':True},{'gripper_min':.8,'gripper_max':.2}):
   with self.subTest(edit=edit),self.assertRaises(PatchError):validate_patch({'rules':[{**RULE,**edit}]})
 def test_abstention(self):self.assertEqual(validate_patch({'rules':[]}),{'rules':[]})
 def test_duplicate(self):
  with self.assertRaises(PatchError):validate_patch({'rules':[RULE,RULE]})
if __name__=='__main__':unittest.main()
