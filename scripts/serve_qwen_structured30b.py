"""Bounded localhost Transformers inference. OpenAI-shaped transport, Qwen backend only.
No shell/code execution, no network image URLs, no policy or evaluator write tools.
"""
import argparse,hashlib,json,os,re,time,traceback
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import torch
from transformers import AutoProcessor,Qwen3VLMoeForConditionalGeneration
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8018);p.add_argument('--model',required=True);p.add_argument('--output',required=True);p.add_argument('--max-calls',type=int,required=True);a=p.parse_args();assert a.max_calls>0
O=Path(a.output);O.mkdir(parents=True,exist_ok=True);torch.set_num_threads(4)
processor=AutoProcessor.from_pretrained(a.model,local_files_only=True)
model=Qwen3VLMoeForConditionalGeneration.from_pretrained(a.model,dtype=torch.bfloat16,device_map='cuda:0',attn_implementation='sdpa',local_files_only=True).eval()
assert model.config.model_type=='qwen3_vl_moe'
from structured_qwen import ToolGrammar,validate_output
grammar=ToolGrammar(processor.tokenizer,model.config.text_config.vocab_size)
model_name='qwen3-vl-30b-a3b-instruct'
identity={'model':model_name,'model_path':a.model,'backend':'transformers','torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'decoder':'xgrammar-0.2.8-native-schema-auto','max_input_tokens':32768,'max_output_tokens':1024,'max_calls':a.max_calls,'started_unix':time.time()}
identity.update(model_class=type(model).__name__,loaded_allocated_bytes=torch.cuda.memory_allocated(),loaded_reserved_bytes=torch.cuda.memory_reserved())
(O/'server-identity.json').write_text(json.dumps(identity,indent=2))
def generate(body, call_id):
 assert body.get('model')==model_name,'model identifier mismatch'
 messages=[];image_count=0
 for m in body['messages']:
  assert m['role'] in ['system','user','assistant','tool']
  content=m.get('content','');copy={k:v for k,v in m.items() if k in ['role','content','tool_calls','tool_call_id','name']}
  if isinstance(content,list):
   converted=[]
   for item in content:
    if item['type']=='image_url':
     url=item['image_url']['url'];assert url.startswith('data:image/'),'Only embedded images permitted';image_count+=1
     converted.append({'type':'image','url':url})
    else:assert item['type']=='text';converted.append(item)
   copy['content']=converted
  elif isinstance(content,str):
   copy["content"]=[{"type":"text","text":content}]
  elif content is None:
   copy["content"]=[]
  else:raise ValueError("unsupported message content")
  messages.append(copy)
 assert image_count<=3,'at most 3 images per request'
 kw={'add_generation_prompt':True,'tokenize':True,'return_dict':True,'return_tensors':'pt'}
 if body.get('tools'):kw['tools']=body['tools']
 inputs=processor.apply_chat_template(messages,**kw).to(model.device)
 n=inputs['input_ids'].shape[1];assert n<=32768,'input budget exceeded'
 max_new=min(int(body.get('max_tokens',512)),1024);assert max_new>0
 torch.cuda.reset_peak_memory_stats();torch.manual_seed(int(body.get('seed',42)));start=time.monotonic()
 constraint,decode_metadata=grammar.processor(body.get('tools',[]))
 (O/f'{call_id}-decoder.json').write_text(json.dumps(decode_metadata))
 try:
  with torch.inference_mode():out=model.generate(**inputs,max_new_tokens=max_new,do_sample=False,logits_processor=[constraint])
 except BaseException as exc:
  partial=constraint.output_ids
  usage={'prompt_tokens':int(n),'completion_tokens':len(partial),'total_tokens':int(n)+len(partial)}
  (O/f'{call_id}-generation.json').write_text(json.dumps({'usage':usage,'usage_is_lower_bound':True,'generation_incomplete':True,'error':repr(exc),'raw_output':processor.decode(partial,skip_special_tokens=True),'generation_seconds':time.monotonic()-start,'image_count':image_count,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()}))
  raise
 ids=out[0,n:];content=processor.decode(ids,skip_special_tokens=True)
 # Meter generated tokens before tool parsing, so invalid tool JSON cannot erase cost.
 usage={'prompt_tokens':int(n),'completion_tokens':len(ids),'total_tokens':int(n)+len(ids)}
 (O/f'{call_id}-generation.json').write_text(json.dumps({'usage':usage,'raw_output':content,'generation_seconds':time.monotonic()-start,'image_count':image_count,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()}))
 validate_output(content,body.get('tools',[]))
 msg={'role':'assistant','content':content};finish='length' if len(ids)>=max_new else 'stop'
 # Parse the model-emitted Hermes tool envelope. Never synthesize a missing tool call.
 envelopes=re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>',content,re.S)
 if envelopes and body.get('tools'):
  tools=[];allowed={t['function']['name'] for t in body['tools']}
  for i,e in enumerate(envelopes):
   t=json.loads(e)
   if t.get('name') not in allowed:raise ValueError('Model emitted undeclared tool: '+str(t.get('name')))
   tools.append({'id':f'call_{time.time_ns()}_{i}','type':'function','function':{'name':t['name'],'arguments':json.dumps(t.get('arguments',{}))}})
  msg['tool_calls']=tools;msg['content']=re.sub(r'<tool_call>.*?</tool_call>','',content,flags=re.S).strip() or None;finish='tool_calls'
 usage={'prompt_tokens':int(n),'completion_tokens':len(ids),'total_tokens':int(n)+len(ids)}
 with open(O/'requests.jsonl','a') as f:f.write(json.dumps({'time':time.time(),'seconds':time.monotonic()-start,'usage':usage,'image_count':image_count,'request_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()})+'\n')
 return {'id':f'local-{time.time_ns()}','object':'chat.completion','created':int(time.time()),'model':model_name,'choices':[{'index':0,'message':msg,'finish_reason':finish}],'usage':usage}
received_calls=0
class Handler(BaseHTTPRequestHandler):
 def send(self,status,data):
  b=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path=='/health':self.send(200,{'status':'ready','backend':'transformers','model':model_name})
  elif self.path=='/v1/models':self.send(200,{'object':'list','data':[{'id':model_name,'object':'model','owned_by':'local'}]})
  else:self.send(404,{'error':'not found'})
 def do_POST(self):
  if self.path!='/v1/chat/completions':return self.send(404,{'error':'not found'})
  global received_calls
  if received_calls>=a.max_calls:return self.send(429,{'error':'fixed server request budget exhausted'})
  received_calls+=1;call_id=f'{received_calls:04d}';start=time.time()
  record={'index':received_calls,'started_unix':start,'max_calls':a.max_calls,'generated_usage_known':False}
  (O/'request-budget.json').write_text(json.dumps({'received_calls':received_calls,'max_calls':a.max_calls}))
  try:
   n=int(self.headers.get('Content-Length',0));assert 0<n<12*1024*1024
   body=json.loads(self.rfile.read(n));(O/f'{call_id}-request.json').write_text(json.dumps(body))
   response=generate(body,call_id);record['http_status']=200;self.send(200,response)
  except Exception as e:
   record.update(http_status=400,error=type(e).__name__+': '+str(e));traceback.print_exc()
   failure={'error':record['error']}
   generated=O/f'{call_id}-generation.json'
   if generated.exists():failure['usage']=json.loads(generated.read_text())['usage']
   self.send(400,failure)
  finally:
   generated=O/f'{call_id}-generation.json'
   if generated.exists():record.update(generated_usage_known=True,usage=json.loads(generated.read_text())['usage'])
   record['elapsed_seconds']=time.time()-start
   (O/f'{call_id}-audit.json').write_text(json.dumps(record,indent=2))
print('READY',json.dumps(identity),flush=True)
HTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
