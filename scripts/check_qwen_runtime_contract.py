"""CPU-only actual validator preflight; no model loading or generation."""
import argparse,hashlib,json
from pathlib import Path
from importlib.metadata import version
from structured_qwen import validate_output
from jsonschema.exceptions import ValidationError

def check():
 expected={'xgrammar':'0.2.8','jsonschema':'4.26.0','jsonschema-specifications':'2025.9.1','referencing':'0.37.0','rpds-py':'2026.9.1','attrs':'26.1.0'}
 for name,wanted in expected.items():assert version(name)==wanted,(name,version(name))
 tools=[{'type':'function','function':{'name':'example','parameters':{'type':'object','properties':{'value':{'type':'integer'}},'required':['value'],'additionalProperties':False}}}]
 assert validate_output('{"plain_text_fixture":true}',[])==0
 assert validate_output('<tool_call>{"name":"example","arguments":{"value":1}}</tool_call>',tools)==1
 try:validate_output('<tool_call>{"name":"example","arguments":{"value":"bad"}}</tool_call>',tools)
 except ValidationError:pass
 else:raise AssertionError('invalid schema accepted')
 return {'status':'passed','checks':['dependency_versions','plain_text','valid_tool','invalid_schema_rejected'],'versions':expected,'model_calls':0,'robot_episodes':0}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--saved-generation',type=Path);p.add_argument('--saved-request',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=check()
 if a.saved_generation:
  g=json.loads(a.saved_generation.read_text());b=json.loads(a.saved_request.read_text());r['saved_output_tool_envelopes']=validate_output(g['raw_output'],b.get('tools',[]));r['saved_generation_sha256']=hashlib.sha256(a.saved_generation.read_bytes()).hexdigest();r['saved_request_sha256']=hashlib.sha256(a.saved_request.read_bytes()).hexdigest();r['saved_output_replayed_into_robot']=False
 a.output.write_text(json.dumps(r,indent=2));print(json.dumps(r))
