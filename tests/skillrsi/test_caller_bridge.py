import ast,hashlib,importlib.util,json,pathlib,sys,tempfile,types,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import skill_rsi_caller_bridge as m
ROOT=pathlib.Path('/root/autodl-tmp/Dex_runtime/agent-rsi/vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4/runtime')
LIM=dict(decisions_max=4,plan_steps_max=8,args_bytes=2048,args_depth=3,atom_return_bytes=4096)
CTX=dict(task_spec={'instruction':'test','roles':{},'criterion_source':'SECRET_SCORER'},skill_md='public description',atoms=['a','b'],history=[],decisions_used=0,decisions_max=4,calls_remaining=90)
def payload(atom='a',finish=True):return dict(note='plan',plan=[dict(type='call',atom=atom,args={})],finish_after_plan=finish,abort=False)
def response(text):return dict(choices=[dict(message={'content':text},finish_reason='stop')],usage={'prompt_tokens':12,'completion_tokens':5})
class Caller(unittest.TestCase):
 def test_prompt_redaction_and_usage(self):
  with tempfile.TemporaryDirectory() as d:
   seen=[]
   def transport(body):seen.append(body);return response(json.dumps(payload()))
   b=m.LocalQwenBroker(ROOT,LIM,pathlib.Path(d)/'q',transport=transport);r=b.decide(CTX,'sha',0)
   self.assertNotIn('SECRET_SCORER',json.dumps(seen));self.assertEqual((r['input_tokens'],r['output_tokens']),(12,5));self.assertEqual(seen[0]['max_tokens'],1024)
 def test_transport_error_is_native_infrastructure(self):
  class Broken:
   def decide(self,*a):raise OSError('offline')
  class Infra(Exception):pass
  with self.assertRaises(Infra):m.native_provider(Broken(),Infra).decide({},'sha',0)
 def test_external_route_refused(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):m.LocalQwenBroker(ROOT,LIM,pathlib.Path(d)/'q',endpoint='https://other.example/v1/chat/completions')
 def test_budget_counts_failed_calls(self):
  with tempfile.TemporaryDirectory() as d:
   def fail(body):raise RuntimeError('synthetic failure')
   b=m.LocalQwenBroker(ROOT,dict(LIM,decisions_max=1),pathlib.Path(d)/'q',transport=fail)
   with self.assertRaises(RuntimeError):b.decide(CTX,'sha',0)
   with self.assertRaises(RuntimeError):b.decide(CTX,'sha',1)
   self.assertEqual(len(list((pathlib.Path(d)/'q').glob('*-request.json'))),1)
 def loop(self,plans,results):
  tree=ast.parse(m.checked(ROOT,'validate.py'));v={};exec(compile(tree,'validate.py','exec'),v)
  scope=dict(json=json,V=types.SimpleNamespace(**v),canonical=lambda x:x,canonical_sha=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest())
  def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x))
  def append(p,x):
   with p.open('a') as f:f.write(json.dumps(x)+'\n')
  scope.update(dump=dump,append=append)
  scope=m.pure_functions(ROOT,'episode.py',['execution_log','_parse_payload'],scope)
  for n in ['SafetyStop','SimTimeout','BudgetExhausted','WallTimeout','InfraFailure']:scope[n]=type(n,(Exception,),{})
  contexts=[];called=[];seq=iter(plans)
  class Provider:
   def decide(self,ctx,sha,k):contexts.append(ctx);return dict(raw_response=json.dumps(next(seq)),status='ok')
  scope['FileBroker']=lambda *a:Provider()
  class API:
   def _set_origin(self,x):pass
   def observe(self):return {'ok':True,'roles':{}}
   def _calls_remaining(self):return 90
   def _state(self):return {'measured':'fixture'}
  class Wall:
   def pause(self):pass
   def start(self):pass
  class Lines:
   def run(self,fn,*args):return fn(*args)
  def atom(name):
   def f(api,args):called.append(name);return results.get(name,{'ok':True})
   return f
  run,h=m.load_orchestrated(ROOT,scope)
  with tempfile.TemporaryDirectory() as d:r=run({x:atom(x) for x in ['a','b']},['a','b'],API(),Wall(),Lines(),CTX['task_spec'],'doc',LIM,pathlib.Path(d))
  return r,called,contexts,h
 def test_native_failure_breaks_plan_and_replans(self):
  p=payload('a');p['plan'].append(dict(type='call',atom='b',args={}))
  r,c,contexts,h=self.loop([p,payload('b')],{'a':{'ok':False}})
  self.assertEqual(c,['a','b']);self.assertEqual(len(contexts),2);self.assertTrue(r['result']['finished']);self.assertNotIn('plan',contexts[1]['history'][1]);self.assertEqual(len(h),64)
 def test_native_unknown_atom_no_execution(self):
  r,c,_,_=self.loop([payload('invented')],{});self.assertEqual(c,[]);self.assertEqual(r['klass'],'decision_rejected')
 def test_native_abort_no_execution(self):
  p=payload();p.update(abort=True,plan=[]);r,c,_,_=self.loop([p],{});self.assertEqual(c,[]);self.assertEqual(r['klass'],'aborted_by_caller')
if __name__=='__main__':unittest.main()
