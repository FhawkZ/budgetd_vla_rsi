"""Independent corrected-caller deployment; unchanged closed worker and source pins."""
import argparse,json,os,subprocess,shutil,time
from pathlib import Path
import run_skill_rsi_caller as native
from gpu_idle_gate import wait_idle
from run_skill_rsi_native_v3 import gpu_read
from qwen_service_owner_301 import service
from migration_evidence import persistent_trial

def verify(cfg):
 assert cfg['id']=='skill-rsi-corrected-caller-dev2-20261105-1630'
 assert cfg['host']=='lzgpu301' and cfg['gpu']==3 and cfg['qwen_gpu']==2
 assert cfg['previous_closed_protocol_sha256']=='a875e755a11e1d15a4f1a743e4bc3a550f53daa3919a654911536fe7cb93abaa'
 assert cfg['budget_relationship']=='independent_new_budget; all prior allowances canceled, no transferred or reused remainder'
 assert cfg['max_qwen_calls_total']==8 and cfg['attempts_max']==2
 manifest=native.ROOT/cfg['seed_manifest']
 assert native.sha(manifest)==cfg['seed_selection_sha256']
 assert [c['seed'] for c in cfg['cases']]==json.loads(manifest.read_text())['selected']
 for n,sha in cfg['host_adapter_sha256'].items():assert native.sha(native.ROOT/n)==sha,n
 native.verify(cfg)

def main():
 p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--protocol-sha',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
 assert native.sha(a.protocol)==a.protocol_sha
 cfg=json.loads(a.protocol.read_text());verify(cfg)
 if a.check:print('corrected-caller pins, independent budget and deterministic seeds verified; zero model/robot calls');return
 runtime=Path(os.environ['RSI_RUNTIME_ROOT']);persistent=Path(os.environ['RSI_PERSISTENT_RECORD_ROOT'])/'outputs'
 for base in (runtime/'outputs',persistent):
  assert not (base/cfg['id']).exists()
  assert not (base/(cfg['id']+'-qwen')).exists()
 assert not (persistent/(cfg['id']+'-mirror.json')).exists()
 preflight=persistent/(cfg['id']+'-validator-preflight.json');assert not preflight.exists()
 persistent.mkdir(parents=True,exist_ok=True)
 # CPU actual post-generation validator, using the exact server interpreter.
 env=dict(os.environ,CUDA_VISIBLE_DEVICES='')
 subprocess.run([cfg['qwen_python'],str(native.ROOT/'scripts/check_qwen_runtime_contract.py'),'--output',str(preflight)],env=env,check=True,timeout=60)
 assert json.loads(preflight.read_text())['status']=='passed'
 # Original approved environment exception; reserve enough persistent space for this bounded output.
 assert shutil.disk_usage(persistent).free > cfg['expected_output_bytes']+10*1024**3
 assert os.statvfs(persistent).f_favail>100000
 for i in (2,3):wait_idle(lambda i=i:gpu_read(i),lambda sample:None)
 receipt=runtime/'outputs'/(cfg['id']+'-resource-checks.jsonl');assert not receipt.exists()
 native.gpu_check=lambda gpu:wait_idle(lambda:gpu_read(gpu),lambda sample:native.append(receipt,sample))
 with persistent_trial(runtime,persistent,cfg['id']):
  with service(cfg):native.parent(cfg,a.protocol.resolve())
if __name__=='__main__':main()
