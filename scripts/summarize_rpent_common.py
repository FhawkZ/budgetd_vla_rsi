"""Read-only reconciliation of a closed native-language RPent development run."""
import argparse,hashlib,json,collections
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def main():
 a=argparse.ArgumentParser();a.add_argument('output');args=a.parse_args();root=Path(args.output);assert (root/'CLOSE.json').exists()
 owner=read(root/'report.json');cfg=read(root/'protocol.json');runtime=root.parents[1]
 control=runtime/'outputs/vla-native-language-pair2-20261030-1510'
 rows=[];totals=collections.Counter()
 for c in cfg['cases']:
  d=root/c['task']
  if not (d/'ledger/ledger.json').exists():rows.append({'task':c['task'],'status':'not_started'});continue
  ledger=read(d/'ledger/ledger.json');totals.update({k:ledger[k] for k in ['backend_attempts','received_requests','prompt_tokens','completion_tokens']})
  episode=read(d/'episode.json') if (d/'episode.json').exists() else {}
  responses=sorted((d/'ledger').glob('*-response.json'));audits=[read(p) for p in sorted((d/'ledger').glob('*-audit.json'))]
  calls=collections.Counter();arguments=[]
  for p in responses:
   v=read(p)
   for call in v['choices'][0]['message'].get('tool_calls',[]):
    f=call['function'];calls[f['name']]+=1;arguments.append({'request':p.stem,'tool':f['name'],'arguments':f['arguments']})
  errors=[{'request':v['index'],'error':v.get('error'),'usage':v.get('usage')} for v in audits if v.get('http_status')!=200]
  initial=read(d/'initial.json') if (d/'initial.json').exists() else None
  prior=next(control.glob('*-'+c['task']+'-s'+str(c['seed'])))
  original=read(prior/'inference-001.json')
  first=read(d/'ledger/001-forwarded.json') if (d/'ledger/001-forwarded.json').exists() else {}
  forwarded=sorted((d/'ledger').glob('*-forwarded.json'))
  request_matches=[]
  for p in forwarded:
   match=[]
   for q in (root/'server').glob('*-request.json'):
    if sha(p)==sha(q):match.append(q.name)
   request_matches.append({'request':p.name,'sha256':sha(p),'server_matches':match})
  row={'task':c['task'],'seed':c['seed'],'episode':episode,'ledger':ledger,'responses':len(responses),'tool_calls':dict(calls),'tools_are_requests_not_physical_actions':True,'http_errors':errors,'first_request_contains_native_language':c['instruction'] in json.dumps(first),'initial_state_equal':initial['robot_state']==original['robot_state'] if initial else None,'initial_images_equal':initial['images']==c['initial_image_sha256'] if initial else None,'prior_vla_only_success':read(prior/'episode.json')['native_eval_success'],'prior_vla_only_calls':read(prior/'episode.json')['vla_inferences'],'request_matches':request_matches}
  (d/'tool-requests.json').write_text(json.dumps(arguments,indent=2)+'\n');rows.append(row)
 summary={'classification':'closed paired development baseline; local-model adaptation, not original paper scores','owner_status':owner['status'],'protocol_sha256':sha(root/'protocol.json'),'rows':rows,'proxy_totals':dict(totals),'server_usage':owner['usage'],'token_totals_exact_match':totals['prompt_tokens']==owner['usage']['prompt_tokens'] and totals['completion_tokens']==owner['usage']['completion_tokens'],'GPU0_allocation_seconds':owner['GPU0_allocation_seconds'],'GPU1_case_wall_seconds':sum(x['allocation_seconds'] for x in owner['cases']),'accepted_updates':0,'retention_after_update':None,'strict_rsi_rounds':0,'limitations':['Two already-used development cases; no stable-rate claim','RPent may use native analytic actions plus VLA; not equal total compute to VLA-only','Native action count is not exact physics ticks or successful planner steps','No terminal stability extension; no budget refill','No task-level persistent learning in evaluation-only official memory']}
 (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k!='rows'},indent=2))
 for row in rows:print(row['task'],row.get('episode',{}).get('native_success'),row.get('tool_calls'),row.get('initial_state_equal'),row.get('initial_images_equal'))
if __name__=='__main__':main()
