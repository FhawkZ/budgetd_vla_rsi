"""Assemble pinned native RoboTwin without altering vendor or verified assets.
CPU-only deployment; no task execution, model generation, or benchmark claim.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from robotwin import assets

root = Path(__file__).resolve().parents[1]
runtime = Path(os.environ['RSI_RUNTIME_ROOT'])
spec = json.loads((root / 'configs/native-sources.json').read_text())['RoboTwin']
manifest = json.loads((root / 'configs/robotwin-assets.json').read_text())
source = runtime / 'vendor' / ('RoboTwin-' + spec['commit'])
asset_root = runtime / 'assets' / ('robotwin-' + manifest['revision'][:8])
target = runtime / 'backends' / ('robotwin-' + spec['commit'][:8] + '-' + manifest['revision'][:8])
output = Path(os.environ.get('RSI_DEPLOY_OUTPUT', str(runtime / 'outputs/native-backend-20261029-1915')))
output.mkdir(parents=True, exist_ok=True)
lock = (runtime / 'locks/prepare-robotwin.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
report = {'status': 'checking', 'model_calls': 0, 'task_episodes': 0, 'gpu_jobs': 0,
          'source_commit': spec['commit'], 'asset_revision': manifest['revision'],
          'target': str(target), 'started_unix': time.time()}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save():
    (output / 'backend-prepare.json').write_text(json.dumps(report, indent=2))

save()
try:
    receipt = json.loads((source / '.source-receipt.json').read_text())
    assert receipt['commit'] == spec['commit'] and receipt['status'] == 'complete'
    assets.validate_root(asset_root)
    identity = json.loads((asset_root / assets.MANIFEST_NAME).read_text())
    assert identity['revision'] == manifest['revision']
    assert identity['archives'] == {r['path']: r['sha256'] for r in manifest['files']}
    assert not target.exists(), 'Existing target must be audited before reuse; will not overwrite'
    source_files = {str(p.relative_to(source)): digest(p) for p in source.rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.pyc')}
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Official setup generates local *.yml alongside *_tmp.yml. Copy embodiments
    # (no hardlinks) so generation cannot modify the verified archive extraction.
    shutil.copytree(asset_root / 'assets/embodiments', target / 'assets/embodiments')
    for name in ('background_texture', 'objects'):
        (target / 'assets' / name).symlink_to(asset_root / 'assets' / name, target_is_directory=True)
    updater = target / 'scripts/update_embodiment_config_path.py'
    with (output / 'embodiment-path-setup.log').open('w') as log:
        subprocess.run([sys.executable, str(updater)], cwd=target,
                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                       timeout=120, check=True)
    configs = []
    for template in (target / 'assets/embodiments').rglob('*_tmp.yml'):
        generated = template.with_name(template.name.replace('_tmp.yml', '.yml'))
        expected = template.read_text().replace('${ASSETS_PATH}', str(target)).replace('$ASSETS_PATH', str(target))
        assert generated.read_text() == expected, f'Generated config mismatch: {generated}'
        original = asset_root / template.relative_to(target)
        assert digest(template) == digest(original), 'Template changed'
        configs.append({'template': str(template.relative_to(target)), 'template_sha256': digest(template),
                        'generated': str(generated.relative_to(target)), 'generated_sha256': digest(generated)})
    assert configs, 'No generated embodiment configs'
    for name, sha in source_files.items():
        assert digest(source / name) == sha and digest(target / name) == sha, f'Source changed: {name}'
    (target / '.source-files.json').write_text(json.dumps(source_files, indent=2))
    report.update(status='prepared', generated_configs=configs, source_files_verified=len(source_files),
                  limitation='Paths/configuration only. cuRobo build, task reset/step and full role transport still require qualification.',
                  finished_unix=time.time())
    save()
    (target / '.backend-receipt.json').write_text(json.dumps(report, indent=2))
except Exception as exc:
    report.update(status='failed', error=repr(exc)); save(); raise
print(json.dumps({'status': report['status'], 'target': str(target), 'source_files_verified': report['source_files_verified']}))
