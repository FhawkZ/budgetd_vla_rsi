"""Read-only closure audit of the independently frozen constraint development pilot."""
import argparse, hashlib, json, math, os
from pathlib import Path
import numpy as np

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def audit(root, repo, runtime):
 root,repo,runtime=map(Path,(root,repo,runtime));report=json.loads((root/'report.json').read_text());cfg=json.loads((root/'protocol.json').read_text())
 assert report['status']=='completed' and json.loads((root/'CLOSE.json').read_text())['status']=='CLOSED'
 assert digest(root/'protocol.json')==report['protocol_sha256']
 files=[]
 def checked(p,expected=None):
  h=digest(p)
  if expected is not None:assert h==expected,str(p)
  files.append({'path':str(p),'sha256':h,'bytes':p.stat().st_size});return h
 for rel,h in cfg['code_sha256'].items():
  checked(repo/rel,h);checked(root/'code'/Path(rel).name,h)
 for row in cfg['programs'].values():checked(runtime/row['path'],row['sha256'])
 totals={'inferences':0,'prefixes':0,'images':0,'native_actions':0,'setup_entries':0,'resets':0,'daemon_exit0':0,'candidate_calls':0,'active_rule_calls':0,'nonzero_injection_calls':0,'guidance_steps':0,'vla_rpc_seconds':0.0}
 episodes=[];pairs={}
 for i,case in enumerate(cfg['cases']):
  d=root/f"{i:02d}-{case['task']}-s{case['seed']}";e=json.loads((d/'episode.json').read_text())
  assert e['status']=='completed' and all(e[k]==case[k] for k in ['task','seed','role','pair_index'])
  assert e['native_skill_attempts']==e['native_skill_actions']==0 and not e['patch_attempts']
  assert e['environment_reset_rpc']==1 and e['initial_reference_matches']
  assert e['native_task_language']==e['policy_task_language'] and e['native_episode_status']['actual_seed']==case['seed']
  for cam,h in e['initial_image_sha256'].items():checked(d/f'initial-{cam}.png',h)
  attempts=lines(d/'seed-attempts.jsonl');beg=[x for x in attempts if x['event']=='setup_begin'];end=[x for x in attempts if x['event']=='setup_return']
  assert len(beg)==len(end)==2 and {x['phase'] for x in beg}=={'setup_task','reset'}
  assert all(x['requested_seed']==x['actual_argument_seed']==case['seed'] for x in beg+end)
  assert len(e['daemon_after_cleanup'])==2 and all(x['returncode']==0 for x in e['daemon_after_cleanup'])
  trace=lines(d/'program-trace.jsonl');done=[x for x in trace if x['status']=='completed'];starts=[x for x in trace if x['status']=='started'];chunks=lines(d/'chunks.jsonl')
  assert len(done)==len(starts)==len(chunks)==e['vla_inferences']
  nzero=0;active=0;mindistance=float('inf');seconds=0.0;prior=0
  for j,(tr,st,ch) in enumerate(zip(done,starts,chunks),1):
   assert tr['index']==st['index']==j and tr['program_sha256']==cfg['programs'][case['role']]['sha256']
   inp=d/f'inference-{j:03d}.json';r=json.loads(inp.read_text());checked(inp);pred=inp.with_suffix('.npy');checked(pred,r['actions_sha256']);x=np.load(pred)
   assert r['index']==j and r['status']=='completed' and r['task_language']==e['native_task_language']
   for im in r['images'].values():checked(d/im['path'],im['sha256']);totals['images']+=1
   for arm in ['left','right']:
    expected=np.asarray(r['robot_state'][arm+'_eef_pose'][:3],dtype=np.float32)
    np.testing.assert_array_equal(np.asarray(tr['bindings'][arm+'_eef'],dtype=np.float32),expected)
   dist=float(np.linalg.norm(np.asarray(tr['bindings']['left_eef'])-tr['bindings']['right_eef']));mindistance=min(mindistance,dist)
   guide=tr['guidance'];assert len(guide)==(10 if case['role']=='candidate' else 0)
   if guide:
    assert all(g['active_rules']==(3 if dist<=0.2 else 0) for g in guide)
    assert all(math.isfinite(g['reward_m2']) and 0<=g['max_injected_xyz_velocity_m']<=.010001 for g in guide)
   active+=int(any(g['active_rules'] for g in guide));nzero+=int(any(g['max_injected_xyz_velocity_m']>0 for g in guide))
   selected=d/f'executed-prefix-{j:03d}.npy';checked(selected,ch['result']['selected_actions_sha256']);y=np.load(selected)
   np.testing.assert_array_equal(y,x[:min(50,cfg['horizon']-prior)])
   status=ch['result']['native_episode_status'];count=status['take_action_cnt']
   assert status['actual_seed']==case['seed'] and prior<count<=min(prior+50,cfg['horizon'])
   prior=count;seconds+=r['elapsed_seconds'];totals['guidance_steps']+=len(guide)
  assert prior==e['native_actions']
  totals['inferences']+=len(done);totals['prefixes']+=len(chunks);totals['native_actions']+=prior;totals['setup_entries']+=2;totals['resets']+=1;totals['daemon_exit0']+=2;totals['vla_rpc_seconds']+=seconds
  totals['candidate_calls']+=len(done) if case['role']=='candidate' else 0;totals['active_rule_calls']+=active;totals['nonzero_injection_calls']+=nzero
  row={'directory':d.name,'task':case['task'],'seed':case['seed'],'role':case['role'],'success':e['native_eval_success'],'vla_calls':len(done),'native_actions':prior,'active_rule_calls':active,'nonzero_injection_calls':nzero,'minimum_measured_eef_distance_m':mindistance,'vla_rpc_seconds':seconds,'wall_seconds':e['wall_seconds']}
  episodes.append(row);pairs.setdefault(case['pair_index'],{})[case['role']]=(d,e,row)
  for f in sorted(d.rglob('*')):
   if f.is_file() and not f.is_symlink():checked(f)
 paired=[]
 for k,rows in sorted(pairs.items()):
  a,ae,ar=rows['baseline'];b,be,br=rows['candidate']
  for key in ['initial_robot_state','initial_image_sha256','native_task_language']:assert ae[key]==be[key]
  first_equal=bool(np.array_equal(np.load(a/'inference-001.npy'),np.load(b/'inference-001.npy')))
  paired.append({'pair':k,'task':ar['task'],'seed':ar['seed'],'baseline':ar['success'],'candidate':br['success'],'initial_inputs_equal':True,'first_prediction_exact_equal':first_equal,'gain':not ar['success'] and br['success'],'loss':ar['success'] and not br['success']})
 assert totals['inferences']==report['total_vla_inferences']==164 and totals['native_actions']==report['native_actions']==8047
 summary={t:{role:{'successes':sum(x['success'] for x in episodes if x['task']==t and x['role']==role),'episodes':3,'vla_calls':sum(x['vla_calls'] for x in episodes if x['task']==t and x['role']==role),'native_actions':sum(x['native_actions'] for x in episodes if x['task']==t and x['role']==role)} for role in ['baseline','candidate']} for t in ['stack_blocks_two','handover_block']}
 unique={x['path']:x for x in files}
 return {'status':'passed_evidence_audit_candidate_rejected','protocol_sha256':report['protocol_sha256'],'planned':12,'completed':12,'invalid':0,'unstarted':0,'complete_pairs':6,'totals':totals,'tasks':summary,'pairs':paired,'episodes':episodes,'gpu1_allocation_seconds':report['gpu1_lock_interval_seconds'],'unused_vla_canceled':124,'verified_file_count':len(unique),'files':list(unique.values()),'decision':'close_measured_eef_constraint_subvariant; move to B. No useful intervention observed. All injections zero; outcome difference is not evidence of a harmful constraint effect. No accepted update, no strict RSI.','accepted_updates':0,'forgetting_after_update':None,'strict_rsi':0,'limitations':['development scenes supplied to proposer','native counter is not physics ticks','1200 adapted horizon, not official10000','no statistical equivalence or stable rate','no new generation/inference/simulation in audit']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=audit(a.root,Path(__file__).resolve().parents[1],os.environ['RSI_RUNTIME_ROOT']);a.output.mkdir(exist_ok=False)
 (a.output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['files','episodes']},indent=2))
