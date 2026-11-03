"""One independent bounded proposal batch for a persistent stage harness.
Reads only explicitly hashed DEVELOPMENT evidence. No action or VLA forward.
"""
import argparse,base64,json,os,signal,time,urllib.request
from pathlib import Path
from qwen_service_owner import service
from run_vla_only_pilot import digest,save
from stage_program import SCHEMA,validate,persist
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--sha',required=True);a=p.parse_args();cfg=json.loads(a.config.read_text())
 assert digest(a.config)==a.sha and cfg['status']=='frozen' and cfg['hostname']==os.uname().nodename
 assert cfg['max_qwen_calls_total']==2 and cfg['max_robot_episodes']==cfg['max_vla_calls']==0
 for rel,h in cfg['new_code_sha256'].items():assert digest(ROOT/rel)==h,rel
 runtime=Path(os.environ['RSI_RUNTIME_ROOT']);s=os.statvfs(runtime);assert s.f_bavail*s.f_frsize>max(100*2**30,.2*s.f_blocks*s.f_frsize)+cfg['expected_output_max_bytes'] and s.f_favail>100000
 from transformers import AutoTokenizer
 tokenizer=AutoTokenizer.from_pretrained(runtime/'models/LingBot-VLA-RoboTwin-EEF-e727b46c/qwen_base',local_files_only=True)
 out=runtime/'outputs'/cfg['run_id'];out.mkdir(exist_ok=False);save(out/'protocol.json',cfg)
 report={'status':'running','qwen_requests_attempted':0,'proposals':[],'vla_calls':0,'robot_episodes':0,'policy_actions':0,'accepted_updates':0,'strict_rsi':0};save(out/'report.json',report)
 tools=[{'type':'function','function':{'name':'submit_program','description':'Persistent stage program, or routes=[] to abstain. Hypotheses are unverified.','parameters':SCHEMA}}]
 content=[{'type':'text','text':cfg['instruction']}]
 for row in cfg['evidence_inputs']:
  f=runtime/row['path'];assert digest(f)==row['sha256'];content.append({'type':'text','text':row['label']})
  content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(f.read_bytes()).decode()}} if f.suffix=='.png' else {'type':'text','text':f.read_text()})
 history=[]
 def expire(*_):raise TimeoutError('900second bounded proposal')
 signal.signal(signal.SIGALRM,expire);signal.alarm(900)
 try:
  with service(cfg):
   for i in range(2):
    messages=[{'role':'system','content':'Propose a finite persistent execution harness from DEVELOPMENT observations. Do not claim contact or grasp stability from commanded gripper numbers or infer success from API returns. Do not use hidden poses/scorers/test records. This is hypothesis exploration, not a new-method claim. Return one submit_program call or abstain.'},{'role':'user','content':content}]
    if history:messages.append({'role':'user','content':'Earlier rejected proposal/reason in this batch: '+json.dumps(history)+'. Correct only if supported, or abstain.'})
    body={'model':cfg['model_id'],'max_tokens':1024,'seed':42,'stream':False,'tools':tools,'tool_choice':'auto','messages':messages};save(out/f'request-{i}.json',body);report['qwen_requests_attempted']+=1;save(out/'report.json',report)
    req=urllib.request.Request('http://127.0.0.1:18029/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as response:reply=json.load(response)
    save(out/f'response-{i}.json',reply);entry={'index':i,'response_sha256':digest(out/f'response-{i}.json')}
    try:
     choice=reply['choices'][0];assert choice['finish_reason']!='length','truncated';calls=choice['message'].get('tool_calls',[]);assert len(calls)==1 and calls[0]['function']['name']=='submit_program','missing/invalid tool'
     program=validate(json.loads(calls[0]['function']['arguments']))
     sha,f=persist(out/'programs',program,{'protocol_sha256':a.sha,'request_index':i,'response_sha256':entry['response_sha256']});entry.update(program_sha256=sha,program_path=str(f.relative_to(runtime)))
     if not program['routes']:
      entry['status']='abstained';report['proposals'].append(entry);report['status']='closed_abstained';break
     assert {r['task'] for r in program['routes']}=={'stack_blocks_two','handover_block'},'need both task routes for declared shared pilot'
     tokens=[]
     for route in program['routes']:
      assert route['evidence_case'] in cfg['allowed_evidence_cases'],'unprovided evidence case'
      for goal in cfg['native_goals'][route['task']]:
       for stage in route['stages']:
        language=goal+' Current stage: '+stage['focus'];n=len(tokenizer.encode(language));assert n<=72,'instruction would be truncated';tokens.append(n)
     entry.update(status='candidate_ready_unaccepted',effective_language_token_max=max(tokens));report['proposals'].append(entry);report.update(status='closed_candidate_ready',candidate_sha256=sha,candidate_path=str(f.relative_to(runtime)));break
    except (ValueError,AssertionError,KeyError,TypeError) as e:
     entry.update(status='rejected',reason=repr(e));history.append({'proposal':reply['choices'][0]['message'],'reason':repr(e)});report['proposals'].append(entry)
    save(out/'report.json',report)
   else:report['status']='closed_all_rejected'
 except BaseException as e:report.update(status='closed_failed',error=repr(e));raise
 finally:
  signal.alarm(0);sr=runtime/'outputs'/(cfg['run_id']+'-qwen')/'report.json'
  if sr.exists():
   r=json.loads(sr.read_text());report.update(usage=r.get('usage'),ledger_match=r.get('token_ledger_match'),gpu0_allocation_seconds=r.get('gpu_allocation_seconds'))
  save(out/'report.json',report);save(out/'CLOSE.json',{'status':'CLOSED','outcome':report['status'],'unused_budget':'canceled','no_robot_execution':True})
 print(json.dumps(report))
if __name__=='__main__':main()
