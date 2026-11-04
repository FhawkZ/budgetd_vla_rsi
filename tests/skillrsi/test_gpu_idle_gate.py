import sys,pathlib,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/"scripts"))
from gpu_idle_gate import wait_idle,GPUUnavailable
class IdleGate(unittest.TestCase):
 def run_samples(self, samples):
  now=[0.0]; seen=[]; calls=[0]
  def read():
   i=min(calls[0],len(samples)-1);calls[0]+=1;return dict(index=1,memory_mib=0,processes=[],**samples[i])
  def sleep(t):now[0]+=t
  result=wait_idle(read,seen.append,timeout=1,clock=lambda:now[0],sleep=sleep)
  return result,seen,now[0]
 def test_trailing_utilization_then_idle(self):
  r,s,t=self.run_samples([dict(utilization=5),dict(utilization=0)])
  self.assertEqual((r['utilization'],len(s),t),(0,2,.5))
 def test_idle_no_delay(self):self.assertEqual(self.run_samples([dict(utilization=0)])[2],0)
 def test_never_idle_refused(self):
  with self.assertRaises(GPUUnavailable):self.run_samples([dict(utilization=5)])
 def test_process_never_waited_or_stopped(self):
  slept=[]
  with self.assertRaises(GPUUnavailable):wait_idle(lambda:dict(memory_mib=0,processes=['other'],utilization=0),lambda x:None,sleep=slept.append)
  self.assertEqual(slept,[])
 def test_memory_never_waited(self):
  with self.assertRaises(GPUUnavailable):wait_idle(lambda:dict(memory_mib=128,processes=[],utilization=0),lambda x:None)
 def test_read_error_propagates(self):
  def fail():raise OSError('nvidia unavailable')
  with self.assertRaises(OSError):wait_idle(fail,lambda x:None)
if __name__=='__main__':unittest.main()
