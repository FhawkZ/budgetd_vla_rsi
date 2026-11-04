"""Data-only CPU perception child. Pinned camera transform; no simulator/CLIP/scorer."""
import ast,base64,hashlib,json,math,os,resource,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from skill_rsi_caller_bridge import checked
from skill_rsi_skill_worker import restrict_cpu
PF_SHA='9abe18dc27816dd8217626f0ad0c7c1980bcdeba30a03847b24808012f81ea1f'
MAX_INPUT=16*2**20

def dependencies(root):
    import numpy as np
    from PIL import Image
    from sklearn.cluster import DBSCAN
    src=(Path(root)/'perception_frozen.py').read_bytes()
    if hashlib.sha256(src).hexdigest()!=PF_SHA:raise ValueError('camera transform source changed')
    tree=ast.parse(src);body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='world_points']
    if len(body)!=1:raise ValueError('camera transform missing')
    scope={'np':np};exec(compile(ast.Module(body=body,type_ignores=[]),'<fixed-world-points>','exec'),scope)
    v={};exec(compile(checked(root,'validate.py'),'<fixed-validator>','exec'),v)
    return np,Image,DBSCAN,scope['world_points'],v

def decode_array(row,np,kind):
    if set(row)!={'shape','dtype','data','sha256'}:raise ValueError('array fields')
    shape=row['shape']
    if not isinstance(shape,list) or any(type(n)!=int or not 0<n<=1024 for n in shape):raise ValueError('shape cap')
    if kind=='rgb' and (len(shape)!=3 or shape[2]!=3 or row['dtype']!='|u1'):raise ValueError('RGB contract')
    if kind=='depth' and (len(shape)!=2 or row['dtype'] not in ['<u2','<f2','<f4','<f8']):raise ValueError('depth contract')
    raw=base64.b64decode(row['data'],validate=True);dtype=np.dtype(row['dtype'])
    if len(raw)!=math.prod(shape)*dtype.itemsize or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('array size/hash')
    a=np.frombuffer(raw,dtype=dtype).reshape(shape).copy()
    if not np.isfinite(a).all():raise ValueError('nonfinite input')
    return a

def plain(v,np):
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,(tuple,list)):return [plain(x,np) for x in v]
    if isinstance(v,dict):return {k:plain(x,np) for k,x in v.items()}
    return v

def main():
    raw=sys.stdin.buffer.readline(MAX_INPUT+1)
    if len(raw)>MAX_INPUT or not raw.endswith(b'\n'):raise ValueError('input framing/cap')
    row=json.loads(raw)
    if set(row)!={'source','rgb','depth','calibration'} or len(row['source'].encode())>60000:raise ValueError('perception input fields')
    root=Path(sys.argv[1]);np,Image,DBSCAN,world_points,v=dependencies(root)
    errors=v['validate_perception'](row['source'])
    if errors:return {'status':'static_rejected','errors':errors}
    rgb=decode_array(row['rgb'],np,'rgb');depth=decode_array(row['depth'],np,'depth')
    if rgb.shape[:2]!=depth.shape:raise ValueError('RGB depth alignment')
    # Preload trusted numerical libraries using a synthetic warmup, not candidate/data.
    np.linalg.inv(np.eye(4));DBSCAN(eps=.1,min_samples=2,n_jobs=1).fit_predict(np.array([[0.,0.],[0.01,0.],[1.,1.]]))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(2*2**30,2*2**30));resource.setrlimit(resource.RLIMIT_CPU,(5,6));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    restrict_cpu()
    detect=v['load_perception'](row['source'],world_points)
    result=plain(detect(rgb,depth,row['calibration']),np)
    return {'status':'result','result':result,'seccomp_allowlist':True,'source_sha256':hashlib.sha256(row['source'].encode()).hexdigest()}

if __name__=='__main__':
    try:
        row=main();text=json.dumps(row,allow_nan=False,separators=(',',':'))
        if len(text.encode())>65536:raise ValueError('output cap')
        print(text,flush=True)
    except BaseException as e:
        print(json.dumps({'status':'worker_error','error_class':type(e).__name__,'message':str(e)[:200]}),flush=True);sys.exit(1)
