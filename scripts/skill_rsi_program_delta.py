"""Literal deltas bound to frozen named AST scopes. Never execute candidate text."""
import ast, hashlib
FILES={'SKILL.md':'skill_doc','skills.py':'inherited_skills','perception.py':'inherited_perception'}
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()

def scopes(text):
    tree=ast.parse(text);lines=text.splitlines(keepends=True);result={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            key='function:'+node.name
        elif isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            key='assignment:'+node.targets[0].id
        else:continue
        if key in result:raise ValueError('ambiguous named AST scope')
        start=min([node.lineno]+[d.lineno for d in getattr(node,'decorator_list',[])])-1
        end=node.end_lineno
        result[key]=(sum(map(len,lines[:start])),sum(map(len,lines[:end])))
    return result

class DeltaCompiler:
    def __init__(self,resources,expected):
        self.original={n:resources[r] for n,r in FILES.items()}
        self.hashes={n:sha(t) for n,t in self.original.items()}
        if self.hashes!=expected:raise ValueError('owner source SHA mismatch')
        self.targets={n:({'document':(0,len(t))} if n=='SKILL.md' else scopes(t)) for n,t in self.original.items()}
    def catalog(self):return {n:sorted(s) for n,s in self.targets.items()}
    def compile(self,proposal):
        if set(proposal)!={'decision','edits','rationale'}:raise ValueError('proposal fields')
        edits=proposal['edits'];reason=proposal['rationale']
        if not isinstance(reason,str) or not reason.strip() or len(reason.encode())>4000:raise ValueError('rationale required/cap')
        if not isinstance(edits,list) or len(edits)>12:raise ValueError('edit cap')
        if proposal['decision']=='abstain':
            if edits:raise ValueError('abstain must have no edits')
            return None
        if proposal['decision']!='propose' or not edits:raise ValueError('explicit nonempty proposal required')
        spans={n:[] for n in FILES};changed={n:set() for n in FILES}
        for e in edits:
            if not isinstance(e,dict) or set(e)!={'file','target','old','new'}:raise ValueError('edit fields')
            name,target,old,new=(e[k] for k in ('file','target','old','new'))
            if name not in self.targets or target not in self.targets[name]:raise ValueError('ungranted AST scope')
            if not isinstance(old,str) or not old or not isinstance(new,str) or old==new:raise ValueError('literal nonempty change required')
            if len(old.encode())+len(new.encode())>12000:raise ValueError('literal size cap')
            a,b=self.targets[name][target];section=self.original[name][a:b]
            if section.count(old)!=1:raise ValueError('anchor not unique inside frozen AST scope')
            start=a+section.index(old);stop=start+len(old)
            if any(start<y and stop>x for x,y,_ in spans[name]):raise ValueError('overlapping frozen spans')
            spans[name].append((start,stop,new));changed[name].add(target)
        result=dict(self.original)
        for name,parts in spans.items():
            text=result[name]
            for a,b,new in sorted(parts,reverse=True):text=text[:a]+new+text[b:]
            if len(text.encode())>(20000 if name=='SKILL.md' else 60000):raise ValueError('artifact cap')
            if name.endswith('.py'):
                tree=ast.parse(text)
                if any(isinstance(n,(ast.Import,ast.ImportFrom)) for n in ast.walk(tree)):raise ValueError('imports denied')
                # Scope edits cannot introduce/delete/rename top-level declarations.
                if set(scopes(text))!=set(self.targets[name]):raise ValueError('top-level scope escape')
                before=ast.parse(self.original[name]).body
                if len(before)!=len(tree.body):raise ValueError('module node injection')
                for oldnode,newnode in zip(before,tree.body):
                    key=('function:'+oldnode.name if isinstance(oldnode,(ast.FunctionDef,ast.AsyncFunctionDef)) else 'assignment:'+oldnode.targets[0].id if isinstance(oldnode,ast.Assign) and len(oldnode.targets)==1 and isinstance(oldnode.targets[0],ast.Name) else None)
                    if key not in changed[name] and ast.dump(oldnode)!=ast.dump(newnode):raise ValueError('ungranted node changed')
            result[name]=text
        result['rationale.md']=reason
        return result
