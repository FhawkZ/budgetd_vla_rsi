"""Finite CPU perception transport; never send file paths or simulator state to source."""
import base64,hashlib,json,os,selectors,subprocess,sys,time
from pathlib import Path
from skill_rsi_skill_ipc import plain

def calibration_json(calibration):
    import numpy as np
    expected={'intrinsic_cv':(3,3),'extrinsic_cv':(3,4),'cam2world_gl':(4,4)}
    if not isinstance(calibration,dict) or set(calibration)!=set(expected):raise ValueError('calibration fields')
    result={}
    for name,shape in expected.items():
        value=calibration[name]
        if not isinstance(value,(list,tuple,np.ndarray)):raise ValueError('calibration type')
        a=np.asarray(value)
        if a.shape!=shape or a.dtype.kind not in 'fiu' or not np.isfinite(a).all():raise ValueError('calibration shape/dtype/finite')
        result[name]=a.tolist()
    return plain(result)

def pack(array):
    import numpy as np
    a=np.ascontiguousarray(array);raw=a.tobytes()
    return {'shape':list(a.shape),'dtype':a.dtype.str,'data':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()}

def run_perception(source,rgb,depth,calibration,upstream,output,timeout=15):
    if not 0<timeout<=15:raise ValueError('CPU wall budget')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    request={'source':source,'rgb':pack(rgb),'depth':pack(depth),'calibration':calibration_json(calibration)}
    raw=json.dumps(request,allow_nan=False,separators=(',',':')).encode()+b'\n'
    if len(raw)>16*2**20:raise ValueError('input byte cap')
    (out/'input.json').write_bytes(raw)
    report={'status':'infrastructure_error','request_sha256':hashlib.sha256(raw).hexdigest(),'model_calls':0,'robot_rollout':False,'accepted_update':False};t=time.monotonic();p=None;writer=None
    try:
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','PYTHONHASHSEED':'0'}
        # stdout has a bounded trusted writer and parent checks the returned frame.
        p=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).with_name('skill_rsi_perception_worker.py')),str(upstream)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,env=env,cwd='/')
        # Reader enforces caps while the input writer streams at most16MiB to child.
        import threading
        def write():
            try:p.stdin.write(raw);p.stdin.flush()
            except (BrokenPipeError,OSError):pass
            finally:p.stdin.close()
        writer=threading.Thread(target=write,daemon=True);writer.start();sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ,'stdout');sel.register(p.stderr,selectors.EVENT_READ,'stderr');bufs={'stdout':b'','stderr':b''}
        while sel.get_map():
            left=timeout-(time.monotonic()-t)
            if left<=0:raise TimeoutError('perception wall budget')
            for key,_ in sel.select(min(.2,left)):
                b=os.read(key.fileobj.fileno(),65537)
                if not b:sel.unregister(key.fileobj);continue
                bufs[key.data]+=b
                if len(bufs[key.data])>65536:raise ValueError('child output cap')
        p.wait(timeout=max(.01,timeout-(time.monotonic()-t)));writer.join(timeout=.5)
        (out/'response.json').write_bytes(bufs['stdout']);(out/'stderr.txt').write_bytes(bufs['stderr'])
        result=json.loads(bufs['stdout']);report.update(status=result['status'],response=result)
        if result['status']=='result' and p.returncode!=0:report['status']='infrastructure_error'
    except Exception as error:report.update(status='rejected_or_error',error=type(error).__name__+':'+str(error))
    finally:
        if p is not None:
            report['exit_before_cleanup']=p.poll()
            if p.poll() is None:p.kill()
            p.wait(timeout=2);report['exit_code']=p.returncode
            if writer is not None:writer.join(timeout=1)
            for stream in [p.stdin,p.stdout,p.stderr]:
                if not stream.closed:stream.close()
        report['seconds']=time.monotonic()-t;(out/'report.json').write_text(json.dumps(report,indent=2))
    return report
