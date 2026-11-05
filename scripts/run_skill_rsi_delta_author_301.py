"""One independent offline response. No robot execution or candidate import."""
import argparse,json,os,hashlib,subprocess,shutil
from pathlib import Path
from skill_rsi_delta_author import run_once,request_body
from skill_rsi_author_workspace import load_resources
from skill_rsi_candidate_artifact import seal
from qwen_service_owner_301 import service
from migration_evidence import persistent_trial
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--protocol-sha',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
 assert sha(a.protocol)==a.protocol_sha;cfg=json.loads(a.protocol.read_text());assert cfg['status']=='FROZEN' and cfg['run_id']=='skill-rsi-delta-author1-20261106-0730'
 assert cfg['max_qwen_calls_total']==1 and cfg['robot_episodes_max']==cfg['vla_calls_max']==0 and cfg['execute_candidate']==False
 for path,h in cfg['source_sha256'].items():assert sha(path)==h,path
 assert sha(cfg['input_manifest'])==cfg['input_manifest_sha256'];resources=load_resources(cfg['input_manifest']);request_body(resources,cfg)
 if a.check:print('delta input/source/budget pins verified; no model or robot');return
 rt=Path(os.environ['RSI_RUNTIME_ROOT']);persistent=Path(os.environ['RSI_PERSISTENT_RECORD_ROOT'])/'outputs';out=rt/'outputs'/cfg['run_id']
 assert not out.exists() and not (persistent/cfg['run_id']).exists()
 preflight=persistent/(cfg['run_id']+'-validator-preflight.json');assert not preflight.exists()
 subprocess.run([cfg['qwen_python'],str(ROOT/'scripts/check_qwen_runtime_contract.py'),'--output',str(preflight)],check=True,timeout=60,env=dict(os.environ,CUDA_VISIBLE_DEVICES=''))
 disk=shutil.disk_usage(persistent);assert disk.free>max(100*2**30,disk.total*.2)+cfg['expected_output_bytes']
 with persistent_trial(rt,persistent,cfg['run_id']):
  with service(cfg):
   report=run_once(resources,cfg,out)
   (out/'protocol.json').write_bytes(a.protocol.read_bytes())
   if report['status']=='compiled_pending_static_review':
    static=seal(out/'workspace',out/'sealed',cfg['upstream_runtime'],cfg['skill_name'])
    (out/'static-result.json').write_text(json.dumps(static,indent=2))
if __name__=='__main__':main()
