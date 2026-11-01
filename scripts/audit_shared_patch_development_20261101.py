import os,json,hashlib,math
from pathlib import Path
import numpy as np
from hcl_robotwin_adapter import load_official,pair_metrics
R=Path(os.environ['RSI_RUNTIME_ROOT']);out=R/'outputs/shared-patch-audit-20261101';out.mkdir(exist_ok=False)
load=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=R/'outputs/official-owner-fixed50-dev10-20261101-0300';cand=R/'outputs/feedback-patch-dev10-20261101-1220';b=load(base/'report.json');c=load(cand/'report.json');assert c['status']=='completed' and len(c['episodes'])==10
rows=[];skills=[];prefixes=0;rpc=0;raw=[]
for i,(br,cr) in enumerate(zip(b['episodes'],c['episodes'])):
 a,e=br['result'],cr['result'];assert a['task']==e['task'] and a['seed']==e['seed'] and e['status']=='completed'
 for key in ['initial_robot_state','initial_image_sha256','native_task_language']:assert a[key]==e[key],(i,key)
 assert all(x['returncode']==0 for x in e['daemon_after_cleanup'])
 ep=cand/f"{i:02d}-{e['task']}-s{e['seed']}";bp=base/ep.name
 assert np.array_equal(np.load(ep/'inference-001.npy'),np.load(bp/'inference-001.npy'))
 records=[load(p) for p in sorted(ep.glob('inference-*.json'))];rpc+=sum(x['elapsed_seconds'] for x in records)
 for p in sorted(ep.glob('executed-prefix-*.npy')):
  arr=np.load(p);n=p.stem.rsplit('-',1)[1];pred=np.load(ep/f'inference-{n}.npy');assert np.array_equal(arr,pred[:len(arr)]);prefixes+=1
 for line in (ep/'native-skills.jsonl').read_text().splitlines():
  x=json.loads(line);r=x['rule'];arm=r['arm'];before=x['before']['robot_state'];after=x['after']['robot_state'];skills.append({'task':e['task'],'seed':e['seed'],'arm':arm,'target':r['gripper_target'],'gripper_before':before[arm+'_gripper'],'gripper_after':after[arm+'_gripper'],'eef_translation_m':float(np.linalg.norm(np.array(after[arm+'_eef_pose'][:3])-np.array(before[arm+'_eef_pose'][:3]))),'native_actions':x['native_actions'],'planning_failure':x['planning_failure']})
 rows.append({'task':e['task'],'seed':e['seed'],'before':a['native_eval_success'],'after':e['native_eval_success'],'baseline_vla':a['vla_inferences'],'candidate_vla':e['vla_inferences'],'candidate_native':e['native_actions']})
 for p in sorted(ep.rglob('*')):
  if p.is_file():raw.append({'path':str(p.relative_to(cand)),'bytes':p.stat().st_size,'sha256':sha(p)})
assert prefixes==c['total_vla_inferences']==170 and len(skills)==20
Optimizer,_,settings=load_official(R);op=Optimizer(record_dir=out/'hcl-gate',**settings)
refs,result=pair_metrics([x['result'] for x in b['episodes']],[x['result'] for x in c['episodes']],'handover_block',['stack_blocks_two'],[(x['task'],x['seed']) for x in rows],behavior_changed=True)
choice=op.select_best_candidate([{'candidate_id':'feedback_patch','validation_errors':[]}],{'feedback_patch':result},refs);assert choice is not None
exposed=[];checked=0
for p in (R/'outputs').rglob('episode.json'):
 try:x=load(p)
 except (OSError,ValueError):continue
 checked+=1
 if x.get('task') in ['stack_blocks_two','handover_block'] and x.get('seed') in range(100006,100011) and x.get('environment_reset_rpc',0)>0:exposed.append(str(p))
assert not exposed,exposed
report={'status':'development_audited_validation_required','classification':'paired development selection, not final test or causal mechanism proof','cases':rows,'baseline':{'stack':2,'handover':1,'episodes_per_task':5,'vla':186,'native_actions':9243,'gpu_seconds':b['GPU_allocation_seconds']},'candidate':{'stack':2,'handover':2,'episodes_per_task':5,'vla':170,'native_actions':8482,'gpu_seconds':c['GPU_allocation_seconds'],'vla_rpc_seconds':rpc,'skill_actions':sum(s['native_actions'] for s in skills)},'paired_old_success_losses':result['historical_anchor_metrics']['forget_count'],'old_recoveries':result['historical_anchor_metrics']['recovered_count'],'hcl_development_gate_passed':True,'hcl_selection_history':op.history,'accepted_shared_updates':0,'forgetting_after_accepted_update':None,'strict_rsi_rounds':0,'all_initials_equal':True,'first_predictions_exactly_equal':True,'prediction_prefixes_verified':prefixes,'skill_audit':skills,'raw_files_hashed':len(raw),'unseen_seed_audit':{'scope':'currentruntime outputs episode records; complements local prior-record search','episode_files_checked':checked,'reset_exposure_matches':exposed,'reserved_seeds':list(range(100006,100011))},'limitations':['One newly successful development case, not a stable success-rate gain.','Holding/settling/time-budget effects and stochastic execution not identified causally.','No terminal stability test; native counter is not physical ticks.','Gate adapter is not full HCL paper reproduction.','Candidate is frozen; no further model call, shared deployment only after independent validation.']}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'raw-manifest.json').write_text(json.dumps(raw,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['status','candidate','paired_old_success_losses','raw_files_hashed','unseen_seed_audit']}))
