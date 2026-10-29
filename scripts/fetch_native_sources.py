"""Fetch exact native backend source commits with bounded transfer and receipts."""
import concurrent.futures, fcntl, hashlib, json, os, subprocess, tarfile, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
runtime=Path(os.environ['RSI_RUNTIME_ROOT']);vendor=runtime/'vendor'
output=Path(os.environ.get('RSI_DEPLOY_OUTPUT', str(runtime/'outputs/native-backend-20261029-1400')))
output.mkdir(parents=True, exist_ok=True)
config=json.loads((root/'configs/native-sources.json').read_text())
lock=(runtime/'locks/native-sources.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
def fetch(item):
    name,spec=item;target=vendor/(name+'-'+spec['commit']);archive=vendor/(target.name+'.tar.gz')
    receipt=output/(name+'-source.json')
    state={'status':'running',**spec,'started_unix':time.time()}
    def save():receipt.write_text(json.dumps(state,indent=2))
    save()
    try:
        if target.exists():
            identity=json.loads((target/'.source-receipt.json').read_text());assert identity['commit']==spec['commit'];state.update(identity,status='complete');save();return
        part=archive.with_suffix('.partial')
        if part.exists():
            part.rename(part.with_name(part.name + '.interrupted-' + str(int(time.time()))))
        url='https://codeload.github.com/'+spec['repository']+'/tar.gz/'+spec['commit']
        with (output/(name+'-transfer.log')).open('w') as log:
            subprocess.run(['curl','--http1.1','-fL','--connect-timeout','20','--max-time','5400','--max-filesize',str(512<<20),url,'-o',str(part)],stdout=log,stderr=log,check=True,timeout=5450)
        archive_hash=hashlib.sha256(part.read_bytes()).hexdigest()
        stage=vendor/(target.name+'.extracting');stage.mkdir(exist_ok=False)
        with tarfile.open(part) as tar:
            members=tar.getmembers();expected=spec['repository'].split('/')[-1]+'-'+spec['commit']
            assert all(m.name.split('/')[0]==expected for m in members), 'Unexpected source root'
            assert sum(m.size for m in members)<(2<<30), 'Source extraction bound'
            tar.extractall(stage,filter='data')
        (stage/expected).rename(target);stage.rmdir();part.replace(archive)
        state.update(status='complete',archive_sha256=archive_hash,archive_bytes=archive.stat().st_size,path=str(target),finished_unix=time.time())
        (target/'.source-receipt.json').write_text(json.dumps(state,indent=2));save()
    except Exception as exc:
        state.update(status='failed',error=repr(exc));save();raise
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(fetch,config.items()))
