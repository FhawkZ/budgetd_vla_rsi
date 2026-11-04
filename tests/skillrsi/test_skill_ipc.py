import json,os,pathlib,subprocess,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
from skill_rsi_skill_ipc import PublicAPI,run_skill
ROOT=pathlib.Path('/root/autodl-tmp/Dex_runtime/agent-rsi/vendor/Skill-RSI-3483ea128ba432730f135aac326da1b768b671e4/runtime')
SOURCE="""ATOMS=['demo']
def demo(api,args):
    spec=api.task_spec()
    pose=api.ee_pose('left')
    ok=api.move_pose('left',pose)
    return {'instruction':spec['instruction'],'roles':spec['roles'],'ok':ok}
def fallback(api):
    return demo(api,{})
"""
class FakeAPI:
 def __init__(self):self.calls=[]
 def task_spec(self):return dict(instruction='synthetic CPU fixture',roles={'target':'object'},criterion_source='SECRET_SCORER',layout='SECRET_LAYOUT')
 def ee_pose(self,arm):return [0.,0.,1.,0.,0.,0.,1.]
 def move_pose(self,arm,pose):self.calls.append((arm,pose));return True
class Boundary(unittest.TestCase):
 def test_cpu_skill_contract_roundtrip_redacts_scorer(self):
  with tempfile.TemporaryDirectory() as d:
   api=FakeAPI();r=run_skill(SOURCE,'demo',{},api,ROOT,pathlib.Path(d)/'out')
   self.assertEqual(r['status'],'result',r);self.assertEqual(r['exit_code'],0);self.assertEqual(len(api.calls),1)
   self.assertTrue(r['ready']['seccomp_allowlist']);self.assertEqual(r['api_requests'],3)
   self.assertNotIn('SECRET_', (pathlib.Path(d)/'out/events.jsonl').read_text())
 def test_native_static_rejection_no_backend_call(self):
  with tempfile.TemporaryDirectory() as d:
   api=FakeAPI();r=run_skill('import os\n'+SOURCE,'demo',{},api,ROOT,pathlib.Path(d)/'out')
   self.assertEqual(r['status'],'rejected');self.assertEqual(api.calls,[]);self.assertNotIn('ready',r)
 def test_broker_unknown_method_and_nested_evaluator_rejected(self):
  p=PublicAPI(FakeAPI(),3)
  for method,args in [('_state',{}),('check_success',{}),('move_pose',{'arm':'left','pose':{'layout':'x'}})]:
   with self.assertRaises(ValueError):p.dispatch(method,args)
  with self.assertRaises(RuntimeError):p.dispatch('task_spec',{})
 def test_native_runtime_budget_nontermination_stopped(self):
  # Function definitions are not executed before filter; recursion/CPU work stays in child.
  source="""ATOMS=['demo']
def demo(api,args):
    for i in range(1000000000):
        x=i*i
    return True
def fallback(api):
    return demo(api,{})
"""
  with tempfile.TemporaryDirectory() as d:
   r=run_skill(source,'demo',{},FakeAPI(),ROOT,pathlib.Path(d)/'out',timeout=.7)
   self.assertEqual(r['status'],'rejected_or_error');self.assertIn('Timeout',r['error']);self.assertLess(r['seconds'],2)
 def test_seccomp_denies_real_file_socket_and_process_creation(self):
  # Trusted containment probe deliberately bypasses candidate AST validation.
  code="""import sys,json,os,socket
sys.path.insert(0,sys.argv[1])
from skill_rsi_skill_worker import restrict_cpu
restrict_cpu()
r={}
for name,fn in [('file',lambda:os.open('/etc/hostname',os.O_RDONLY)),('socket',lambda:socket.socket()),('fork',lambda:os.fork())]:
    try:
        v=fn()
        if name=='fork' and v==0:os._exit(2)
        r[name]='ALLOWED'
        if name=='file':os.close(v)
        if name=='socket':v.close()
        if name=='fork':os.waitpid(v,0)
    except OSError as e:r[name]=e.errno
print(json.dumps(r))
"""
  p=subprocess.run([sys.executable,'-I','-B','-c',code,str(pathlib.Path(__file__).resolve().parents[2]/'scripts')],capture_output=True,text=True,timeout=5,env={'PATH':'/usr/bin:/bin'})
  self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout),{'file':1,'socket':1,'fork':1})
 def test_memory_pressure_is_child_failure_not_parent_mutation(self):
  s=SOURCE.replace("spec=api.task_spec()","x=[0]*100000000\n    spec=api.task_spec()")
  with tempfile.TemporaryDirectory() as d:
   api=FakeAPI();r=run_skill(s,'demo',{},api,ROOT,pathlib.Path(d)/'out')
   self.assertEqual(r['status'],'error',r);self.assertEqual(r['terminal']['error_class'],'MemoryError');self.assertEqual(api.calls,[])
if __name__=='__main__':unittest.main()
