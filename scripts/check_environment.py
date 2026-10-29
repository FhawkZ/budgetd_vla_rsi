"""CPU-only imports and exact version audit. No model calls or CUDA allocation."""
import argparse,importlib,importlib.metadata,json,os,platform,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--profile',choices=['qwen','agent','rpent','sim'],required=True);p.add_argument('--output',required=True);a=p.parse_args()
modules={'qwen':['torch','torchvision','transformers','accelerate','tokenizers'],'agent':['openai','litellm','pydantic','roborsi.cli.commands','roborsi.evaluation.atomic'],'rpent':['rpent','pydantic_ai','pydantic_ai_harness'],'sim':['sapien','mplib','cv2','numpy','h5py']}
r={'profile':a.profile,'python':platform.python_version(),'executable':sys.executable,'imports':{},'packages':dict(sorted((d.metadata['Name'].lower(),d.version) for d in importlib.metadata.distributions() if d.metadata['Name'])),'model_calls':0}
for m in modules[a.profile]:
 try:mod=importlib.import_module(m);r['imports'][m]={'ok':True,'path':getattr(mod,'__file__',None)}
 except Exception as e:r['imports'][m]={'ok':False,'error':repr(e)}
if a.profile=='qwen':
 import torch
 from transformers import Qwen3VLForConditionalGeneration,AutoProcessor
 r['torch_cuda_build']=torch.version.cuda;r['cuda_initialized']=torch.cuda.is_initialized()
r['passed']=all(v['ok'] for v in r['imports'].values())
Path(a.output).write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='packages'},indent=2));sys.exit(0 if r['passed'] else 1)
