import copy,json,tempfile,unittest
from unittest.mock import patch
from stage_client_adapter import StageBinding
from test_stage_program import P,observation
class Response:
 def __init__(self,data):self.data=json.dumps(data).encode()
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,*args):return self.data
class Tests(unittest.TestCase):
 def test_current_images_schema_and_transition_change_real_language(self):
  with tempfile.TemporaryDirectory() as d:
   b=StageBinding(P,'handover_block','successor_aware',d,'fixed-qwen',lambda s:12);o=observation();seen=[];requests=[]
   def http(req,**kwargs):
    body=json.loads(req.data);requests.append(body);sc=body['tools'][0]['function']['parameters'];decision={'frame_sha256':sc['properties']['frame_sha256']['enum'][0],'stage_index':0,'completed':'yes','successor_ready':'yes','evidence':'fixture only'}
    self.assertNotIn('scorer',json.dumps(body));self.assertNotIn('left_gripper',json.dumps(body));self.assertEqual(sum(x['type']=='image_url' for x in body['messages'][1]['content']),3)
    return Response({'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'assess_boundary','arguments':json.dumps(decision)}}]}}],'usage':{'prompt_tokens':1,'completion_tokens':1}})
   with patch('urllib.request.urlopen',side_effect=http):
    for _ in range(4):b.infer(lambda x:seen.append(x['task_language']),o)
   self.assertEqual(len(requests),1);self.assertEqual(seen[0],seen[1]);self.assertNotEqual(seen[1],seen[2]);self.assertEqual(b.qwen_calls,1);self.assertEqual(b.controller.stage_index,1)
 def test_failed_call_is_counted_and_no_vla_after_failure(self):
  with tempfile.TemporaryDirectory() as d:
   b=StageBinding(P,'handover_block','successor_aware',d,'fixed',lambda s:12);o=observation()
   for _ in range(2):b.infer(lambda x:None,o)
   with patch('urllib.request.urlopen',side_effect=TimeoutError('fixture')):
    with self.assertRaises(TimeoutError):b.infer(lambda x:self.fail('VLA after failure'),o)
   self.assertEqual(b.qwen_calls,1);self.assertEqual(b.vla_calls,2)
if __name__=='__main__':unittest.main()
