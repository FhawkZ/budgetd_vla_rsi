"""Receipt adapter for pinned HCL gate/screening; not a full HCL reproduction.
No model calls or robot actions. Unknown/censored outcomes fail closed.
"""
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

COMMIT = 'a6e5a01536ac8d42ca28f0a82efa223869c8c48d'
PROFILE = 'deepseek_flash_reasoning_hcl_stability_250_50_500.json'

def load_official(runtime):
    runtime = Path(runtime)
    vendor = runtime / 'vendor' / ('Harness-Continual-Learning-' + COMMIT)
    receipt = json.loads((runtime/'outputs/hcl-source-qualification-20261101/source-manifest.json').read_text())
    assert receipt['commit'] == COMMIT
    files = {x['path']: x for x in receipt['files']}
    for relative in ('hcl/optimizer.py', 'hcl/pipeline.py', 'configs/'+PROFILE):
        assert hashlib.sha256((vendor/relative).read_bytes()).hexdigest() == files[relative]['sha256']
    sys.path.insert(0, str(vendor))
    from hcl.optimizer import Optimizer
    from hcl.pipeline import HCLPipeline
    assert Path(sys.modules['hcl.optimizer'].__file__).resolve() == vendor/'hcl/optimizer.py'
    config = json.loads((vendor/'configs'/PROFILE).read_text())['optimizer']
    return Optimizer, HCLPipeline, config

def pair_metrics(baseline, candidate, current_task, old_tasks, expected_keys, *, behavior_changed):
    """Full-panel comparison; callers cannot promote a partially screened panel."""
    def index(rows):
        result = {}
        for row in rows:
            key = (row['task'], row['seed'])
            if key in result: raise ValueError('duplicate case')
            if row['status'] != 'completed' or type(row['native_eval_success']) is not bool:
                raise ValueError('unknown or infrastructure-censored outcome')
            result[key] = row
        if set(result) != set(expected_keys): raise ValueError('incomplete or foreign panel')
        return result
    before, after = index(baseline), index(candidate)
    current, old = [], []
    if set(old_tasks) & {current_task}: raise ValueError('overlapping task roles')
    for key in sorted(before):
        a, b = before[key], after[key]
        for field in ('initial_robot_state', 'initial_image_sha256', 'native_task_language'):
            if a[field] != b[field]: raise ValueError('paired input mismatch: '+field)
        pair = (a['native_eval_success'], b['native_eval_success'])
        if key[0] == current_task: current.append(pair)
        elif key[0] in old_tasks: old.append(pair)
        else: raise ValueError('undeclared task')
    if not current or not old or set(old_tasks)-{k[0] for k in before}: raise ValueError('missing task role')
    current_metrics = lambda i: {'primary_score':sum(x[i] for x in current)/len(current), 'correct':sum(x[i] for x in current), 'total':len(current), 'format_compliance_rate':1.0}
    lost = sum(a and not b for a,b in old); recovered = sum(not a and b for a,b in old)
    reference = {'metrics':{}, 'current_task_metrics':current_metrics(0)}
    result = {'metrics':{'behavior_comparable_count':len(before), 'behavior_change_count':int(behavior_changed), 'forget_count':sum(a and not b for a,b in current)},
              'current_task_metrics':current_metrics(1), 'historical_anchor_metrics':{'forget_count':lost,'recovered_count':recovered,'total':len(old),'forget_rate':lost/len(old)}}
    return reference, result

def screening_contract(runtime, optimizer, current, old):
    """Calls the exact upstream sampling method without constructing execution services."""
    _, Pipeline, _ = load_official(runtime)
    holder = SimpleNamespace(optimizer=optimizer, harness_version=0)
    c, a, union = Pipeline._candidate_screening_examples(holder,current,old,component='shared_typed_skill',batch_index=0)
    # Exact activation condition from upstream HCLPipeline.run; caller must also have >1 candidates.
    active_for_multiple_candidates = optimizer.selection_objective == 'balanced' and len(union)<len(current)+len(old)
    return {'current_selected':len(c),'old_selected':len(a),'total_selected':len(union),'active_for_multiple_candidates':active_for_multiple_candidates}
