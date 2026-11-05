import hashlib,json,os,tempfile,threading,time,unittest,shutil
from pathlib import Path
from skill_rsi_native_lifecycle import NativeSession,IsolatedDetect,NativeBudget,NativeInfrastructure,build_native
from skill_rsi_api_supervisor import APISupervisor,APIFailure
from skill_rsi_skill_ipc import PublicAPI,run_skill
from native_lifecycle_fixture import FakeHooks,CONFIG,PERCEPTION,Infrastructure
UPSTREAM=Path(os.environ['RSI_RUNTIME_ROOT'])/'vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4/runtime'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
class LifecycleTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):
  if os.environ.get('RSI_TEST_EVIDENCE'):
   dest=Path(os.environ['RSI_TEST_EVIDENCE'])/self._testMethodName
   shutil.copytree(self.root,dest)
  self.temp.cleanup()
 def session(self,mode='ok'):
  h=FakeHooks(mode);b=NativeSession(CONFIG,h,self.root/'backend',lambda *a:([],.74));return b,h
 def test_same_thread_lifecycle_projection_false_and_no_score(self):
  b,h=self.session();a=PublicAPI(b);spec=a.dispatch('task_spec',{});self.assertEqual(set(spec),{'instruction','roles'});self.assertNotIn('SECRET',json.dumps(spec));self.assertIs(a.dispatch('move_pose',{'arm':'left','pose':[0,0,0,1,0,0,0]}),False)
  b.close();b.close();self.assertEqual(h.task.closed,1);self.assertEqual(h.task.scored,0);self.assertTrue(h.restored);self.assertEqual(len({e['thread'] for e in b.events}),1)
 def test_setup_error_once_without_hidden_retry(self):
  h=FakeHooks('setup_error')
  with self.assertRaises(Infrastructure):NativeSession(CONFIG,h,self.root/'backend',None)
  self.assertEqual(len([x for x in h.calls if isinstance(x,tuple)]),1);self.assertTrue(h.restored);self.assertEqual(h.task.closed,0)
 def test_monitor_failure_closes_returned_task(self):
  h=FakeHooks('monitor_error')
  with self.assertRaises(Infrastructure):NativeSession(CONFIG,h,self.root/'backend',None)
  self.assertEqual(h.task.closed,1);self.assertTrue(h.restored)
 def test_native_timeout_mapping_and_no_second_call(self):
  b,h=self.session('sim_timeout')
  with self.assertRaises(NativeBudget) as ctx:b.wait(seconds=1)
  self.assertEqual(str(ctx.exception),'native_sim_timeout')
  with self.assertRaises(NativeInfrastructure):b.wait(seconds=1)
  self.assertEqual(h.calls.count('wait'),1);b.close();self.assertEqual(h.task.scored,0)
 def test_error_name_does_not_drive_classification(self):
  b,h=self.session('unknown')
  with self.assertRaises(NativeInfrastructure) as ctx:b.wait(seconds=1)
  self.assertEqual(str(ctx.exception),'unmapped_native_exception');b.close()
 def test_wrong_thread_has_no_backend_call(self):
  b,h=self.session();errors=[]
  def wrong():
   try:b.wait(seconds=1)
   except BaseException as e:errors.append(e)
  t=threading.Thread(target=wrong);t.start();t.join();self.assertEqual(len(errors),1);self.assertEqual(h.calls.count('wait'),0);b.close()
 def test_perception_incomplete_cannot_be_swallowed_as_detect_failure(self):
  seen=[]
  def invoke(*args,**kw):seen.append((args,kw));return {'status':'rejected_or_error','exit_code':-9}
  detect=IsolatedDetect(PERCEPTION,UPSTREAM,self.root,invoke=invoke)
  with self.assertRaises(NativeInfrastructure):detect('rgb','depth',{'K':'cal'})
  self.assertEqual(seen[0][0][:4],(PERCEPTION,'rgb','depth',{'K':'cal'}));self.assertEqual(seen[0][1]['timeout'],15)
 def factory(self,mode):
  path=self.root/'factory.py';scripts=Path(__import__('skill_rsi_native_lifecycle').__file__).parent;fixture=Path(__import__('native_lifecycle_fixture').__file__).parent
  path.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(scripts))+')\nsys.path.insert(0,'+repr(str(fixture))+')\nfrom skill_rsi_native_lifecycle import NativeSession,IsolatedDetect,EXCEPTIONS\nfrom native_lifecycle_fixture import FakeHooks,CONFIG,PERCEPTION\ndef build():\n    out=Path('+repr(str(self.root/'native'))+')\n    d=IsolatedDetect(PERCEPTION,'+repr(str(UPSTREAM))+',out)\n    return NativeSession(CONFIG,FakeHooks('+repr(mode)+'),out,d),EXCEPTIONS\n')
  return path
 def test_actual_skill_supervisor_perception_chain_on_synthetic_backend(self):
  factory=self.factory('ok');source='ATOMS = ["toy"]\ndef toy(api, args):\n    spec = api.task_spec()\n    obs = api.observe()\n    moved = api.move_pose("left", [0,0,0,1,0,0,0])\n    return {"status":"fixture", "failure_code":None, "spec":spec, "obs":obs, "moved":moved}\ndef fallback(api):\n    return toy(api, {})\n'
  with APISupervisor(factory,sha(factory),self.root/'supervisor',startup_seconds=3,call_seconds=5,total_seconds=9) as backend:
   r=run_skill(source,'fallback',{},backend,UPSTREAM,self.root/'skill',timeout=8)
   self.assertEqual(r['status'],'result',r);value=r['terminal']['value'];self.assertFalse(value['moved']);self.assertNotIn('SECRET',json.dumps(value));self.assertEqual(value['obs']['table_z_estimate'],.74)
  self.assertEqual(backend.report['exit_code'],0);self.assertFalse(backend.report.get('killed_owned_child',False))
  pr=json.loads((self.root/'native/perception-000/report.json').read_text());self.assertEqual(pr['exit_code'],0);self.assertEqual(pr['response']['source_sha256'],hashlib.sha256(PERCEPTION.encode()).hexdigest())
 def test_supervisor_unknown_timeout_no_render_retry(self):
  factory=self.factory('blocking')
  with APISupervisor(factory,sha(factory),self.root/'supervisor',startup_seconds=2,call_seconds=.1,total_seconds=2) as b:
   with self.assertRaises(APIFailure) as c:b.wait(seconds=1)
   self.assertEqual(c.exception.status,'api_timeout');self.assertEqual(b.report['pending_outcome'],'unknown');self.assertEqual(b.report['dispatches'],1)
   with self.assertRaises(APIFailure):b.observe()
  self.assertEqual(b.report['exit_code'],-9)
 def test_no_unfrozen_or_generated_native_launch(self):
  p=self.root/'protocol.json';p.write_text(json.dumps({'status':'DRAFT','source_class':'generated'}))
  with self.assertRaises(ValueError):build_native(p,sha(p))
if __name__=='__main__':unittest.main()
