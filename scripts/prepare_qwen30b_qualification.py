"""CPU asset verification, transport audit and independent finite protocol freeze."""
import copy,hashlib,json,os,socket,time
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']=''
import torch
from transformers import AutoProcessor
from budget_proxy import adapt
ROOT=Path(__file__).resolve().parents[1];R=Path(os.environ['RSI_RUNTIME_ROOT']);O=R/'outputs/qwen30b-qualification-prepare-20261031-0630';O.mkdir(exist_ok=False)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
manifest=ROOT/'configs/qwen30b-candidate-model-files.json';rows=[];start=time.time()
for f in json.loads(manifest.read_text())['files']:
 p=R/'models/Qwen3-VL-30B-A3B-Instruct'/f['path'];actual=sha(p)
 assert actual==f['sha256'] and p.stat().st_size==f['bytes'],f['path']
 rows.append({**f,'mtime_ns':p.stat().st_mtime_ns})
receipt=O/'assets.json';save(receipt,dict(status='passed',manifest_sha256=sha(manifest),files=rows,total_bytes=sum(x['bytes'] for x in rows),seconds=time.time()-start,model_generations=0))
torch.set_num_threads(4);processor=AutoProcessor.from_pretrained(R/'models/Qwen3-VL-30B-A3B-Instruct',local_files_only=True)
def count(body):
 messages=[]
 for m in body['messages']:
  c={k:v for k,v in m.items() if k in ['role','content','tool_calls','tool_call_id','name']};value=c.get('content')
  if isinstance(value,list):c['content']=[{'type':'image','url':v['image_url']['url']} if v['type']=='image_url' else v for v in value]
  elif isinstance(value,str):c['content']=[{'type':'text','text':value}]
  elif value is None:c['content']=[]
  messages.append(c)
 kw=dict(add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt')
 if body.get('tools'):kw['tools']=body['tools']
 return int(processor.apply_chat_template(messages,**kw)['input_ids'].shape[1])
# These are recorded POST-compaction inputs. They cannot reconstruct already lost text.
audit=[];prior=R/'outputs/rpent-structured-native-dev64-20261031-0140'
for task in ['stack_blocks_two','handover_block']:
 files=list((prior/task/'ledger').glob('*-incoming.json'))
 def images(p):
  b=json.loads(p.read_text());return sum(v.get('type')=='image_url' for m in b['messages'] if isinstance(m.get('content'),list) for v in m['content'])
 chosen=max(files,key=images);body=json.loads(chosen.read_text());forwarded,meta=adapt(body)
 before=count(body);after=count(forwarded)
 audit.append(dict(task=task,source=str(chosen.relative_to(R)),source_sha256=sha(chosen),images_before=meta['images_before'],images_after=meta['images_after'],exact_unclipped_tokens=before,exact_transport_tokens=after,excess_if_all_images_retained=before-after))
save(O/'compactor-audit.json',dict(status='completed_cpu_only',rows=audit,model_calls=0,findings=['Compactor counts every historical BinaryContent image; proxy retains latest3 and replaces older images with text markers.','Exact counts above are on saved post-compaction requests, not the missing pre-compaction context.','No inference that omitted context caused failure; large text/tool responses remain additional contributors.','No native compactor changes activated; future correction needs message-subsequence-aware accounting and paired CPU tests.']))
old=json.loads((ROOT/'configs/structured-qual3-20261031-0130.json').read_text());cfg=copy.deepcopy(old)
cfg.update(run_id='qwen30b-qual3-20261031-0640',classification='new_30B_backend_qualification_not_task_score',model_id='qwen3-vl-30b-a3b-instruct',model_weights='Qwen3-VL-30B-A3B-Instruct immutable candidate manifest; separate from8B',model_class='Qwen3VLMoeForConditionalGeneration',asset_receipt=str(receipt.relative_to(R)),asset_receipt_sha256=sha(receipt),protocol_scope='Two historical image/tool boundary requests with only model-id changed, plus exact31744-input-token text canary under1024output cap. No robot tools. Fourth proxy request must be refused. No retry after any failed case.')
fixtures=[]
for i,f in enumerate(old['inputs'][:2]):
 src=R/f['path'];assert sha(src)==f['sha256'];b=json.loads(src.read_text());b['model']=cfg['model_id'];dest=O/f'boundary-{i+1}.json';save(dest,b)
 fixtures.append(dict(kind=f['kind'],path=str(dest.relative_to(R)),sha256=sha(dest),source_sha256=f['sha256'],change='model identifier only',exact_input_tokens=count(b)))
b=json.loads((R/old['inputs'][2]['path']).read_text());b['model']=cfg['model_id'];b['max_tokens']=1024
base='This is a transport and context-capacity canary. Ignore the padding; reply with exactly qualification-ok. Padding:'
n=31000
for _ in range(6):
 b['messages']=[{'role':'user','content':base+' x'*n+'\nReply with exactly qualification-ok.'}];actual=count(b)
 if actual==31744:break
 n+=31744-actual
assert actual==31744
canary=O/'context-canary.json';save(canary,b);fixtures.append(dict(kind='context_capacity_plain_text',path=str(canary.relative_to(R)),sha256=sha(canary),exact_input_tokens=actual,output_cap=1024,combined_reserved_tokens=32768))
cfg['inputs']=fixtures
cfg['code_sha256']={f:sha(ROOT/f) for f in ['scripts/structured_qwen.py','scripts/serve_qwen_structured30b.py','scripts/qualify_qwen30b.py','scripts/budget_proxy30b.py','scripts/run_vla_only_pilot.py']}
protocol=ROOT/'configs/qwen30b-qual3-20261031-0640.json';assert not protocol.exists();save(protocol,cfg)
save(O/'prepare-report.json',dict(status='passed',assets_sha256=sha(receipt),protocol_sha256=sha(protocol),model_calls=0,gpu_jobs=0,compactor_audit=audit,fixtures=fixtures))
print(json.dumps(dict(status='passed',protocol=str(protocol),sha256=sha(protocol),audit=audit),indent=2))
