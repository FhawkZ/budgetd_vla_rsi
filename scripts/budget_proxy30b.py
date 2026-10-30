"""Explicit latest-three-image transport for fixed local Qwen, with a hard call ledger.
An adapted model transport, not an RSI improvement or faithful original backbone.
"""
import argparse,copy,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer

def adapt(body):
 out=copy.deepcopy(body)
 assert out.get('model')=='qwen3-vl-30b-a3b-instruct','wrong model'
 positions=[]
 for m in out['messages']:
  if isinstance(m.get('content'),list):
   for i,part in enumerate(m['content']):
    if part.get('type')=='image_url':
     assert part['image_url']['url'].startswith('data:image/'),'embedded images required'
     positions.append((m['content'],i))
 removed=[]
 for parts,i in positions[:-3]:
  h=hashlib.sha256(parts[i]['image_url']['url'].encode()).hexdigest();removed.append(h)
  parts[i]={'type':'text','text':f'[Earlier image omitted by fixed latest-three-image transport; SHA256 {h}. Original textual observation retained.]'}
 requested=out.get('max_tokens',out.get('max_completion_tokens',512))
 assert isinstance(requested,int) and 0<requested<=1024,'explicit output cap must be <=1024'
 out.pop('max_completion_tokens',None);out['max_tokens']=requested;out['seed']=42
 return out,{'images_before':len(positions),'images_after':min(3,len(positions)),'omitted_image_sha256':removed,'requested_output_cap':requested,'rule':'retain latest3images across full request; retain all text/tools; no text truncation'}

def account_usage(state,usage):
 if not isinstance(usage,dict) or any(type(usage.get(k)) is not int or usage[k]<0 for k in ('prompt_tokens','completion_tokens')):
  raise ValueError('missing or invalid token accounting')
 state['prompt_tokens']+=usage['prompt_tokens'];state['completion_tokens']+=usage['completion_tokens']

def main():
 p=argparse.ArgumentParser();p.add_argument('--upstream',required=True);p.add_argument('--port',type=int,default=18019);p.add_argument('--output',required=True);p.add_argument('--max-calls',type=int,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
 R=Path(a.output);R.mkdir(exist_ok=a.resume,parents=True)
 state={'backend_attempts':0,'received_requests':0,'prompt_tokens':0,'completion_tokens':0,'max_backend_calls':a.max_calls,'started_unix':time.time(),'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 if a.resume:
  old=json.loads((R/'ledger.json').read_text());assert old['max_backend_calls']==a.max_calls
  old.setdefault('adapter_versions',[]).append(old['adapter_sha256']);old['adapter_sha256']=state['adapter_sha256'];state=old
 def save(): (R/'ledger.json').write_text(json.dumps(state,indent=2))
 save()
 class H(BaseHTTPRequestHandler):
  def send(self,status,obj):
   b=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
  def send_completion(self,response,stream):
   if not stream:return self.send(200,response)
   choice=response['choices'][0];message=copy.deepcopy(choice['message'])
   for i,t in enumerate(message.get('tool_calls',[])):t['index']=i
   base={k:response[k] for k in ['id','created','model']};base['object']='chat.completion.chunk'
   chunks=[{**base,'choices':[{'index':0,'delta':message,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':choice['finish_reason']}]},{**base,'choices':[],'usage':response.get('usage',{})}]
   self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
   for chunk in chunks:self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
   self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
  def do_GET(self):
   self.send(200,{'status':'ready','model':'qwen3-vl-30b-a3b-instruct','transport':'latest3images-v1','ledger':state})
  def do_POST(self):
   if self.path!='/v1/chat/completions':return self.send(404,{'error':'unsupported endpoint'})
   state['received_requests']+=1;idx=state['received_requests'];record={'index':idx,'started_unix':time.time()};save()
   try:
    n=int(self.headers.get('Content-Length',0));assert 0<n<12*1024*1024
    body=json.loads(self.rfile.read(n));(R/f'{idx:03d}-incoming.json').write_text(json.dumps(body))
    out,audit=adapt(body);record['adaptation']=audit;out['stream']=False
    if state['backend_attempts']>=a.max_calls:
     record['error']='fixed backend call budget exhausted';record['http_status']=400;return self.send(400,{'error':record['error']})
    state['backend_attempts']+=1;save();(R/f'{idx:03d}-forwarded.json').write_text(json.dumps(out))
    req=urllib.request.Request(a.upstream+'/v1/chat/completions',data=json.dumps(out).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as f:response=json.load(f)
    (R/f'{idx:03d}-response.json').write_text(json.dumps(response));usage=response.get('usage',{})
    account_usage(state,usage);record.update(http_status=200,usage=usage);self.send_completion(response,stream=bool(body.get('stream')))
   except urllib.error.HTTPError as e:
    raw=e.read().decode();record.update(http_status=e.code,error=raw)
    try:payload=json.loads(raw)
    except ValueError:payload={}
    usage=payload.get('usage') if isinstance(payload,dict) else None
    if usage is not None:
     try:account_usage(state,usage);record.update(usage=usage,failed_generation_usage_accounted=True)
     except ValueError as invalid:record['usage_accounting_error']=str(invalid)
    else:record['usage_status']='unknown or no generation; consult server audit, never assume zero'
    self.send(400,{'error':raw,**({'usage':usage} if usage is not None else {})})
   except Exception as e:
    record.update(http_status=400,error=repr(e));self.send(400,{'error':repr(e)})
   finally:
    record['elapsed_seconds']=time.time()-record['started_unix'];(R/f'{idx:03d}-audit.json').write_text(json.dumps(record,indent=2));save()
 HTTPServer(('127.0.0.1',a.port),H).serve_forever()
if __name__=='__main__':main()
