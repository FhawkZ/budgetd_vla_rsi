"""Audit a closed language qualification, separately from task performance."""
import argparse,hashlib,json
from pathlib import Path

def audit(root):
 r=Path(root);assert (r/'CLOSE.json').exists()
 state=json.loads((r/'state.json').read_text());owner=json.loads((r/'owner-report.json').read_text())
 events=[json.loads(x) for x in (r/'role-language-audit.jsonl').read_text().splitlines()] if (r/'role-language-audit.jsonl').exists() else []
 requests={int(p.name.split('-')[0]):json.loads(p.read_text()) for p in (r/'server').glob('*-request.json')}
 checks=[]
 for event in events:
  indexes=[]
  for i,d in requests.items():
   if event['ledger_before']<i<=event['ledger_after']:
    texts=[]
    for msg in d.get('messages',[]):
     c=msg.get('content');texts += [c] if isinstance(c,str) else [p.get('text','') for p in c if isinstance(p,dict)] if isinstance(c,list) else []
    if any(event['instruction'] in x for x in texts):indexes.append(i)
  checks.append({'role':event['role'],'task':event['task'],'argument_exact':event['matched'],'instruction_sha256':event['instruction_sha256'],'ledger_before':event['ledger_before'],'ledger_after':event['ledger_after'],'actual_model_requests_with_instruction':indexes})
 cap={name:json.loads((r/name).read_text()) for name in ['capabilities-client.json','capabilities-rpc.json'] if (r/name).exists()}
 disabled={'grasp_object','grasp_diverse','grasp_top_down'}
 exposed=[];proposed=[]
 for i,d in requests.items():
  for t in (d.get('tools') or []):
   name=t.get('function',{}).get('name','')
   if name in disabled:exposed.append({'request':i,'tool':name})
 for p in (r/'ledger').glob('*-response.json'):
  d=json.loads(p.read_text())
  for choice in d.get('choices',[]):
   for t in choice['message'].get('tool_calls',[]):
    if t['function']['name'] in disabled:proposed.append({'file':p.name,'tool':t['function']['name']})
 roles_ok={x['role'] for x in checks if x['argument_exact'] and x['actual_model_requests_with_instruction']}=={'planner','engineer','reviewer'}
 cap_ok=len(cap)==2 and all(set(v['removed'])==disabled for v in cap.values()) and not exposed and not proposed
 attempts=owner.get('detail',{}).get('attempts',[])
 result={'classification':'closed native language/capability contract only; not task/RSI success','status':'passed' if roles_ok and cap_ok else 'failed','role_checks':checks,'capabilities':cap,'disabled_tools_exposed':exposed,'disabled_tools_proposed':proposed,'actual_model_calls':len(requests),'usage':owner.get('server_generation_usage'),'task_successes':sum(x.get('success') is True for x in attempts),'reviewer_verdicts':[x.get('reviewer_verdict') for x in attempts],'task_instructions':[x.get('task_instruction') for x in attempts],'accepted_updates':0,'retention_after_update':None,'strict_rsi_rounds':0,'qualification_limit':'Checks language delivery and declared tool surface; does not certify semantic task understanding, motion competence, reviewer accuracy or sandbox isolation.'}
 (r/'language-contract-report.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('run');args=p.parse_args();print(json.dumps(audit(args.run),indent=2))
