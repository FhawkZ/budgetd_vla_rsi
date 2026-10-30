import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from budget_proxy30b import adapt
class CandidateRouting(unittest.TestCase):
 def body(self):return dict(model='qwen3-vl-30b-a3b-instruct',max_tokens=1024,messages=[dict(role='user',content=[dict(type='text',text='keep exactly')]+[dict(type='image_url',image_url=dict(url='data:image/png;base64,'+str(i))) for i in range(5)])])
 def test_transport_retains_last_three_and_all_text_without_mutation(self):
  b=self.body();original=copy.deepcopy(b);out,audit=adapt(b)
  self.assertEqual(b,original);self.assertEqual(audit['images_after'],3)
  self.assertEqual(out['messages'][0]['content'][0],b['messages'][0]['content'][0])
  self.assertEqual(out['messages'][0]['content'][-3:],b['messages'][0]['content'][-3:])
  self.assertEqual(len(audit['omitted_image_sha256']),2)
 def test_8b_identity_and_excess_budget_rejected(self):
  for key,value in [('model','qwen3-vl-8b-instruct'),('max_tokens',1025)]:
   b=self.body();b[key]=value
   with self.assertRaises(AssertionError):adapt(b)
 def test_remote_image_rejected(self):
  b=self.body();b['messages'][0]['content'][-1]['image_url']['url']='https://example.com/a.png'
  with self.assertRaises(AssertionError):adapt(b)
if __name__=='__main__':unittest.main()
