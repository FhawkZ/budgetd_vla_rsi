"""Common reduced controller transport; no fallback actions or argument repairs."""
import base64,copy,hashlib,io,json,urllib.request
from pathlib import Path
import jsonschema
from PIL import Image
MODEL='qwen3-vl-30b-a3b-instruct'
SYSTEM='''You control a frozen vision-language-action robot policy through three tools. Complete the native task using the available observations. execute_vla_chunk runs the frozen policy from fresh camera/state input; you choose 25 or 50 unchanged predicted waypoints. observe obtains camera/state without motion. stop ends the attempt. Choose exactly one declared tool each turn. You may stop when unable to proceed. Do not claim unobserved success. No other tools or files are available. All calls and failed attempts consume budget. At zero remaining execution allowance, stop.''' 

def image_parts(observation):
    parts=[{'type':'text','text':json.dumps({'task_language':observation['task_language'],'robot_state':observation['robot_state']},default=lambda x:x.tolist())}]
    for name in ('head','left_wrist','right_wrist'):
        rgb=observation['views'][name]['rgb'];buf=io.BytesIO();Image.fromarray(rgb).save(buf,format='PNG');raw=buf.getvalue()
        parts.extend([{'type':'text','text':name+' PNG SHA256 '+hashlib.sha256(raw).hexdigest()},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(raw).decode()}}])
    return parts

def parse_response(response,tools):
    choice=response['choices'][0]
    if choice.get('finish_reason')=='length':raise ValueError('truncated decision')
    msg=choice['message'];calls=msg.get('tool_calls',[])
    if len(calls)!=1:raise ValueError('exactly one tool decision required; no synthesized action')
    call=calls[0];fun=call['function'];table={x['function']['name']:x['function'] for x in tools}
    if fun['name'] not in table:raise ValueError('undeclared tool')
    args=json.loads(fun['arguments']);jsonschema.Draft202012Validator(table[fun['name']]['parameters']).validate(args)
    return {'action':fun['name'],**args},copy.deepcopy(msg),call['id']

class Controller:
    def __init__(self,tools,observation,endpoint,output,max_calls):
        self.tools=copy.deepcopy(tools);self.endpoint=endpoint;self.output=Path(output);self.output.mkdir(exist_ok=False)
        self.max_calls=max_calls;self.calls=0;self.history=[{'role':'system','content':SYSTEM},{'role':'user','content':image_parts(observation)}]
    def decide(self,counters):
        if self.calls>=self.max_calls:raise RuntimeError('controller budget exhausted')
        self.calls+=1
        messages=self.history+[{'role':'user','content':json.dumps({'budget':counters,'controller_calls_remaining_including_current':self.max_calls-self.calls+1})}]
        body={'model':MODEL,'messages':messages,'tools':self.tools,'tool_choice':'auto','max_tokens':1024,'seed':42,'stream':False}
        (self.output/f'{self.calls:03d}-request.json').write_text(json.dumps(body))
        req=urllib.request.Request(self.endpoint,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=180) as f:response=json.load(f)
        (self.output/f'{self.calls:03d}-response.json').write_text(json.dumps(response))
        decision,msg,call_id=parse_response(response,self.tools)
        self.history=messages+[msg];self.pending=call_id
        return decision
    def feedback(self,text,observation=None):
        self.history.append({'role':'tool','tool_call_id':self.pending,'content':json.dumps(text)})
        if observation is not None:self.history.append({'role':'user','content':image_parts(observation)})
