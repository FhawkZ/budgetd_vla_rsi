"""Zero-generation CPU token count, matching serve_qwen preprocessing exactly."""
import argparse,hashlib,json,os
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']=''
import torch
from transformers import AutoProcessor
p=argparse.ArgumentParser();p.add_argument('--requests',required=True);p.add_argument('--model',required=True);p.add_argument('--output',required=True);a=p.parse_args();torch.set_num_threads(4)
processor=AutoProcessor.from_pretrained(a.model,local_files_only=True)
source=Path(a.requests);bodies=json.loads(source.read_text());bodies=bodies if isinstance(bodies,list) else [bodies]
records=[]
for index,body in enumerate(bodies,1):
 messages=[];images=0
 for m in body['messages']:
  content=m.get('content','');copy={k:v for k,v in m.items() if k in ['role','content','tool_calls','tool_call_id','name']}
  if isinstance(content,list):
   converted=[]
   for item in content:
    if item['type']=='image_url':
     url=item['image_url']['url'];assert url.startswith('data:image/');images+=1;converted.append({'type':'image','url':url})
    else:assert item['type']=='text';converted.append(item)
   copy['content']=converted
  elif isinstance(content,str):copy['content']=[{'type':'text','text':content}]
  elif content is None:copy['content']=[]
  else:raise ValueError('unsupported content')
  messages.append(copy)
 kw={'add_generation_prompt':True,'tokenize':True,'return_dict':True,'return_tensors':'pt'}
 if body.get('tools'):kw['tools']=body['tools']
 inputs=processor.apply_chat_template(messages,**kw);n=int(inputs['input_ids'].shape[1]);cap=min(int(body.get('max_tokens',512)),1024)
 records.append({'index':index,'request_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),'input_tokens':n,'output_cap':cap,'image_count':images,'tool_count':len(body.get('tools') or []),'input_headroom':32768-n,'input_plus_cap':n+cap,'fits_fixed_input_limit':n<=32768,'fits_input_plus_output_32k':n+cap<=32768})
report={'classification':'CPU exact processor token count; no weights loaded and zero generation','model_path':a.model,'requests_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'model_calls':0,'gpu_jobs':0,'records':records}
Path(a.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
