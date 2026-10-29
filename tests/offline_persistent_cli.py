"""Real pinned CLI + upstream persistent_agent against a deterministic loopback fixture.
All returned text and token counts are SYNTHETIC. No neural model or GPU involved.
"""
import argparse,base64,json,os,subprocess,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--codex',required=True);p.add_argument('--scoped-mcp',action='store_true');a=p.parse_args()
r=Path(a.output);r.mkdir(parents=True,exist_ok=False)
requests=[]
class Fake(BaseHTTPRequestHandler):
 def do_GET(self):
  encoded=json.dumps({"ledger":{"max_backend_calls":8,"backend_attempts":len(requests)},"classification":"SYNTHETIC"}).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(encoded)));self.end_headers();self.wfile.write(encoded)
 def do_POST(self):
  b=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(b)
  (r/'fixture-requests.json').write_text(json.dumps(requests,indent=2))
  answer='- SYNTHETIC durable lesson: preserve fixture token alpha.' if len(requests)==4 else f'SYNTHETIC fixture response {len(requests)}'
  data={'model':'qwen3-vl-8b-instruct','choices':[{'index':0,'message':{'role':'assistant','content':answer},'finish_reason':'stop'}],'usage':{'prompt_tokens':111,'completion_tokens':7,'total_tokens':118}}
  if len(requests)==6:
   data['choices'][0]={'index':0,'message':{'role':'assistant','content':None,'tool_calls':[{'id':'fixture_call_view','type':'function','function':{'name':next(t['function']['name'] for t in b['tools'] if t['function']['name'].endswith('read_image')) if a.scoped_mcp else 'view_image','arguments':json.dumps({'path':str(r/'workspace'/'pixel.png')})}}]},'finish_reason':'tool_calls'}
  if len(requests)==8:
   encoded=json.dumps({'error':{'message':'SYNTHETIC forced backend failure'}}).encode();self.send_response(400);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded);return
  encoded=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
server=HTTPServer(('127.0.0.1',0),Fake);threading.Thread(target=server.serve_forever,daemon=True).start()
probe=HTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler);port=probe.server_port;probe.server_close()
log=(r/'adapter.log').open('w')
adapter=subprocess.Popen([sys.executable,'scripts/responses_adapter.py','--upstream',f'http://127.0.0.1:{server.server_port}','--port',str(port),'--output',str(r/'adapter')],stdout=log,stderr=log)
home=r/'codex-home';home.mkdir();robo=r/'roborsi-home';robo.mkdir()
(home/'config.toml').write_text(f'''model = "qwen3-vl-8b-instruct"
model_provider = "qwen_local"
model_context_window = 32768
model_auto_compact_token_limit = 28000
model_supports_reasoning_summaries = false
web_search = "disabled"
[model_providers.qwen_local]
name = "Fixed local Qwen"
base_url = "http://127.0.0.1:{port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
supports_websockets = false
[analytics]
enabled = false
[feedback]
enabled = false
[otel]
exporter = "none"
metrics_exporter = "none"
trace_exporter = "none"
[features]
multi_agent = false
apps = false
plugins = false
image_generation = false
browser_use = false
computer_use = false
''')
if a.scoped_mcp:
 with (home/'config.toml').open('a') as f:
  f.write('\nshell_tool = false\nview_image = false\n[mcp_servers.role_evidence]\ncommand = '+json.dumps(sys.executable)+'\nargs = '+json.dumps([str(Path('scripts/readonly_role_mcp.py').resolve()),'--root',str(r/'workspace'),'--audit',str(r/'mcp-audit.jsonl')])+'\nstartup_timeout_sec = 20\ntool_timeout_sec = 20\n')
