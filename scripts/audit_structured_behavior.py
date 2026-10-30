import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root');a=p.parse_args();root=Path(a.root)
assert (root/'CLOSE.json').exists()
audit=json.loads((root/'schema-audit.json').read_text());assert audit['schema_violations']==[] and audit['request_pairs']==64
rows=[]
for task in ['stack_blocks_two','handover_block']:
 d=root/task;logs=[json.loads(p.read_text()) for p in sorted((d/'ledger').glob('*-incoming.json'))];tool_feedback={}
 for req in logs:
  for m in req['messages']:
   if m['role']=='tool':tool_feedback[m.get('tool_call_id',str(len(tool_feedback)))]=m.get('content')
 error_strings=[x for x in tool_feedback.values() if isinstance(x,str) and ('"error"' in x or x.startswith('Invalid arguments'))]
 comp=[json.loads(s) for s in (d/'compaction.jsonl').read_text().splitlines()]
 rows.append(dict(task=task,distinct_tool_feedback=len(tool_feedback),error_feedback_count=len(error_strings),error_examples=error_strings[:6],compactions=sum(x['after_messages']<x['before_messages'] for x in comp),peak_estimate=max(x['estimate_before'] for x in comp)))
out=dict(status='closed',native_schema_violations=0,requests=64,rows=rows,model_calls=0,conclusion='Grammar removes schema errors but does not establish autonomous action under the frozen32-call protocol. Read-only loop persists; stop this configuration, do not raise budgets.')
(root/'behavior-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
