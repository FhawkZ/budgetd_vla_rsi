"""Stage the frozen native RoboTwin archives; verify SHA before extraction."""
import concurrent.futures, fcntl, hashlib, json, os, shutil, signal, threading, time, zipfile
from pathlib import Path
from huggingface_hub import hf_hub_download
from robotwin import assets

root = Path(__file__).resolve().parents[1]
runtime = Path(os.environ['RSI_RUNTIME_ROOT'])
manifest = json.loads((root / 'configs/robotwin-assets.json').read_text())
assert manifest['revision'] == assets.ASSET_REVISION
output = Path(os.environ.get('RSI_DEPLOY_OUTPUT', str(runtime / 'outputs/native-backend-20261029-1400')))
output.mkdir(parents=True, exist_ok=True)
lock = (runtime / 'locks/robotwin-assets.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
dest = runtime / ('assets/robotwin-' + manifest['revision'][:8])
staging = dest.with_name(dest.name + '.staging')
archives = runtime / 'downloads/robotwin-assets'
state = {'status': 'running', 'pid': os.getpid(), 'started_unix': time.time(),
         'revision': manifest['revision'], 'model_calls': 0, 'gpu_jobs': 0,
         'verified_archives': [], 'workers': 3, 'files': {}, 'endpoint': 'https://hf-mirror.com'}
def save():
    state['updated_unix'] = time.time()
    p = output / 'assets-status.json'; t = p.with_suffix('.tmp')
    t.write_text(json.dumps(state, indent=2)); t.replace(p)
save()
state_lock = threading.Lock()
def terminated(signum, frame):
    # timeout sends to the whole process group; persist terminal state before exit.
    state.update(status='interrupted', error=f'signal {signum}; cached downloads retained')
    save()
    os._exit(128 + signum)
signal.signal(signal.SIGTERM, terminated)
signal.signal(signal.SIGINT, terminated)
def fetch(row):
    with state_lock:
        state['files'][row['path']] = 'downloading'; save()
    p = Path(hf_hub_download(repo_id=manifest['repository'], repo_type='dataset',
          revision=manifest['revision'], filename=row['path'], local_dir=archives,
          endpoint=state['endpoint'], token=False))
    assert p.stat().st_size == row['bytes'] and assets._sha256(p) == row['sha256'], 'Archive mismatch'
    with state_lock:
        state['files'][row['path']] = 'verified'
        state['verified_archives'].append(row); save()
try:
    assert shutil.disk_usage(runtime).free > (100 << 30), 'Insufficient asset staging space'
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(fetch, manifest['files']))
    if dest.exists():
        identity = assets.validate_root(dest)
        existing = json.loads((dest / assets.MANIFEST_NAME).read_text())
        assert existing['archives'] == {r['path']: r['sha256'] for r in manifest['files']}
    else:
        if staging.exists():
            raise RuntimeError('Incomplete staging exists; inspect before retrying extraction')
        staging.mkdir(parents=True)
        target = staging / 'assets'; target.mkdir()
        state['status'] = 'extracting'; save()
        expanded = 0
        for row in manifest['files']:
            p = archives / row['path']
            with zipfile.ZipFile(p) as z:
                expanded += sum(i.file_size for i in z.infolist())
            assert expanded < (150 << 30) and shutil.disk_usage(staging).free > expanded, 'Extraction disk bound'
            assets._safe_extract(p, target)
        (staging / assets.MANIFEST_NAME).write_text(json.dumps({'repository': manifest['repository'], 'revision': manifest['revision'], 'archives': {r['path']: r['sha256'] for r in manifest['files']}}, indent=2))
        assets.validate_root(staging); staging.rename(dest)
        identity = assets.validate_root(dest)
    state.update(status='complete', identity=identity, source_sha256=hashlib.sha256(Path(assets.__file__).read_bytes()).hexdigest()); save()
except Exception as e:
    state.update(status='failed', error=repr(e)); save(); raise
