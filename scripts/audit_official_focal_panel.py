"""CPU audit of pinned upstream evaluation seeds; no screening or score selection."""
from pathlib import Path
import json,hashlib,os
r=Path(os.environ['RSI_RUNTIME_ROOT']);root=Path(__file__).resolve().parents[1]
s=r/'vendor/RPent-a744bd5f128ebef3cb8c6736cf7cd98adff681f1'
f=s/'robots/robotwin/eval/demo_randomized.json';suite=json.loads(f.read_text());spec=s/'robots/robotwin/robot_spec.py'
assert suite['num_tasks']==len(suite['tasks'])==50
assert suite['num_episodes']==sum(len(v) for v in suite['tasks'].values())==250
out=r/'outputs/reduced-controller-20261031-1630';out.mkdir(exist_ok=True)
selected={k:suite['tasks'][k] for k in ['stack_blocks_two','handover_block']}
record=dict(classification='CPU source audit only; no runtime eligibility or task scores',suite_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),source_commit='a744bd5f128ebef3cb8c6736cf7cd98adff681f1',suite_tasks=50,suite_episodes=250,source_cli_recommends_official_task_seeds='use a per-task seed from' in spec.read_text(),source_cli_default_action_budget=10000,our_development_horizon=1200,historical_development_seeds={'stack_blocks_two':2026103011,'handover_block':2026103012},historical_seeds_in_official_panel={k:any(x['seed']==v for x in suite['tasks'][k]) for k,v in [('stack_blocks_two',2026103011),('handover_block',2026103012)]},selected_official_focal_panel=selected,selection_rule='All five published cases for each already fixed focal task, in published order; no success/outcome screening, backfill or resampling',status='draft_not_launched',remaining_contracts=['Check runtime native language equals published text before accepting a common benchmark label; if mismatch stop and diagnose without silently replacing task language','Check local embodiment/asset/runtime compatibility against pinned source; cannot infer from matching task names','Freeze separate fixed50 panel protocol and total budgets;1200 differs from native RPent10000 default and must be labeled budget-limited adaptation','All ten cases are development only, some official seeds occurred in historical zero-action pilots; exclude from independent final test','Preserve every failed result; if fixed50 has no handover competence across this panel, stop prefix/prompt tuning and reassess executor/checkpoint compatibility'],gpu_calls=0,model_calls=0)
(out/'official-panel-source-audit.json').write_text(json.dumps(record,indent=2)+'\n')
(root/'configs/official-focal-panel-draft.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
