import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
from skill_rsi_author_workspace import AuthorWorkspace,OUTPUTS
from skill_rsi_candidate_artifact import seal
ROOT=pathlib.Path('/root/autodl-tmp/Dex_runtime/agent-rsi/vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4')
NAME='move_can_pot_d885e5'
SKILL_NAME=next(x.split(':',1)[1].strip() for x in (ROOT/'frozen_skills'/NAME/'SKILL.md').read_text().splitlines() if x.startswith('name:'))
class Artifact(unittest.TestCase):
 def stage(self,d,malicious=False):
  w=AuthorWorkspace(pathlib.Path(d)/'w',{'skill_doc':'fixture'})
  for name in OUTPUTS:
   text='CPU fixture; not an autonomous proposal' if name=='rationale.md' else (ROOT/'frozen_skills'/NAME/name).read_text()
   if name=='skills.py' and malicious:text='open("/tmp/forbidden-author-execution", "w")\n'+text
   w.dispatch(dict(op='write',name=name,content=text,expected_sha256=None))
  return w
 def test_published_bytes_static_valid_not_execution_permission(self):
  with tempfile.TemporaryDirectory() as d:
   w=self.stage(d);r=seal(w.root,pathlib.Path(d)/'sealed',ROOT/'runtime',SKILL_NAME)
   self.assertEqual(r['errors'],[]);self.assertTrue(r['status'].startswith('static_valid'))
   self.assertFalse(r['executed']);self.assertFalse(r['rollout_authorized']);self.assertFalse(r['accepted_update'])
 def test_malicious_source_rejected_never_loaded(self):
  with tempfile.TemporaryDirectory() as d:
   w=self.stage(d,True);r=seal(w.root,pathlib.Path(d)/'sealed',ROOT/'runtime',SKILL_NAME)
   self.assertEqual(r['status'],'rejected');self.assertTrue(any('open' in x for x in r['errors']))
   self.assertFalse((pathlib.Path(d)/'sealed/artifacts').exists())
 def test_tampered_output_and_versions_refused(self):
  for target in ['output/skills.py','versions/002-skills.py']:
   with self.subTest(target=target),tempfile.TemporaryDirectory() as d:
    w=self.stage(d);(w.root/target).write_text('tampered');r=seal(w.root,pathlib.Path(d)/'sealed',ROOT/'runtime',SKILL_NAME)
    self.assertEqual(r['status'],'rejected')
 def test_symlink_and_extra_artifact_refused(self):
  for sym in [False,True]:
   with self.subTest(sym=sym),tempfile.TemporaryDirectory() as d:
    w=self.stage(d)
    if sym:
     p=w.root/'output/skills.py';p.unlink();p.symlink_to(w.root/'versions/002-skills.py')
    else:(w.root/'output/scorer.py').write_text('not allowed')
    self.assertEqual(seal(w.root,pathlib.Path(d)/'sealed',ROOT/'runtime',SKILL_NAME)['status'],'rejected')
 def test_destination_immutable(self):
  with tempfile.TemporaryDirectory() as d:
   w=self.stage(d);dest=pathlib.Path(d)/'sealed';seal(w.root,dest,ROOT/'runtime',SKILL_NAME)
   with self.assertRaises(FileExistsError):seal(w.root,dest,ROOT/'runtime',SKILL_NAME)
if __name__=='__main__':unittest.main()
