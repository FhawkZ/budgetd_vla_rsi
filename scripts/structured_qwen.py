"""Schema-constrained sampling for Qwen Hermes calls, with no argument repair.
Shared deployment adapter only; not a learned harness or RSI contribution.
"""
import copy,hashlib,json,re,time
from importlib.metadata import version
import xgrammar as xgr
from xgrammar.contrib.hf import LogitsProcessor

class MeteredProcessor(LogitsProcessor):
 def __init__(self,compiled):
  super().__init__(compiled);self.prompt_length=None;self.output_ids=[]
 def __call__(self,input_ids,scores):
  if self.prompt_length is None:self.prompt_length=input_ids.shape[1]
  self.output_ids=input_ids[0,self.prompt_length:].detach().cpu().tolist()
  return super().__call__(input_ids,scores)

class ToolGrammar:
 def __init__(self,tokenizer,vocab_size):
  assert version('xgrammar')=='0.2.8'
  self.info=xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=vocab_size)
  self.compiler=xgr.GrammarCompiler(self.info,max_threads=4)
  self.cache={}
 def compile(self,tools):
  before=json.dumps(tools,sort_keys=True);key=hashlib.sha256(before.encode()).hexdigest()
  if key not in self.cache:
   local=copy.deepcopy(tools)
   for tool in local:
    assert tool['type']=='function' and isinstance(tool['function']['parameters'],dict)
    # Compiler-only strictness: original schema bytes and prompt remain unchanged.
    tool['function']['strict']=True
   tag=xgr.get_model_structural_tag('qwen_3',tools=local,tool_choice='auto',reasoning='disabled')
   self.cache[key]=self.compiler.compile_structural_tag(tag)
  assert json.dumps(tools,sort_keys=True)==before
  return self.cache[key],key
 def processor(self,tools):
  start=time.monotonic();compiled,key=self.compile(tools)
  return MeteredProcessor(compiled),{'schema_sha256':key,'compile_seconds':time.monotonic()-start,'adapter':'xgrammar-0.2.8-qwen3-auto-no-reasoning','tool_choice':'auto','arguments_rewritten':False,'property_order':'compiler declared order; original JSON schema unchanged'}

def validate_output(content,tools):
 from jsonschema import Draft202012Validator
 allowed={t['function']['name']:t['function']['parameters'] for t in tools}
 spans=re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>',content,re.S)
 if content.count('<tool_call>')!=len(spans) or content.count('</tool_call>')!=len(spans):raise ValueError('Incomplete tool envelope; no repair')
 for span in spans:
  value=json.loads(span);name=value.get('name')
  if name not in allowed:raise ValueError('Undeclared tool; no repair')
  if 'arguments' not in value:raise ValueError('Missing arguments; no repair')
  Draft202012Validator(allowed[name]).validate(value['arguments'])
 return len(spans)
