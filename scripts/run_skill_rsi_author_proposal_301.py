"""Offline author proposal owner; no candidate imports or robot execution."""
import argparse,json,os,hashlib,subprocess,shutil
from pathlib import Path
from skill_rsi_author_loop import run_author
from skill_rsi_author_workspace import load_resources
from skill_rsi_candidate_artifact import seal
from qwen_service_owner_301 import service
from migration_evidence import persistent_trial
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--protocol-sha',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
 assert sha(a.protocol)==a.protocol_sha;cfg=json.loads(a.protocol.read_text());assert cfg['status']=='FROZEN' and cfg['run_id']=='skill-rsi-author-proposal8-20261105-2130'
 assert cfg['max_qwen_calls_total']==8 and cfg['robot_episodes_max']==cfg['vla_calls_max']==0 and cfg['execute_candidate']==False
 for path,h in cfg['source_sha256'].items():assert sha(path)==h,path
 assert sha(cfg['input_manifest'])==cfg['input_manifest_sha256'];resources=load_resources(cfg['input_manifest'])
 if a.check:print('author input/source/budget pins verified; no model or robot');return
 rt=Path(os.environ['RSI_RUNTIME_ROOT']);persistent=Path(os.environ['RSI_PERSISTENT_RECORD_ROOT'])/'outputs';persistent.mkdir(parents=True,exist_ok=True);out=rt/'outputs'/cfg['run_id']
 assert not out.exists() and not (persistent/cfg['run_id']).exists()
 preflight=persistent/(cfg['run_id']+'-validator-preflight.json');assert not preflight.exists()
 subprocess.run([cfg['qwen_python'],str(ROOT/'scripts/check_qwen_runtime_contract.py'),'--output',str(preflight)],check=True,timeout=60,env=dict(os.environ,CUDA_VISIBLE_DEVICES=''))
 assert shutil.disk_usage(persistent).free>10*1024**3+cfg['expected_output_bytes']
 with persistent_trial(rt,persistent,cfg['run_id']):
  with service(cfg):
   report=run_author(resources,cfg['objective'],out,8,cfg['author_wall_seconds'])
   (out/'protocol.json').write_bytes(a.protocol.read_bytes())
   if report['status']=='submitted_unaccepted_not_executed':
    static=seal(out/'workspace',out/'sealed',cfg['upstream_runtime'],cfg['skill_name'])
    (out/'static-result.json').write_text(json.dumps(static,indent=2))
if __name__=='__main__':main()
