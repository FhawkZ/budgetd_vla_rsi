import unittest,sys,json,hashlib,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import task_language_contract as m
class LanguageTest(unittest.TestCase):
 def test_reset_identity_and_missing_task(self):
  sentinel=object()
  class Env:
   task='handover_block';calls=0
   def reset(self,seed):self.calls+=1;return sentinel
  m.install(Env,{'handover_block':'Pass left to right.'});e=Env()
  self.assertIs(e.reset(42),sentinel);self.assertEqual(e.instruction,'Pass left to right.');self.assertEqual(e.calls,1)
  e.task='missing'
  with self.assertRaises(ValueError):e.reset(43)
  self.assertEqual(e.calls,1)
 def test_pinned_content(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);p=r/'description/task_instruction/a.json';p.parent.mkdir(parents=True);p.write_text('{"full_description":"public goal"}')
   manifest=r/'manifest.json';manifest.write_text(json.dumps({'status':'PUBLIC_LANGUAGE_BINDING_V1','tasks':[{'task':'a','field':'full_description','source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'instruction':'public goal'}]}))
   self.assertEqual(m.load(manifest,r),{'a':'public goal'})
   p.write_text('{"full_description":"different"}')
   with self.assertRaises(AssertionError):m.load(manifest,r)
if __name__=='__main__':unittest.main()
