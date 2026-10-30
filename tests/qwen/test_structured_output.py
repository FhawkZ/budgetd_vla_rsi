"""Synthetic rejection-path checks, independent from robot success labels."""
import copy,json,unittest
from structured_qwen import validate_output
TOOLS=[{'type':'function','function':{'name':'pixel','parameters':{'type':'object','properties':{'pixels':{'type':'array','items':{'type':'array','items':{'type':'integer'},'minItems':2,'maxItems':2},'minItems':1}},'required':['pixels'],'additionalProperties':False}}}]
def call(name,args):return '<tool_call>'+json.dumps({'name':name,'arguments':args})+'</tool_call>'
class Output(unittest.TestCase):
 def test_nested_valid_and_no_mutation(self):
  original=copy.deepcopy(TOOLS);text=call('pixel',{'pixels':[[1,2]]});self.assertEqual(validate_output(text,TOOLS),1);self.assertEqual(TOOLS,original)
 def test_flat_rejected(self):
  with self.assertRaises(Exception):validate_output(call('pixel',{'pixels':[1,2]}),TOOLS)
 def test_truncated_rejected(self):
  with self.assertRaisesRegex(ValueError,'Incomplete'):validate_output('<tool_call>{"name":"pixel"',TOOLS)
 def test_undeclared_rejected(self):
  with self.assertRaisesRegex(ValueError,'Undeclared'):validate_output(call('invented',{}),TOOLS)
 def test_plain_text_allowed(self):self.assertEqual(validate_output('qualification-ok',TOOLS),0)
if __name__=='__main__':unittest.main()
