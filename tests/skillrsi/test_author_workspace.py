import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
from skill_rsi_author_workspace import AuthorWorkspace,load_resources,digest
class Workspace(unittest.TestCase):
 def test_roundtrip_and_stale_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   w=AuthorWorkspace(pathlib.Path(t)/'w',{'api_doc':'example'})
   self.assertEqual(w.dispatch(dict(op='read',resource='api_doc',offset=0,limit=10))['text'],'example')
   r=w.dispatch(dict(op='write',name='skills.py',content='draft',expected_sha256=None))
   with self.assertRaises(ValueError):w.dispatch(dict(op='write',name='skills.py',content='stale',expected_sha256=None))
   w.dispatch(dict(op='write',name='skills.py',content='new',expected_sha256=r['sha256']))
   self.assertEqual(len(list((w.root/'versions').iterdir())),2);self.assertFalse(w.ready())
 def test_path_and_shell_refused(self):
  with tempfile.TemporaryDirectory() as t:
   w=AuthorWorkspace(pathlib.Path(t)/'w',{})
   for req in [dict(op='write',name='../outside',content='bad',expected_sha256=None),dict(op='read',resource='/etc/passwd',offset=0,limit=10),dict(op='shell',command='true')]:
    with self.assertRaises(ValueError):w.dispatch(req)
   self.assertFalse((pathlib.Path(t)/'outside').exists());self.assertEqual(len((w.root/'operations.jsonl').read_text().splitlines()),3)
 def test_symlink_refused(self):
  with tempfile.TemporaryDirectory() as t:
   w=AuthorWorkspace(pathlib.Path(t)/'w',{});outside=pathlib.Path(t)/'outside';outside.write_text('untouched');(w.root/'output/skills.py').symlink_to(outside)
   with self.assertRaises(ValueError):w.dispatch(dict(op='write',name='skills.py',content='bad',expected_sha256=None))
   self.assertEqual(outside.read_text(),'untouched')
 def test_grants_pin_and_reject_unknown(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t);src=p/'api.txt';src.write_text('API only');manifest=p/'manifest.json';g={'id':'api_doc','path':str(src),'sha256':digest(src.read_bytes())}
   manifest.write_text(json.dumps({'status':'FROZEN_AUTHOR_INPUT','resources':[g]}));self.assertEqual(load_resources(manifest)['api_doc'],'API only')
   src.write_text('changed')
   with self.assertRaises(ValueError):load_resources(manifest)
 def test_budget_and_size(self):
  with tempfile.TemporaryDirectory() as t:
   w=AuthorWorkspace(pathlib.Path(t)/'w',{},max_operations=1)
   with self.assertRaises(ValueError):w.dispatch(dict(op='write',name='SKILL.md',content='x'*20001,expected_sha256=None))
   with self.assertRaises(RuntimeError):w.dispatch(dict(op='write',name='skills.py',content='x',expected_sha256=None))
if __name__=='__main__':unittest.main()
