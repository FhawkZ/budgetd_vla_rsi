"""Seal author text for review; never import/execute candidate code or authorize rollouts."""
import hashlib,json,os,stat
from pathlib import Path
from skill_rsi_author_workspace import OUTPUTS
from skill_rsi_caller_bridge import checked

def digest(b):return hashlib.sha256(b).hexdigest()
def read_regular(p,limit):
    p=Path(p)
    if any(x.is_symlink() for x in [p,*p.parents]):raise ValueError('symlink path refused')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('regular file required')
        data=f.read(limit+1)
    if len(data)>limit:raise ValueError('file size cap')
    return data

def seal(workspace,destination,upstream,skill_name):
    w=Path(workspace);dest=Path(destination)
    # Destination must be new: do not overwrite another candidate or rejection.
    if dest.exists() or dest.is_symlink():raise FileExistsError(dest)
    dest.mkdir(parents=True,exist_ok=False)
    receipt={'status':'rejected','executed':False,'accepted_update':False,'rollout_authorized':False,'errors':[],'files':{}}
    try:
        rows=[json.loads(s) for s in read_regular(w/'operations.jsonl',8_000_000).decode().splitlines()]
        if not rows or len(rows)>24:raise ValueError('operation count')
        latest={}
        for i,row in enumerate(rows,1):
            if row['operation']!=i:raise ValueError('noncontiguous operation ledger')
            req=row['request']
            if isinstance(req,dict) and req.get('op')=='write' and 'result' in row:
                r=row['result'];name=req['name']
                if name not in OUTPUTS or r['name']!=name or r['version']!=f'{i:03d}-{name}':raise ValueError('version identity')
                b=read_regular(w/'versions'/r['version'],OUTPUTS[name])
                if b!=req['content'].encode() or digest(b)!=r['sha256'] or len(b)!=r['bytes']:raise ValueError('version hash/content')
                latest[name]=r
        if set(latest)!=set(OUTPUTS) or {p.name for p in (w/'output').iterdir()}!=set(OUTPUTS):raise ValueError('exact four artifacts required')
        contents={}
        for name,limit in OUTPUTS.items():
            b=read_regular(w/'output'/name,limit)
            if digest(b)!=latest[name]['sha256']:raise ValueError('output revision mismatch')
            contents[name]=b;receipt['files'][name]={'sha256':digest(b),'bytes':len(b)}
        scope={};source=checked(upstream,'validate.py')
        exec(compile(source,'<pinned-official-validator>','exec'),scope)
        errors,atoms=scope['validate_skills'](contents['skills.py'].decode())
        errors+=scope['validate_perception'](contents['perception.py'].decode())
        errors+=scope['validate_skill_md'](contents['SKILL.md'].decode(),atoms,skill_name)
        if not contents['rationale.md'].decode().strip():errors.append('empty rationale')
        receipt.update(validator_sha256=digest(source.encode()),atoms=atoms,errors=errors,
                       operations_sha256=digest(read_regular(w/'operations.jsonl',8_000_000)),
                       inputs_manifest_sha256=digest(read_regular(w/'resource-manifest.json',100_000)))
        if errors:return receipt
        # Byte snapshots, not execution or promotion. Static validation is not a sandbox.
        (dest/'artifacts').mkdir()
        for name,b in contents.items():
            with (dest/'artifacts'/name).open('xb') as f:f.write(b)
        receipt['status']='static_valid_pending_execution_boundary_and_independent_protocol'
        receipt['candidate_sha256']=digest(json.dumps(receipt['files'],sort_keys=True,separators=(',',':')).encode())
        return receipt
    except Exception as error:
        receipt['errors'].append(type(error).__name__+':'+str(error));return receipt
    finally:
        (dest/'receipt.json').write_text(json.dumps(receipt,indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--destination',required=True);p.add_argument('--upstream',required=True);p.add_argument('--skill-name',required=True);a=p.parse_args()
    print(json.dumps(seal(a.workspace,a.destination,a.upstream,a.skill_name),indent=2))
