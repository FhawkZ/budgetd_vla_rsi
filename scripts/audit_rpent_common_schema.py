"""CPU-only audit: locate schema errors before transport parsing. No repair."""
import argparse,json,re,hashlib
from pathlib import Path
from jsonschema import Draft202012Validator

def main():
 p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args();root=Path(a.output);assert (root/'CLOSE.json').exists()
 errors=[];matches=[]
 for task in ('stack_blocks_two','handover_block'):
  for forwarded in sorted((root/task/'ledger').glob('*-forwarded.json')):
   raw=forwarded.read_bytes();sha=hashlib.sha256(raw).hexdigest();server=[p for p in (root/'server').glob('*-request.json') if hashlib.sha256(p.read_bytes()).hexdigest()==sha]
   assert len(server)==1,(forwarded,server)
   request=json.loads(raw);gen=json.loads(server[0].with_name(server[0].name.replace('-request','-generation')).read_text())
   response=json.loads(forwarded.with_name(forwarded.name.replace('-forwarded','-response')).read_text())
   original=[json.loads(x) for x in re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>',gen['raw_output'],re.S)]
   transported=response['choices'][0]['message'].get('tool_calls',[])
   assert len(original)==len(transported)
   for rawcall,call in zip(original,transported):
    name=call['function']['name'];args=json.loads(call['function']['arguments'])
    assert rawcall['name']==name and rawcall['arguments']==args,'transport changed original tool arguments'
    schema=next(t['function']['parameters'] for t in request['tools'] if t['function']['name']==name)
    issues=list(Draft202012Validator(schema).iter_errors(args))
    if issues:errors.append(dict(task=task,request=forwarded.name,tool=name,raw_arguments=args,errors=[e.message for e in issues],raw_matches_transport=True,raw_generation_sha256=hashlib.sha256(server[0].with_name(server[0].name.replace('-request','-generation')).read_bytes()).hexdigest()))
   matches.append(dict(task=task,request=forwarded.name,request_sha256=sha,server=server[0].name,raw_arguments_unchanged=True))
 result=dict(classification='offline exact original-generation versus transport audit',model_calls=0,simulator_episodes=0,request_pairs=len(matches),schema_violations=errors,all_raw_tool_arguments_preserved=True,request_matches=matches,conclusion='Invalid flat pixel arrays originate in generated output; no evidence of transport flattening. No repaired calls or additional execution.')
 (root/'schema-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='request_matches'},indent=2))
if __name__=='__main__':main()
