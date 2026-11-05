import json,tempfile,unittest
from pathlib import Path
from skill_rsi_delta_author import run_once,request_body
from skill_rsi_program_delta import FILES,sha
class TransportTests(unittest.TestCase):
 def setUp(self):
  self.r={'skill_doc':'name: demo','inherited_skills':'def f(): return 1\n','inherited_perception':'def detect(x): return x\n'};self.cfg={'objective':'Synthetic task only','author_wall_seconds':1,'original_file_sha256':{n:sha(self.r[r]) for n,r in FILES.items()}}
 def response(self,finish='stop'):
  return {'choices':[{'finish_reason':finish,'message':{'content':None,'tool_calls':[{'type':'function','id':'x','function':{'name':'submit_delta','arguments':json.dumps({'decision':'abstain','edits':[],'rationale':'Unknown.'})}}]}}],'usage':{'prompt_tokens':3,'completion_tokens':5}}
 def test_once_abstain(self):
  calls=[]
  with tempfile.TemporaryDirectory() as p:
   x=run_once(self.r,self.cfg,Path(p)/'o',lambda b:(calls.append(b),self.response())[1]);self.assertEqual(len(calls),1);self.assertEqual(x['status'],'abstained_closed');self.assertFalse((Path(p)/'o/workspace').exists());self.assertEqual(x['completion_tokens'],5)
 def test_truncated_counted_no_retry(self):
  with tempfile.TemporaryDirectory() as p:
   x=run_once(self.r,self.cfg,Path(p)/'o',lambda b:self.response('length'));self.assertEqual(x['status'],'rejected_closed');self.assertEqual(x['model_calls'],1);self.assertEqual(x['completion_tokens'],5)
 def test_no_browse_or_feedback(self):
  x=request_body(self.r,self.cfg);self.assertEqual([t['function']['name'] for t in x['tools']],['submit_delta']);self.assertEqual(len(x['messages']),2);self.assertEqual(x['max_tokens'],1024)
if __name__=='__main__':unittest.main()
