import json,tempfile,unittest,urllib.error,io,hashlib
from pathlib import Path
from skill_rsi_small_author_loop import run_small_author
R={'skill_doc':'name: toy\n','inherited_skills':'def fallback(api):\n    return {}\n','inherited_perception':'def detect(rgb, depth_mm, calibration):\n    return [], 0.74\n','api_doc':'synthetic only'}
def response(name,args):return {'model':'qwen3-vl-30b-a3b-instruct','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'type':'function','id':'fakeid','function':{'name':name,'arguments':json.dumps(args)}}]}}],'usage':{'prompt_tokens':10,'completion_tokens':4}}
class SmallTransportTests(unittest.TestCase):
 def test_structured_small_edits_then_finish_not_execute(self):
  with tempfile.TemporaryDirectory() as t:
   seen=[]
   def request(body):
    seen.append(json.loads(json.dumps(body)))
    if len(seen)==1:return response('edit_lines',{'name':'rationale.md','expected_sha256':None,'start':1,'delete_count':0,'expected_slice_sha256':hashlib.sha256(b'').hexdigest(),'text':'Unverified fixture\n'})
    return response('finish',{})
   r=run_small_author(R,'fixture',Path(t)/'out',2,transport=request)
   self.assertEqual(r['status'],'submitted_unaccepted_not_executed');self.assertFalse(r['executed']);self.assertEqual(seen[1]['messages'][-1]['role'],'tool');self.assertEqual([x['function']['name'] for x in seen[0]['tools']],['read_lines','edit_lines','finish'])
 def test_whole_write_denied_and_failed_usage_retained(self):
  with tempfile.TemporaryDirectory() as t:
   r=run_small_author(R,'fixture',Path(t)/'out',8,transport=lambda b:response('write_file',{}))
   self.assertEqual(r['model_calls'],1);self.assertEqual(r['completion_tokens'],4);self.assertEqual(r['unused_calls_canceled'],7)
 def test_http_failure_no_retry(self):
  with tempfile.TemporaryDirectory() as t:
   def fail(body):raise urllib.error.HTTPError('local',400,'truncated',{},io.BytesIO(json.dumps({'usage':{'prompt_tokens':10,'completion_tokens':1024}}).encode()))
   r=run_small_author(R,'fixture',Path(t)/'out',8,transport=fail);self.assertEqual(r['model_calls'],1);self.assertEqual(r['completion_tokens'],1024);self.assertEqual(r['unused_calls_canceled'],7)
if __name__=='__main__':unittest.main()
