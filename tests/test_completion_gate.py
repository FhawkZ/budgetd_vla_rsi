import unittest,tempfile,threading,json
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from skill_rsi_completion import CompletionGate,OwnerCompletion
from skill_rsi_skill_ipc import FIELDS
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'private.json';self.events=[];self.now=0
  self.s=SimpleNamespace(thread=threading.get_ident(),closed=False,poisoned=False,report={'status':'ready'},task=object())
  self.receipt=OwnerCompletion(0,False,False,False,False,False,'returned')
 def gate(self,score=False,settle=None):
  return CompletionGate(self.s,self.path,settle or (lambda t,n:(self.events.append(('settle',n)),500)[1]),lambda t:(self.events.append(('score',)),score)[1],lambda:self.now)
 def test_native_false_and_order_private(self):
  ack=self.gate(False).finish(self.receipt,5);self.assertEqual(self.events,[('settle',2),('score',)]);self.assertNotIn('success',ack);self.assertIs(json.loads(self.path.read_text())['success'],False)
 def test_success_not_policy_boolean(self):
  self.gate(True).finish(self.receipt,5);self.assertIs(json.loads(self.path.read_text())['success'],True)
 def test_no_public_evaluation(self):self.assertTrue({'finish','evaluate','check_success','settle'}.isdisjoint(FIELDS))
 def test_bad_receipts_no_calls(self):
  for field,value in [('pending_api',True),('child_alive',True),('transport_failed',True),('deadline_exceeded',True),('render_error',True),('child_exit_code',1),('outcome','unknown')]:
   with self.subTest(field=field):
    self.s.poisoned=False;self.path.unlink(missing_ok=True)
    with self.assertRaises(ValueError):self.gate().finish(replace(self.receipt,**{field:value}),5)
    self.assertEqual(self.events,[])
 def test_settle_error_no_score_or_retry(self):
  def settle(t,n):self.events.append(('settle',n));raise RuntimeError('native safety')
  g=self.gate(settle=settle)
  with self.assertRaises(RuntimeError):g.finish(self.receipt,5)
  with self.assertRaises(RuntimeError):g.finish(self.receipt,5)
  self.assertEqual(self.events,[('settle',2)]);self.assertIsNone(json.loads(self.path.read_text())['success'])
 def test_deadline_after_settle(self):
  def settle(t,n):self.now=6;return 500
  with self.assertRaises(TimeoutError):self.gate(settle=settle).finish(self.receipt,5)
  self.assertEqual(self.events,[])
 def test_poisoned_or_wrong_thread(self):
  self.s.thread=-1
  with self.assertRaises(ValueError):self.gate().finish(self.receipt,5)
  self.assertEqual(self.events,[])
 def test_candidate_dict_refused(self):
  with self.assertRaises(ValueError):self.gate().finish(self.receipt.__dict__,5)
  self.assertEqual(self.events,[])
if __name__=='__main__':unittest.main()
