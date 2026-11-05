import unittest
from skill_rsi_program_delta import DeltaCompiler,sha
class DeltaTests(unittest.TestCase):
 def setUp(self):
  self.r={'skill_doc':'name: demo\n','inherited_skills':'N = 1\ndef f():\n    return "值"\n','inherited_perception':'def detect(x):\n    return x[:2]\n'}
  self.h={n:sha(self.r[r]) for n,r in {'SKILL.md':'skill_doc','skills.py':'inherited_skills','perception.py':'inherited_perception'}.items()};self.c=DeltaCompiler(self.r,self.h)
 def p(self,old='x[:2]',new='x[:3]',file='perception.py',target='function:detect'):
  return {'decision':'propose','edits':[{'file':file,'target':target,'old':old,'new':new}],'rationale':'Synthetic test only.'}
 def test_exact_unicode_and_no_mutation(self):
  p=self.p('"值"','"新"','skills.py','function:f');x=self.c.compile(p);self.assertEqual(x['skills.py'],'N = 1\ndef f():\n    return "新"\n');self.assertEqual(self.c.hashes,self.h)
 def test_hash_binding(self):
  with self.assertRaises(ValueError):DeltaCompiler(self.r,{})
 def test_abstain(self):self.assertIsNone(self.c.compile({'decision':'abstain','edits':[],'rationale':'No sufficient evidence.'}))
 def test_ambiguous_anchor(self):
  with self.assertRaises(ValueError):self.c.compile(self.p('e','q',file='skills.py',target='function:f'))
 def test_overlap(self):
  p=self.p();p['edits']*=2
  with self.assertRaises(ValueError):self.c.compile(p)
 def test_import_and_escape(self):
  for new in ('x\n    import os','x\ndef evil():\n    pass','x\nprint(1)'):
   with self.assertRaises(ValueError):self.c.compile(self.p(new=new))
 def test_syntax_no_repair(self):
  with self.assertRaises(SyntaxError):self.c.compile(self.p(new='('))
 def test_path_denied(self):
  with self.assertRaises(ValueError):self.c.compile(self.p(file='../scorer.py'))
 def test_duplicate_name(self):
  from skill_rsi_program_delta import scopes
  with self.assertRaises(ValueError):scopes('def f(): pass\ndef f(): pass\n')
 def test_untouched_and_multiple_scopes(self):
  p=self.p();p['edits'].append({'file':'SKILL.md','target':'document','old':'demo','new':'newdemo'})
  x=self.c.compile(p);self.assertEqual(x['skills.py'],self.r['inherited_skills']);self.assertEqual(x['SKILL.md'],'name: newdemo\n')
if __name__=='__main__':unittest.main()
