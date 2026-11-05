from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path('/dev/shm/agent-rsi-lzgpu301-20261105/runtime');B=Path('/root/autodl-tmp/qian/budgeted-vla-rsi-migration');SOFT=Path('/root/autodl-tmp/qian/.dex_env/agent-rsi-standalone/software');C=Path('/root/autodl-tmp/qian/budgeted-vla-rsi');OLD='/root/autodl-tmp/Dex_runtime/agent-rsi'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert json.loads((B/'direct-transfer-status.json').read_text())['status']=='transferred_verified_pending_environment_path_binding_and_protocol_freeze'
changes=[];native=R/'vendor/robotwin-official-6dde571'; original_cfg=json.loads((C/'configs/skill-rsi-caller-dev2-lzgpu301-draft.json').read_text()); original_manifest={f['path']:f for f in json.loads((B/'source-file-manifest.json').read_text())}
for p in native.rglob('*'):
 if p.is_symlink():
  target=os.readlink(p)
  if target.startswith(OLD+'/'):
   new=str(R)+target[len(OLD):];p.unlink();p.symlink_to(new);changes.append({'path':str(p),'old_target':target,'new_target':new})
for n in ['curobo_left.yml','curobo_right.yml']:
 p=native/'assets/embodiments/aloha-agilex'/n;s=p.read_text();original=s.replace(str(R),OLD);before=hashlib.sha256(original.encode()).hexdigest();assert before==original_cfg['source_files'][str(p)];p.write_text(original.replace(OLD,str(R)));changes.append({'path':str(p),'old_sha256':before,'new_sha256':sha(p),'change':'absolute planning path only'})
p=SOFT/'envs/skillrsi/lib/python3.11/site-packages/robotwin_frozen_parent.pth';s=p.read_text();original=s.replace(str(SOFT),OLD+'/software');before=hashlib.sha256(original.encode()).hexdigest();assert before==original_manifest['software/envs/skillrsi/lib/python3.11/site-packages/robotwin_frozen_parent.pth']['sha256'];p.write_text(original.replace(OLD+'/software',str(SOFT)));changes.append({'path':str(p),'old_sha256':before,'new_sha256':sha(p),'change':'uv parent site path only'})
env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(SOFT/'python'),UV_CACHE_DIR='/dev/shm/agent-rsi-lzgpu301-20261105/uv-cache',TMPDIR=str(SOFT/'tmp'),CUDA_VISIBLE_DEVICES='',LD_LIBRARY_PATH=str(SOFT/'system/usr/lib/x86_64-linux-gnu'))
py=SOFT/'python/cpython-3.11.17-linux-x86_64-gnu/bin/python';uv='/home/lzgpu301/.local/bin/uv'
q=subprocess.run([uv,'venv','--allow-existing','--python',str(py),str(SOFT/'envs/skillrsi')],env=env,capture_output=True,text=True,timeout=60);(B/'skillrsi-uv-restore.log').write_text(q.stdout+q.stderr);q.check_returncode()
# Source mapping adjustments are explicit, not changes to published evaluator or primitive code.
p=C/'configs/skill-rsi-caller-dev2-lzgpu301-draft.json';cfg=json.loads(p.read_text());mapped={}
for path,digest in cfg['source_files'].items():
 new=path.replace(str(R)+'/software/',str(SOFT)+'/')
 if new in {x.get('path') for x in changes if x.get('change')=='absolute planning path only'}:
  assert any(x.get('old_sha256')==digest and x['path']==new for x in changes);digest=sha(new)
 assert sha(new)==digest,new
 mapped[new]=digest
cfg['source_files']=mapped;cfg['environment']['curobo']=str(SOFT/'envs/robotwin/lib/python3.11/site-packages/curobo');cfg['qwen_asset_receipt']='records/deploy-lzgpu301-20261105/qwen-assets-verified.json';dest=R/cfg['qwen_asset_receipt'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((B/'qwen-assets-verified.json').read_bytes());cfg['qwen_asset_receipt_sha256']=sha(dest)
cfg['deployment_state']='DRAFT_PENDING_ENV_IMPORTS_RESOURCE_CHECK_FREEZE';cfg['host_path_changes']=changes
p.write_text(json.dumps(cfg,indent=2)+'\n');(B/'path-relocations.json').write_text(json.dumps(changes,indent=2));(B/'source-pin-audit.json').write_text(json.dumps({'status':'passed','source_files':len(mapped),'path_only_changes':changes,'protocol_status':cfg['status'],'model_calls':0,'robot_episodes':0},indent=2));print(json.dumps({'sources':len(mapped),'changes':len(changes),'status':'pins_passed_pending_imports_and_freeze'}))
