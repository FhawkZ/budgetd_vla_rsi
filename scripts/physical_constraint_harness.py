"""Typed persistent spatial programs; common-backend adapter, not a new VLS claim.
No arbitrary code, task scorer, hidden object state, or learned parameter updates.
"""
from __future__ import annotations
from contextlib import contextmanager
import copy
import hashlib
import json
import math
from pathlib import Path

REFS = ('left_eef', 'right_eef', 'landmark0', 'landmark1')
SCHEMA = {
 'type':'object','additionalProperties':False,
 'properties':{
  'version':{'type':'integer','enum':[1]},
  'rationale':{'type':'string'},
  'landmarks':{'type':'array','maxItems':2,'items':{'type':'string'}},
  'rules':{'type':'array','maxItems':3,'items':{
   'type':'object','additionalProperties':False,
   'properties':{
    'subject':{'type':'string','enum':['left_eef','right_eef']},
    'reference':{'type':'string','enum':list(REFS)},
    'axis':{'type':'string','enum':['x','y','z','distance']},
    'relation':{'type':'string','enum':['at_least','at_most','equal']},
    'offset_m':{'type':'number','minimum':-0.30,'maximum':0.30},
    'activation_distance_m':{'type':'number','minimum':0.01,'maximum':0.60},
    'tolerance_m':{'type':'number','minimum':0.002,'maximum':0.05}},
   'required':['subject','reference','axis','relation','offset_m','activation_distance_m','tolerance_m']}},
 }, 'required':['version','rationale','landmarks','rules']}

def validate_program(raw):
 import jsonschema
 jsonschema.validate(raw,SCHEMA)
 p=copy.deepcopy(raw)
 if len(p['rationale'])>2000: raise ValueError('rationale too long')
 for s in p['landmarks']:
  if not s.strip() or len(s)>80:raise ValueError('invalid landmark description')
 if len(set(p['landmarks']))!=len(p['landmarks']):raise ValueError('duplicate landmarks')
 seen=set()
 for rule in p['rules']:
  if rule['subject']==rule['reference']:raise ValueError('self-referential rule')
  if rule['reference'].startswith('landmark') and int(rule['reference'][-1])>=len(p['landmarks']):raise ValueError('undeclared landmark')
  if rule['axis']=='distance' and rule['offset_m']<0:raise ValueError('negative distance')
  for k in ('offset_m','activation_distance_m','tolerance_m'):
   if not math.isfinite(rule[k]):raise ValueError('nonfinite scalar')
  key=json.dumps(rule,sort_keys=True)
  if key in seen:raise ValueError('duplicate rule')
  seen.add(key)
 return p

