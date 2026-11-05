from pathlib import Path
import json,hashlib,os,sys,time,socket,importlib.metadata as m,subprocess
C=Path('/root/autodl-tmp/qian/budgeted-vla-rsi');R=Path('/dev/shm/agent-rsi-lzgpu301-20261105/runtime');B=Path('/root/autodl-tmp/qian/budgeted-vla-rsi-migration');SOFT=Path('/root/autodl-tmp/qian/.dex_env/agent-rsi-standalone/software');sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert json.loads((B/'direct-transfer-status.json').read_text())['status']=='transferred_verified_pending_environment_path_binding_and_protocol_freeze'
assert json.loads((B/'source-pin-audit.json').read_text())['status']=='passed'
cfg=json.loads((C/'configs/skill-rsi-caller-dev2-lzgpu301-draft.json').read_text())
metadata={k:m.version(k) for k in ['torch','torchvision','sapien','mplib','numpy','clip','ftfy','scikit-learn']}
for k,v in metadata.items():assert v==cfg['environment'][k],(k,v,cfg['environment'][k])
assert sys.version.split()[0]=='3.11.17';assert int(subprocess.check_output(['du','-sb',str(SOFT)],text=True).split()[0])<11*2**30
transfer=json.loads((B/'allocation-transfer.json').read_text());assert transfer['consumed_calls']==transfer['consumed_episodes']==transfer['additional_budget']==0
sys.path.insert(0,str(C/'scripts'));from run_skill_rsi_native_v3 import gpu_read
from gpu_idle_gate import wait_idle
resources={str(i):wait_idle(lambda i=i:gpu_read(i),lambda sample:None) for i in [2,3]}
for port in [8020,18029]:
 s=socket.socket();s.bind(('127.0.0.1',port));s.close()
for p in [R,Path('/root/autodl-tmp/qian')]:
 d=os.statvfs(p);resources[str(p)]={'free_bytes':d.f_bavail*d.f_frsize,'free_inodes':d.f_favail};assert d.f_favail>100000
assert resources[str(R)]['free_bytes']>max(100*2**30,.2*os.statvfs(R).f_blocks*os.statvfs(R).f_frsize)+cfg['expected_output_bytes']
assert resources['/root/autodl-tmp/qian']['free_bytes']>cfg['expected_output_bytes']+40*2**30
for suffix in ['', '-qwen']:assert not (R/'outputs'/(cfg['id']+suffix)).exists()
cfg.update(status='FROZEN',deployment_state='FROZEN_READY_NOT_LAUNCHED',frozen_unix=time.time(),pending_freeze_checks=[],allocation_transfer=transfer,migration_environment_verification=metadata,migration_audit_sha256=sha(B/'restored-files-audit.json'))
cfg['difference_disclosure'] += ['lzgpu301 host GPU2 Qwen/GPU3 simulator, explicit uv executable/data path relocation; models, dependencies and native assets byte matched before declared path-only edits.','Volatile model/asset copy has canonical original on201; runtime evidence mirrors to persistent301 disk every5seconds/finally; approved temporary11GiB executable environment storage.']
path=C/'configs'/(cfg['id']+'.json');assert not path.exists();path.write_text(json.dumps(cfg,indent=2)+'\n')
from run_skill_rsi_caller import verify
verify(cfg)
report={'status':'frozen_verified_not_launched','protocol':str(path),'sha256':sha(path),'metadata':metadata,'resources':resources,'source_pins':len(cfg['source_files']),'host_adapter_sha256':cfg['host_adapter_sha256'],'allocation_transfer':transfer,'model_calls':0,'robot_episodes':0,'time':time.time()};(B/'freeze.json').write_text(json.dumps(report,indent=2));print(json.dumps({'protocol':str(path),'sha256':sha(path),'status':report['status']}))
