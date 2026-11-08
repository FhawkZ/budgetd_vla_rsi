import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deepseek_audited_provider_v2 import reserve,settle,budget_state,decoded_headers

class SettlementTest(unittest.TestCase):
    def test_settlement_and_unknown_hold(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ledger';reserve(p,b'x'*1000000,8192,3,.5)
            with self.assertRaises(RuntimeError):reserve(p,b'x'*1000000,8192,3,.5)
            settle(p,1,dict(prompt_tokens=1000,completion_tokens=200,prompt_cache_hit_tokens=900))
            reserve(p,b'x'*1000000,8192,3,.5);settle(p,2,None)
            self.assertGreater(budget_state([json.loads(x) for x in p.read_text().splitlines()])[1],.3)
            with self.assertRaises(RuntimeError):reserve(p,b'x'*1000000,8192,3,.5)
            with self.assertRaises(ValueError):settle(p,1,dict(prompt_tokens=1,completion_tokens=1))
    def test_decode_headers(self):
        self.assertEqual(decoded_headers({'content-encoding':'zstd','content-length':'1','content-type':'text/event-stream'}),{'content-type':'text/event-stream'})

if __name__=='__main__':unittest.main()
