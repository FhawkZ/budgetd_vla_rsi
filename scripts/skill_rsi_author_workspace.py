"""Capability-based file transport for offline author text. Never execute generated code.
Not an OS sandbox. Resource contents are pre-snapshotted by the experiment owner.
"""
import hashlib,json,os,time
from pathlib import Path

OUTPUTS={'SKILL.md':20000,'skills.py':60000,'perception.py':60000,'rationale.md':20000}
def digest(b):return hashlib.sha256(b).hexdigest()

class AuthorWorkspace:
 def __init__(self,root,resources,max_operations=24):
  if not 1<=max_operations<=24:raise ValueError('operation budget')
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False);self.resources=dict(resources);self.limit=max_operations;self.n=0;self.state={}
  if any(not isinstance(k,str) or not k.isidentifier() or not isinstance(v,str) for k,v in self.resources.items()):raise ValueError('resource IDs and text only')
  (self.root/'versions').mkdir();(self.root/'output').mkdir()
  (self.root/'resource-manifest.json').write_text(json.dumps({k:{'bytes':len(v.encode()),'sha256':digest(v.encode())} for k,v in self.resources.items()},indent=2))
 def dispatch(self,request):
  if self.n>=self.limit:raise RuntimeError('author operation budget exhausted')
  self.n+=1;row={'operation':self.n,'request':request,'time':time.time()}
  try:
   if not isinstance(request,dict):raise ValueError('object required')
   if request.get('op')=='read':
    if set(request)!={'op','resource','offset','limit'}:raise ValueError('read keys')
    rid=request['resource'];start=request['offset'];size=request['limit']
    if rid not in self.resources or type(start)!=int or type(size)!=int or start<0 or not 1<=size<=6000:raise ValueError('read capability/range')
    text=self.resources[rid];result={'text':text[start:start+size],'offset':start,'total_characters':len(text),'sha256':digest(text.encode())}
   elif request.get('op')=='write':
    if set(request)!={'op','name','content','expected_sha256'}:raise ValueError('write keys')
    name=request['name'];content=request['content']
    if name not in OUTPUTS or not isinstance(content,str):raise ValueError('output capability')
    data=content.encode()
    if len(data)>OUTPUTS[name]:raise ValueError('artifact byte cap')
    if request['expected_sha256']!=self.state.get(name):raise ValueError('stale revision')
    if any(p.is_symlink() for p in [self.root,self.root/'versions',self.root/'output',self.root/'output'/name]):raise ValueError('symlink refused')
    version=self.root/'versions'/f'{self.n:03d}-{name}';fd=os.open(version,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    # Model cannot choose directories or use append/exec; every full revision retained.
    temp=self.root/'output'/f'.{self.n:03d}.tmp';fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    temp.replace(self.root/'output'/name);self.state[name]=digest(data)
    result={'name':name,'sha256':self.state[name],'bytes':len(data),'version':version.name,'status':'staged_unaccepted_not_executed'}
   else:raise ValueError('unknown author operation')
   row['result']=result;return result
  except BaseException as e:row['error']=repr(e);raise
  finally:
   with (self.root/'operations.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 def ready(self):return set(self.state)==set(OUTPUTS)


def load_resources(manifest):
    grants=json.loads(Path(manifest).read_text())
    if grants.get('status')!='FROZEN_AUTHOR_INPUT':raise ValueError('owner must freeze input grants')
    allowed={'api_doc','skill_doc','inherited_skills','inherited_perception','development_feedback'}
    resources={}
    for g in grants['resources']:
        if set(g)!={'id','path','sha256'} or g['id'] not in allowed or g['id'] in resources:raise ValueError('resource grant')
        data=Path(g['path']).read_bytes()
        if digest(data)!=g['sha256'] or len(data)>300000:raise ValueError('input hash/size')
        resources[g['id']]=data.decode()
    return resources

if __name__=='__main__':
    import argparse,sys
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--workspace',required=True);p.add_argument('--max-operations',type=int,default=24);a=p.parse_args()
    workspace=AuthorWorkspace(a.workspace,load_resources(a.manifest),a.max_operations)
    # Requests are capability objects only; this process never evaluates their contents.
    for line in sys.stdin:
        try:response={'ok':True,'result':workspace.dispatch(json.loads(line))}
        except Exception as e:response={'ok':False,'error':type(e).__name__+':'+str(e)}
        print(json.dumps(response),flush=True)
