import unittest,sys,subprocess
from skill_rsi_owner_accounting import BoundSkill,ActiveWall,CodeLineBudget,ExecutionBudget
class Tests(unittest.TestCase):
 def child(self):
  p=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.readline()'],stdin=subprocess.PIPE)
  self.addCleanup(lambda:p.poll() is None and (p.kill(),p.wait()))
  self.addCleanup(p.stdin.close)
  return p
 def test_bound_real_child(self):
  p=self.child();b=BoundSkill(p,'run','src');p.stdin.write(b'\n');p.stdin.flush();p.wait();self.assertEqual(b.consume(p,'run','src')['exit_code'],0)
  with self.assertRaises(RuntimeError):b.consume(p,'run','src')
 def test_other_process_not_substitute(self):
  p=self.child();q=self.child();b=BoundSkill(p,'run','src')
  with self.assertRaises(ValueError):b.consume(q,'run','src')
 def test_active_and_mismatched_source(self):
  for source in ['src','other']:
   p=self.child();b=BoundSkill(p,'run','src')
   with self.assertRaises(ValueError):b.consume(p,'run',source)
 def test_wall_pause_accumulates(self):
  now=[0];w=ActiveWall(4,lambda:now[0]);w.start();now[0]=2;w.pause();now[0]=100;w.start();now[0]=102
  with self.assertRaises(ExecutionBudget):w.pause()
  self.assertEqual(w.spent,4)
  with self.assertRaises(ExecutionBudget):w.start()
 def test_wall_no_nesting_or_invalid(self):
  for x in [float('inf'),float('nan'),0,-1,True]:
   with self.assertRaises(ValueError):ActiveWall(x)
  w=ActiveWall();w.start()
  with self.assertRaises(RuntimeError):w.start()
 def test_lines_cumulative_and_trace_restored(self):
  scope={};exec(compile('def f():\n x=1\n return x\n','<skills>','exec'),scope);b=CodeLineBudget(3)
  old=sys.gettrace();self.assertEqual(b.run(scope['f']),1)
  with self.assertRaises(ExecutionBudget):b.run(scope['f'])
  self.assertIs(sys.gettrace(),old);self.assertEqual(b.n,4)
 def test_unrelated_lines_excluded(self):
  b=CodeLineBudget(1);self.assertEqual(b.run(lambda:1),1);self.assertEqual(b.n,0)
if __name__=='__main__':unittest.main()
