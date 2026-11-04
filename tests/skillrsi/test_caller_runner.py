import pathlib,sys,unittest,tempfile,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
from run_skill_rsi_caller import eligible_invalid
class InvalidScene(unittest.TestCase):
 def test_only_exact_action_free_native_instability(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'setup.jsonl').write_text(json.dumps({'event':'enter','seed':1})+'\n'+json.dumps({'event':'raised','seed':1})+'\n')
   r=dict(infra_reason='setup:UnStableError:fixture',cleanup_error=None,setup_attempts=1,setup_completed=0,primitive_calls=0,qwen_calls=0,vla_calls=0,clip_assignments=0)
   receipt=dict(exit_code=0,external_timeout=False,stderr_render_error=False,lingering_owned_group=False)
   self.assertTrue(eligible_invalid(r,receipt,p,{'seed':1}))
   for field,value in [('primitive_calls',1),('qwen_calls',1),('setup_attempts',2),('cleanup_error','error'),('infra_reason','setup:TimeoutError:x')]:
    self.assertFalse(eligible_invalid(dict(r,**{field:value}),receipt,p,{'seed':1}))
   self.assertFalse(eligible_invalid(r,dict(receipt,exit_code=1),p,{'seed':1}))
   self.assertFalse(eligible_invalid(r,receipt,p,{'seed':2}))
if __name__=='__main__':unittest.main()
