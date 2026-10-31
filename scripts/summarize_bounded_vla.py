"""Closed four-case diagnostic: do not select schedules or feed final tests back."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args();r=Path(a.output);assert (r/'CLOSE.json').exists()
read=lambda p:json.loads(p.read_text())
owner=read(r/'report.json');cfg=read(r/'protocol.json');rows=[]
for i,c in enumerate(cfg['cases']):
 d=r/f"{i:02d}-{c['task']}-s{c['seed']}"
 if not (d/'episode.json').exists():rows.append(dict(task=c['task'],prefix=c['use_length'],status='not_started'));continue
 ep=read(d/'episode.json');inf=[read(x) for x in sorted(d.glob('inference-*.json'))];chunks=[json.loads(x) for x in (d/'chunks.jsonl').read_text().splitlines()] if (d/'chunks.jsonl').exists() else []
 first=inf[0] if inf else None
 prefixes=[]
 for j,chunk in enumerate(chunks,1):
  prediction=np.load(d/f'inference-{j:03d}.npy');selected=np.load(d/f'executed-prefix-{j:03d}.npy');prefixes.append(bool(np.array_equal(selected,prediction[:len(selected)])))
 row=dict(case=i,task=c['task'],seed=c['seed'],prefix=c['use_length'],status=ep['status'],success=ep.get('native_eval_success'),actions=ep.get('native_actions'),vla_calls=ep.get('vla_inferences'),native_language_equal=ep.get('policy_task_language')==c['instruction'],initial_images_equal=({k:v['sha256'] for k,v in first['images'].items()}==c['initial_image_sha256']) if first else None,initial_state_equal=first['robot_state']==c['initial_robot_state'] if first else None,all_inference_languages_equal=all(x['task_language']==c['instruction'] for x in inf),all_executed_arrays_are_exact_prediction_prefixes=all(prefixes) if prefixes else None,prefixes_checked=len(prefixes),inference_rpc_seconds=sum(x.get('elapsed_seconds',0) for x in inf),wall_seconds=ep.get('wall_seconds'),error=ep.get('error'))
 rows.append(row)
pairs=[]
for task in ['stack_blocks_two','handover_block']:
 pair=[x for x in rows if x['task']==task]
 if len(pair)!=2 or any(x['status']!='completed' for x in pair):continue
 paths=[r/f"{x['case']:02d}-{task}-s{x['seed']}" for x in pair]
 a0=np.load(paths[0]/'inference-001.npy');b0=np.load(paths[1]/'inference-001.npy')
 pairs.append(dict(task=task,first_prediction_exact_equal=bool(np.array_equal(a0,b0)),first_prediction_max_abs_diff=float(np.max(np.abs(a0-b0))),second_inference_state_equal=read(paths[0]/'inference-002.json')['robot_state']==read(paths[1]/'inference-002.json')['robot_state'] if all((d/'inference-002.json').exists() for d in paths) else None,success50=pair[0]['success'],success25=pair[1]['success'],calls50=pair[0]['vla_calls'],calls25=pair[1]['vla_calls']))
summary=dict(classification='paired development executor diagnosis; fixed scheduling, no learned high-level Agent or RSI',status=owner['status'],rows=rows,pairs=pairs,total_vla_inferences=owner['total_vla_inferences'],total_native_actions=owner['total_native_actions'],GPU_allocation_seconds=owner['GPU_allocation_seconds'],inference_rpc_seconds=sum(x.get('inference_rpc_seconds',0) for x in rows),qwen_calls=0,accepted_updates=0,retention_after_update=None,strict_rsi_rounds=0,unused_inference_allowance_canceled=cfg['max_vla_inferences_total']-owner['total_vla_inferences'],limitations=['Two historical development scenes, not stable task rates','Equal horizons/caps, potentially unequal consumedcompute: not a fair-method ranking','No persistent update or retention test','Native actions not exact physics ticks or successful motion plans'])
(r/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
