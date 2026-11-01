"""Finite feedback-conditioned proposals. Stops on first valid patch or abstention.
No robot episodes; prior closed proposal is not reopened.
"""
import argparse,base64,json,os,signal,time,urllib.request
from pathlib import Path
from qwen_service_owner import service
from run_vla_only_pilot import digest,save
from typed_skill_patch import SCHEMA,validate_patch
R=Path(os.environ['RSI_RUNTIME_ROOT'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--sha',required=True);a=p.parse_args();cfg=json.loads(a.config.read_text());assert digest(a.config)==a.sha and cfg['max_qwen_calls_total']==3 and cfg['status']=='frozen'
 disk=os.statvfs(R);assert disk.f_bavail*disk.f_frsize>max(100*2**30,.2*disk.f_blocks*disk.f_frsize)+cfg['expected_output_max_bytes'];assert disk.f_favail>100000
 out=R/'outputs'/cfg['run_id'];assert not out.exists();out.mkdir();save(out/'protocol.json',cfg)
 report={'status':'running','candidates':[],'robot_episodes':0,'accepted_shared_updates':0,'strict_rsi_rounds':0};save(out/'report.json',report)
 content=[{'type':'text','text':cfg['instruction']}]
 for row in cfg['evidence_inputs']:
  f=R/row['path'];assert digest(f)==row['sha256'];content.append({'type':'text','text':row['label']})
  if f.suffix=='.png':content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(f.read_bytes()).decode()}})
  else:content.append({'type':'text','text':f.read_text()})
 tools=[{'type':'function','function':{'name':'submit_patch','description':'Submit a shared bounded patch, or empty rules to abstain.','parameters':SCHEMA}}]
 history=[]
 def timeout(*_):raise TimeoutError('batch wall limit')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(900)
 try:
  with service(cfg):
   for i in range(3):
    messages=[{'role':'system','content':'Use only supplied measured development evidence. No task-specific branch, hidden state or arbitrary tools. Do not claim improvement before evaluation.'},{'role':'user','content':content}]
    if history:messages.append({'role':'user','content':'Earlier rejected outputs in this finite batch, including diagnostics: '+json.dumps(history)+'. Propose a distinct legal patch or abstain. No task evaluation has occurred.'})
    body={'model':cfg['model_id'],'max_tokens':1024,'seed':42,'stream':False,'tools':tools,'tool_choice':'auto','messages':messages};save(out/f'{i}-request.json',body)
    req=urllib.request.Request('http://127.0.0.1:18029/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as f:response=json.load(f)
    save(out/f'{i}-response.json',response);entry={'index':i,'response_sha256':digest(out/f'{i}-response.json')}
    try:
     choice=response['choices'][0];assert choice['finish_reason']!='length','output truncated';tc=choice['message'].get('tool_calls',[]);assert len(tc)==1 and tc[0]['function']['name']=='submit_patch','missing/foreign tool';raw=json.loads(tc[0]['function']['arguments']);patch=validate_patch(raw)
     if not patch['rules']:
      entry['status']='abstained';report['status']='closed_abstained';report['candidates'].append(entry);break
     save(out/'candidate.json',patch);entry.update(status='valid_for_development_only',candidate_sha256=digest(out/'candidate.json'));report.update(status='closed_candidate_ready',candidate_relative=str((out/'candidate.json').relative_to(R)));report['candidates'].append(entry);break
    except (ValueError,AssertionError,KeyError,TypeError) as exc:
     entry.update(status='rejected',reason=repr(exc));history.append({'raw_message':response['choices'][0]['message'],'rejection':repr(exc)});report['candidates'].append(entry)
    save(out/'report.json',report)
   else:report['status']='closed_all_rejected'
 except BaseException as exc:report.update(status='closed_failed',error=repr(exc));raise
 finally:
  signal.alarm(0);sr=R/'outputs'/(cfg['run_id']+'-qwen')/'report.json'
  if sr.exists():
   s=json.loads(sr.read_text());report.update(usage=s.get('usage'),token_ledger_match=s.get('token_ledger_match'),gpu_allocation_seconds=s.get('gpu_allocation_seconds'))
  save(out/'report.json',report);save(out/'CLOSE.json',{'status':report['status'],'remaining_allowance':'canceled'})
 print(json.dumps(report))
if __name__=='__main__':main()
