"""Posthoc source and recorded-request audit; no generations or hidden-data access."""
import hashlib,inspect,json,os
from pathlib import Path
from tokenizers import Tokenizer
from pydantic_ai_harness.compaction import _shared
R=Path(os.environ['RSI_RUNTIME_ROOT']);root=R/'outputs/rpent-structured-native-dev64-20261031-0140';out=R/'outputs/qwen30b-qualification-prepare-20261031-0630'
tok=Tokenizer.from_file(str(R/'models/Qwen3-VL-30B-A3B-Instruct/tokenizer.json'));rows=[]
for task in ['stack_blocks_two','handover_block']:
 d=root/task;calls={}
 for p in sorted((d/'ledger').glob('*-response.json')):
  b=json.loads(p.read_text())
  for t in b.get('choices',[{}])[0].get('message',{}).get('tool_calls',[]):calls[t['id']]=t['function']['name']
 comp=[json.loads(s) for s in (d/'compaction.jsonl').read_text().splitlines()];events=[]
 for idx,c in enumerate(comp,1):
  if c['after_messages']>=c['before_messages']:continue
  p=d/'ledger'/f'{idx:03d}-incoming.json';b=json.loads(p.read_text());texts=[]
  for m in b['messages']:
   if m['role']=='tool' and isinstance(m.get('content'),str):
    text=m['content'];texts.append(dict(tool=calls.get(m.get('tool_call_id')),tokens=len(tok.encode(text,add_special_tokens=False).ids),bytes=len(text.encode()),text_sha256=hashlib.sha256(text.encode()).hexdigest()))
  response=d/'ledger'/f'{idx:03d}-response.json';usage=json.loads(response.read_text()).get('usage',{}) if response.exists() else None
  events.append(dict(request=idx,compaction=c,post_compaction_tool_texts=texts,actual_post_compaction_usage=usage))
 rows.append(dict(task=task,events=events))
report=dict(status='completed_cpu_source_and_record_audit',rows=rows,model_calls=0,source_sha256={name:hashlib.sha256(inspect.getsource(getattr(_shared,name)).encode()).hexdigest() for name in ['estimate_context_tokens','find_token_cutoff']},findings=['Trigger uses latest provider input/output usage anchor plus new suffix when an anchor exists: it does NOT recount every historical image at every trigger.','Cutoff search uses unanchored estimate_token_count on candidate suffix and counts all BinaryContent images; this remains a potential mismatch.','Trigger can overestimate when newly returned images replace old images already counted in provider anchor.','Exact recorded six-image vs latest-three requests differ by only8/15tokens for the selected max-image cases; insufficient evidence that image transport explains47K/50Kestimates.','Original pre-trim Pydantic histories are not stored. Audit identifies retained large tool responses, cannot measure all lost history or prove counterfactual task outcomes.'],code_modified=False)
(out/'compaction-cause-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
