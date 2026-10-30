"""CPU-only native-schema acceptance/rejection qualification; no rollout."""
import argparse,copy,hashlib,json,os,time
from pathlib import Path
from transformers import AutoTokenizer,AutoConfig
import xgrammar as xgr
from structured_qwen import ToolGrammar,validate_output

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.mkdir(exist_ok=True,parents=True)
 root=Path(os.environ['RSI_RUNTIME_ROOT']);model=root/'models/Qwen3-VL-8B-Instruct'
 tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True);config=AutoConfig.from_pretrained(model,local_files_only=True)
 grammar=ToolGrammar(tokenizer,config.text_config.vocab_size)
 request=root/'outputs/rpent-common-native-dev64-20261030-2040/stack_blocks_two/ledger/020-forwarded.json'
 tools=json.loads(request.read_text())['tools'];original=copy.deepcopy(tools);start=time.time();compiled,key=grammar.compile(tools);assert tools==original
 def wrap(name,args):return '<tool_call>\n'+json.dumps({'name':name,'arguments':args})+'\n</tool_call>'
 cases=[('valid_nested',wrap('sample_world_xyz',{'view':'head','pixels':[[120,160]],'step':0}),True),('invalid_flat',wrap('sample_world_xyz',{'view':'head','pixels':[120,160],'step':0}),False),('invalid_3coords',wrap('sample_world_xyz',{'view':'head','pixels':[[120,160,0]]}),False),('invalid_float',wrap('sample_world_xyz',{'view':'head','pixels':[[1.5,2]]}),False),('invalid_empty',wrap('sample_world_xyz',{'view':'head','pixels':[]}),False),('unknown_tool',wrap('grasp_object',{}),False),('valid_vla',wrap('lingbot_act',{'chunks':1,'use_length':50}),True),('wrong_chunk_length',wrap('lingbot_act',{'chunks':1,'use_length':49}),False),('plain_answer','qualification-ok',True),('two_calls',wrap('lingbot_act',{})+'\n'+wrap('finish',{'status':'failed','summary':'bounded'}),True)]
 rows=[]
 for name,text,expected in cases:
  matcher=xgr.GrammarMatcher(compiled);accepted=matcher.accept_string(text);actual=accepted and matcher.is_completed()
  try:validate_output(text,tools);validated=True
  except Exception:validated=False
  rows.append({'name':name,'grammar_accepts_complete':actual,'original_schema_valid':validated,'expected':expected});assert actual==expected and validated==expected,rows[-1]
 # Token-level rejection at exact historical schema violation, not just byte parsing.
 invalid=cases[1][1];matcher=xgr.GrammarMatcher(compiled);ids=tokenizer.encode(invalid,add_special_tokens=False);rejected=[]
 for i,token in enumerate(ids):
  if not matcher.accept_token(token):rejected.append({'index':i,'token':token});break
 assert rejected
 import torch
 assert not torch.cuda.is_initialized(),'CPU audit must not allocate GPU'
 report={'status':'passed','classification':'CPU_structured_decoder_contract','xgrammar':'0.2.8','schema_sha256':key,'tool_count':len(tools),'tests':rows,'invalid_token_rejected':rejected,'tools_unchanged':tools==original,'model_calls':0,'episodes':0,'wall_seconds':time.time()-start,'adapter_sha256':hashlib.sha256((Path(__file__).parent/'structured_qwen.py').read_bytes()).hexdigest(),'sources':['https://xgrammar.mlc.ai/docs/latest/start/quick_start.html','https://xgrammar.mlc.ai/docs/latest/structural_tag/tool_calling_and_reasoning.html']}
 (out/'cpu-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
