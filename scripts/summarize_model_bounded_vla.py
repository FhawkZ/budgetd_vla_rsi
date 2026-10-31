"""Read-only reconciliation of closed reduced controller experiment."""
import argparse,collections,hashlib,json,os
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args();r=Path(os.environ['RSI_RUNTIME_ROOT'])/'outputs'/a.run_id;q=r.with_name(r.name+'-qwen')
read=lambda p:json.loads(p.read_text())
assert (r/'CLOSE.json').exists() and (q/'CLOSE.json').exists()
owner=read(r/'report.json');cfg=read(r/'protocol.json');model=read(q/'report.json')
def canonical(x):return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
paired=[]
for f in sorted((q/'server').glob('*-request.json')):
 idx=int(f.name.split('-')[0]);forward=q/'ledger'/f'{idx:03d}-forwarded.json'
 same=canonical(read(f))==canonical(read(forward));assert same
 g=read(f.with_name(f'{idx:04d}-generation.json'));audit=read(q/'ledger'/f'{idx:03d}-audit.json');assert g['usage']==audit['usage']
 paired.append(dict(index=idx,request_sha256=canonical(read(f)),usage=g['usage'],image_count=g['image_count']))
assert len(paired)==model['usage']['generations'] and model['token_ledger_match']
rows=[]
for i,c in enumerate(cfg['cases']):
 d=r/f"{i:02d}-{c['task']}-s{c['seed']}"
 if not (d/'episode.json').exists():rows.append(dict(task=c['task'],status='not_started'));continue
 ep=read(d/'episode.json');ds=[json.loads(x) for x in (d/'decisions.jsonl').read_text().splitlines()] if (d/'decisions.jsonl').exists() else []
 inf=[read(x) for x in sorted(d.glob('inference-*.json'))];chunks=[json.loads(x) for x in (d/'chunks.jsonl').read_text().splitlines()] if (d/'chunks.jsonl').exists() else []
 assert len(ds)<=ep['qwen_calls']
 prefix=[]
 for j,x in enumerate(chunks,1):
  pred=np.load(d/f'inference-{j:03d}.npy');sub=np.load(d/f'executed-prefix-{j:03d}.npy');prefix.append(bool(np.array_equal(pred[:len(sub)],sub)))
 row=dict(task=c['task'],seed=c['seed'],status=ep['status'],success=ep.get('native_eval_success') if ep['status']=='completed' else None,native_success_at_last_receipt=ep.get('native_eval_success'),action_count_is_lower_bound=ep['status']!='completed',completed_chunk_receipts=len(chunks),unreturned_inference_count=len(inf)-len(chunks),termination=ep.get('termination'),controller_error=ep.get('controller_error'),qwen_calls=ep['qwen_calls'],vla_calls=ep['vla_inferences'],native_actions=ep['native_actions'],tool_counts=dict(collections.Counter(x['decision']['action'] for x in ds)),prefix_choices=dict(collections.Counter(x['decision'].get('use_length') for x in ds if x['decision']['action']=='execute_vla_chunk')),initial_images_equal=ep.get('initial_images_equal'),initial_state_equal=ep.get('initial_state_equal'),native_language_equal=ep.get('policy_task_language')==c['instruction'],all_vla_languages_equal=all(x['task_language']==c['instruction'] for x in inf),all_returned_chunk_prefixes_exact=all(prefix) if prefix else None,vla_inference_rpc_seconds=sum(x['elapsed_seconds'] for x in inf),wall_seconds=ep['wall_seconds'])
 rows.append(row)
summary=dict(status=owner['status'],classification='reduced common-interface autonomous development; not original native reproduction or learning',rows=rows,qwen_usage=model['usage'],raw_forwarded_request_sha_and_usage_pairs=len(paired),token_ledger_exact=model['token_ledger_match'],gpu0_allocation_seconds=model['gpu_allocation_seconds'],gpu1_allocation_seconds=owner['GPU_allocation_seconds'],vla_inferences=owner['total_vla_inferences'],native_actions=owner['total_native_actions'],native_actions_are_lower_bound=any(x.get('action_count_is_lower_bound',True) for x in rows),unused_qwen_allowance_canceled=cfg['max_qwen_calls_total']-model['usage']['generations'],unused_vla_allowance_canceled=cfg['max_vla_inferences_total']-owner['total_vla_inferences'],accepted_updates=0,retention_after_update=None,strict_rsi_rounds=0,limitations=['Two historical development scenes only','No learned update; fixed50 comparison is descriptive with unequal actual model costs','Native action counts are not physics ticks or successful motion plans','Automatic native terminal handling; no extra stability evaluation'])
(r/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(r/'request-reconciliation.json').write_text(json.dumps(paired,indent=2)+'\n');print(json.dumps(summary,indent=2))
