"""One bounded, non-GPU download of the upstream Skill-RSI CLIP artifact."""
import fcntl, hashlib, json, os, subprocess, time
from pathlib import Path

ROOT=Path(os.environ['RSI_RUNTIME_ROOT'])
SHA='40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af'
URL='https://openaipublic.azureedge.net/clip/models/'+SHA+'/ViT-B-32.pt'
OUT=ROOT/'outputs/skill-rsi-clip-preparation-20261104-0030'

def main():
    OUT.mkdir(exist_ok=False)
    row={'status':'running','pid':os.getpid(),'starttime':Path('/proc/self/stat').read_text().split()[21],'started_unix':time.time(),'url':URL,'expected_sha256':SHA,'wall_seconds_limit':200,'download_seconds_limit':180,'max_bytes':512*1024**2,'gpu_used':False,'model_calls':0}
    def save(): (OUT/'status.json').write_text(json.dumps(row,indent=2)+'\n')
    save()
    with (ROOT/'locks/skill-rsi-clip-download.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        target=ROOT/'models/CLIP-ViT-B-32'/('ViT-B-32.pt');target.parent.mkdir(exist_ok=True)
        part=target.with_suffix('.pt.partial-20261104')
        try:
            st=os.statvfs(ROOT)
            assert st.f_bavail*st.f_frsize>max(100*1024**3,.2*st.f_blocks*st.f_frsize)+512*1024**2
            if not target.exists():
                assert not part.exists(),'do not overwrite or duplicate earlier partial'
                cmd=['curl','--fail','--location','--connect-timeout','12','--max-time','180','--max-filesize',str(512*1024**2),'--output',str(part),URL]
                with (OUT/'download.log').open('w') as f:
                    r=subprocess.run(cmd,stdout=f,stderr=f,timeout=190)
                row['curl_exit_code']=r.returncode
                if r.returncode: raise RuntimeError('bounded download failed; no retry')
                assert hashlib.sha256(part.read_bytes()).hexdigest()==SHA,'weight SHA mismatch'
                part.replace(target)
            assert hashlib.sha256(target.read_bytes()).hexdigest()==SHA
            row.update(status='verified_download_only',bytes=target.stat().st_size,path=str(target),actual_sha256=SHA)
        except BaseException as e:
            row.update(status='failed',error=repr(e),partial_bytes=part.stat().st_size if part.exists() else 0)
        finally:
            row['finished_unix']=time.time();save()
            (OUT/'CLOSE.json').write_text(json.dumps({'status':'CLOSED','outcome':row['status'],'no_automatic_retries':True},indent=2)+'\n')
    return 0 if row['status']=='verified_download_only' else 1

if __name__=='__main__':raise SystemExit(main())