# No inherited credentials or HOME configuration. Preserve Python import path.
for k in list(os.environ):
 if any(x in k for x in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN')):os.environ.pop(k,None)
os.environ.update(CODEX_HOME=str(home),ROBORSI_HOME=str(robo),ROBORSI_ROLE_BACKEND='codex',ROBORSI_ROLE_SESSION='1',ROBORSI_SESSION_ROLL_CHARS='10000000')
# The same explicit permission adaptation as the online canary: remove
# upstream yolo and force read-only/never for both fresh and resumed turns.
bin_dir=r/'bin';bin_dir.mkdir();wrapper=bin_dir/'codex'
wrapper.write_text('#!'+sys.executable+'\nimport os,sys\nargs=[x for x in sys.argv[1:] if x!="--dangerously-bypass-approvals-and-sandbox"]\ncmd='+repr([a.codex,'-c','sandbox_mode="read-only"','-c','approval_policy="never"'])+'+args\nos.execv(cmd[0],cmd)\n');wrapper.chmod(0o755)
os.environ['PATH']=str(bin_dir)+':'+os.environ['PATH']
try:
 for _ in range(60):
  try:urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1);break
  except OSError:time.sleep(.1)
 from roborsi.agents.sessions import persistent_agent as pa
 # Use an isolated actual Git checkout as the working dir; model output is fixed.
 workspace=r/'workspace';workspace.mkdir();subprocess.run(['git','init','-q',str(workspace)],check=True)
 pa._REPO=workspace
 from PIL import Image
 image=workspace/'pixel.png';Image.new('RGB',(64,64),(255,0,0)).save(image)
 out=[]
 out.append(pa.run('planner','transport_fixture','remember alpha',system_prompt='Fixture only',model='openai/qwen3-vl-8b-instruct',images=[str(image)]))
 sid=pa.session_id('planner','transport_fixture');assert sid
 out.append(pa.run('planner','transport_fixture','recall earlier observation',system_prompt='Fixture only',model='openai/qwen3-vl-8b-instruct'))
 assert pa.session_id('planner','transport_fixture')==sid,'resume changed session id'
 os.environ['ROBORSI_SESSION_ROLL_CHARS']='1'
 out.append(pa.run('planner','transport_fixture','trigger manager roll',system_prompt='Fixture only',model='openai/qwen3-vl-8b-instruct'))
 assert pa.session_id('planner','transport_fixture') is None
 assert pa.memory_file('planner','transport_fixture').exists()
 os.environ['ROBORSI_SESSION_ROLL_CHARS']='10000000'
 out.append(pa.run('planner','transport_fixture','start successor',system_prompt='Fixture only',model='openai/qwen3-vl-8b-instruct'))
 assert pa.session_id('planner','transport_fixture')!=sid
 assert len(requests)==5,(len(requests),out)
 out.append(pa.run('reviewer','transport_fixture','inspect the fixture image with a tool',system_prompt='Fixture only',model='openai/qwen3-vl-8b-instruct'))
 assert len(requests)==7
 assert any(m.get('tool_call_id')=='fixture_call_view' for m in requests[6]['messages'])
 try:
  pa.run('reviewer','transport_failure','force one failure',system_prompt='Fixture only',model='openai/qwen3-vl-8b-instruct')
  raise AssertionError('backend failure was falsely treated as success')
 except RuntimeError:
  assert len(requests)==8,'failure was retried invisibly'
 assert 'remember alpha' in json.dumps(requests[1])
 assert 'data:image/png;base64,' in json.dumps(requests[0])
 assert 'Compact your own memory' in json.dumps(requests[3])
 assert 'SYNTHETIC durable lesson' in json.dumps(requests[4])
 result={'status':'passed','classification':'offline synthetic fixture only','model_calls':0,'gpu_jobs':0,'synthetic_backend_requests':len(requests),'real_cli_version':'0.165.0','permission_adaptation':'strip upstream yolo; read-only/never','scoped_read_mcp':a.scoped_mcp,'checks':['upstream persistent_agent fresh run','same ID resume with full text/image history','manager summary call','manager clears prior session','successor seeded with memory','real CLI view_image tool call/output ID and image serialization','backend HTTP failure reaches upstream runner without hidden retry'],'outputs':out}
except Exception as e:
 result={'status':'failed','classification':'offline synthetic fixture only','model_calls':0,'gpu_jobs':0,'synthetic_backend_requests':len(requests),'error':repr(e)}
finally:
 adapter.terminate();adapter.wait(timeout=10);server.shutdown();log.close()
(r/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));sys.exit(0 if result['status']=='passed' else 1)
