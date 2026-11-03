"""Typed persistent subgoal programs and fresh-observation boundary state machine.
Explicit language adapter for all comparison arms, not a claimed novel algorithm.
Never consumes the environment's success flag or changes model actions/weights.
"""
import copy,hashlib,json
from pathlib import Path

TEXT={'type':'string','minLength':1,'maxLength':240}
STAGE={'type':'object','additionalProperties':False,'properties':{'focus':TEXT,'done_when':TEXT,'next_ready_when':TEXT},'required':['focus','done_when','next_ready_when']}
SCHEMA={'type':'object','additionalProperties':False,'properties':{'version':{'type':'integer','enum':[1]},'rationale':{'type':'string','maxLength':1500},'routes':{'type':'array','maxItems':2,'items':{'type':'object','additionalProperties':False,'properties':{'task':{'type':'string','enum':['stack_blocks_two','handover_block']},'evidence_case':{'type':'string','maxLength':120},'boundary_hypothesis':{'type':'string','maxLength':600},'stages':{'type':'array','minItems':2,'maxItems':3,'items':STAGE}},'required':['task','evidence_case','boundary_hypothesis','stages']}}},'required':['version','rationale','routes']}
DECISION_SCHEMA={'type':'object','additionalProperties':False,'properties':{'frame_sha256':{'type':'string'},'stage_index':{'type':'integer','minimum':0,'maximum':2},'completed':{'type':'string','enum':['yes','no','unknown']},'successor_ready':{'type':'string','enum':['yes','no','unknown']},'evidence':{'type':'string','maxLength':500}},'required':['frame_sha256','stage_index','completed','successor_ready','evidence']}

def validate(raw):
 import jsonschema
 jsonschema.validate(raw,SCHEMA);p=copy.deepcopy(raw)
 if len({r['task'] for r in p['routes']})!=len(p['routes']):raise ValueError('duplicate task route')
 for r in p['routes']:
  for s in r['stages']:
   for key in ('focus','done_when','next_ready_when'):
    if not s[key].strip():raise ValueError('empty text')
   if len(s['focus'].split())>24:raise ValueError('stage focus exceeds24words')
 return p

def persist(root,p,provenance):
 p=validate(p);data=(json.dumps(p,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();sha=hashlib.sha256(data).hexdigest();root=Path(root);root.mkdir(exist_ok=True,parents=True);f=root/(sha+'.json')
 if f.exists():assert f.read_bytes()==data
 else:f.write_bytes(data)
 receipt=root/(sha+'.proposal.json')
 if not receipt.exists():receipt.write_text(json.dumps({'status':'proposed_unaccepted','program_sha256':sha,'provenance':provenance},indent=2)+'\n')
 return sha,f

def visible_frame(observation):
 """Permit only RGB and measured EEF. Drop commanded grippers and scorer."""
 import numpy as np
 parts={};h=hashlib.sha256()
 for key in ('head','left_wrist','right_wrist'):
  x=np.asarray(observation['views'][key]['rgb'])
  if x.ndim!=3 or x.shape[-1]!=3 or x.dtype!=np.uint8:raise ValueError('RGB contract')
  parts[key]=hashlib.sha256(x.tobytes()).hexdigest();h.update(key.encode()+json.dumps(list(x.shape)).encode()+x.tobytes())
 state={a:observation['robot_state'][a+'_eef_pose'][:3] for a in ('left','right')}
 if not all(np.isfinite(np.asarray(x,dtype=float)).all() for x in state.values()):raise ValueError('nonfinite measured position')
 # EEF values are metadata; frame freshness and binding include them as well.
 state={k:np.asarray(v,dtype=float).tolist() for k,v in state.items()};h.update(json.dumps(state,sort_keys=True).encode())
 return {'frame_sha256':h.hexdigest(),'rgb_sha256':parts,'measured_eef_xyz':state}

class StageProgram:
 def __init__(self,program,task,goal,mode='successor_aware'):
  if mode not in ('native','postcondition_only','successor_aware'):raise ValueError('mode')
  self.program=validate(program);self.route=next((r for r in self.program['routes'] if r['task']==task),None);self.goal=goal;self.mode=mode;self.stage_index=0;self.calls_in_stage=0;self.last_decision_inference=-1;self.events=[]
 def effective_language(self):
  if self.mode=='native' or self.route is None:return self.goal
  return self.goal+' Current stage: '+self.route['stages'][self.stage_index]['focus']
 def decision_context(self,frame,inference_index):
  if self.mode=='native' or self.route is None or self.stage_index>=len(self.route['stages'])-1:return None
  if self.calls_in_stage<1:raise ValueError('no preceding stage action')
  return {'goal':self.goal,'stage_index':self.stage_index,'current':self.route['stages'][self.stage_index],'next':self.route['stages'][self.stage_index+1],'inference_index':inference_index,**frame}
 def complete_vla_call(self):self.calls_in_stage+=1
 def apply_decision(self,decision,frame,inference_index):
  import jsonschema
  jsonschema.validate(decision,DECISION_SCHEMA)
  if self.route is None or self.mode=='native':raise ValueError('no editable route')
  if decision['frame_sha256']!=frame['frame_sha256'] or decision['stage_index']!=self.stage_index:raise ValueError('stale or misbound decision')
  if inference_index<=self.last_decision_inference:raise ValueError('duplicate/nonmonotonic decision')
  if self.calls_in_stage<1:raise ValueError('transition before stage execution')
  if not decision['evidence'].strip():raise ValueError('missing visual rationale')
  advance=decision['completed']=='yes' and (self.mode=='postcondition_only' or decision['successor_ready']=='yes') and self.stage_index<len(self.route['stages'])-1
  old=self.stage_index;self.last_decision_inference=inference_index
  if advance:self.stage_index+=1;self.calls_in_stage=0
  event={'inference_index':inference_index,'before':old,'after':self.stage_index,'decision':copy.deepcopy(decision),'advanced':advance}
  self.events.append(event);return event

def adapted_infer(original,observation,controller,token_count,log):
 """Changes the REAL client's task_language, not ignored lingbot_act(prompt).
 Original goal, RGB/state objects and observation remain intact. No silent truncation.
 """
 language=controller.effective_language()
 if token_count(language)>72:raise ValueError('effective instruction exceeds native72token budget')
 frame=visible_frame(observation);payload=dict(observation);payload['task_language']=language
 record={'native_language':observation['task_language'],'effective_language':language,'stage_index':controller.stage_index,**frame,'status':'started'};log(record)
 try:
  result=original(payload);controller.complete_vla_call();record=dict(record,status='completed');return result
 except BaseException as e:record=dict(record,status='failed',error=repr(e));raise
 finally:log(record)
