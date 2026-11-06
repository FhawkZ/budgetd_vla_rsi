import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from run_skill_rsi_published_owner import run_owner, validate_native_config, native_factory_text
from skill_rsi_owner_accounting import BoundSkill

UP = Path(os.environ['RSI_RUNTIME_ROOT'])/'vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4/runtime'
SOURCE = '''ATOMS = ["read"]
def read(api, args):
    return api.observe()
def fallback(api):
    value = read(api, {})
    return {"status": "done", "failure_code": None, "observed": value}
'''

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
    def factory(self, mode):
        p = self.root/'factory.py'
        p.write_text('''import time,threading,subprocess,sys,os
from pathlib import Path
from skill_rsi_completion import CompletionGate
class E(BaseException):pass
class B:
 def __init__(self):
  self.thread=threading.get_ident();self.closed=False;self.poisoned=False;self.report={'status':'ready'};self.task=self
 def observe(self):
  if MODE=='hang_child':
   p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
   Path(CHILD).write_text(str(p.pid));time.sleep(60)
  if MODE=='render_api':os.write(2,b'OptiX Error: injected CPU fixture\\n')
  if MODE=='native_error':raise E('synthetic')
  return {'ok':False,'value':17}
 def task_spec(self):return {'instruction':'synthetic','roles':{}}
 def close(self):self.closed=True
 def settle(self,t,seconds):
  if MODE=='settle_hang':time.sleep(60)
  return 500
 def score(self,t):return True
def build():
 if MODE=='render_init':
  os.write(2,b'VK_ERROR_DEVICE_LOST injected CPU fixture\\n');time.sleep(60)
 return B(),{k:E for k in ['budget_exhausted','safety_stop','infrastructure_error']}
def completion_gate(b):return CompletionGate(b,PRIVATE,b.settle,b.score)
'''.replace('MODE',repr(mode)).replace('CHILD',repr(str(self.root/'descendant.pid'))).replace('PRIVATE',repr(str(self.root/'private.json'))))
        return p
    def run_case(self, mode='ok', source=SOURCE, **kwargs):
        p=self.factory(mode)
        row=run_owner(source=source,upstream=UP,factory=p,
            factory_sha=hashlib.sha256(p.read_bytes()).hexdigest(),output=self.root/'run',
            run_id='cpu-fixture',wall_seconds=kwargs.pop('wall_seconds',3),
            startup_seconds=1,api_seconds=kwargs.pop('api_seconds',2),completion_seconds=.2,**kwargs)
        self.assertFalse(row['accepted_update'])
        for info in [row.get('skill_cleanup'),row.get('backend',{}).get('cleanup')]:
            if info:self.assertEqual(info['live_remaining'],[])
        return row
    def test_normal_identity_false_api_and_private_score(self):
        r=self.run_case()
        self.assertEqual(r['status'],'completed_private',r)
        self.assertEqual(r['receipt']['pid'],r['skill_identity']['pid'])
        self.assertFalse(r['terminal']['value']['observed']['ok'])
        self.assertTrue(json.loads((self.root/'private.json').read_text())['success'])
        self.assertNotIn('success',(self.root/'run/events.jsonl').read_text())
        self.assertGreater(r['terminal']['code_lines'],0)
    def test_identity_refusal_prevents_scoring(self):
        with patch.object(BoundSkill,'consume',side_effect=ValueError('identity mismatch')):
            r=self.run_case()
        self.assertNotEqual(r['status'],'completed_private')
        self.assertFalse((self.root/'private.json').exists())
    def test_abnormal_skill_exit_no_score(self):
        r=self.run_case(source='ATOMS=[]\ndef fallback(api):\n    return 1/0\n')
        self.assertNotEqual(r['status'],'completed_private')
        self.assertFalse((self.root/'private.json').exists())
    def test_cumulative_line_budget_refuses(self):
        r=self.run_case(code_lines=2)
        self.assertNotEqual(r['status'],'completed_private')
        self.assertFalse((self.root/'private.json').exists())
    def test_hard_wall_cleans_inherited_descendant(self):
        r=self.run_case('hang_child',wall_seconds=1.2,api_seconds=2)
        self.assertLess(r['elapsed'],4)
        self.assertNotEqual(r['status'],'completed_private')
        self.assertFalse((self.root/'private.json').exists())
        pid=int((self.root/'descendant.pid').read_text())
        p=Path('/proc')/str(pid)/'stat'
        self.assertTrue(not p.exists() or p.read_text().rsplit(')',1)[1].split()[0]=='Z')
    def test_render_init_no_score(self):
        r=self.run_case('render_init')
        self.assertLess(r['elapsed'],3)
        self.assertFalse((self.root/'private.json').exists())
        backend=json.loads((self.root/'run/backend/report.json').read_text())
        self.assertEqual(backend['render_error'],'VK_ERROR_DEVICE_LOST')
        self.assertEqual(backend['cleanup']['live_remaining'],[])
    def test_render_api_no_score(self):
        r=self.run_case('render_api')
        self.assertNotEqual(r['status'],'completed_private')
        self.assertFalse((self.root/'private.json').exists())
    def test_settle_hang_no_score(self):
        r=self.run_case('settle_hang')
        self.assertNotEqual(r['status'],'completed_private')
        self.assertFalse((self.root/'private.json').exists())
    def test_native_exception_no_retry(self):
        r=self.run_case('native_error')
        self.assertEqual(r['api_attempts'],1)
        self.assertFalse((self.root/'private.json').exists())
    def test_config_fail_closed(self):
        p=self.root/'config.json';p.write_text('{"status":"DRAFT"}')
        with self.assertRaises(ValueError):validate_native_config(p,'0'*64)
        with self.assertRaises(ValueError):validate_native_config(p,hashlib.sha256(p.read_bytes()).hexdigest())
    def test_factory_wires_native_private_gate_without_importing_native(self):
        import threading
        from types import SimpleNamespace
        from skill_rsi_completion import OwnerCompletion
        private=self.root/'native-private.json';log=self.root/'native.log';log.write_text('')
        text=native_factory_text('/p','sha',private,log)
        ns={};exec(compile(text,'<trusted-factory>','exec'),ns)
        events=[]
        task=SimpleNamespace(check_success=lambda:events.append('score') or True)
        b=SimpleNamespace(thread=threading.get_ident(),closed=False,poisoned=False,
            report={'status':'ready'},task=task,hooks=SimpleNamespace(env=SimpleNamespace(
                settle=lambda t,n:events.append(('settle',n)) or 500)))
        with patch.dict(ns,build_native=lambda p,s: (b,(p,s))):
            self.assertEqual(ns['build']()[1],('/p','sha'))
        gate=ns['completion_gate'](b)
        ack=gate.finish(OwnerCompletion(0,False,False,False,False,False,'returned'),time.monotonic()+1)
        self.assertEqual(events,[('settle',2),'score'])
        self.assertEqual(ack,{'status':'completion_recorded'})
        self.assertTrue(json.loads(private.read_text())['success'])
    def test_declared_native_config_requires_all_source_pins(self):
        root=self.root/'vendor';(root/'runtime').mkdir(parents=True)
        pkg=root/'frozen_skills/pkg';pkg.mkdir(parents=True)
        for name in ['skills.py','perception.py']:(pkg/name).write_text('')
        c={'status':'FROZEN_NATIVE_ISOLATED','source_class':'published','gpu':3,
           'limits':{'wall_seconds':240,'code_lines':30000,'primitive_budget':90,'sim_seconds':90,'settle_seconds':2},
           'output':'/root/autodl-tmp/qian/Dex_runtime/agent-rsi-migration-20261105/outputs/future/backend',
           'owner_output':'/root/autodl-tmp/qian/Dex_runtime/agent-rsi-migration-20261105/outputs/future/owner',
           'upstream':str(root/'runtime'),'skills_file':str(pkg/'skills.py'),
           'perception_file':str(pkg/'perception.py'),'source_sha256':{}}
        p=self.root/'config.json';p.write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError,'missing owner source pin'):
            validate_native_config(p,hashlib.sha256(p.read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
