import contextlib,hashlib,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import run_constraint_vla_server as server

class ServerBoundaryTests(unittest.TestCase):
 def test_rebinding_before_native_mutation_and_no_gripper_measurement(self):
  program={'version':1,'rationale':'fixture','landmarks':[],'rules':[]};seen=[]
  class Native:
   def __init__(self):self.vla=SimpleNamespace(feature_transform=None,model=object(),requires_grad_=lambda x:None)
   def infer(self,obs):
    if obs.get('reset'):return {'action':None}
    value=np.asarray(obs['observation.state']).copy();obs['observation.state'][:]=-999
    return {'action':value}
  @contextlib.contextmanager
  def guide(model,mapping,p,bindings,**kwargs):seen.append(bindings);yield
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'p.json';f.write_text(json.dumps(program));trace=Path(d)/'trace.jsonl'
   env={'RSI_CONSTRAINT_PROGRAM_FILE':str(f),'RSI_CONSTRAINT_PROGRAM_SHA256':hashlib.sha256(f.read_bytes()).hexdigest(),'RSI_CONSTRAINT_VELOCITY_M':'0.01','RSI_CONSTRAINT_TRACE':str(trace)}
   with patch.dict(os.environ,env),patch.object(server,'LingBotPhysicalMap',return_value=object()),patch.object(server,'physical_guidance',guide):
    module=SimpleNamespace(LingbotVLAServer=Native);server.install(module);policy=module.LingbotVLAServer()
    for offset in [0,100]:
     a=np.arange(16,dtype=float)+offset;r=policy.infer({'observation.state':a});np.testing.assert_array_equal(r['action'],np.arange(16)+offset)
    policy.infer({'reset':True})
    assert seen==[{'left_eef':[0,1,2],'right_eef':[8,9,10]},{'left_eef':[100,101,102],'right_eef':[108,109,110]}]
    records=[json.loads(l) for l in trace.read_text().splitlines()];assert len(records)==4 and records[-1]['index']==2
    with patch.dict(os.environ,{'RSI_CONSTRAINT_PROGRAM_SHA256':'bad'}):
     with self.assertRaises(AssertionError):server.install(SimpleNamespace(LingbotVLAServer=Native))

 def test_common_worker_injection_is_scoped(self):
  import run_constraint_panel as runner,typed_skill_patch
  from rpent.utils.daemon import ProcessDaemon
  original_patch=typed_skill_patch.TypedSkillPatch;original_start=ProcessDaemon.start;started=[]
  cfg={'cases':[{'role':'candidate'}],'programs':{'candidate':{'path':'test.json','sha256':'abc'}},'max_injected_xyz_velocity_m':0.01}
  def native_start(d):started.append(d)
  def fake_worker(c,i,o):
   assert typed_skill_patch.TypedSkillPatch is not original_patch
   assert typed_skill_patch.TypedSkillPatch().before_vla(0) is None
   d=SimpleNamespace(name='lingbot_vla_server',cmd=['python','/upstream/vla_server.py'],subprocess_env={'PYTHONPATH':'source'})
   ProcessDaemon.start(d)
   assert Path(d.cmd[1]).name=='run_constraint_vla_server.py'
   assert d.subprocess_env['RSI_CONSTRAINT_PROGRAM_SHA256']=='abc'
   raise RuntimeError('injected failure')
  with tempfile.TemporaryDirectory() as d,patch.object(ProcessDaemon,'start',native_start),patch.object(runner.common,'worker',fake_worker):
   with self.assertRaisesRegex(RuntimeError,'injected failure'):runner.worker(cfg,0,Path(d))
   assert ProcessDaemon.start is native_start and typed_skill_patch.TypedSkillPatch is original_patch
  assert ProcessDaemon.start is original_start and len(started)==1
if __name__=='__main__':unittest.main()
