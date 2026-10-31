import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_phase_trace import wrap
class Tests(unittest.TestCase):
 def test_identity_counts_and_exceptions(self):
  token=object();err=ValueError('original');seen=[];events=[]
  class Example:
   def method(self,arg,*,fail=False):
    seen.append(arg)
    if fail:raise err
    return token
  original=wrap(Example,'method',events.append);o=Example()
  self.assertIs(o.method(3),token)
  try:o.method(4,fail=True)
  except ValueError as caught:self.assertIs(caught,err)
  self.assertEqual(seen,[3,4]);self.assertEqual([x['event'] for x in events],['enter','exit','enter','error'])
  self.assertEqual([x['phase'] for x in events],['Example.method']*4)
if __name__=='__main__':unittest.main()
