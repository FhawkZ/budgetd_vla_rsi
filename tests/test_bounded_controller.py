import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bounded_controller import parse_response
TOOLS=json.loads((Path(__file__).resolve().parents[1]/'configs/bounded-vla-interface-v1.json').read_text())['tools']
def response(name='execute_vla_chunk',args=None):
 return {'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'x','function':{'name':name,'arguments':json.dumps({'use_length':25} if args is None else args)}}]}}]}
class TestController(unittest.TestCase):
 def test_exact_parameters(self):self.assertEqual(parse_response(response(),TOOLS)[0],{'action':'execute_vla_chunk','use_length':25})
 def test_no_guess_repair(self):
  for name,args in [('execute_vla_chunk',{'use_length':26}),('execute_vla_chunk',{'use_length':'25'}),('observe',{'path':'secret'}),('exec_python',{})]:
   with self.assertRaises(Exception):parse_response(response(name,args),TOOLS)
 def test_no_forced_action(self):
  r=response();r['choices'][0]['message']['tool_calls']=[]
  with self.assertRaises(ValueError):parse_response(r,TOOLS)
  self.assertEqual(parse_response(response('stop',{}),TOOLS)[0],{'action':'stop'})
 def test_no_multiple_or_truncated(self):
  r=response();r['choices'][0]['message']['tool_calls']*=2
  with self.assertRaises(ValueError):parse_response(r,TOOLS)
  r=response();r['choices'][0]['finish_reason']='length'
  with self.assertRaises(ValueError):parse_response(r,TOOLS)
if __name__=='__main__':unittest.main()
