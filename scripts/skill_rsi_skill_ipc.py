"""CPU prototype of an isolated skill/API broker. Not connected to a robot runner.
Caller input/received frames and denial receipts are retained. No automatic retries.
"""
import hashlib,json,math,os,selectors,subprocess,sys,time
from pathlib import Path

FIELDS={'task_spec':set(),'observe':set(),'ee_pose':{'arm'},'gripper_state':{'arm'},
        'move_pose':{'arm','pose'},'gripper':{'arm','value'},'wait':{'seconds'}}
FORBIDDEN={'criterion_source','scorer','official_success','check_success','layout','layout_sha256','object_pose'}

def plain(value):
    data=json.dumps(value,allow_nan=False)
    if len(data.encode())>60000:raise ValueError('response size')
    result=json.loads(data)
    def check(v):
        if isinstance(v,dict):
            if set(v)&FORBIDDEN:raise ValueError('evaluator field rejected')
            for x in v.values():check(x)
        elif isinstance(v,list):
            for x in v:check(x)
    check(result);return result

class PublicAPI:
    def __init__(self,backend,max_requests=120):
        self.backend=backend;self.n=0;self.limit=max_requests
    def dispatch(self,method,args):
        self.n+=1
        if self.n>self.limit:raise RuntimeError('IPC request budget')
        if method not in FIELDS or not isinstance(args,dict) or set(args)!=FIELDS[method]:raise ValueError('ungranted method/args')
        # Roundtrip gives the backend primitive JSON values only, no candidate objects.
        args=plain(args)
        if method=='task_spec':
            spec=self.backend.task_spec();value={k:spec[k] for k in ('instruction','roles')}
        else:value=getattr(self.backend,method)(**args)
        return plain(value)

def run_skill(source,entry,args,backend,upstream,output,timeout=5,max_requests=120):
    if not 0<timeout<=10 or not 1<=max_requests<=120:raise ValueError('CPU prototype budget')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    init={'source':source,'entry':entry,'args':args};encoded=json.dumps(init,allow_nan=False).encode()+b'\n'
    if len(encoded)>100000:raise ValueError('initial input cap')
    (out/'input.json').write_bytes(encoded)
    api=PublicAPI(backend,max_requests);events=[];started=time.monotonic();p=None
    report={'status':'infrastructure_error','robot_rollout':False,'accepted_update':False,'api_requests':0,'source_sha256':hashlib.sha256(source.encode()).hexdigest()}
    try:
        p=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).with_name('skill_rsi_skill_worker.py')),str(upstream)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,close_fds=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},cwd='/')
        p.stdin.write(encoded);p.stdin.flush();sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ);buffer=b'';finished=False;frames=0
        while not finished:
            remaining=timeout-(time.monotonic()-started)
            if remaining<=0:raise TimeoutError('child wall budget')
            if not sel.select(min(remaining,.2)):
                if p.poll() is not None and not buffer:raise RuntimeError('child exited without terminal frame')
                continue
            block=os.read(p.stdout.fileno(),65537)
            if not block:raise RuntimeError('unexpected child EOF')
            buffer+=block
            if len(buffer)>65536:raise ValueError('child frame cap')
            while b'\n' in buffer:
                line,buffer=buffer.split(b'\n',1);row=json.loads(line);frames+=1
                if frames>max_requests+3:raise ValueError('frame budget')
                events.append({'direction':'child','payload':row})
                if row.get('type')=='ready':report['ready']=row
                elif row.get('type')=='api':
                    if set(row)!={'type','method','args'}:raise ValueError('API frame fields')
                    report['api_requests']+=1
                    try:answer={'ok':True,'value':api.dispatch(row['method'],row['args'])}
                    except Exception as error:
                        events.append({'direction':'broker','refusal':type(error).__name__});raise
                    events.append({'direction':'parent','payload':answer});p.stdin.write(json.dumps(answer,allow_nan=False).encode()+b'\n');p.stdin.flush()
                elif row.get('type') in ('result','error','rejected'):
                    report.update(status=row['type'],terminal=row);finished=True;break
                else:raise ValueError('unknown frame')
        p.stdin.close();p.wait(timeout=max(.01,timeout-(time.monotonic()-started)))
        if report['status']=='result' and p.returncode!=0:report['status']='infrastructure_error'
    except Exception as error:report.update(status='rejected_or_error',error=type(error).__name__+':'+str(error))
    finally:
        if p is not None:
            report['exit_before_cleanup']=p.poll()
            if p.poll() is None:p.kill()
            p.wait(timeout=2);report['exit_code']=p.returncode
            (out/'stderr.txt').write_bytes(p.stderr.read(65536))
            for stream in [p.stdin,p.stdout,p.stderr]:
                if not stream.closed:stream.close()
        report['seconds']=time.monotonic()-started
        (out/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
        report['events_sha256']=hashlib.sha256((out/'events.jsonl').read_bytes()).hexdigest()
        (out/'report.json').write_text(json.dumps(report,indent=2))
    return report
