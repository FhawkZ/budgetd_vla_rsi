import hashlib,json,tempfile,unittest
from pathlib import Path
from skill_rsi_small_edits import SmallEdits,TOOLS
R={'skill_doc':'name: fixture\n','inherited_skills':'def f():\n    return 0\n\ndef g():\n    return 1\n','inherited_perception':'def detect():\n    return []\n','api_doc':'fixture only'}
sha=lambda x:hashlib.sha256(x.encode()).hexdigest()
class SmallEditTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.e=SmallEdits(Path(self.temp.name)/'w',R)
 def tearDown(self):self.temp.cleanup()
 def edit(self,**kw):
  a={'name':'skills.py','expected_sha256':self.e.workspace.state['skills.py'],'start':2,'delete_count':1,'expected_slice_sha256':sha('    return 0\n'),'text':'    return 2\n'};a.update(kw);return self.e.dispatch('edit_lines',a)
 def test_exact_local_edit_and_stale_refusal(self):
  initial=self.e.workspace.state['skills.py'];self.edit();self.assertEqual((self.e.workspace.root/'output/skills.py').read_text(),R['inherited_skills'].replace('return 0','return 2'))
  with self.assertRaises(ValueError):self.edit(expected_sha256=initial)
  self.assertEqual((self.e.workspace.root/'versions/002-skills.py').read_text(),R['inherited_skills'])
 def test_unicode_and_no_newline_repair(self):
  self.edit(text='    return "碗"')
  self.assertIn('return "碗"\ndef g()', (self.e.workspace.root/'output/skills.py').read_text())
 def test_caps_hashes_and_path(self):
  for kw in [{'text':'x'*1601},{'start':0},{'delete_count':25},{'expected_slice_sha256':'bad'},{'name':'../scorer'}]:
   with self.assertRaises(ValueError):self.edit(**kw)
  self.assertEqual(self.e.workspace.state['skills.py'],sha(R['inherited_skills']))
 def test_missing_rationale_and_no_auto_execute(self):
  with self.assertRaises(ValueError):self.e.dispatch('finish',{})
  marker=Path(self.temp.name)/'owned';code='open('+repr(str(marker))+',"w").write("x")\n'
  self.edit(text=code)
  self.e.dispatch('edit_lines',{'name':'rationale.md','expected_sha256':None,'start':1,'delete_count':0,'expected_slice_sha256':sha(''),'text':'Unverified\n'})
  self.assertEqual(self.e.dispatch('finish',{})['status'],'submitted_unaccepted_not_executed');self.assertFalse(marker.exists())
 def test_no_whole_file_tool_and_read_cap(self):
  self.assertEqual([t['function']['name'] for t in TOOLS],['read_lines','edit_lines','finish'])
  with self.assertRaises(ValueError):self.e.dispatch('write_file',{})
  row=self.e.dispatch('read_lines',{'name':'skills.py','start':1,'count':2});self.assertEqual(row['text'],'def f():\n    return 0\n');self.assertEqual(row['slice_sha256'],sha(row['text']))
 def test_external_tamper_and_symlink(self):
  p=self.e.workspace.root/'output/skills.py';p.write_text('tamper')
  with self.assertRaises(ValueError):self.e.dispatch('read_lines',{'name':'skills.py','start':1,'count':1})
  p.unlink();p.symlink_to('/etc/passwd')
  with self.assertRaises(ValueError):self.e.dispatch('read_lines',{'name':'skills.py','start':1,'count':1})
if __name__=='__main__':unittest.main()
