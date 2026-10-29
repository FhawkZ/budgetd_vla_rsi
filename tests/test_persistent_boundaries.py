"""CPU-only tests of path escape and namespace/cap contract boundaries."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
def module(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=module('responses','scripts/responses_adapter.py');m=module('mcp_scope','scripts/readonly_role_mcp.py');p=module('pilot','scripts/run_roborsi_native_pilot.py')
class Boundary(unittest.TestCase):
 def test_namespace_roundtrip(self):
  b={'model':a.MODEL,'input':[{'role':'user','content':'inspect'}],'tools':[{'type':'namespace','name':'mcp__role_evidence','tools':[{'type':'function','name':'read_text','parameters':{'type':'object','properties':{'path':{'type':'string'}}}}]}]}
  out,audit=a.translate_request(b);name=out['tools'][0]['function']['name']
  chat={'model':a.MODEL,'choices':[{'message':{'content':None,'tool_calls':[{'id':'call_m','function':{'name':name,'arguments':'{"path":"/fixture/x"}'}}]},'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13}}
  result=a.translate_response(chat,audit)['output'][0]
  self.assertEqual(result['namespace'],'mcp__role_evidence');self.assertEqual(result['name'],'read_text')
  b['input'] += [result,{'type':'function_call_output','call_id':'call_m','output':[{'type':'input_text','text':'evidence'}]}]
  translated,_=a.translate_request(b);self.assertEqual(translated['messages'][-1]['tool_call_id'],'call_m')
  self.assertEqual(translated['messages'][-2]['tool_calls'][0]['function']['name'],name)
 def test_scope_escape_and_credentials(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'root';root.mkdir();outside=Path(d)/'outside';outside.write_text('not exposed')
   (root/'good.txt').write_text('one\ntwo');(root/'leak').symlink_to(outside);(root/'auth.json').write_text('fixture no secret')
   scope=m.Scope([root],Path(d)/'audit.jsonl');self.assertEqual(scope.text(str(root/'good.txt'))['text'],'one\ntwo')
   for path in (outside,root/'leak',root/'auth.json'):
    with self.assertRaises(PermissionError):scope.resolve(str(path))
   with self.assertRaises(ValueError):scope.resolve('good.txt')
 def test_explicit_cap_adaptation(self):
  out,audit=p.cap_request({'model':p.MODEL,'messages':[],'max_completion_tokens':16384})
  self.assertEqual(out['max_tokens'],1024);self.assertEqual(audit['original_caps']['max_completion_tokens'],16384)
  with self.assertRaises(ValueError):p.cap_request({'model':'paid-other','max_tokens':10})
  with self.assertRaises(ValueError):p.cap_request({'model':p.MODEL,'max_tokens':50,'max_completion_tokens':1024})
if __name__=='__main__':unittest.main()
