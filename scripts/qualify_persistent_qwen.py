"""Five real model calls for session transport only, under a separate 12-call cap.
No robot task or baseline score. Does not launch a model, adapter or budget proxy.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time, urllib.request
from pathlib import Path
from PIL import Image


def get(url):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=5) as f:
        return json.load(f)


def main():
    p=argparse.ArgumentParser()
    for name in ('budget-url','adapter-url','codex','protocol','output'):
        p.add_argument('--'+name, required=True)
    a=p.parse_args()
    protocol=Path(a.protocol)
    assert protocol.is_file()
    ledger=get(a.budget_url.rstrip('/')+'/health')['ledger']
    assert ledger['max_backend_calls']==12 and ledger['backend_attempts']==0, 'new fixed 12-call budget required'
    identity=get(a.adapter_url.rstrip('/')+'/health')['identity']
    assert identity['max_output']==1024 and identity['model']=='qwen3-vl-8b-instruct'
    assert identity['upstream']==a.budget_url.rstrip('/')
    r=Path(a.output);r.mkdir(parents=True,exist_ok=False)
    home=r/'codex-home';home.mkdir();robo=r/'roborsi-home';robo.mkdir()
    workspace=r/'workspace';workspace.mkdir();subprocess.run(['git','init','-q',str(workspace)],check=True)
    pixel=workspace/'synthetic-red-square.png';Image.new('RGB',(64,64),(255,0,0)).save(pixel)
    (home/'config.toml').write_text(f'''model = "qwen3-vl-8b-instruct"
model_provider = "qwen_local"
model_context_window = 32768
model_auto_compact_token_limit = 28000
model_supports_reasoning_summaries = false
web_search = "disabled"
sandbox_mode = "read-only"
approval_policy = "never"
[model_providers.qwen_local]
name = "Fixed local Qwen"
base_url = "{a.adapter_url.rstrip('/')}/v1"
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
''')
    # Wrapping changes permission enforcement only. Upstream persistence, prompt,
    # role/task IDs, image arguments, resume and manager roll remain active.
    bin_dir=r/'bin';bin_dir.mkdir();wrapper=bin_dir/'codex'
    wrapper.write_text('#!'+sys.executable+'\nimport json,os,sys\nfrom pathlib import Path\nargs=[x for x in sys.argv[1:] if x!="--dangerously-bypass-approvals-and-sandbox"]\ncmd='+repr([a.codex,'-c','sandbox_mode="read-only"','-c','approval_policy="never"'])+'+args\nwith open('+repr(str(r/'cli-launches.jsonl'))+',"a") as f:f.write(json.dumps({"incoming":sys.argv[1:],"outgoing":cmd})+"\\n")\nos.execv(cmd[0],cmd)\n');wrapper.chmod(0o755)
    for key in list(os.environ):
        if any(x in key for x in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN')):
            os.environ.pop(key,None)
    os.environ.update(CODEX_HOME=str(home),ROBORSI_HOME=str(robo),ROBORSI_WORKSPACE=str(robo/'workspace'),ROBORSI_ROLE_BACKEND='codex',ROBORSI_ROLE_SESSION='1',ROBORSI_SESSION_ROLL_CHARS='10000000',PATH=str(bin_dir)+':'+os.environ['PATH'])
    from roborsi.agents.sessions import persistent_agent as pa
    pa._REPO=workspace
    result={'classification':'online persistent-transport qualification; not task/RSI performance','started_unix':time.time(),'protocol_sha256':hashlib.sha256(protocol.read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'adapter_identity':identity,'start_ledger':ledger,'outputs':[],'checks':[]}
    (r/'started.json').write_text(json.dumps(result,indent=2))
    def turn(prompt,images=None):
        output=pa.run('planner','qwen_transport_fixture',prompt,system_prompt='This is a short local transport canary with a synthetic image. Answer using only the supplied conversation. Do not call tools, read files, or make network requests. Keep the answer under 80 words.',model='openai/qwen3-vl-8b-instruct',images=images)
        result['outputs'].append({'prompt':prompt,'response':output,'ledger':get(a.budget_url.rstrip('/')+'/health')['ledger']})
        (r/'progress.json').write_text(json.dumps(result,indent=2))
        return output
    try:
        turn('Observe the square image and remember marker ORBIT-731. Reply with its color and the marker.',[str(pixel)])
        sid=pa.session_id('planner','qwen_transport_fixture');assert sid
        turn('State the color and marker from the previous turn; say unknown if unavailable.')
        assert pa.session_id('planner','qwen_transport_fixture')==sid
        result['checks'].append('same task-role session ID resumed')
        os.environ['ROBORSI_SESSION_ROLL_CHARS']='1'
        turn('Write one durable lesson preserving the observed color and marker. Do not use tools.')
        memory=pa.memory_file('planner','qwen_transport_fixture')
        assert memory.is_file() and pa.session_id('planner','qwen_transport_fixture') is None, 'manager roll failed'
        result['checks'].append('upstream manager roll wrote memory and cleared predecessor session')
        result['memory_sha256']=hashlib.sha256(memory.read_bytes()).hexdigest()
        os.environ['ROBORSI_SESSION_ROLL_CHARS']='10000000'
        turn('Based on your compacted memory, state the remembered color and marker; say unknown if unavailable.')
        assert pa.session_id('planner','qwen_transport_fixture') not in (None,sid)
        result['checks'].append('successor created and supplied compacted memory')
        result['end_ledger']=get(a.budget_url.rstrip('/')+'/health')['ledger']
        assert result['end_ledger']['backend_attempts']==5, 'unexpected extra generation or tool turn; inspect rather than retry'
        result['status']='passed'
    except Exception as exc:
        result.update(status='failed',error=repr(exc))
        result['end_ledger']=get(a.budget_url.rstrip('/')+'/health')['ledger']
    result['finished_unix']=time.time()
    result['remaining_allocation']='unused calls must be canceled by owning launcher; never automatically consumed'
    (r/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':sys.exit(main())
