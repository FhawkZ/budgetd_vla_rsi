"""Audit exact repeated arguments in closed development runs; never execute tools."""
import argparse,collections,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args();r=Path(a.output);assert (r/'CLOSE.json').exists();rows=[]
for task in ('stack_blocks_two','handover_block'):
 d=r/task;counts=collections.Counter((x['tool'],json.dumps(json.loads(x['arguments']),sort_keys=True)) for x in json.loads((d/'tool-requests.json').read_text()))
 repeated=[dict(tool=k[0],arguments=json.loads(k[1]),count=v) for k,v in counts.items() if v>1]
 rows.append(dict(task=task,repeated_identical_arguments=repeated))
report=dict(classification='posthoc exact argument audit, no model or simulator calls',rows=rows)
(r/'repeated-reads.json').write_text(json.dumps(report,indent=2)+'\n')
