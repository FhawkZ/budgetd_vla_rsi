"""Bounded CPU compilation of the pinned cuRobo source for the robotwin uv env.
Wait only for the existing source transfer; never launch a duplicate download.
No GPU import, model generation, robot reset or experiment is performed.
"""
import fcntl
import hashlib
import importlib.metadata as metadata
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
runtime = Path(os.environ['RSI_RUNTIME_ROOT'])
output = Path(os.environ['RSI_DEPLOY_OUTPUT'])
spec = json.loads((root / 'configs/native-sources.json').read_text())['curobo']
source = runtime / 'vendor' / ('curobo-' + spec['commit'])
build = runtime / 'software/build' / ('curobo-' + spec['commit'])
expected_python = runtime / 'software/envs/robotwin/bin/python'
assert Path(sys.prefix) == expected_python.parent.parent, 'Use uv robotwin environment'
lock = (runtime / 'locks/build-curobo.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
state = {'status': 'waiting_source', 'pid': os.getpid(), 'started_unix': time.time(),
         'source_commit': spec['commit'], 'wait_limit_seconds': 5700, 'build_limit_seconds': 1800,
         'max_build_jobs': 2, 'cuda_arch': '12.0', 'cuda_home': '/usr/local/cuda-12.8',
         'model_calls': 0, 'task_episodes': 0, 'gpu_jobs': 0}

def save():
    state['updated_unix'] = time.time()
    p = output / 'curobo-build.json'; t = p.with_suffix('.tmp')
    t.write_text(json.dumps(state, indent=2)); t.replace(p)

active_process = None

def bounded_run(command, *, env, log, timeout):
    global active_process
    active_process = subprocess.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
    try:
        code = active_process.wait(timeout=timeout)
        if code:
            raise subprocess.CalledProcessError(code, command)
    except BaseException:
        try: os.killpg(active_process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        active_process.wait()
        raise
    finally:
        active_process = None

def interrupted(signum, frame):
    if active_process is not None:
        try: os.killpg(active_process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    state.update(status='interrupted', error=f'signal {signum}'); save(); os._exit(128+signum)

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
save()
try:
    deadline = time.monotonic() + 5700
    while not (source / '.source-receipt.json').exists():
        receipt_path = output / 'curobo-source.json'
        if receipt_path.exists():
            try: transfer = json.loads(receipt_path.read_text())
            except json.JSONDecodeError: transfer = {}
            assert transfer.get('status') != 'failed', 'Source transfer failed; no build or automatic retry'
        assert time.monotonic() < deadline, 'Source wait bound reached'
        save(); time.sleep(30)
    receipt = json.loads((source / '.source-receipt.json').read_text())
    assert receipt['commit'] == spec['commit'] and receipt['status'] == 'complete'
    archive = source.with_name(source.name + '.tar.gz')
    h = hashlib.sha256()
    with archive.open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''): h.update(chunk)
    assert h.hexdigest() == receipt['archive_sha256'], 'Source archive identity mismatch'
    assert shutil.disk_usage(runtime).free > (30 << 30)
    assert not build.exists(), 'Existing build must be audited before retry'
    shutil.copytree(source, build)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', CUDA_HOME=state['cuda_home'],
               TORCH_CUDA_ARCH_LIST='12.0', MAX_JOBS='2', CMAKE_BUILD_PARALLEL_LEVEL='2',
               OMP_NUM_THREADS='2', SETUPTOOLS_SCM_PRETEND_VERSION='0.7.8')
    env['PATH'] = state['cuda_home'] + '/bin:' + env['PATH']
    before = {re.sub(r'[-_.]+', '-', d.metadata['Name']).lower(): d.version for d in metadata.distributions()}
    state.update(status='building', source_archive_sha256=h.hexdigest(),
                 torch_version=metadata.version('torch'), build_started_unix=time.time()); save()
    with (output / 'curobo-build.log').open('w') as log:
        bounded_run([os.environ['UV_BIN'], 'pip', 'install', '--python', str(expected_python),
                        '--no-deps', '--no-build-isolation', str(build)],
                       env=env, log=log, timeout=1800)
        bounded_run([os.environ['UV_BIN'], 'pip', 'check', '--python', str(expected_python)],
                       env=env, log=log, timeout=120)
    after = {re.sub(r'[-_.]+', '-', d.metadata['Name']).lower(): d.version for d in metadata.distributions()}
    changed = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    assert set(changed) <= {'nvidia-curobo'} and after.get('nvidia-curobo') == '0.7.8', changed
    dist = metadata.distribution('nvidia-curobo')
    extensions = [Path(dist.locate_file(p)) for p in dist.files if str(p).endswith('.so')]
    assert len(extensions) >= 5, 'Missing compiled CUDA extension artifacts'
    state.update(status='built_not_gpu_qualified', package_version='0.7.8', changed_packages=changed,
                 extensions={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in extensions},
                 finished_unix=time.time())
    save()
except Exception as exc:
    state.update(status='failed', error=repr(exc)); save(); raise
