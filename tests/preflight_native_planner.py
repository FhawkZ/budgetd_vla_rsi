"""Native Planner+fixed CLI wire capture with real reset images, zero generation.
SkillSelector gets a synthetic fixed shortlist; later history size is not implied.
"""
import argparse,importlib.util,json,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pilot',ROOT/'scripts/run_roborsi_native_pilot.py');pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--image',action='append',required=True);a=p.parse_args()
def port():
 s=HTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler);n=s.server_port;s.server_close();return n
requests=[]
class Fixture(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send(200,{'ledger':{'max_backend_calls':8,'backend_attempts':len(requests),'started_unix':1},'classification':'SYNTHETIC_NO_GENERATION'})
 def send(self,status,data):
  b=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  b=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(b)
  pilot.write(Path(a.output)/'wire-requests.json',requests)
  selected=['observe','find_pixel','sample_world_xyz','move_to_pose','gripper','grasp_then_lift','place_on_surface','done']
  answer=json.dumps(selected) if 'SKILL SELECTOR sub-agent' in json.dumps(b) else '```json\n{"task":"stack_blocks_two","candidate_skills":["observe","done"],"sub_goals":["SYNTHETIC fixture"],"success_criteria":"SYNTHETIC fixture"}\n```\n# SYNTHETIC fixture plan\nNo execution.'
  self.send(200,{'id':'fixture-'+str(len(requests)),'object':'chat.completion','created':1,'model':pilot.MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':answer},'finish_reason':'stop'}],'usage':{'prompt_tokens':111,'completion_tokens':7,'total_tokens':118}})
fake=HTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=fake.serve_forever,daemon=True).start()
state=pilot.prepare(a.output,'http://127.0.0.1:'+str(fake.server_port),'http://127.0.0.1:'+str(port()),'http://127.0.0.1:'+str(port()),'http://127.0.0.1:'+str(port()),a.image)
r=Path(a.output);procs=[];logs=[]
try:
 for script,args,logname in [(ROOT/'scripts/responses_adapter.py',['--upstream',state['budget_url'],'--port',state['adapter_url'].split(':')[-1],'--output',str(r/'adapter')],'adapter.log'),(ROOT/'scripts/run_roborsi_native_pilot.py',['cap-bridge','--state',str(r/'state.json'),'--output',str(r/'cap-bridge')],'cap.log')]:
  log=(r/logname).open('w');logs.append(log);procs.append(subprocess.Popen([sys.executable,str(script)]+args,stdout=log,stderr=log))
 for url in (state['cap_url'],state['adapter_url']):
  for _ in range(100):
   try:pilot.get(url+'/health');break
   except OSError:time.sleep(.1)
  else:raise RuntimeError('fixture service not ready')
 pilot.clean_environment(state)
 from roborsi.agents.sessions import persistent_agent
 persistent_agent._REPO=Path(state['workspace'])
 from roborsi.agents.memory.workspace import new_workspace
 from roborsi.agents.roles.planner import Planner
 from roborsi.runtime_mode import RunMode,use_run_mode
 with use_run_mode(RunMode.EVAL):
  result=Planner(model=pilot.ROLE_MODEL).plan(task='stack_blocks_two',user_msg='Evaluate atomic task stack_blocks_two at seed=42 using the frozen released capability set.',recent_reflections='',workspace=new_workspace('stack_blocks_two'),images=state['images'])
 assert len(requests)==2,len(requests)
 assert len([t for t in requests[1]['tools'] if t['function']['name'].startswith('mcp__role_evidence__')])==4,'MCP tool surface mismatch'
 assert 'data:image/' in json.dumps(requests[1])
 pilot.write(r/'report.json',{'status':'passed','model_generations':0,'physical_episodes':0,'synthetic_responses':2,'roles':['native SkillSelector request','native persistent Planner CLI first request'],'limits':'fixed mock shortlist; Reviewer/Engineer history size not claimed; no neural task performance','result':result})
 print(json.dumps({'status':'passed','wire_requests':len(requests),'output':str(r)}))
finally:
 for proc in procs:proc.terminate();proc.wait(timeout=10)
 for log in logs:log.close()
 fake.shutdown()
