import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import responses_adapter as a
class ProfileTests(unittest.TestCase):
 def body(self):
  return {'model':a.MODEL,'input':[{'role':'user','content':'Inspect evidence.'}],'tools':[{'type':'function','name':n,'parameters':{'type':'object','properties':{}}} for n in sorted(a.ROLE_EVIDENCE_TOOLS|{'read_mcp_resource','create_goal'})]}
 def test_allowlist_and_disclosure(self):
  out,audit=a.translate_request(self.body(),tool_profile='role-evidence')
  self.assertEqual(set(audit['tool_names']),a.ROLE_EVIDENCE_TOOLS)
  self.assertEqual(audit['removed_tools'],['create_goal','read_mcp_resource'])
 def test_default_unchanged(self):
  out,audit=a.translate_request(self.body());self.assertIn('read_mcp_resource',audit['tool_names'])
 def test_missing_tools_rejected(self):
  body=self.body();body['tools']=[]
  with self.assertRaises(a.ContractError):a.translate_request(body,tool_profile='role-evidence')
 def test_existing_excluded_history_rejected(self):
  body=self.body();body['input'] += [{'type':'function_call','name':'read_mcp_resource','call_id':'x','arguments':'{}'},{'type':'function_call_output','call_id':'x','output':'error'}]
  with self.assertRaises(a.ContractError):a.translate_request(body,tool_profile='role-evidence')
if __name__=='__main__':unittest.main()
