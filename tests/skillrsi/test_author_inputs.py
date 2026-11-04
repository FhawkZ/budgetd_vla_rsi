import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
from skill_rsi_author_inputs import prepare
from skill_rsi_author_workspace import load_resources
R=pathlib.Path('/root/autodl-tmp/Dex_runtime/agent-rsi');REPO=pathlib.Path(__file__).resolve().parents[2]
class Inputs(unittest.TestCase):
 def test_both_approved_resources_pinned_and_loadable(self):
  for task in ['move_can_pot','stack_bowls_two']:
   with self.subTest(task=task),tempfile.TemporaryDirectory() as d:
    dest=pathlib.Path(d)/'prepared';r=prepare(task,R,REPO,dest);data=load_resources(dest/'manifest.json')
    self.assertEqual(set(data),{'api_doc','skill_doc','inherited_skills','inherited_perception','development_feedback'})
    feedback=json.loads(data['development_feedback']);self.assertNotIn('official_success',feedback);self.assertNotIn('task_spec',feedback);self.assertEqual(r['author_calls'],0);self.assertEqual(r['image_attachments'],0)
 def test_unknown_task_refused_before_access(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):prepare('sealed_task','/does/not/exist',REPO,pathlib.Path(d)/'out')
 def test_snapshot_tamper_rejected_by_author_transport(self):
  with tempfile.TemporaryDirectory() as d:
   dest=pathlib.Path(d)/'prepared';prepare('move_can_pot',R,REPO,dest);(dest/'development_feedback.txt').write_text('tampered')
   with self.assertRaises(ValueError):load_resources(dest/'manifest.json')
 def test_no_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   dest=pathlib.Path(d)/'prepared';prepare('move_can_pot',R,REPO,dest)
   with self.assertRaises(FileExistsError):prepare('move_can_pot',R,REPO,dest)
if __name__=='__main__':unittest.main()
