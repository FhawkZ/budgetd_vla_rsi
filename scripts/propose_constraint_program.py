"""Independent finite Agent proposals for persistent harness programs.
Offline applicability checks use DEVELOPMENT inputs only, never sealed validation.
"""
import argparse,base64,copy,json,os,signal,time,urllib.request
from pathlib import Path
from qwen_service_owner import service
from run_vla_only_pilot import digest,save
from physical_constraint_harness import SCHEMA,validate_program,persist_proposal,program_reward
ROOT=Path(__file__).resolve().parents[1]

def applicability(program,cases,runtime):
 import numpy as np
 import torch
 result=[];files=[]
 for directory in cases:
  d=runtime/directory;rows=[]
  for p in sorted(d.glob('inference-*.json')):
   r=json.loads(p.read_text());actions=p.with_suffix('.npy')
   assert r['status']=='completed' and digest(actions)==r['actions_sha256']
   for v in r['images'].values():assert digest(d/v['path'])==v['sha256']
   state=r['robot_state'];bindings={a+'_eef':state[a+'_eef_pose'][:3] for a in ['left','right']}
   x=torch.from_numpy(np.load(actions)).float().requires_grad_(True)
   reward,active=program_reward(x,program,bindings);g=torch.autograd.grad(reward,x)[0]
   rows.append({'inference':r['index'],'active_rules':active,'gradient_nonzero':bool(torch.count_nonzero(g)),'reward_m2':float(reward.detach())})
   files.append({'input':str(p.relative_to(runtime)),'input_sha256':digest(p),'actions_sha256':digest(actions)})
  result.append({'case':directory,'observations':len(rows),'nonzero_gradient':sum(x['gradient_nonzero'] for x in rows),'rows':rows})
 return {'classification':'offline_applicability_not_task_performance','cases':result,'files':files,'observations':sum(x['observations'] for x in result),'nonzero_gradient':sum(x['nonzero_gradient'] for x in result)}

def main():
 a=argparse.ArgumentParser();a.add_argument('--config',type=Path,required=True);a.add_argument('--sha',required=True);args=a.parse_args()
 cfg=json.loads(args.config.read_text());assert digest(args.config)==args.sha and cfg['status']=='frozen'
 assert cfg['max_qwen_calls_total']==2 and cfg['max_robot_episodes']==0 and cfg['max_vla_calls']==0
 assert cfg['execution_host']=='lzgpu201' and cfg['hostname']==os.uname().nodename
 for rel,h in cfg['new_code_sha256'].items():assert digest(ROOT/rel)==h,rel
 runtime=Path(os.environ['RSI_RUNTIME_ROOT']);s=os.statvfs(runtime)
 assert s.f_bavail*s.f_frsize>max(100*2**30,.2*s.f_blocks*s.f_frsize)+cfg['expected_output_max_bytes'] and s.f_favail>100000
 out=runtime/'outputs'/cfg['run_id'];out.mkdir(exist_ok=False);save(out/'protocol.json',cfg)
 report={'status':'running','qwen_requests_attempted':0,'proposals':[],'vla_calls':0,'robot_episodes':0,'policy_actions':0,'accepted_updates':0,'strict_rsi':0}
 save(out/'report.json',report)
 # Expose only measured EEF references in this first bounded subspace. RGB-D
 # grounding helper exists but live semantic binding has not been qualified.
 schema=copy.deepcopy(SCHEMA);schema['properties']['landmarks']['maxItems']=0
 schema['properties']['rules']['items']['properties']['reference']['enum']=['left_eef','right_eef']
 tools=[{'type':'function','function':{'name':'submit_program','description':'Propose a reusable executable constraint program, or empty rules to abstain.','parameters':schema}}]
 content=[{'type':'text','text':cfg['instruction']}]
 for row in cfg['evidence_inputs']:
  p=runtime/row['path'];assert digest(p)==row['sha256']
  content.append({'type':'text','text':row['label']})
  if p.suffix=='.png':content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()}})
  else:content.append({'type':'text','text':p.read_text()})
 history=[]
 def expire(*_):raise TimeoutError('900 second proposal budget')
 signal.signal(signal.SIGALRM,expire);signal.alarm(900)
 try:
  with service(cfg):
   for i in range(2):
    messages=[{'role':'system','content':'Use only supplied development evidence. Propose a persistent typed harness program, not a claim of task success. Gripper numbers are requested commands, NOT measured openings or contact. No hidden geometry, new tools or scorer access.'},{'role':'user','content':content}]
    if history:messages.append({'role':'user','content':'Within this independent finite proposal budget, earlier rejected proposal and exact reason: '+json.dumps(history)+'. Propose a distinct supported program or abstain.'})
    body={'model':cfg['model_id'],'max_tokens':1024,'seed':42,'stream':False,'tools':tools,'tool_choice':'auto','messages':messages}
    save(out/f'request-{i}.json',body);report['qwen_requests_attempted']+=1;save(out/'report.json',report)
    request=urllib.request.Request('http://127.0.0.1:18029/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=180) as response:reply=json.load(response)
    save(out/f'response-{i}.json',reply);entry={'index':i,'response_sha256':digest(out/f'response-{i}.json')}
    try:
     choice=reply['choices'][0];assert choice['finish_reason']!='length','truncated'
     calls=choice['message'].get('tool_calls',[]);assert len(calls)==1 and calls[0]['function']['name']=='submit_program','wrong/missing tool'
     raw=json.loads(calls[0]['function']['arguments']);program=validate_program(raw)
     assert not program['landmarks'],'unqualified landmark binding'
     h,path=persist_proposal(out/'programs',program,{'protocol_sha256':args.sha,'request_index':i,'response_sha256':entry['response_sha256']})
     entry.update(program_sha256=h,program_path=str(path.relative_to(runtime)))
     if not program['rules']:
      entry['status']='abstained';report['proposals'].append(entry);report['status']='closed_abstained';break
     analysis=applicability(program,cfg['development_case_directories'],runtime);save(out/f'applicability-{i}.json',analysis)
     entry['nonzero_gradient_observations']=analysis['nonzero_gradient'];entry['observations']=analysis['observations']
     if not analysis['nonzero_gradient']:raise ValueError('no nonzero program reward gradient on any declared development prediction')
     entry['status']='candidate_ready_not_accepted';report['proposals'].append(entry);report.update(status='closed_candidate_ready',candidate_path=str(path.relative_to(runtime)),candidate_sha256=h);break
    except (ValueError,AssertionError,KeyError,TypeError) as exc:
     entry.update(status='rejected',reason=repr(exc));history.append({'message':reply['choices'][0]['message'],'reason':repr(exc)});report['proposals'].append(entry)
    save(out/'report.json',report)
   else:report['status']='closed_all_rejected'
 except BaseException as exc:
  report.update(status='closed_failed',error=repr(exc));raise
 finally:
  signal.alarm(0);sr=runtime/'outputs'/(cfg['run_id']+'-qwen')/'report.json'
  if sr.exists():
   s=json.loads(sr.read_text());report.update(usage=s.get('usage'),ledger_match=s.get('token_ledger_match'),gpu0_allocation_seconds=s.get('gpu_allocation_seconds'))
  save(out/'report.json',report);save(out/'CLOSE.json',{'status':'CLOSED','outcome':report['status'],'unused_budget':'canceled','no_robot_execution':True})
 print(json.dumps(report))
if __name__=='__main__':main()
