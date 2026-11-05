import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from skill_rsi_api_supervisor import APISupervisor, APIFailure

VENDOR=Path('/root/autodl-tmp/Dex_runtime/agent-rsi/vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4/runtime')
PINS={'common.py':'74f8ea355b0356c40ec1225505257ac4d75c641d73b1d85c2911cd42c4d9aeba',
      'envadapter.py':'96e60a0ea1dfd7949fb845a94b5f1076489be7047e7fb539f54ce52e8c025119'}


def native_classes():
    parts=[]
    for file,sha in PINS.items():
        source=(VENDOR/file).read_bytes()
        assert hashlib.sha256(source).hexdigest()==sha
        text=source.decode()
        for node in ast.parse(text).body:
            if isinstance(node,ast.ClassDef) and node.name in {'InfraFailure','SafetyStop','BudgetExhausted'}:
                parts.append(ast.get_source_segment(text,node))
    return '\n\n'.join(parts)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.definitions=native_classes()
    def tearDown(self):self.tmp.cleanup()
    def factory(self,body,build_prefix=''):
        p=self.root/'factory.py'
        p.write_text('import os,time,threading\n'+self.definitions+'\n'+body+'\n'
          'def build():\n'+('    '+build_prefix+'\n' if build_prefix else '')+
          '    return Backend(), {"budget_exhausted":BudgetExhausted,"safety_stop":SafetyStop,"infrastructure_error":InfraFailure}\n')
        return p,hashlib.sha256(p.read_bytes()).hexdigest()
    def launch(self,body,**opts):
        p,sha=self.factory(body)
        return APISupervisor(p,sha,self.root/'out',**opts)
    def test_state_thread_projection_and_false(self):
        with self.launch('''class Backend:
    def __init__(self):self.i=0;self.t=threading.get_ident()
    def task_spec(self):return {'instruction':'public','roles':{},'criterion_source':'SECRET'}
    def observe(self):
        self.i+=1
        return {'i':self.i,'same_thread':self.t==threading.get_ident()}
    def move_pose(self,arm,pose):return False
''') as s:
            self.assertEqual(s.dispatch('task_spec',{}),{'instruction':'public','roles':{}})
            self.assertEqual(s.dispatch('observe',{}),{'i':1,'same_thread':True})
            self.assertEqual(s.dispatch('observe',{}),{'i':2,'same_thread':True})
            self.assertIs(s.dispatch('move_pose',{'arm':'left','pose':[0]*7}),False)
        self.assertEqual(s.report['exit_code'],0)
        self.assertNotIn('SECRET',(self.root/'out/events.jsonl').read_text())
    def test_exact_native_baseexception_mapping(self):
        for cls,status in [('BudgetExhausted','budget_exhausted'),('SafetyStop','safety_stop'),('InfraFailure','infrastructure_error')]:
            with self.subTest(cls=cls):
                p,sha=self.factory(f'class Backend:\n    def observe(self):raise {cls}("secret evaluator detail")\n')
                with APISupervisor(p,sha,self.root/cls) as s:
                    with self.assertRaises(APIFailure) as caught:s.dispatch('observe',{})
                    self.assertEqual(caught.exception.status,status)
                    self.assertTrue(s.closed)
                    self.assertEqual(s.report['pending_outcome'],'exception_returned')
                self.assertNotIn('secret evaluator',(self.root/cls/'events.jsonl').read_text())
    def test_same_name_is_not_native_type(self):
        p,sha=self.factory('class Backend:\n    def observe(self):\n        Other=type("SafetyStop",(Exception,),{})\n        raise Other("cuda error")\n')
        with APISupervisor(p,sha,self.root/'other') as s:
            with self.assertRaises(APIFailure) as caught:s.dispatch('observe',{})
            self.assertEqual(caught.exception.status,'native_error')
    def test_timeout_unknown_no_retry_cleanup(self):
        started=time.monotonic()
        with self.launch('class Backend:\n    def wait(self,seconds):time.sleep(20)\n',call_seconds=.15) as s:
            with self.assertRaises(APIFailure) as caught:s.dispatch('wait',{'seconds':1})
            self.assertEqual(caught.exception.status,'api_timeout')
            self.assertEqual(s.report['pending_outcome'],'unknown')
            self.assertIsNotNone(s.process.poll())
            with self.assertRaises(APIFailure):s.dispatch('observe',{})
            self.assertEqual(s.report['dispatches'],1)
        self.assertLess(time.monotonic()-started,3)
    def test_init_deadline_and_crash(self):
        for prefix,status in [('time.sleep(20)','initialization_timeout'),('os._exit(7)','initialization_error')]:
            p,sha=self.factory('class Backend:pass',prefix)
            out=self.root/status
            with self.assertRaises(APIFailure):APISupervisor(p,sha,out,startup_seconds=.15)
            report=json.loads((out/'report.json').read_text())
            self.assertEqual(report['status'],status)
            self.assertIsNotNone(report['exit_code'])
    def test_dispatch_crash_is_not_false(self):
        with self.launch('class Backend:\n    def observe(self):os._exit(7)\n') as s:
            with self.assertRaises(APIFailure) as caught:s.dispatch('observe',{})
            self.assertEqual(caught.exception.status,'transport_error')
            self.assertEqual(s.report['pending_outcome'],'unknown')
            self.assertEqual(s.report['exit_code'],7)
    def test_preflight_and_request_budget(self):
        with self.launch('class Backend:\n    def observe(self):return True\n',max_requests=1) as s:
            self.assertTrue(s.dispatch('observe',{}))
            with self.assertRaises(APIFailure):s.dispatch('observe',{})
            self.assertEqual(s.report['dispatches'],1)
        p,sha=self.factory('class Backend:pass')
        with APISupervisor(p,sha,self.root/'reject') as s:
            with self.assertRaises(APIFailure):s.dispatch('check_success',{})
            self.assertEqual(s.report['dispatches'],0)
    def test_output_denial_and_hash_tamper(self):
        with self.launch('class Backend:\n    def observe(self):return {"scorer":"SECRET"}\n') as s:
            with self.assertRaises(APIFailure):s.dispatch('observe',{})
        self.assertNotIn('SECRET',(self.root/'out/events.jsonl').read_text())
        p,sha=self.factory('class Backend:pass')
        p.write_text('raise RuntimeError("tampered")')
        with self.assertRaises(ValueError):APISupervisor(p,sha,self.root/'tamper')

if __name__=='__main__':unittest.main()
