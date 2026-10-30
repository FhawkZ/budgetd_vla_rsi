"""Read-only CPU audit of actual LingBot transforms and closed VLA traces."""
import argparse,hashlib,json,os,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch,yaml
from transformers import AutoTokenizer
from lingbotvla.data.vla_data.utils import FeatureTransform

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
 r=Path(os.environ['RSI_RUNTIME_ROOT']);model=r/'models/LingBot-VLA-RoboTwin-EEF-e727b46c';run=r/'outputs/vla-publiclang-dev2-20261030-1040';site=Path(sys.prefix)/'lib/python3.11/site-packages';src=r/'vendor/RPent-a744bd5f128ebef3cb8c6736cf7cd98adff681f1'
 cfg=yaml.safe_load((model/'lingbotvla_cli.yaml').read_text());data=SimpleNamespace(**cfg['data'])
 tr=FeatureTransform(str(model/'configs/robot_configs/robotwin_eef.yaml'),data,None,None,norm_stats_path=str(model/'norm_stats/robotwin_eef.json'))
 tok=AutoTokenizer.from_pretrained(model/'qwen_base',local_files_only=True)
 rows=[]
 for ep in sorted(run.glob('*/episode.json')):
  d=json.loads(ep.read_text());f=ep.parent;first=json.loads((f/'inference-001.json').read_text());state=first['robot_state'];x=np.asarray(state['left_eef_pose']+[state['left_gripper']]+state['right_eef_pose']+[state['right_gripper']],dtype=np.float32)
  ac=np.concatenate([np.load(p)for p in sorted(f.glob('inference-*.npy'))]);v={'observation.state':torch.tensor(x),'action':torch.tensor(ac,dtype=torch.float32)}
  v.update({k:torch.zeros(3,2,2)for k in tr.org_features['images']})
  conv=tr.convert_features(v);recovered=tr.reverse_features(tr.normalizer.unnormalize(tr.normalizer.normalize({k:z.clone() for k,z in conv.items()})))
  error=max(float(torch.max(torch.abs(recovered[k]-z)))for k,z in v.items());assert error<1e-5
  assert not any(tr.action_subtract_state.values())
  langs=[]
  for label in ['native_task_language','policy_task_language']:
   text=d[label];ids=tok('<bos>'+text+'\n')['input_ids'];langs.append({'kind':label,'text':text,'wrapped_tokens':len(ids),'max_tokens':72,'truncated':len(ids)>72})
  rows.append({'task':d['task'],'seed':d['seed'],'roundtrip_max_abs_error':error,'action_shape':list(ac.shape),'finite':bool(np.isfinite(ac).all()),'quaternion_norm_ranges':[[float(np.linalg.norm(ac[:,j:j+4],axis=1).min()),float(np.linalg.norm(ac[:,j:j+4],axis=1).max())]for j in [3,11]],'gripper_range':[float(ac[:,[7,15]].min()),float(ac[:,[7,15]].max())],'languages':langs})
 paths=[site/'deploy/lingbot_vla_policy.py',site/'lingbotvla/data/vla_data/utils.py',site/'lingbotvla/data/vla_data/transform.py',site/'robotwin/envs/_base_task.py',model/'configs/robot_configs/robotwin_eef.yaml',model/'norm_stats/robotwin_eef.json',src/'robots/robotwin/vla_client.py',src/'robots/robotwin/primitives.py',src/'robots/robotwin/rlinf_env.py']
 result={'classification':'read-only CPU source and saved-tensor audit; not motion qualification','status':'passed_numeric_transform_checks','model_generations':0,'new_simulation_steps':0,'normalization':'checkpoint bounds_99;actual convert->normalize->unnormalize->reverse roundtrip','action_convention':'absolute left xyz+wxyz+gripper,right xyz+wxyz+gripper; subtract_state false; native ee','chunk_contract':'50 EEF waypoints then new observation; each waypoint native planner trajectory, not50physics ticks or fixed50Hz','prompt_parameter':'official lingbot_act(prompt=...) explicitly ignored; only env.get_task_language sent to model','rows':rows,'source_hashes':{str(p):sha(p) for p in paths},'limitations':['No semantic image or grasp accuracy guarantee','Native planner may reject a waypoint while action counter advances; need readonly telemetry before causal claim','Prior failed seeds are development only; public vs native language and random scene remain confounded before paired diagnosis']}
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
