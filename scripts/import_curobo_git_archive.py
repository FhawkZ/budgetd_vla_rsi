"""Import a local-authenticated git archive, checking each blob against GitHub's pinned tree.
Fallback for interrupted codeload transport; no source edits or dependency changes.
"""
import argparse, fcntl, hashlib, json, os, shutil, tarfile, time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--tree',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1];runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
output=Path(os.environ['RSI_DEPLOY_OUTPUT']);output.mkdir(parents=True,exist_ok=True)
spec=json.loads((root/'configs/native-sources.json').read_text())['curobo']
target=runtime/'vendor'/('curobo-'+spec['commit'])
lock=(runtime/'locks/native-sources.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert not target.exists(), 'Refuse to overwrite source'
tree=json.loads(a.tree.read_text());assert tree['truncated'] is False
assert tree['sha']==spec['commit'], 'API tree response must identify the exact pinned commit'
blobs={r['path']:r for r in tree['tree'] if r['type']=='blob'}
assert not [r for r in tree['tree'] if r['type'] not in ('blob','tree')], 'Submodule not supported'
stage=target.with_name(target.name+'.git-importing');stage.mkdir()
with tarfile.open(a.archive) as tar:
 members=tar.getmembers();assert all(m.name.split('/')[0]==target.name for m in members)
 assert sum(m.size for m in members)<(2<<30)
 tar.extractall(stage,filter='data')
source=stage/target.name
actual={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file() or p.is_symlink()}
assert actual==set(blobs), 'Archive paths differ from pinned Git tree'
for name,row in blobs.items():
 file=source/name
 data=os.readlink(file).encode() if file.is_symlink() else file.read_bytes()
 assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['sha'], name
 assert (row['mode']=='120000')==file.is_symlink(), name
archive=target.with_name(target.name+'.tar.gz')
if archive.exists(): archive.rename(archive.with_name(archive.name+'.interrupted-'+str(int(time.time()))))
shutil.copyfile(a.archive,archive)
h=hashlib.sha256()
with archive.open('rb') as f:
 for block in iter(lambda:f.read(8<<20),b''):h.update(block)
receipt={'status':'complete',**spec,'path':str(target),'archive_sha256':h.hexdigest(),
         'archive_bytes':archive.stat().st_size,'transport':'local authenticated Git fetch/checkout and git archive; SSH file transfer',
         'verified_git_blobs':len(blobs),'tree_sha256':hashlib.sha256(a.tree.read_bytes()).hexdigest(),
         'finished_unix':time.time()}
(source/'.source-receipt.json').write_text(json.dumps(receipt,indent=2));source.rename(target);stage.rmdir()
(output/'curobo-source.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
