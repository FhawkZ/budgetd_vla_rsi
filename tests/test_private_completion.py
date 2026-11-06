import unittest,tempfile,hashlib,subprocess,sys,json
from pathlib import Path
from skill_rsi_completion_supervisor import CompletionSupervisor,APIFailure
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def launch(self,mode='ok'):
  p=self.root/'factory.py';p.write_text('''import time,threading
from skill_rsi_completion import CompletionGate
class E(BaseException):pass
class B:
 def __init__(self):self.thread=threading.get_ident();self.closed=False;self.poisoned=False;self.report={'status':'ready'};self.task=self
 def observe(self):
  if MODE=='api_timeout':time.sleep(10)
  return {'ok':True}
 def close(self):self.closed=True
 def settle(self,t,n):
  if MODE=='settle_timeout':time.sleep(10)
  return 500
 def score(self,t):return True
 def task_spec(self):return {'instruction':'synthetic','roles':{}}
def build():return B(),{k:E for k in ['budget_exhausted','safety_stop','infrastructure_error']}
def completion_gate(b):return CompletionGate(b,OUTPUT,b.settle,b.score)
'''.replace('MODE',repr(mode)).replace('OUTPUT',repr(str(self.root/'private.json'))))
  return CompletionSupervisor(p,hashlib.sha256(p.read_bytes()).hexdigest(),self.root/'supervisor',call_seconds=.2,total_seconds=5)
 def child(self,code='pass',wait=True):
  p=subprocess.Popen([sys.executable,'-c',code]);self.addCleanup(lambda:p.poll() is None and (p.kill(),p.wait()))
  if wait:p.wait()
  return p
 def test_real_child_private_score(self):
  s=self.launch();self.assertEqual(s.dispatch('observe',{}),{'ok':True})
  a=s.complete_from_owner(self.child(),outcome='returned');self.assertEqual(a,{'status':'completion_recorded'})
  self.assertTrue(json.loads((self.root/'private.json').read_text())['success']);self.assertEqual(s.report['exit_code'],0)
  self.assertNotIn('success',(self.root/'supervisor/events.jsonl').read_text())
  with self.assertRaises(APIFailure):s.dispatch('observe',{})
 def test_public_control_denied(self):
  s=self.launch()
  with self.assertRaises(APIFailure):s.dispatch('complete',{})
  self.assertFalse((self.root/'private.json').exists())
 def test_running_child_denied(self):
  s=self.launch();p=self.child('import time;time.sleep(10)',False)
  with self.assertRaises(APIFailure):s.complete_from_owner(p,outcome='returned')
  self.assertFalse((self.root/'private.json').exists())
 def test_failed_child_denied(self):
  s=self.launch()
  with self.assertRaises(APIFailure):s.complete_from_owner(self.child('raise SystemExit(2)'),outcome='returned')
  self.assertFalse((self.root/'private.json').exists())
 def test_api_timeout_no_score(self):
  s=self.launch('api_timeout')
  with self.assertRaises(APIFailure):s.dispatch('observe',{})
  with self.assertRaises(APIFailure):s.complete_from_owner(self.child(),outcome='returned')
  self.assertFalse((self.root/'private.json').exists())
 def test_evaluation_timeout_kills_backend(self):
  s=self.launch('settle_timeout')
  with self.assertRaises(APIFailure):s.complete_from_owner(self.child(),outcome='returned')
  self.assertIsNotNone(s.process.poll());self.assertEqual(s.report['completion'],'unknown_or_refused')
  self.assertFalse((self.root/'private.json').exists())
 def test_render_error_denied(self):
  s=self.launch()
  with self.assertRaises(APIFailure):s.complete_from_owner(self.child(),outcome='returned',render_error=True)
  self.assertFalse((self.root/'private.json').exists())
if __name__=='__main__':unittest.main()
