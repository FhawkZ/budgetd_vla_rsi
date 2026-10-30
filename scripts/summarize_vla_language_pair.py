"""Summarize a CLOSED development language contrast; no model or simulator calls."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from PIL import Image

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('native');a=ap.parse_args();n=Path(a.native)
 cfg=json.loads((n/'protocol.json').read_text());p=Path(cfg['paired_closed_reference'])
 assert sha(p/'protocol.json')==cfg['paired_reference_protocol_sha256']
 before=json.loads((p/'report.json').read_text());after=json.loads((n/'report.json').read_text())
 assert before['status']=='completed' and after['status']=='completed','both owners must finish before summary'
 rows=[]
 for arm in after['episodes']:
  key=arm['case'];ref=next(x for x in before['episodes']if x['case']==key);old=ref['result'];new=arm['result']
  d1=next(p.glob('*-'+key['task']+'-s'+str(key['seed'])));d2=next(n.glob('*-'+key['task']+'-s'+str(key['seed'])))
  i1=json.loads((d1/'inference-001.json').read_text());i2=json.loads((d2/'inference-001.json').read_text())
  images={}
  for name,x in i1['images'].items():
   aa=np.array(Image.open(d1/x['path']),dtype=float);bb=np.array(Image.open(d2/i2['images'][name]['path']),dtype=float)
   images[name]={'same_sha':x['sha256']==i2['images'][name]['sha256'],'mean_abs_pixel_difference':float(np.abs(aa-bb).mean()),'max_abs_pixel_difference':float(np.abs(aa-bb).max())}
  same_state=i1['robot_state']==i2['robot_state'];same_images=all(x['same_sha']for x in images.values())
  assert new['policy_task_language']==old['native_task_language'],'native instruction changed between runs'
  traces=[json.loads(x.read_text())for x in d2.glob('inference-*.json')]
  assert len(traces)==new['vla_inferences'] and all(x['task_language']==new['policy_task_language']for x in traces)
  rows.append({'task':key['task'],'seed':key['seed'],'initial_images':images,'initial_robot_state_equal':same_state,'initial_observation_exact_match':same_images and same_state,'public_success':old['native_eval_success'],'native_success':new['native_eval_success'],'public_vla_calls':old['vla_inferences'],'native_vla_calls':new['vla_inferences'],'public_actions':old['native_actions'],'native_actions':new['native_actions'],'public_language':old['policy_task_language'],'native_language':new['policy_task_language'],'native_inference_rpc_seconds':sum(x.get('elapsed_seconds',0)for x in traces),'inference_language_verified':True})
 summary={'status':'closed_completed','classification':'posthoc paired development diagnosis, not independent final test or harness method comparison','new_protocol_sha256':sha(n/'protocol.json'),'reference_protocol_sha256':sha(p/'protocol.json'),'rows':rows,'new_vla_calls':after['total_vla_inferences'],'new_native_actions':after['total_native_actions'],'new_GPU1_allocation_seconds':after['GPU_allocation_seconds'],'new_qwen_calls':0,'unused_vla_allowance_canceled':cfg['max_vla_inferences_total']-after['total_vla_inferences'],'initial_observations_all_exact_match':all(x['initial_observation_exact_match']for x in rows),'accepted_updates':0,'retention_after_update':None,'strict_rsi_rounds':0,'limitations':['Two development cases chosen for failure diagnosis; not stable success rate','If first observations differ, language-only causal attribution invalid','Even matching inputs do not prove deterministic later physics/GPU generation','No old protocol reopened; no success-seed selection or expert actions']}
 (n/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(n/'CLOSE.json').write_text(json.dumps({'closed_unix':time.time(),'unused_allowance_canceled':summary['unused_vla_allowance_canceled'],'reopen_allowed':False},indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
