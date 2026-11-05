import json,tempfile,unittest,urllib.error,io
from pathlib import Path
from skill_rsi_author_loop import AuthorEdits,run_author,parse_call
R={'skill_doc':'name: toy','inherited_skills':'TOKEN\nTOKEN\nunique','inherited_perception':'detector','api_doc':'public methods only','development_feedback':'no task score'}
def response(name,args,usage=True,finish='stop'):
 d={'model':'qwen3-vl-30b-a3b-instruct','choices':[{'finish_reason':finish,'message':{'content':'<tool_call>'+json.dumps({'name':name,'arguments':args})+'</tool_call>'}}]}
 if usage:d['usage']={'prompt_tokens':10,'completion_tokens':4}
 return d
class Tests(unittest.TestCase):
 def test_inherit_cas_unique_and_capability(self):
  with tempfile.TemporaryDirectory() as t:
   e=AuthorEdits(Path(t)/'w',R);s=e.workspace.state['skills.py'];self.assertEqual(e.workspace.n,3)
   for args in [{'name':'skills.py','expected_sha256':s,'old':'TOKEN','new':'x'},{'name':'skills.py','expected_sha256':'bad','old':'unique','new':'x'},{'name':'../x','expected_sha256':None,'old':'x','new':'y'}]:
    with self.assertRaises(ValueError):e.dispatch('replace_text',args)
   e.dispatch('replace_text',{'name':'skills.py','expected_sha256':s,'old':'unique','new':'changed'});self.assertEqual((e.workspace.root/'versions/003-perception.py').read_text(),'detector');self.assertEqual((e.workspace.root/'versions/002-skills.py').read_text(),R['inherited_skills'])
 def test_complete_loop_and_rejected_finish_accounted(self):
  with tempfile.TemporaryDirectory() as t:
   seq=iter([response('finish',{}),response('write_file',{'name':'rationale.md','expected_sha256':None,'content':'Unverified proposal, no execution.'}),response('finish',{})]);seen=[]
   def send(body):seen.append(json.loads(json.dumps(body)));return next(seq)
   r=run_author(R,'test only',Path(t)/'run',3,transport=send)
   self.assertEqual(r['status'],'submitted_unaccepted_not_executed');self.assertEqual(r['model_calls'],3);self.assertFalse(r['edit_results'][0]['ok']);self.assertEqual(r['prompt_tokens'],30);self.assertFalse(r['executed']);self.assertTrue('expected_sha256' in json.dumps(seen[0]['tools']))
 def test_budget_stops_no_auto_finish(self):
  with tempfile.TemporaryDirectory() as t:
   r=run_author(R,'test only',Path(t)/'run',2,transport=lambda b:response('read_output',{'name':'skills.py'}));self.assertEqual(r['model_calls'],2);self.assertEqual(r['status'],'model_budget_exhausted_unsubmitted');self.assertFalse(r['executed'])
 def test_error_usage_no_retry(self):
  with tempfile.TemporaryDirectory() as t:
   calls=[]
   def fail(b):
    calls.append(b);raise urllib.error.HTTPError('local',400,'bad',{},io.BytesIO(json.dumps({'usage':{'prompt_tokens':12,'completion_tokens':3}}).encode()))
   r=run_author(R,'test only',Path(t)/'run',8,transport=fail);self.assertEqual(len(calls),1);self.assertEqual(r['prompt_tokens'],12);self.assertEqual(r['unused_calls_canceled'],7)
 def test_truncation_and_tool_unknown(self):
  with tempfile.TemporaryDirectory() as t:
   r=run_author(R,'test only',Path(t)/'run',8,transport=lambda b:response('finish',{},finish='length'));self.assertEqual(r['model_calls'],1);self.assertEqual(r['status'],'refused_or_transport_error')
  for s in ['hello','<tool_call>{"name":"shell","arguments":{}}</tool_call>','<tool_call>{"name":"finish","arguments":{}}</tool_call>extra']:
   with self.assertRaises(ValueError):parse_call(s)
 def test_real_server_structured_response_shape(self):
  with tempfile.TemporaryDirectory() as t:
   seen=[]
   def send(b):
    seen.append(json.loads(json.dumps(b)))
    name='write_file' if len(seen)==1 else 'finish'
    args={'name':'rationale.md','expected_sha256':None,'content':'test'} if len(seen)==1 else {}
    return {'model':'qwen3-vl-30b-a3b-instruct','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'native_id','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],'usage':{'prompt_tokens':10,'completion_tokens':4}}
   r=run_author(R,'test',Path(t)/'run',2,transport=send);self.assertEqual(r['status'],'submitted_unaccepted_not_executed');self.assertEqual(seen[1]['messages'][-1]['role'],'tool');self.assertEqual(seen[1]['messages'][-1]['tool_call_id'],'native_id')
 def test_generated_code_never_imported(self):
  with tempfile.TemporaryDirectory() as t:
   marker=Path(t)/'owned';payload=f'open({str(marker)!r},"w").write("bad")';initial=AuthorEdits(Path(t)/'seed',R).initial
   seq=iter([response('write_file',{'name':'skills.py','expected_sha256':initial['skills.py'],'content':payload}),response('write_file',{'name':'rationale.md','expected_sha256':None,'content':'test'}),response('finish',{})])
   r=run_author(R,'test only',Path(t)/'run',3,transport=lambda b:next(seq));self.assertFalse(marker.exists());self.assertEqual(r['status'],'submitted_unaccepted_not_executed')
if __name__=='__main__':unittest.main()
