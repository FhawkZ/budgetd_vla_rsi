import copy,hashlib,json,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];R=Path(os.environ['RSI_RUNTIME_ROOT'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
runner=ROOT/'scripts/run_bounded_vla_pilot.py';s=runner.read_text().replace("cfg['max_vla_inferences_total']==144", "cfg['max_vla_inferences_total']==192")
s=s.replace('    assert digest(ROOT/"scripts/bounded_vla.py")==cfg["interface_sha256"]','    assert digest(ROOT/"scripts/bounded_vla.py")==cfg["interface_sha256"]\n    receipt=Path(os.environ["RSI_RUNTIME_ROOT"])/cfg["cpu_receipt"]\n    assert digest(receipt)==cfg["cpu_receipt_sha256"] and json.loads(receipt.read_text())["status"]=="passed"')
runner.write_text(s)
cfg=json.loads((ROOT/'configs/vla-native-language-pair2-20261030-frozen.json').read_text());cfg.update(classification='common_bounded_vla_schedule_diagnostic',run_id='bounded-vla-pair4-20261031-1130',max_episodes=4,max_vla_inferences_per_episode=48,max_vla_inferences_total=192,episode_wall_seconds=1200,total_wall_seconds=4800,runner_sha256=sha(runner),interface_sha256=sha(ROOT/'scripts/bounded_vla.py'),frozen_unix=time.time())
cfg.pop('use_length',None)
manifest=json.loads((ROOT/'configs/rpent30b-native-dev64-20261031-0710.json').read_text());cases=[]
for c in manifest['cases']:
 previous=next((R/'outputs/vla-native-language-pair2-20261030-1510').glob('*-'+c['task']+'-s'+str(c['seed'])))
 initial=json.loads((previous/'inference-001.json').read_text())
 for length in [50,25]:cases.append(dict(task=c['task'],seed=c['seed'],use_length=length,instruction=c['instruction'],initial_image_sha256=c['initial_image_sha256'],initial_robot_state=initial['robot_state']))
cfg['cases']=cases
receipt=R/'outputs/bounded-vla-prepare-20261031-1120/cpu-native-equivalence.json';cfg.update(cpu_receipt=str(receipt.relative_to(R)),cpu_receipt_sha256=sha(receipt))
cfg['limitations']=['Four paired development episodes on two already-used seeds, not final test or stable success rates.','Prefix50reproduces native dispatch; prefix25is explicit common-executor adaptation: unchanged model observation/action prediction but execute shorter prefix before fresh inference. Original tool/schema remains unchanged.','Equal1200native-actionhorizon and48inferencecaps percase; actualcost can differ. Not equal-cost method superiority; report success and actualcost jointly.','No Qwen/no learned high-level policy/no update/no RSI. Fixed-harness execution only; no manual/expert action, forced model action or episode replay.','No automatic retry or resampling; initialization or infrastructure error cancels remainder. All unusedallocation canceled.','Native action counter not exactphysicsticks or successfulplanning count. Retention is not measured without realsharedupdate.']
cfg['cpu_unit_tests']=6;cfg['independent_new_budget']=True;cfg['old_protocols_remain_closed']=True
p=ROOT/'configs/bounded-vla-pair4-20261031-1130.json';assert not p.exists();p.write_text(json.dumps(cfg,indent=2)+'\n');print(sha(p))
