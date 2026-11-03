import copy,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
import yaml
from physical_constraint_harness import (LingBotPhysicalMap,validate_program,persist_proposal,sample_grounding,program_reward,physical_guidance)

P={'version':1,'rationale':'test fixture, not autonomous','landmarks':[], 'rules':[{'subject':'left_eef','reference':'right_eef','axis':'z','relation':'at_least','offset_m':0.03,'activation_distance_m':0.6,'tolerance_m':0.002}]}
B={'left_eef':[0,0,0],'right_eef':[0.1,0,0]}
class PhysicalHarnessTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from lingbotvla.data.vla_data.utils import FeatureTransform
  r=Path(os.environ['RSI_RUNTIME_ROOT'])/'models/LingBot-VLA-RoboTwin-EEF-e727b46c'
  train=yaml.safe_load((r/'lingbotvla_cli.yaml').read_text());config=json.loads((r/'config.json').read_text())
  d=SimpleNamespace(**train['data']);d.max_action_dim=config['max_action_dim'];d.max_state_dim=config['max_state_dim']
  ft=FeatureTransform(str(r/'configs/robot_configs/robotwin_eef.yaml'),d,None,None,norm_stats_path=str(r/'norm_stats/robotwin_eef.json'))
  cls.mapping=LingBotPhysicalMap(ft)
 def test_actual_native_inverse_and_gradient(self):
  g=torch.Generator().manual_seed(20261103);x=torch.randn((50,self.mapping.width),generator=g)
  torch.testing.assert_close(self.mapping.decode(x),self.mapping.native_decode(x),rtol=1e-6,atol=1e-6)
  x=x.double().requires_grad_(True);loss=self.mapping.decode(x)[...,2].sum();grad=torch.autograd.grad(loss,x)[0]
  expected=self.mapping.matrix[2].double().expand_as(x);torch.testing.assert_close(grad,expected,rtol=0,atol=0)
  assert self.mapping.xyz_internal_indices==[0,1,2,7,8,9]
 def test_physical_reward_translation_and_sign(self):
  x=torch.zeros((1,50,16),requires_grad=True);r,n=program_reward(x,P,B);g=torch.autograd.grad(r,x)[0]
  assert n==1 and (g[...,2]>0).all() and (g[...,10]<0).all()
  y=x.detach().clone();y[...,0:3]+=3;y[...,8:11]+=3;r2,_=program_reward(y,P,B)
  torch.testing.assert_close(r,r2)
  y=x.detach().clone();y[...,2]=0.04;assert float(program_reward(y,P,B)[0])==0
 def test_missing_and_out_of_scope_bindings_abstain(self):
  p=copy.deepcopy(P);p['landmarks']=['red block'];p['rules'][0]['reference']='landmark0'
  x=torch.zeros((1,50,16),requires_grad=True)
  assert program_reward(x,p,B)[1]==0
  far=copy.deepcopy(B);far['right_eef']=[5,0,0];assert program_reward(x,P,far)[1]==0
 def test_same_frame_depth_and_rejections(self):
  w=np.zeros((5,7,3));w[...,2]=0.75
  assert sample_grounding(w,[2,3],rgb_shape=(5,7,3),frame_id=1,requested_frame_id=1)==[0,0,0.75]
  for args in [dict(frame_id=1,requested_frame_id=2,pixel=[2,3],rgb_shape=(5,7,3)),dict(frame_id=1,requested_frame_id=1,pixel=[2,3],rgb_shape=(7,5,3)),dict(frame_id=1,requested_frame_id=1,pixel=[False,3],rgb_shape=(5,7,3))]:
   with self.assertRaises(ValueError):sample_grounding(w,**args)
  w[2,3,2]=1.0
  with self.assertRaises(ValueError):sample_grounding(w,[2,3],rgb_shape=(5,7,3),frame_id=1,requested_frame_id=1)
 def test_illegal_programs_and_persistence(self):
  for mutate in [lambda p:p.update(extra='code'),lambda p:p['rules'][0].update(reference='left_eef'),lambda p:p['rules'][0].update(reference='landmark0'),lambda p:p['rules'][0].update(offset_m=float('nan'))]:
   p=copy.deepcopy(P);mutate(p)
   with self.assertRaises(Exception):validate_program(p)
  with tempfile.TemporaryDirectory() as d:
   h,f=persist_proposal(d,P,{'source':'fixture'});before=f.read_bytes();h2,_=persist_proposal(d,P,{'source':'second'})
   assert h==h2 and f.read_bytes()==before
   assert json.loads((Path(d)/(h+'.proposal.json')).read_text())['status']=='proposed_unaccepted'
 def test_zero_path_restore_and_bounded_injection(self):
  class M:
   def predict_velocity(self,*args):return torch.zeros_like(args[-2])
  m=M();old=m.predict_velocity;x=torch.zeros((1,50,self.mapping.width));t=torch.tensor([0.5])
  with physical_guidance(m,self.mapping,P,B,max_velocity_m=0,ledger=[]):
   assert torch.equal(m.predict_velocity(None,None,None,x,t),old(None,None,None,x,t))
  assert m.predict_velocity==old
  log=[]
  # Use a native physical fixture with equal EEF heights so the rule is active.
  raw=torch.zeros(50,16);ft=self.mapping.feature_transform
  item={'observation.state':torch.zeros(16),'action':raw,'action_is_pad':torch.zeros(50),'task':''}
  item.update({key:torch.zeros(3,1,1) for key in ft.org_features['images']})
  it=ft.convert_features(item)
  batch=ft.pad_and_concat(ft.normalizer.normalize(it));n=torch.nn.functional.pad(batch['action'],(0,self.mapping.width-batch['action'].shape[-1]))[None]
  with self.assertRaisesRegex(RuntimeError,'stop'):
   with physical_guidance(m,self.mapping,P,B,max_velocity_m=0.01,ledger=log):
    v=m.predict_velocity(None,None,None,n,t);effect=-(v@self.mapping.matrix.T)
    assert float(effect[...,2].mean())>0 and float(effect[...,10].mean())<0
    assert float(torch.linalg.vector_norm(effect[...,:3],dim=-1).max())<=0.010001
    assert torch.count_nonzero(effect[...,[3,4,5,6,7,11,12,13,14,15]])==0
    raise RuntimeError('stop')
  assert m.predict_velocity==old and len(log)==1
if __name__=='__main__':unittest.main()
