import json,sys,unittest
from pathlib import Path
from urllib.request import Request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rpent_action_wait import ActionWaitOpener
class TestActionWait(unittest.TestCase):
    def test_only_action_wait_changes(self):
        calls=[];answer=object()
        def delegate(req,**kw):calls.append((req,kw));return answer
        opener=ActionWaitOpener(delegate)
        for method,expected in [('env.step',None),('env.chunk_step',None),('env.reset',600),('env.get_state',600)]:
            req=Request('http://127.0.0.1/call',data=json.dumps({'method':method}).encode())
            self.assertIs(opener.open(req,timeout=600),answer)
            self.assertIs(calls[-1][0],req)
            self.assertEqual(calls[-1][1],{'timeout':expected})
        self.assertEqual(len(calls),4)
if __name__=='__main__':unittest.main()
