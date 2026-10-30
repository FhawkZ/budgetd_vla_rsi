"""Explicit local Qwen token accounting for native RPent sliding-window trimming.
Images are counted only; message payloads and tool schemas are never rewritten.
"""
import hashlib,json,os,re,time
from io import BytesIO
from pathlib import Path
CONFIG=dict(max_messages=80,max_tokens=28672,keep_tokens=24000,preserve_first_user_message=True)
TOKENIZER_SHA='a5d85b6dcc535e6b93115a9ef287e6132fdbf30270da6218194ba742261173c7'

def install(tokenizer_path,log):
 from tokenizers import Tokenizer
 from PIL import Image
 from transformers.models.qwen2_vl.image_processing_qwen2_vl import smart_resize
 from pydantic_ai.messages import BinaryContent,ToolReturnPart
 from pydantic_ai_harness.compaction import _shared,SlidingWindowCompaction
 import rpent.planner.api_loop as api
 assert hashlib.sha256(Path(tokenizer_path).read_bytes()).hexdigest()==TOKENIZER_SHA
 tokenizer=Tokenizer.from_file(str(tokenizer_path));original=_shared._request_part_text
 def count(s):
  match=re.fullmatch(r'<rsi_image_token_count:(\d+)>',s)
  return int(match[1]) if match else len(tokenizer.encode(s,add_special_tokens=False).ids)
 def parts(part):
  if not (isinstance(part,ToolReturnPart) and isinstance(part.content,list) and any(isinstance(x,BinaryContent) for x in part.content)):return original(part)
  result=[]
  for item in part.content:
   if not isinstance(item,BinaryContent):result.append(str(item));continue
   with Image.open(BytesIO(item.data)) as image:w,h=image.size
   rh,rw=smart_resize(h,w,factor=32,min_pixels=65536,max_pixels=16777216)
   result.append(f'<rsi_image_token_count:{(rh//16)*(rw//16)//4+2}>')
  return result
 _shared._request_part_text=parts
 class Logged(SlidingWindowCompaction):
  async def before_model_request(self,ctx,request_context):
   before=len(request_context.messages)
   estimate=_shared.estimate_context_tokens(request_context.messages,self.tokenizer,model_request_parameters=request_context.model_request_parameters)
   result=await super().before_model_request(ctx,request_context)
   with Path(log).open('a') as stream:stream.write(json.dumps(dict(time=time.time(),before_messages=before,after_messages=len(result.messages),estimate_before=estimate,config=CONFIG,reserved_margin=4096))+'\n')
   return result
 api.SlidingWindowCompaction=lambda **kwargs:Logged(**CONFIG,tokenizer=count)
 return count,parts
