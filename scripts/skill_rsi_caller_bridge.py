"""Local-Qwen deployment adapter for the exact upstream orchestrated loop.
Only pure functions/AST are loaded on CPU. No GPU, service launch or author execution.
"""
import ast,copy,hashlib,json,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path

PIN={'episode.py':'0d77a29d359c2fc8509b4a0bed3807d6bd742b574df07c400f458fa20f069554','broker.py':'f9c94521418988fc42b4df0e8cb208dd02b5bdf835770f7af2f1a82c50894339','validate.py':'20e80e06e64491ebf6f5848036762fdf61a2538a670bcbaefd62c65989bbbb72','prompts/caller_prompt.md':'82c58f6a654c5280a49579923961d49556ef491cc9f1c206205228145c0aaa25'}
MODEL='qwen3-vl-30b-a3b-instruct'

def sha(data):return hashlib.sha256(data).hexdigest()
def checked(root,name):
 data=(Path(root)/name).read_bytes()
 if sha(data)!=PIN[name]:raise ValueError('upstream source mismatch: '+name)
 return data.decode()
def pure_functions(root,name,names,namespace):
 tree=ast.parse(checked(root,name));body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 if {n.name for n in body}!=set(names):raise ValueError('missing upstream function')
 exec(compile(ast.Module(body=body,type_ignores=[]),name,'exec'),namespace)
 return namespace

def load_orchestrated(root,upstream_globals):
 tree=ast.parse(checked(root,'episode.py'));run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
 branches=[n for n in ast.walk(run) if isinstance(n,ast.If) and ast.dump(n.test)==ast.dump(ast.parse('mode == "fallback"',mode='eval').body)]
 if len(branches)!=1:raise ValueError('ambiguous native orchestration')
 body=copy.deepcopy(branches[0].orelse)
 prefix=ast.parse('root=ev\neid="local"\nreplay=False\nrecords=None\nklass=None\ndecisions=[]\ndecisions_rejected=0\natom_calls=0\natom_errors=0\n').body
 suffix=ast.parse('return dict(result=result,klass=klass,decisions=decisions,decisions_rejected=decisions_rejected,atom_calls=atom_calls,atom_errors=atom_errors,history=history)').body
 # Native exception propagation retained; persist partial history before propagation.
 handler=ast.parse('try:\n pass\nfinally:\n if "history" in locals():\n  dump(ev / "history.json", history)').body[0];handler.body=body+suffix
 fn=ast.FunctionDef(name='orchestrate',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg=x) for x in ['ns','atoms','api','wall','lines','spec','skill_md','lim','ev']],kwonlyargs=[],kw_defaults=[],defaults=[]),body=prefix+[handler],decorator_list=[])
 module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));scope=dict(upstream_globals)
 exec(compile(module,'<pinned-native-orchestrated>','exec'),scope)
 return scope['orchestrate'],sha(ast.dump(ast.Module(body=body,type_ignores=[])).encode())

def public_context(ctx):
 out=copy.deepcopy(ctx)
 if set(out)!={'task_spec','skill_md','atoms','history','decisions_used','decisions_max','calls_remaining'}:raise ValueError('unexpected context fields')
 spec=out['task_spec'];out['task_spec']={k:spec[k] for k in ['instruction','roles']}
 def check(v):
  if isinstance(v,dict):
   if set(v)&{'criterion_source','scorer','official_success','layout','layout_sha256','object_pose'}:raise ValueError('evaluator field in caller context')
   for x in v.values():check(x)
  elif isinstance(v,list):
   for x in v:check(x)
 check(out)
 return out

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('local service redirects prohibited')

class LocalQwenBroker:
 def __init__(self,root,limits,output,endpoint='http://127.0.0.1:18029/v1/chat/completions',transport=None):
  parsed=urllib.parse.urlparse(endpoint)
  if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.port!=18029 or parsed.path!='/v1/chat/completions' or parsed.query or parsed.username:raise ValueError('fixed budget proxy endpoint required')
  self.limits=dict(limits);self.output=Path(output);self.output.mkdir(parents=True,exist_ok=False);self.calls=0;self.endpoint=endpoint;self.transport=transport
  if not 1<=self.limits['decisions_max']<=4:raise ValueError('per-case maximum4')
  import re
  self.formatters=pure_functions(root,'broker.py',['render','fill'],{'json':json,'re':re})
  self.template=checked(root,'prompts/caller_prompt.md')
 def decide(self,ctx,context_sha,k):
  if self.calls>=self.limits['decisions_max'] or k!=self.calls:raise RuntimeError('caller budget/sequence rejected before network')
  safe=public_context(ctx);prompt=self.formatters['fill'](self.template,dict(self.limits,context=self.formatters['render'](safe)))
  body={'model':MODEL,'messages':[{'role':'user','content':prompt}],'max_tokens':1024,'seed':42,'stream':False}
  self.calls+=1;stem=f'{self.calls:03d}';encoded=json.dumps(body).encode();start=time.monotonic()
  (self.output/(stem+'-request.json')).write_bytes(encoded)
  receipt={'index':self.calls,'native_context_sha256':context_sha,'request_sha256':sha(encoded),'prompt_sha256':sha(prompt.encode()),'model':MODEL,'attempts':1,'cost_usd':None,'cost_note':'local compute; monetary conversion not defined'}
  try:
   if self.transport is not None:response=self.transport(body)
   else:
    req=urllib.request.Request(self.endpoint,data=encoded,headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(req,timeout=180) as f:response=json.load(f)
   (self.output/(stem+'-response.json')).write_text(json.dumps(response))
   if response.get('model',MODEL)!=MODEL:raise ValueError('unexpected response model')
   usage=response.get('usage',{});receipt.update(input_tokens=usage.get('prompt_tokens'),output_tokens=usage.get('completion_tokens'),usage=usage)
   msg=response['choices'][0];content=msg['message'].get('content');receipt.update(raw_response=content,status='ok',finish_reason=msg.get('finish_reason'))
   if msg.get('finish_reason')=='length' or msg['message'].get('tool_calls') or not isinstance(content,str):receipt.update(status='refused',refusal='truncated/non-text native JSON decision; no repair')
   return receipt
  except urllib.error.HTTPError as e:
   raw=e.read();(self.output/(stem+'-error-body.bin')).write_bytes(raw)
   try:
    error=json.loads(raw);receipt['usage']=error.get('usage');receipt['input_tokens']=(error.get('usage') or {}).get('prompt_tokens');receipt['output_tokens']=(error.get('usage') or {}).get('completion_tokens')
   except ValueError:pass
   receipt.update(status='transport_error',error=repr(e));raise
  except BaseException as e:receipt.update(status='transport_error',error=repr(e));raise
  finally:
   receipt.update(latency_seconds=time.monotonic()-start,waited_seconds=0)
   (self.output/(stem+'-receipt.json')).write_text(json.dumps(receipt,indent=2))


def native_provider(broker,infra_exception):
    class Provider:
        def decide(self,ctx,sha,k):
            try:return broker.decide(ctx,sha,k)
            except Exception as error:raise infra_exception('local_qwen_transport:'+type(error).__name__+':'+str(error)) from error
    return Provider()
