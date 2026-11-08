"""Two-attempt one-shot deployment comparison. No model or generated skills."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from run_skill_rsi_native_v2 import dump,sha,render_log_error
from run_skill_rsi_native_v3 import gpu_read
from gpu_idle_gate import wait_idle
from skill_rsi_owner_process import OwnedSession,proc_start

ROOT=Path(__file__).resolve().parents[1]
DURABLE=Path('/root/autodl-tmp/qian/Dex_runtime/agent-rsi-migration-20261105/outputs')

def verify(c):
    assert c['status']=='FROZEN_DEPLOYMENT_PAIR' and c['gpu']==3
    assert c['attempts_max']==2 and c['qwen_max']==c['vla_max']==0
    assert c['process_wall_seconds']==300 and c['total_wall_seconds']==660
    assert c['expected_output_bytes']==268435456
    assert c['cases'][0]['mode']=='baseline' and c['cases'][1]['mode']=='isolated'
    assert c['cases'][0]['seed']==c['cases'][1]['seed']
    assert c['cases'][0]['task']==c['cases'][1]['task']
    assert Path(c['output']).resolve().parent==DURABLE
    for p,h in c['source_files'].items():assert sha(p)==h,p
    for case in c['cases']:assert sha(case['protocol'])==case['sha256']

def resources(output,expected):
    v=os.statvfs(DURABLE)
    assert v.f_bavail*v.f_frsize>=max(100*2**30,.2*v.f_blocks*v.f_frsize)+expected
    assert v.f_favail>100000
    def save(row):
        with (output/'resources.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    return wait_idle(lambda:gpu_read(3),save,timeout=6)

def descendants(parent):
    table={}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            f=(p/'stat').read_text().rsplit(')',1)[1].split()
            table[int(p.name)]={'pid':int(p.name),'ppid':int(f[1]),'pgid':int(f[2]),'sid':int(f[3]),'starttime':f[19],'state':f[0]}
        except (OSError,ValueError,IndexError):pass
    selected={parent};changed=True
    while changed:
        added={pid for pid,r in table.items() if r['ppid'] in selected}-selected
        changed=bool(added);selected.update(added)
    return [table[pid] for pid in selected if pid!=parent and pid in table]

def cleanup_known(known):
    rows=[]
    for row in reversed(list(known.values())):
        pid=row['pid']
        try:
            if proc_start(pid)!=row['starttime']:continue
            f=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
            if f[0]=='Z':continue
            os.kill(pid,signal.SIGKILL);rows.append({'pid':pid,'starttime':row['starttime'],'signal':'SIGKILL'})
        except (FileNotFoundError,ProcessLookupError):pass
    return rows

def run(c,path):
    verify(c)
    out=Path(c['output']);out.mkdir(parents=True,exist_ok=False)
    runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
    panel=(runtime/'locks/native-owner-pair.lock').open('a')
    fcntl.flock(panel,fcntl.LOCK_EX|fcntl.LOCK_NB)
    r={'status':'running','planned':2,'attempted':0,'completed':0,'unstarted':2,'episodes':[],
       'protocol_sha256':sha(path),'started':time.time(),'Qwen':0,'VLA':0,'accepted_H_updates':0}
    dump(out/'protocol.json',c);dump(out/'report.json',r)
    try:
        for case in c['cases']:
            gpu=resources(out,c['expected_output_bytes'])
            if time.time()-r['started']>=c['total_wall_seconds']:raise TimeoutError('panel deadline')
            lock=None;p=None;owned=None;start=time.monotonic();logpath=out/(case['mode']+'.log')
            row={'case':case,'gpu':gpu,'started_unix':time.time()}
            known={}
            try:
                if case['mode']=='baseline':
                    lock=(runtime/'locks/gpu3.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    gpu=resources(out,c['expected_output_bytes'])
                env=dict(os.environ,CUDA_VISIBLE_DEVICES='3',CUDA_DEVICE_ORDER='PCI_BUS_ID',
                    RSI_EXPECTED_GPU_PCI=gpu['pci'],PYTHONPATH='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
                args=[sys.executable,str(ROOT/'scripts/run_native_pair_case_v4.py'),'--mode',case['mode'],
                    '--protocol',case['protocol'],'--sha256',case['sha256'],'--output',str(out/'baseline')]
                with logpath.open('w') as log:
                    p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
                    owned=OwnedSession(p);row['identity']=owned.receipt.copy()
                    r['attempted']+=1;r['unstarted']-=1;r['active']=row;dump(out/'report.json',r)
                    deadline=min(start+300,time.monotonic()+660-(time.time()-r['started']))
                    while p.poll() is None:
                        for ident in descendants(p.pid):known[(ident['pid'],ident['starttime'])]=ident
                        dump(out/(case['mode']+'-descendants.json'),list(known.values()))
                        if render_log_error(logpath.read_text(errors='replace')):raise RuntimeError('render_error')
                        if time.monotonic()>deadline:raise TimeoutError('outer process deadline')
                        time.sleep(.1)
                    row['exit_before_cleanup']=p.returncode
                row['render_error']=render_log_error(logpath.read_text(errors='replace'))
                rp=out/'baseline/episode.json' if case['mode']=='baseline' else out/'isolated-owner/report.json'
                row['result']=json.loads(rp.read_text()) if rp.exists() else {}
                row['valid']=p.returncode==0 and not row['render_error'] and row['result'].get('status') in ['completed','completed_private']
            except BaseException as e:
                row.update(valid=False,error_class=type(e).__name__,error=str(e))
            finally:
                if owned is not None:
                    row['outer_cleanup']=owned.cleanup()
                row['tracked_descendant_cleanup']=cleanup_known(known)
                if row['tracked_descendant_cleanup']:
                    row['valid']=False;row['cleanup_required_extra_signals']=True
                if lock is not None:lock.close()
                row['gpu_process_interval_seconds']=time.monotonic()-start
                r['episodes'].append(row);r['active']=None
                if row.get('valid'):r['completed']+=1
                dump(out/'report.json',r)
            if not row.get('valid'):
                r['status']='stopped_infrastructure';break
        else:r['status']='completed'
    except BaseException as e:r.update(status='owner_error',error=repr(e))
    finally:
        r['finished']=time.time();r['remaining_attempts_canceled']=r['unstarted']
        dump(out/'report.json',r);dump(out/'CLOSE.json',{'status':'CLOSED','report_sha256':sha(out/'report.json'),
             'remaining_attempts_canceled':r['unstarted']})
        panel.close()
    return r

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);p.add_argument('--sha256',required=True);p.add_argument('--check',action='store_true')
    a=p.parse_args();assert sha(a.protocol)==a.sha256;c=json.loads(Path(a.protocol).read_text());verify(c)
    if a.check:print('all frozen source and case hashes match; no initialization')
    else:print(json.dumps(run(c,Path(a.protocol))))
