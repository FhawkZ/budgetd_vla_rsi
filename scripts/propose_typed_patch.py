"""Two-call independent contract/proposal protocol. No robot execution or updates."""
import argparse,base64,json,os,signal,time,urllib.request,urllib.error
from pathlib import Path
from qwen_service_owner import service
from run_vla_only_pilot import digest,save
from typed_skill_patch import SCHEMA,validate_patch
ROOT=Path(__file__).resolve().parents[1];R=Path(os.environ['RSI_RUNTIME_ROOT'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--sha',required=True);a=p.parse_args();cfg=json.loads(a.config.read_text());assert digest(a.config)==a.sha and cfg['status']=='frozen' and cfg['max_qwen_calls_total']==2
 out=R/'outputs'/cfg['run_id'];assert not out.exists();out.mkdir();save(out/'protocol.json',cfg)
 tool={'type':'function','function':{'name':'submit_patch','description':'Submit a shared finite patch. Empty rules means abstention. No execution occurs in this request.','parameters':SCHEMA}}
 report={'status':'running','qualification_passed':False,'candidate_accepted_for_development_evaluation':False,'skill_updates':0,'episodes':0,'model_calls':0};save(out/'report.json',report)
 def request(body,index):
  report['model_calls']+=1;save(out/f'{index}-request.json',body);save(out/'report.json',report)
  req=urllib.request.Request('http://127.0.0.1:18029/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=180) as f:response=json.load(f)
  save(out/f'{index}-response.json',response);choice=response['choices'][0];assert choice['finish_reason']!='length'
  calls=choice['message'].get('tool_calls',[]);assert len(calls)==1 and calls[0]['function']['name']=='submit_patch'
  return validate_patch(json.loads(calls[0]['function']['arguments']))
 def alarm(*args):raise TimeoutError('new protocol wall limit')
 signal.signal(signal.SIGALRM,alarm);signal.alarm(600)
 try:
  with service(cfg):
   body={'model':cfg['model_id'],'max_tokens':1024,'seed':42,'stream':False,'tools':[tool],'tool_choice':'auto'}
   fixture={'rules':[{'arm':'left','min_vla_calls':1,'gripper_min':0.,'gripper_max':.5,'operation':'move_relative','delta_xyz':[0.,0.,.04],'gripper_target':0.}]}
   body['messages']=[{'role':'user','content':'Serialization fixture only, no task and no execution. Submit exactly this JSON through submit_patch: '+json.dumps(fixture)}]
   assert request(body,'qualification')==fixture;report['qualification_passed']=True;save(out/'report.json',report)
   content=[{'type':'text','text':cfg['proposal_instruction']}]
   for row in cfg['evidence_inputs']:
    file=R/row['path'];assert digest(file)==row['sha256']
    if file.suffix=='.png':content.extend([{'type':'text','text':row['label']},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode()}}])
    else:content.append({'type':'text','text':file.read_text()})
   body['messages']=[{'role':'system','content':'You propose a reusable bounded harness patch for two robot tasks. Do not claim improvement without evaluation. No other tools, hidden state, files, or feedback are available.'},{'role':'user','content':content}]
   candidate=request(body,'proposal');save(out/'candidate.json',candidate);report['candidate_sha256']=digest(out/'candidate.json')
   report['candidate_accepted_for_development_evaluation']=bool(candidate['rules']);report['rejection_reason']=None if candidate['rules'] else 'model_abstained_no_behavior_change'
   try:
    request(body,'budget-refusal');raise AssertionError('third request admitted')
   except urllib.error.HTTPError as e:assert e.code==400 and 'budget exhausted' in e.read().decode();report['hard_budget_refusal']=True
   report['status']='closed_candidate_ready' if candidate['rules'] else 'closed_abstained'
 except BaseException as exc:report.update(status='closed_failed',error=repr(exc))
 finally:
  signal.alarm(0);report['proxy_requests']=report['model_calls'];service_report=R/'outputs'/(cfg['run_id']+'-qwen')/'report.json'
  if service_report.exists():
   sr=json.loads(service_report.read_text());report['model_calls']=sr.get('usage',{}).get('generations',0);report['usage']=sr.get('usage',{});report['token_ledger_match']=sr.get('token_ledger_match');report['gpu_allocation_seconds']=sr.get('gpu_allocation_seconds')
  else:report['model_calls']=0
  save(out/'report.json',report);save(out/'CLOSE.json',{'status':report['status'],'unused_allowance':'canceled'})
 print(json.dumps(report));return 0 if report['status'] in ('closed_candidate_ready','closed_abstained') else 1
if __name__=='__main__':raise SystemExit(main())
