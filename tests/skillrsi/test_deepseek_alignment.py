import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import skill_rsi_deepseek_bridge as b
from run_skill_rsi_deepseek_pair import invalid


class Adapter:
    cfg={'model':'deepseek-flash','base_url':'https://api.deepseek.com',
         'params':{'temperature':0,'max_tokens':32768},'structured_output':'json_object'}
    def __init__(self,fail=False):self.calls=0;self.fail=fail
    def caller(self,wd,prompt,schema,timeout,log,tag):
        self.calls+=1;self.prompt=prompt
        if self.fail:return {'status':'cli_error','input_tokens':None,'output_tokens':None}
        return {'status':'ok','raw_response':'{}','input_tokens':10,'output_tokens':2,'finish_reason':'stop'}


class Tests(unittest.TestCase):
    def test_shared_reservation_cap_and_no_reclaim(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'l'
            b.reserve(p,100,32768,1,2)
            with self.assertRaises(RuntimeError):b.reserve(p,100,32768,1,2)
            self.assertEqual(len(p.read_text().splitlines()),1)

    def test_money_and_request_limits_before_network(self):
        with tempfile.TemporaryDirectory() as t:
            for size,cap,exc in [(100,.001,RuntimeError),(200001,2,ValueError)]:
                with self.assertRaises(exc):b.reserve(Path(t)/str(size),size,32768,12,cap)

    def make(self,t,ad):
        fmt={'fill':lambda template,x:x['context'],'render':lambda x:json.dumps(x)}
        with patch.object(b,'checked',return_value='template'),patch.object(b,'pure_functions',return_value=fmt):
            return b.DeepSeekBroker(t,{'decisions_max':4},Path(t)/'calls',adapter=ad)

    def context(self):
        return {'task_spec':{'instruction':'public','criterion_source':'original supplied code'},
                'skill_md':'published','atoms':['a'],'history':[],
                'decisions_used':0,'decisions_max':4,'calls_remaining':90}

    def test_preserves_original_task_spec_and_records_usage(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'RSI_DEEPSEEK_LEDGER':t+'/l',
                          'RSI_DEEPSEEK_MAX_CALLS':'12','RSI_DEEPSEEK_USD_CAP':'2'}):
            ad=Adapter();broker=self.make(t,ad);ctx=self.context()
            rec=broker.decide(ctx,'source',0)
            self.assertEqual(json.loads(ad.prompt),ctx)
            self.assertEqual(rec['output_tokens'],2)
            self.assertEqual(ad.calls,1)
            self.assertTrue((Path(t)/'calls/001-receipt.json').exists())

    def test_failed_call_consumed_once_no_retry(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'RSI_DEEPSEEK_LEDGER':t+'/l',
                          'RSI_DEEPSEEK_MAX_CALLS':'12','RSI_DEEPSEEK_USD_CAP':'2'}):
            ad=Adapter(True);broker=self.make(t,ad)
            with self.assertRaises(RuntimeError):broker.decide(self.context(),'source',0)
            self.assertEqual(ad.calls,1)
            self.assertEqual(broker.calls,1)
            self.assertEqual(len(Path(t+'/l').read_text().splitlines()),1)

    def test_audit_captures_body_not_authorization(self):
        import urllib.request
        request=urllib.request.Request('https://api.deepseek.com/chat/completions',
                       data=b'{"model":"deepseek-flash"}',headers={'Authorization':'Bearer SECRET'})
        module=types.SimpleNamespace(urllib=types.SimpleNamespace(request=types.SimpleNamespace(
                          urlopen=lambda *a,**k:io.BytesIO(b'{"usage":{}}'))))
        with tempfile.TemporaryDirectory() as t:
            with b.capture_http(module,Path(t)):
                with module.urllib.request.urlopen(request) as r:self.assertEqual(json.load(r),{'usage':{}})
            self.assertTrue(all('SECRET' not in p.read_text() for p in Path(t).iterdir()))

    def test_invalid_requires_native_preactive_receipts(self):
        r={'infra_reason':'setup:UnStableError:x','setup_attempts':1,'setup_completed':0,
           'seed':7,'primitive_calls':0,'deepseek_calls':0,'vla_calls':0,'clip_assignments':0}
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'setup.jsonl').write_text('\n'.join(json.dumps({'event':x,'seed':7}) for x in ['enter','raised']))
            self.assertTrue(invalid(r,p,0,[]))
            for k in ['primitive_calls','deepseek_calls','clip_assignments']:
                self.assertFalse(invalid(dict(r,**{k:1}),p,0,[]))
            self.assertFalse(invalid(r,p,1,[]))
            self.assertFalse(invalid(r,p,0,['render_error']))


if __name__=='__main__':unittest.main()
