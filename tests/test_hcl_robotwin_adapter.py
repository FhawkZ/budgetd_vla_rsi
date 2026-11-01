import copy, unittest
from hcl_robotwin_adapter import pair_metrics

def rows():
 return [{'task':t,'seed':i,'status':'completed','native_eval_success':v,'initial_robot_state':{'x':[1.]},'initial_image_sha256':{'head':'same'},'native_task_language':t} for t,vs in [('new',[False,True]),('old',[True,False])] for i,v in enumerate(vs)]
class PairMetricsTests(unittest.TestCase):
 def metric(self,b,c):return pair_metrics(b,c,'new',['old'],[(x['task'],x['seed']) for x in b],behavior_changed=True)
 def test_paired_forgetting_not_net_rate(self):
  b=rows();c=copy.deepcopy(b);c[0]['native_eval_success']=True;c[2]['native_eval_success']=False;c[3]['native_eval_success']=True
  a,r=self.metric(b,c);self.assertEqual(a['current_task_metrics']['correct'],1);self.assertEqual(r['current_task_metrics']['correct'],2);self.assertEqual(r['historical_anchor_metrics']['forget_count'],1);self.assertEqual(r['historical_anchor_metrics']['recovered_count'],1)
 def test_censoring_not_failure(self):
  b=rows();c=copy.deepcopy(b);c[0]['native_eval_success']=None
  with self.assertRaisesRegex(ValueError,'censored'):self.metric(b,c)
 def test_missing_and_duplicate(self):
  b=rows()
  for c in (b[:-1],b+[b[0]]):
   with self.assertRaises(ValueError):self.metric(b,c)
 def test_pair_contract(self):
  b=rows();c=copy.deepcopy(b);c[1]['native_task_language']='changed'
  with self.assertRaisesRegex(ValueError,'mismatch'):self.metric(b,c)
