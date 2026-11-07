import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import skill_rsi_deepseek_reuse_bridge as b


class Tests(unittest.TestCase):
    def test_original_bmin_twelve_then_stop(self):
        class Adapter:
            cfg={'model':'deepseek-flash','base_url':'https://api.deepseek.com',
                 'params':{'temperature':0,'max_tokens':32768},'structured_output':'json_object'}
            calls=0
            def caller(self,*a):
                self.calls+=1
                return {'status':'ok','raw_response':'{}','input_tokens':10,'output_tokens':2,'finish_reason':'stop'}
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'RSI_DEEPSEEK_LEDGER':t+'/l',
                                'RSI_DEEPSEEK_MAX_CALLS':'180','RSI_DEEPSEEK_USD_CAP':'8'}):
            ad=Adapter()
            with patch.object(b,'checked',return_value='x'),patch.object(b,'pure_functions',return_value={
                'fill':lambda t,x:x['context'],'render':json.dumps}):
                broker=b.DeepSeekReuseBroker(t,{'decisions_max':12},Path(t)/'calls',adapter=ad)
            ctx={'task_spec':{},'skill_md':'x','atoms':['a'],'history':[],
                 'decisions_used':0,'decisions_max':12,'calls_remaining':90}
            for i in range(12):broker.decide(ctx,'s',i)
            with self.assertRaises(RuntimeError):broker.decide(ctx,'s',12)
            self.assertEqual(ad.calls,12)
            self.assertEqual(len(Path(t+'/l').read_text().splitlines()),12)

    def test_bmin_rejects_old_four_decision_config(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):b.DeepSeekReuseBroker(t,{'decisions_max':4},Path(t)/'calls')


if __name__=='__main__':unittest.main()
