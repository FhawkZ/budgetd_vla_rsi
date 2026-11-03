"""Owned-client stage adapter. The fixed Qwen observes only current RGB/EEF.
One explicit fresh decision every2 completed VLA calls until final stage; no repair.
"""
import base64,copy,io,json,time,urllib.request
from pathlib import Path
import numpy as np
from PIL import Image
from stage_program import StageProgram,DECISION_SCHEMA,adapted_infer,visible_frame
from run_vla_only_pilot import save,digest

class StageBinding:
 def __init__(self,program,task,mode,out,model_id,token_count):
  self.program=program;self.task=task;self.mode=mode;self.out=Path(out);self.model_id=model_id;self.token_count=token_count;self.controller=None;self.vla_calls=0;self.qwen_calls=0
 def append(self,row):
  with (self.out/'language-trace.jsonl').open('a') as f:f.write(json.dumps(row,default=lambda x:x.tolist())+'\n')
 def infer(self,original,observation):
  goal=observation['task_language']
  if self.controller is None:self.controller=StageProgram(self.program,self.task,goal,self.mode)
  assert goal==self.controller.goal,'native goal changed'
  if self.mode!='native' and self.vla_calls and self.vla_calls%2==0:
   frame=visible_frame(observation);context=self.controller.decision_context(frame,self.vla_calls)
   if context is not None:self.check_boundary(observation,frame,context)
  self.vla_calls+=1
  return adapted_infer(original,observation,self.controller,self.token_count,lambda row:self.append(dict(row,index=self.vla_calls,program_mode=self.mode)))
 def check_boundary(self,observation,frame,context):
  assert self.qwen_calls<11,'per episode observation budget exhausted'
  self.qwen_calls+=1;n=self.qwen_calls
  schema=copy.deepcopy(DECISION_SCHEMA);schema['properties']['frame_sha256']['enum']=[frame['frame_sha256']];schema['properties']['stage_index']['enum']=[self.controller.stage_index]
  content=[{'type':'text','text':json.dumps(context)}]
  for camera in ('head','left_wrist','right_wrist'):
   b=io.BytesIO();Image.fromarray(np.asarray(observation['views'][camera]['rgb'])).save(b,format='PNG');content.extend([{'type':'text','text':camera+' CURRENT RGB'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()}}])
  body={'model':self.model_id,'max_tokens':1024,'seed':42,'stream':False,'tool_choice':'auto','tools':[{'type':'function','function':{'name':'assess_boundary','description':'Assess both visible current completion and next-stage entry readiness. Unknown is allowed.','parameters':schema}}],'messages':[{'role':'system','content':'Use only the current RGB and measured EEF positions supplied. Report current done_when and next_ready_when separately. A requested command or API return is not contact/grasp evidence. If occluded or uncertain, say unknown. Never infer native score or task success. Do not change the stage program, task goal or actions. Return exactly one assess_boundary tool call.'},{'role':'user','content':content}]}
  request_file=self.out/f'boundary-{n:03d}-request.json';save(request_file,body);row={'index':n,'vla_calls_completed':self.vla_calls,'status':'attempted','request_sha256':digest(request_file),'frame':frame,'started_unix':time.time()};save(self.out/f'boundary-{n:03d}.json',row)
  try:
   req=urllib.request.Request('http://127.0.0.1:18029/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=180) as r:reply=json.load(r)
   save(self.out/f'boundary-{n:03d}-response.json',reply);choice=reply['choices'][0];assert choice['finish_reason']!='length','truncated boundary assessment';calls=choice['message'].get('tool_calls',[]);assert len(calls)==1 and calls[0]['function']['name']=='assess_boundary','invalid tool call'
   decision=json.loads(calls[0]['function']['arguments']);event=self.controller.apply_decision(decision,frame,self.vla_calls);row.update(status='completed',usage=reply.get('usage'),decision=decision,event=event)
  except BaseException as e:row.update(status='failed',error=repr(e));raise
  finally:row['finished_unix']=time.time();save(self.out/f'boundary-{n:03d}.json',row)
