"""Bounded *full* native RoboRSI development pilot, with explicit local adaptations.
Prepare is CPU-only. Starting rpc/cap-bridge/run requires a separately frozen
protocol; no service, GPU, model generation or allowance is auto-created here.
This is not a VLA baseline and not a strong OS sandbox for native exec_python.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,os,shutil,subprocess,sys,time,urllib.error,urllib.parse,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path

MODEL='qwen3-vl-8b-instruct'
ROLE_MODEL='openai/'+MODEL
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path('/root/autodl-tmp/Dex_runtime/agent-rsi')
VENDOR=RUNTIME/'vendor/RoboRSI-90c8569705bf4004a4f79e34e650c87ab7f075d4'
CODEX=RUNTIME/'software/codex-0.165.0/package/vendor/x86_64-unknown-linux-musl/bin/codex'
ROLE_VARS=('ROBORSI_PLANNER_MODEL','ROBORSI_ENGINEER_MODEL','ROBORSI_REVIEWER_MODEL','ROBORSI_VLM_MODEL','ROBORSI_SKILL_SELECTOR_MODEL','ROBORSI_PERCEPTION_MODEL')
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('redirect forbidden')
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def local(url):
    u=urllib.parse.urlparse(url)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port or u.username or u.query or u.fragment:raise ValueError('explicit loopback URL required')
    return url.rstrip('/')
def get(url):
    with OPENER.open(url,timeout=8) as f:return json.load(f)
def write(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def clean_environment(state):
    # No inherited provider, proxy, authentication, user configuration, or model
    # routing. These are transport restrictions, not a filesystem sandbox.
    for key in list(os.environ):
        if any(x in key.upper() for x in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','ANTHROPIC','AZURE','GEMINI','GOOGLE_APPLICATION_CREDENTIALS','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')) or key.startswith(('ROBORSI_','CODEX_','OPENAI_')):
            os.environ.pop(key,None)
    env=state['environment'];os.environ.update(env)
    os.environ['PATH']=str(Path(state['run_root'])/'bin')+':'+os.environ['PATH']
    source=state['source'];os.environ['PYTHONPATH']=source
    sys.path.insert(0,source)
    os.chdir(state['workspace'])

def prepare(output,budget_url,adapter_url,cap_url,rpc_url,images=()):
    r=Path(output).resolve();r.mkdir(parents=True,exist_ok=False)
    source=r/'source';shutil.copytree(VENDOR,source,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc'))
    # Preserve an exact code/skill snapshot, separate from every other experiment.
    subprocess.run(['git','init','-q',str(source)],check=True)
    work=r/'workspace';work.mkdir();subprocess.run(['git','init','-q',str(work)],check=True)
    for name in ('home','codex-home','roborsi-home','bin','input-images'):(r/name).mkdir()
    image_paths=[]
    for path in images:
        p=Path(path).resolve(strict=True);dest=r/'input-images'/p.name;shutil.copy2(p,dest);image_paths.append(str(dest))
    from qualify_native_vision import verify_models
    vision=verify_models()
    model_env={k:ROLE_MODEL for k in ROLE_VARS}
    model_env.update(ROBORSI_GROUNDING_DINO_MODEL=vision['dino']['directory'],ROBORSI_POINT_SAM_MODEL=vision['sam']['directory'],ROBORSI_PERCEPTION_DEVICE='cuda:0')
    model_env.update({'ROBORSI_VLM_PROVIDER':'openai','ROBORSI_OPENAI_BASE_URL':local(cap_url)+'/v1','OPENAI_BASE_URL':local(cap_url)+'/v1','ROBORSI_OPENAI_API_KEY':'local-only-no-secret','OPENAI_API_KEY':'local-only-no-secret','ROBORSI_OPENAI_TRANSPORT':'chat_completions','ROBORSI_OPENAI_MAX_OUTPUT_TOKENS':'1024','ROBORSI_ROLE_BACKEND':'codex','ROBORSI_ROLE_SESSION':'1','ROBORSI_SESSION_ROLL_CHARS':'600000','ROBORSI_HOME':str(r/'roborsi-home'),'ROBORSI_WORKSPACE':str(r/'roborsi-home'/'workspace'),'CODEX_HOME':str(r/'codex-home'),'HOME':str(r/'home'),'ROBORSI_SIM_URL':local(rpc_url),'ROBORSI_ROBOTWIN_ROOT':str(RUNTIME/'backends/robotwin-ae507381-c15cc97b'),'NO_PROXY':'127.0.0.1,localhost','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','ROBORSI_USE_GRASPGEN':'0'})
    config=f'''model = "{MODEL}"
model_provider = "qwen_local"
model_context_window = 32768
model_auto_compact_token_limit = 28000
model_supports_reasoning_summaries = false
web_search = "disabled"
sandbox_mode = "read-only"
approval_policy = "never"
[model_providers.qwen_local]
name = "Fixed local Qwen"
base_url = "{local(adapter_url)}/v1"
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
shell_tool = false
view_image = false
[mcp_servers.role_evidence]
command = {json.dumps(sys.executable)}
args = {json.dumps([str(ROOT/'scripts/readonly_role_mcp.py'),'--root',str(source),'--root',str(work),'--root',str(r/'roborsi-home'),'--root',str(r/'input-images'),'--audit',str(r/'mcp-audit.jsonl')])}
startup_timeout_sec = 20
tool_timeout_sec = 20
'''
    (r/'codex-home/config.toml').write_text(config)
    wrapper=r/'bin/codex'
    wrapper.write_text('#!'+sys.executable+'\nimport json,os,sys\nargs=[x for x in sys.argv[1:] if x!="--dangerously-bypass-approvals-and-sandbox"]\ncmd='+repr([str(CODEX),'-c','sandbox_mode="read-only"','-c','approval_policy="never"'])+'+args\nwith open('+repr(str(r/'cli-launches.jsonl'))+',"a") as f:f.write(json.dumps({"incoming":sys.argv[1:],"outgoing":cmd})+"\\n")\nos.execv(cmd[0],cmd)\n');wrapper.chmod(0o755)
    files={str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*')) if p.is_file() and '.git' not in p.parts}
    write(r/'source-manifest.json',files)
    state={'status':'PREPARED_NOT_AUTHORIZED_TO_GENERATE','classification':'full native RoboRSI frozen-eval development qualification; local Qwen/tool transport adaptation; NOT VLA or faithful backbone reproduction','run_root':str(r),'source':str(source),'workspace':str(work),'images':image_paths,'source_manifest_sha256':sha(r/'source-manifest.json'),'upstream_commit':'90c8569705bf4004a4f79e34e650c87ab7f075d4','budget_url':local(budget_url),'adapter_url':local(adapter_url),'cap_url':local(cap_url),'rpc_url':local(rpc_url),'environment':model_env,'model':MODEL,'max_output_tokens':1024,'max_physics_steps':20000,'wall_seconds':1800,'native_vision_manifest':str(ROOT/'configs/native-vision-models.json'),'native_vision_manifest_sha256':sha(ROOT/'configs/native-vision-models.json'),'verified_native_vision':vision,'tool_surface':'native Engineer skills unchanged; Planner/Reviewer shell/view_image replaced by scoped read/list/search/image MCP; persistent sessions kept','isolation_limit':'Native exec_python uses same-process Python+NumPy; this is NOT a strong FS/network sandbox. No D_final/D_curve exists or is mounted. Qualification development files only.','script_hashes':{str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'scripts/responses_adapter.py',ROOT/'scripts/readonly_role_mcp.py',ROOT/'scripts/roborsi_rpc_compat.py',ROOT/'scripts/qualify_native_vision.py')}}
    write(r/'state.json',state);return state

def cap_request(body):
    out=copy.deepcopy(body)
    if out.get('model')!=MODEL:raise ValueError('fixed local model required')
    caps={k:out[k] for k in ('max_completion_tokens','max_tokens') if k in out}
    if len(caps)>1 and len(set(caps.values()))>1:raise ValueError('conflicting output cap fields')
    requested=next(iter(caps.values()),512)
    if type(requested) is not int or requested<=0:raise ValueError('positive output cap required')
    out.pop('max_completion_tokens',None);out['max_tokens']=min(requested,1024)
    return out,{'original_caps':caps,'applied_cap':out['max_tokens'],'explicit_adaptation':'native requested output reduced to common fixed <=1024; no budget increase'}

def cap_bridge(state,output):
    ledger=get(state['budget_url']+'/health')['ledger'];assert ledger['max_backend_calls']>0
    r=Path(output);r.mkdir(parents=True,exist_ok=False)
    identity={'model':MODEL,'upstream':state['budget_url'],'cap':1024,'state_sha256':sha(Path(state['run_root'])/'state.json'),'script_sha256':sha(__file__),'ledger_started_unix':ledger['started_unix']}
    write(r/'identity.json',identity)
    class H(BaseHTTPRequestHandler):
        counter=0
        def send(self,status,b,kind='application/json'):
            if not isinstance(b,bytes):b=json.dumps(b).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def do_GET(self):
            if self.path=='/health':return self.send(200,{'identity':identity,'ledger':get(state['budget_url']+'/health')['ledger']})
            self.send(404,{'error':'unsupported endpoint'})
        def do_POST(self):
            if self.path!='/v1/chat/completions':return self.send(404,{'error':'unsupported endpoint'})
            H.counter+=1;idx=f'{H.counter:04d}';audit={'started_unix':time.time()}
            try:
                n=int(self.headers.get('Content-Length',0));assert 0<n<12*1024*1024
                incoming=json.loads(self.rfile.read(n));write(r/(idx+'-incoming.json'),incoming)
                out,adapt=cap_request(incoming);audit.update(adapt);write(r/(idx+'-forwarded.json'),out)
                req=urllib.request.Request(state['budget_url']+'/v1/chat/completions',data=json.dumps(out).encode(),headers={'Content-Type':'application/json'})
                with OPENER.open(req,timeout=200) as f:raw=f.read();kind=f.headers.get('Content-Type','application/json')
                (r/(idx+'-response.bin')).write_bytes(raw);audit['http_status']=200;self.send(200,raw,kind)
            except urllib.error.HTTPError as e:
                raw=e.read();audit.update(http_status=e.code,error=raw.decode(errors='replace'));self.send(e.code,raw)
            except Exception as e:
                audit.update(http_status=400,error=repr(e));self.send(400,{'error':repr(e)})
            finally:write(r/(idx+'-audit.json'),audit)
    HTTPServer(('127.0.0.1',urllib.parse.urlparse(state['cap_url']).port),H).serve_forever()

def route_health(state):
    budget=get(state['budget_url']+'/health');cap=get(state['cap_url']+'/health');adapter=get(state['adapter_url']+'/health')
    if cap['identity']['upstream']!=state['budget_url'] or adapter['identity']['upstream']!=state['budget_url']:raise ValueError('split ledger routes')
    if cap['identity']['cap']!=1024 or adapter['identity']['max_output']!=1024:raise ValueError('cap mismatch')
    if cap['ledger']['started_unix']!=budget['ledger']['started_unix']:raise ValueError('different ledger identity')
    return {'budget':budget,'cap':cap,'adapter':adapter}

def rpc(state,protocol):
    frozen=json.loads(Path(protocol).read_text())
    assert frozen['status']=='FROZEN' and frozen['state_sha256']==sha(Path(state['run_root'])/'state.json')
    assert 0<frozen['max_physics_steps']<=state['max_physics_steps'] and 0<frozen['wall_seconds']<=state['wall_seconds']
    from qualify_native_vision import verify_models
    assert sha(state['native_vision_manifest'])==state['native_vision_manifest_sha256']
    assert verify_models()==state['verified_native_vision']
    clean_environment(state)
    if state.get('capability_contract'):
        from native_contracts import install_capabilities
        install_capabilities(Path(state['run_root'])/'capabilities-rpc.json')
    routes=route_health(state)
    from roborsi_rpc_compat import install_runtime
    runtime_identity=install_runtime(root=Path(os.environ['ROBORSI_ROBOTWIN_ROOT']),gpu=1,max_physics_steps=frozen['max_physics_steps'],audit_path=Path(state['run_root'])/'rpc-runtime.json')
    # Read-only native vision compute accounting; preserve outputs/exceptions/cache.
    import importlib
    vision_module=importlib.import_module('roborsi.embodied.skills.base.detect_object.robotwin.policy')
    original_load=vision_module._load
    vision_cost={'loads':0,'load_seconds':0.0,'dino_calls':0,'sam_calls':0,'forward_seconds':0.0,'failed_forwards':0}
    def save_vision():write(Path(state['run_root'])/'vision-cost.json',dict(vision_cost,cache_stats=vision_module.cache_stats()))
    def metered_load():
        if getattr(vision_module,'_rsi_metered',False):return original_load()
        start=time.monotonic()
        values=original_load();vision_cost['loads']+=1;vision_cost['load_seconds']+=time.monotonic()-start
        for name,model in [('dino',values[1]),('sam',values[3])]:
            original_forward=model.forward
            def forward(*args,_fn=original_forward,_name=name,**kwargs):
                import torch
                start=time.monotonic();vision_cost[_name+'_calls']+=1
                try:return _fn(*args,**kwargs)
                except Exception:vision_cost['failed_forwards']+=1;raise
                finally:
                    torch.cuda.synchronize();vision_cost['forward_seconds']+=time.monotonic()-start;save_vision()
            model.forward=forward
        vision_module._rsi_metered=True;save_vision();return values
    vision_module._load=metered_load;save_vision()
    from roborsi.embodied.sim.robotwin.server import app
    @app.get('/rsi-qualification')
    def identity():
        return {'runtime':runtime_identity,'state_sha256':sha(Path(state['run_root'])/'state.json'),'model_routes':{k:os.environ[k] for k in ROLE_VARS},'model_api':os.environ['ROBORSI_OPENAI_BASE_URL'],'role_session':os.environ['ROBORSI_ROLE_SESSION'],'ledger_started_unix':routes['budget']['ledger']['started_unix'],'script_sha256':sha(__file__),'classification':'full native RoboRSI development qualification with explicit local transport adaptation'}
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=urllib.parse.urlparse(state['rpc_url']).port,log_level='info')

def run(state,protocol):
    frozen=json.loads(Path(protocol).read_text())
    assert frozen['status']=='FROZEN' and frozen['state_sha256']==sha(Path(state['run_root'])/'state.json')
    assert frozen['classification']=='native_roborsi_development_qualification' and frozen['mode']=='eval' and frozen['agent_mode']=='roborsi'
    assert frozen['tasks'] and all(t['task'] in ('stack_blocks_two','handover_block') for t in frozen['tasks'])
    assert all(type(t['seed']) is int for t in frozen['tasks'])
    assert frozen['max_model_calls']>0 and 0<frozen['tool_budget']<=40
    assert frozen['max_output_tokens']==1024 and frozen['max_input_tokens']==32768
    assert 0<frozen['max_physics_steps']<=state['max_physics_steps'] and 0<frozen['wall_seconds']<=state['wall_seconds']
    for path,h in state['script_hashes'].items():assert sha(ROOT/path)==h,'code changed after preparation'
    clean_environment(state)
    if state.get('capability_contract'):
        from native_contracts import install_capabilities
        install_capabilities(Path(state['run_root'])/'capabilities-client.json')
    routes=route_health(state)
    ledger=routes['budget']['ledger'];assert ledger['backend_attempts']==0 and ledger['max_backend_calls']==frozen['max_model_calls']
    rpc_id=get(state['rpc_url']+'/rsi-qualification')
    assert rpc_id['state_sha256']==sha(Path(state['run_root'])/'state.json')
    assert rpc_id['ledger_started_unix']==ledger['started_unix'] and rpc_id['model_api']==state['cap_url']+'/v1'
    assert all(v==ROLE_MODEL for v in rpc_id['model_routes'].values())
    assert get(state['rpc_url']+'/healthz')['ok']
    from roborsi.agents.sessions import persistent_agent as pa
    pa._REPO=Path(state['workspace'])
    if state.get('reviewer_contract')=='explicit-evidence-v1':
        from reviewer_contract import install_native_contract
        install_native_contract(state,pa)
    if state.get('public_language_manifest'):
        from task_language_contract import load, install
        assert sha(state['public_language_manifest'])==state['public_language_manifest_sha256']
        instructions=load(state['public_language_manifest'],RUNTIME/'backends/robotwin-ae507381-c15cc97b')
        from roborsi.embodied.sim.robotwin.client import HttpRobotwinEnv
        install(HttpRobotwinEnv,instructions)
        from native_contracts import install_role_audit
        install_role_audit(instructions,Path(state['run_root'])/'role-language-audit.jsonl',lambda:get(state['budget_url']+'/health')['ledger']['backend_attempts'])
    from roborsi.evaluation.atomic import run_atomic_attempt
    from roborsi.runtime_mode import RunMode
    r=Path(state['run_root']);report={'classification':state['classification'],'protocol_sha256':sha(protocol),'initial_ledger':ledger,'rpc_identity':rpc_id,'attempts':[],'strict_rsi_rounds':0,'vla_episodes':0}
    try:
        for task in frozen['tasks']:
            result=run_atomic_attempt(task=task['task'],seed=task['seed'],mode=RunMode.EVAL,tool_budget=frozen['tool_budget'],backend='robotwin-http',planner_model=ROLE_MODEL,engineer_model=ROLE_MODEL,reviewer_model=ROLE_MODEL,agent_mode='roborsi')
            report['attempts'].append(result);report['latest_ledger']=get(state['budget_url']+'/health')['ledger'];write(r/'pilot-report.json',report)
            if result.get('status')!='terminal':break
        report['status']='finished_bounded_attempts'
    except Exception as e:report.update(status='failed',error=repr(e))
    finally:
        report['final_ledger']=get(state['budget_url']+'/health')['ledger'];report['unused_calls']='cancel; never consume merely to exhaust allowance';write(r/'pilot-report.json',report)
    print(json.dumps(report,indent=2));return report

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
    q=s.add_parser('prepare');q.add_argument('--output',required=True);q.add_argument('--image',action='append',default=[])
    for n,v in (('budget-url','http://127.0.0.1:18019'),('adapter-url','http://127.0.0.1:18020'),('cap-url','http://127.0.0.1:18021'),('rpc-url','http://127.0.0.1:8181')):q.add_argument('--'+n,default=v)
    for name in ('cap-bridge','rpc','run'):
        q=s.add_parser(name);q.add_argument('--state',required=True)
        if name=='cap-bridge':q.add_argument('--output',required=True)
        if name in ('run','rpc'):q.add_argument('--protocol',required=True)
    a=p.parse_args()
    if a.cmd=='prepare':print(json.dumps(prepare(a.output,a.budget_url,a.adapter_url,a.cap_url,a.rpc_url,a.image),indent=2));return
    state=json.loads(Path(a.state).read_text())
    if a.cmd=='cap-bridge':cap_bridge(state,a.output)
    elif a.cmd=='rpc':rpc(state,a.protocol)
    else:run(state,a.protocol)
if __name__=='__main__':main()
