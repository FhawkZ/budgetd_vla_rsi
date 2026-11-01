"""Shared, bounded native-skill patches. No code execution or VLA action edits.
A patch is a finite list of one-shot rules evaluated before unchanged fixed50.
Only proprioceptive EEF-relative targets are allowed; no object pose oracle.
"""
import copy, math
class PatchError(ValueError): pass

def validate_patch(p):
 if not isinstance(p,dict) or set(p)!={'rules'} or not isinstance(p['rules'],list) or len(p['rules'])>4:raise PatchError('rules list length0..4 required')
 for r in p['rules']:
  if set(r)!={'arm','min_vla_calls','gripper_min','gripper_max','operation','delta_xyz','gripper_target'}:raise PatchError('unexpected fields')
  if r['arm'] not in ('left','right') or r['operation'] not in ('move_relative','set_gripper'):raise PatchError('undeclared operation')
  if type(r['min_vla_calls']) is not int or not 0<=r['min_vla_calls']<=23:raise PatchError('min_vla_calls')
  def num(v):return type(v) in (int,float) and math.isfinite(v)
  if not all(num(r[k]) for k in ('gripper_min','gripper_max','gripper_target')):raise PatchError('nonfinite')
  if not 0<=r['gripper_min']<=r['gripper_max']<=1 or not 0<=r['gripper_target']<=1:raise PatchError('gripper range')
  d=r['delta_xyz']
  if not isinstance(d,list) or len(d)!=3 or not all(num(v) and abs(v)<=.08 for v in d) or sum(v*v for v in d)>.01+1e-12:raise PatchError('offset bound')
  if r['operation']=='set_gripper' and any(d):raise PatchError('unused displacement must be zero')
  if r['operation']=='move_relative' and not any(d):raise PatchError('zero displacement no-op')
 # Identical repeated rules would merely consume extra trial budget.
 if len({repr(sorted(r.items())) for r in p['rules']})!=len(p['rules']):raise PatchError('duplicate rules')
 return copy.deepcopy(p)

SCHEMA={'type':'object','properties':{'rules':{'type':'array','maxItems':4,'items':{'type':'object','properties':{
 'arm':{'type':'string','enum':['left','right']},'min_vla_calls':{'type':'integer','minimum':0,'maximum':23},
 'gripper_min':{'type':'number','minimum':0,'maximum':1},'gripper_max':{'type':'number','minimum':0,'maximum':1},
 'operation':{'type':'string','enum':['move_relative','set_gripper']},
 'delta_xyz':{'type':'array','items':{'type':'number','minimum':-.08,'maximum':.08},'minItems':3,'maxItems':3},
 'gripper_target':{'type':'number','minimum':0,'maximum':1}},
 'required':['arm','min_vla_calls','gripper_min','gripper_max','operation','delta_xyz','gripper_target'],'additionalProperties':False}}},'required':['rules'],'additionalProperties':False}

class TypedSkillPatch:
 def __init__(self,patch,env,primitives,horizon=1200):
  self.patch=validate_patch(patch);self.env=env;self.primitives=primitives;self.horizon=horizon;self.fired=set();self.attempts=0
 def before_vla(self,inferences):
  s=self.env.last_info['episode_status'];state=self.env.last_info['robot_state']
  if s['eval_success'] or self.horizon-int(s['take_action_cnt'])<10:return None
  for i,r in enumerate(self.patch['rules']):
   if i in self.fired or inferences<r['min_vla_calls']:continue
   g=float(state[r['arm']+'_gripper'])
   if not r['gripper_min']<=g<=r['gripper_max']:continue
   self.fired.add(i);self.attempts+=1;assert self.attempts<=4
   before=copy.deepcopy(self.env.last_info);target=None
   try:
    if r['operation']=='move_relative':
     pose=state[r['arm']+'_eef_pose'];target=[float(pose[j])+r['delta_xyz'][j] for j in range(3)]
     result=self.primitives.move_to(arm=r['arm'],xyz=target,quat=None,gripper=None,substeps=10).data
    else:result=self.primitives.set_gripper(arm=r['arm'],val=r['gripper_target'],steps=10).data
   except BaseException:
    # No retry: caller records failure then closes episode/remaining allocation.
    raise
   after=copy.deepcopy(self.env.last_info);delta=int(after['episode_status']['take_action_cnt'])-int(before['episode_status']['take_action_cnt'])
   if not 0<=delta<=10 or int(after['episode_status']['take_action_cnt'])>self.horizon:raise RuntimeError('native skill budget violation')
   return {'rule_index':i,'rule':copy.deepcopy(r),'before':before,'after':after,'target_xyz':target,'result':result,'native_actions':delta,'attempt':self.attempts,'planning_failure':result.get('plan_status') not in (None,'Success')}
  return None
