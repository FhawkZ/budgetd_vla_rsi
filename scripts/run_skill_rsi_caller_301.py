"""Explicit lzgpu301 GPU2/3 host adapter; unchanged native caller worker.
Do not run until the relocated protocol is independently FROZEN and pinned.
"""
import argparse,json,os
from pathlib import Path
import run_skill_rsi_caller as native
from gpu_idle_gate import wait_idle
from run_skill_rsi_native_v3 import gpu_read
from qwen_service_owner_301 import service
from migration_evidence import persistent_trial

def main():
 p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--protocol-sha',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
 assert native.sha(a.protocol)==a.protocol_sha
 cfg=json.loads(a.protocol.read_text())
 assert cfg['host']=='lzgpu301' and cfg['gpu']==3 and cfg['qwen_gpu']==2
 assert cfg['parent_protocol_sha256']=='151db4d79e342f4aede2a5cfe3e713f7e4486d57abc80fc1cb21d8b3b73fa564'
 assert cfg['max_qwen_calls_total']==8 and [c['seed'] for c in cfg['cases']]==[3455213,3446055]
 for n,sha in cfg['host_adapter_sha256'].items():assert native.sha(native.ROOT/n)==sha,n
 native.verify(cfg)
 if a.check:print('migrated sources and budget verified; no model or simulation');return
 runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
 assert not (runtime/'outputs'/cfg['id']).exists()
 assert not (runtime/'outputs'/(cfg['id']+'-qwen')).exists()
 for i in [2,3]:wait_idle(lambda i=i:gpu_read(i),lambda sample:None)
 receipt=runtime/'outputs'/(cfg['id']+'-resource-checks.jsonl')
 assert not receipt.exists()
 native.gpu_check=lambda gpu:wait_idle(lambda:gpu_read(gpu),lambda sample:native.append(receipt,sample))
 with persistent_trial(runtime,Path(os.environ["RSI_PERSISTENT_RECORD_ROOT"])/"outputs",cfg["id"]):
  with service(cfg):native.parent(cfg,a.protocol.resolve())
if __name__=='__main__':main()
