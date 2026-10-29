"""Read-only accounting analysis of a CLOSED bounded local native qualification."""
import argparse,collections,hashlib,json,time
from pathlib import Path

def canonical(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('run');a=p.parse_args();r=Path(a.run)
 assert (r/'CLOSE.json').is_file(),'never label an ongoing run completed'
 owner=json.loads((r/'owner-report.json').read_text());ledger=json.loads((r/'ledger/ledger.json').read_text());protocol=json.loads((r/'protocol.json').read_text())
 fwd=collections.Counter(canonical(json.loads(p.read_text())) for p in (r/'ledger').glob('*-forwarded.json'))
 served=collections.Counter(canonical(json.loads(p.read_text())) for p in (r/'server').glob('*-request.json'))
 generations=[json.loads(p.read_text()) for p in (r/'server').glob('*-generation.json')]
 actions=[]
 for p in sorted((r/'ledger').glob('*-response.json')):
  m=json.loads(p.read_text())['choices'][0]['message']
  actions.extend(t['function']['name'] for t in m.get('tool_calls',[]))
 attempts=owner.get('detail',{}).get('attempts',[])
 summary={'classification':'native RoboRSI development qualification with Qwen/MCP/runtime adaptations; NOT VLA/paper number/RSI comparison','protocol_sha256':hashlib.sha256((r/'protocol.json').read_bytes()).hexdigest(),'owner_status':owner['status'],'attempts':attempts,'task_completed_by_runner':bool(attempts) and all(x.get('status')=='terminal' for x in attempts),'native_successes':sum(x.get('success') is True for x in attempts),'model_calls':ledger['backend_attempts'],'received_proxy_requests':ledger['received_requests'],'forwarded_request_hash_multiset_equals_server':fwd==served,'forwarded_count':sum(fwd.values()),'server_received_count':sum(served.values()),'server_generation_count':len(generations),'prompt_tokens':sum(x['usage']['prompt_tokens'] for x in generations),'completion_tokens':sum(x['usage']['completion_tokens'] for x in generations),'generation_seconds':sum(x['generation_seconds'] for x in generations),'ledger_usage':{k:ledger[k] for k in ('prompt_tokens','completion_tokens')},'tool_proposals':dict(collections.Counter(actions)),'GPU0_allocation_seconds':owner['GPU0_allocation_seconds'],'unused_model_allowance_canceled':protocol['max_model_calls']-ledger['backend_attempts'],'accepted_updates':0,'strict_rsi_rounds':0,'retention_after_update':None,'owned_direct_children_exited':owner['owned_children_exited'],'updated_unix':time.time()}
 for name in ['rpc-runtime.json','vision-cost.json']:
  if (r/name).exists():summary[name]=json.loads((r/name).read_text())
 summary['physics_counter_note']='Checkpoint saves every25steps and includes resets; unless process_exit recorded, counter is a lower bound, never exact motor-action count.'
 original=json.loads((r/'source-manifest.json').read_text())
 changes=[]
 for name,h in original.items():
  p=r/'source'/name
  if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:changes.append(name)
 summary['original_source_files_changed']=changes
 summary['code_snapshot_hashes_match']=all(hashlib.sha256((r/'code'/Path(n).name).read_bytes()).hexdigest()==h for n,h in owner['script_hashes'].items()) if (r/'code').exists() else None
 (r/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
