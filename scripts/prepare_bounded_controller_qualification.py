from pathlib import Path
import json,hashlib,os
root=Path('/root/autodl-tmp/budgeted-vla-rsi');runtime=Path('/root/autodl-tmp/Dex_runtime/agent-rsi')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
s=(root/'scripts/qualify_qwen30b_contract2.py').read_text()
s=s.replace("cfg['max_calls']==2","cfg['max_calls']==4").replace('model_calls_cap=2','model_calls_cap=4').replace("'--max-calls','2'","'--max-calls','4'")
a=s.index('  from structured_qwen import validate_output');b=s.index("  report['status']='passed'",a)
s=s[:a]+'''  from bounded_controller import Controller
  import numpy as np
  from PIL import Image
  tools=json.loads((ROOT/'configs/bounded-vla-interface-v1.json').read_text())['tools']
  observation=dict(task_language=cfg['cached_observation']['task_language'],robot_state=cfg['cached_observation']['robot_state'],views={})
  for name,item in cfg['cached_observation']['images'].items():
   path=RUNTIME/item['path'];assert digest(path)==item['sha256']
   observation['views'][name]={'rgb':np.array(Image.open(path))}
  endpoint='http://127.0.0.1:18029/v1/chat/completions'
  c=Controller(tools,observation,endpoint,out/'autonomous-initial',1)
  decision=c.decide({'remaining_inferences':48,'remaining_observations':48,'remaining_native_actions':1200})
  report['results'].append(dict(kind='cached_initial_autonomous_choice',decision=decision,robot_executed=False));save(out/'report.json',report)
  c=Controller(tools,observation,endpoint,out/'observe-roundtrip',2)
  c.history.append({'role':'user','content':'Transport qualification only: call observe once now. This is a prescribed branch fixture, not a robot task decision.'})
  decision=c.decide({'remaining_inferences':48,'remaining_observations':48,'remaining_native_actions':1200})
  assert decision=={'action':'observe'},'prescribed observe branch not covered'
  c.feedback({'qualification':'cached camera return; no simulator execution'},observation)
  decision=c.decide({'remaining_inferences':48,'remaining_observations':47,'remaining_native_actions':1200})
  report['results'].append(dict(kind='cached_observe_tool_image_roundtrip',decision=decision,robot_executed=False));save(out/'report.json',report)
  c=Controller(tools,observation,endpoint,out/'exhausted-execution',1)
  decision=c.decide({'remaining_inferences':0,'remaining_observations':0,'remaining_native_actions':0})
  assert decision=={'action':'stop'},'zero execution budget must stop'
  report['results'].append(dict(kind='zero_execution_budget_stop',decision=decision,robot_executed=False))
  body=json.loads((out/'exhausted-execution/001-request.json').read_text())
  try:request(body);raise AssertionError('budget allowed fifth request')
  except urllib.error.HTTPError as e:
   payload=e.read().decode();assert e.code==400 and 'budget exhausted' in payload;report['hard_budget_rejection_verified']=True
''' + s[b:]
s=s.replace('"""Independent three-generation qualification; never executes robot tools.\nTwo frozen development inputs + one free-text canary, then hard budget refusal.\n"""','"""Four-generation reduced-controller cached transport qualification; zero robot episodes."""')
runner=root/'scripts/qualify_bounded_controller.py';assert not runner.exists();runner.write_text(s)
cfg=json.loads((root/'configs/qwen30b-contract2-20261031-0700.json').read_text());cfg.update(run_id='bounded-controller-qual4-20261031-1630',max_calls=4,classification='reduced_controller_cached_transport_qualification_not_autonomous_task_score',closed_predecessor=None,protocol_scope='Independent4call cached initial free choice, prescribed observe branch then image feedback free choice, zero execution budget stop. Fifthrequest hardrefused; no robot action; stop on failed qualification.',inputs=[])
cfg.pop('prelaunch_amendment',None)
d=runtime/'outputs/bounded-vla-pair4-20261031-1130/00-stack_blocks_two-s2026103011';o=json.loads((d/'inference-001.json').read_text());cfg['cached_observation']=dict(task_language=o['task_language'],robot_state=o['robot_state'],images={k:dict(path=str((d/v['path']).relative_to(runtime)),sha256=v['sha256']) for k,v in o['images'].items()})
cfg['code_sha256'].pop('scripts/qualify_qwen30b_contract2.py')
for rel in ['scripts/bounded_controller.py','scripts/qualify_bounded_controller.py','configs/bounded-vla-interface-v1.json']:cfg['code_sha256'][rel]=sha(root/rel)
p=root/'configs/bounded-controller-qual4-20261031-1630.json';assert not p.exists();p.write_text(json.dumps(cfg,indent=2)+'\n');print('SHA',sha(p))
