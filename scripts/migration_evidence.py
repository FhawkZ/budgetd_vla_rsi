"""Persist volatile trial evidence; never upload data or alter the executor."""
import contextlib,shutil,threading,time,os
from pathlib import Path

def snapshot(source,destination,allowed_targets=()):
    source,destination=Path(source),Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    for p in source.rglob('*'):
        if p.is_symlink():
            target=str(p.resolve())
            if target not in allowed_targets:raise ValueError('evidence symlink refused: '+str(p))
            import json
            q=destination/p.relative_to(source);q.parent.mkdir(parents=True,exist_ok=True)
            q.with_name(q.name+'.symlink.json').write_text(json.dumps({'source_link':str(p),'target':target,'copied_target':False}))
            continue
        if not p.is_file():continue
        rel=p.relative_to(source);q=destination/rel;q.parent.mkdir(parents=True,exist_ok=True)
        stat=p.stat()
        if q.exists() and q.stat().st_size==stat.st_size and q.stat().st_mtime_ns==stat.st_mtime_ns:continue
        tmp=q.with_name(q.name+'.mirror-part')
        shutil.copy2(p,tmp)
        with tmp.open('rb') as f:os.fsync(f.fileno())
        tmp.replace(q)

@contextlib.contextmanager
def persistent_trial(runtime,destination,run_id):
    runtime,destination=Path(runtime),Path(destination)
    assert runtime.resolve()!=destination.resolve()
    destination.mkdir(parents=True,exist_ok=True)
    marker=destination/(run_id+'-mirror.json')
    assert not marker.exists(),'persistent evidence already exists; no repeat'
    marker.write_text('{"status":"started","volatile_source":true}')
    stop=threading.Event();errors=[]
    def copy():
        for suffix in ['', '-qwen']:
            src=runtime/'outputs'/(run_id+suffix)
            if src.exists():snapshot(src,destination/(run_id+suffix),allowed_targets=(str((runtime/'vendor/robotwin-official-6dde571').resolve()),))
        src=runtime/'outputs'/(run_id+'-resource-checks.jsonl')
        if src.exists():shutil.copy2(src,destination/src.name)
    def work():
        while not stop.wait(5):
            try:copy()
            except Exception as e:errors.append(repr(e));stop.set()
    thread=threading.Thread(target=work,daemon=True);thread.start()
    try:yield
    finally:
        stop.set();thread.join(timeout=30)
        if thread.is_alive():raise RuntimeError('persistent mirror did not stop')
        copy()
        import json
        marker.write_text(json.dumps({'status':'mirrored','prior_copy_errors':errors,'finished_unix':time.time()}))
        if errors:raise RuntimeError('intermediate evidence mirror failure: '+str(errors))