def persist_proposal(root,raw,provenance):
 """Immutable proposal storage is NOT acceptance or deployment."""
 p=validate_program(raw);data=(json.dumps(p,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
 sha=hashlib.sha256(data).hexdigest();root=Path(root);root.mkdir(parents=True,exist_ok=True)
 f=root/(sha+'.json')
 if f.exists():
  if f.read_bytes()!=data:raise ValueError('content-address collision')
 else:
  with f.open('xb') as out:out.write(data)
 receipt=root/(sha+'.proposal.json')
 if not receipt.exists():
  receipt.write_text(json.dumps({'status':'proposed_unaccepted','program_sha256':sha,'provenance':provenance},indent=2)+'\n')
 return sha,f

class LingBotPhysicalMap:
 """Differentiable affine map derived from actual native reverse transform.
 Supported checkpoint uses absolute EEF16; reject state-relative transforms.
 Does not normalize model parameters or change native model features.
 """
 def __init__(self,feature_transform):
  import torch
  ft=feature_transform
  if any(ft.action_subtract_state.values()):raise ValueError('relative action unsupported')
  width=ft.data_config.max_action_dim
  item={'observation.state':torch.zeros(16),'action':torch.zeros(1,16),'action_is_pad':torch.zeros(1),'task':''}
  item.update({key:torch.zeros(3,1,1) for key in ft.org_features['images']})
  probe=ft.convert_features(item)
  batch=ft.pad_and_concat(ft.normalizer.normalize(probe))
  mask=torch.nn.functional.pad(batch['joint_mask'],(0,width-batch['joint_mask'].numel())).bool()
  state=torch.zeros(width)
  def native(x):return ft.unapply({'actions':x,'state':state,'joint_mask':mask})['action']
  offset=native(torch.zeros(1,width))[0]
  matrix=(native(torch.eye(width))-offset).T.contiguous()
  if tuple(matrix.shape)!=(16,width):raise ValueError('unsupported action shape')
  if not torch.isfinite(matrix).all():raise ValueError('nonfinite map')
  self.offset=offset;self.matrix=matrix;self.width=width;self.feature_transform=ft;self.mask=mask;self.state=state
  # The XYZ jacobian must be a nonzero one-to-one mapping, not an invented index list.
  rows=matrix[[0,1,2,8,9,10]]
  if not ((rows!=0).sum(-1)==1).all():raise ValueError('non-affine XYZ layout')
  self.xyz_internal_indices=rows.abs().argmax(-1).tolist()
  if len(set(self.xyz_internal_indices))!=6:raise ValueError('aliased XYZ axes')
 def decode(self,x):
  return x@self.matrix.to(x.device,x.dtype).T+self.offset.to(x.device,x.dtype)
 def native_decode(self,x):
  return self.feature_transform.unapply({'actions':x,'state':self.state,'joint_mask':self.mask})['action']

def sample_grounding(world_xyz,pixel,*,rgb_shape,frame_id,requested_frame_id):
 """Use calibrated same-frame RGB-D world XYZ, never simulator object truth.
 Pixel [row,col] is in exact displayed RGB coordinates. Invalid data abstains.
 """
 import numpy as np
 if frame_id!=requested_frame_id:raise ValueError('stale grounding')
 w=np.asarray(world_xyz)
 if w.ndim!=3 or w.shape[-1]!=3 or tuple(w.shape[:2])!=tuple(rgb_shape[:2]):raise ValueError('RGB/world-map mismatch')
 if not isinstance(pixel,list) or len(pixel)!=2 or any(isinstance(v,bool) or not isinstance(v,int) for v in pixel):raise ValueError('pixel schema')
 row,col=pixel
 if not (0<=row<w.shape[0] and 0<=col<w.shape[1]):raise ValueError('pixel out of bounds')
 region=w[max(0,row-1):row+2,max(0,col-1):col+2].reshape(-1,3)
 good=region[np.isfinite(region).all(-1)]
 if len(good)<3:raise ValueError('insufficient valid depth')
 med=np.median(good,axis=0)
 if np.linalg.norm(good-med,axis=-1).max()>0.03:raise ValueError('depth discontinuity')
 return med.tolist()

def program_reward(raw_actions,program,bindings):
 """Reward in meters; no truth success/reward. Returns reward and active count.
 Activation uses measured current EEF/landmark positions, not hallucinated contact.
 All referenced observations must be re-bound for each invocation.
 """
 import torch
 zero=raw_actions.sum()*0.0;reward=zero;active=0
 for rule in program['rules']:
  ref=rule['reference'];sub=rule['subject']
  if sub not in bindings or ref not in bindings:continue
  current=torch.as_tensor(bindings[sub],device=raw_actions.device,dtype=raw_actions.dtype)
  reference=torch.as_tensor(bindings[ref],device=raw_actions.device,dtype=raw_actions.dtype)
  if current.shape!=(3,) or reference.shape!=(3,) or not torch.isfinite(current).all() or not torch.isfinite(reference).all():raise ValueError('invalid binding')
  if float(torch.linalg.vector_norm(current-reference))>rule['activation_distance_m']:continue
  s=slice(0,3) if sub=='left_eef' else slice(8,11)
  if ref in ('left_eef','right_eef'):
   t=slice(0,3) if ref=='left_eef' else slice(8,11);delta=raw_actions[...,s]-raw_actions[...,t]
  else:delta=raw_actions[...,s]-reference
  value=torch.linalg.vector_norm(delta,dim=-1) if rule['axis']=='distance' else delta[...,{'x':0,'y':1,'z':2}[rule['axis']]]
  residual=value-rule['offset_m'];tol=rule['tolerance_m']
  if rule['relation']=='at_least':penalty=torch.relu(-residual-tol)
  elif rule['relation']=='at_most':penalty=torch.relu(residual-tol)
  else:penalty=torch.relu(residual.abs()-tol)
  reward=reward-penalty.square().mean();active+=1
 return reward,active

@contextmanager
def physical_guidance(model,coordinate_map,program,bindings,*,max_velocity_m,ledger):
 """Flow clean-estimate guidance, fixed physical velocity budget, no scale search.
 Detached native velocity is a documented first-order approximation. Normalized
 velocity perturbations are mapped from bounded raw XYZ corrections. Other model
 outputs may still change through later denoising; no final-motion guarantee.
 """
 import torch
 program=validate_program(program)
 if not 0<=max_velocity_m<=0.01:raise ValueError('physical cap')
 original=model.predict_velocity
 def wrapped(state,masks,cache,sample,timestep):
  velocity=original(state,masks,cache,sample,timestep)
  if max_velocity_m==0 or not program['rules']:return velocity
  with torch.enable_grad():
   x=sample.detach().float().requires_grad_(True)
   time=timestep.reshape(-1,1,1).float()
   clean=x-time*velocity.detach().float()
   physical=coordinate_map.decode(clean)
   reward,active=program_reward(physical,program,bindings)
   raw_grad=torch.autograd.grad(reward,physical)[0]
   delta=torch.zeros_like(velocity,dtype=torch.float32)
   max_effect=0.0
   for rawidx in ((0,1,2),(8,9,10)):
    g=raw_grad[...,list(rawidx)]
    norm=torch.linalg.vector_norm(g,dim=-1,keepdim=True)
    step=g/(norm+1e-12)*max_velocity_m
    for j,k in enumerate(rawidx):
     row=coordinate_map.matrix[k];internal=int(row.abs().argmax())
     delta[...,internal]=step[...,j]/row[internal].to(step.device)
    max_effect=max(max_effect,float(torch.linalg.vector_norm(step,dim=-1).max()))
  if not torch.isfinite(delta).all():raise ValueError('nonfinite guidance')
  ledger.append({'active_rules':active,'reward_m2':float(reward.detach()),'max_injected_xyz_velocity_m':max_effect,'timestep':float(timestep[0]),'clean_estimate':'x_t-t*v_t_detached'})
  return velocity-delta.to(velocity.dtype)
 model.predict_velocity=wrapped
 try:yield
 finally:model.predict_velocity=original
