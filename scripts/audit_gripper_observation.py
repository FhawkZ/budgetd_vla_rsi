"""CPU-only source/AST audit; no environment creation, model calls or physics."""
import argparse, ast, hashlib, json
from pathlib import Path
from types import SimpleNamespace

def audit(runtime,output):
    robot=runtime/'software/envs/robotwin/lib/python3.11/site-packages/robotwin/envs/robot/robot.py'
    base=runtime/'vendor/RPent-a744bd5f128ebef3cb8c6736cf7cd98adff681f1/robots/robotwin'
    paths=[robot,base/'rlinf_env.py',base/'primitives.py']
    wanted={'get_left_gripper_val','get_right_gripper_val','get_normal_real_gripper_val','set_gripper','_robot_state'}
    evidence=[]; methods={}
    for path in paths:
        text=path.read_text();nodes=[n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name in wanted]
        entries=[]
        for n in nodes:
            entries.append(dict(name=n.name,start_line=n.lineno,end_line=n.end_lineno,source=ast.get_source_segment(text,n)))
            if path==robot:methods[n.name]=n
        evidence.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),functions=entries))
    probes=[]
    for arm in ('left','right'):
        node=methods[f'get_{arm}_gripper_val'];scope={}
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) for n in ast.walk(node))
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(robot),'exec'),scope)
        fn=scope[node.name]
        for command in (0.,.3):
            for physical in (0.,1.):
                fake=SimpleNamespace(**{arm+'_gripper':[object()],arm+'_gripper_val':command,'synthetic_physical_aperture':physical})
                value=fn(fake);assert value==command
                probes.append(dict(arm=arm,cached_command=command,synthetic_physical_aperture=physical,reported=value))
    audit_file=runtime/'outputs/single-seed-closure-audit-20261102-0310/report.json'
    results=json.loads(audit_file.read_text());skills=results['skill_audit']
    out=dict(classification='CPU_source_contract_not_physical_grounding_validation',model_calls=0,gpu_used=False,sources=evidence,getter_probes=probes,probes_passed=len(probes),source_findings=['RPent left/right_gripper uses native getters returning cached requested gripper values.','Native setter writes cached gripper_val before drive-target interpolation; neither getter reads actual finger qpos, force or contact.','Function named get_normal_real_gripper_val reads drive targets, not measured aperture.','RPent arm_qpos_real12 excludes gripper entries; arm state is not a substitute finger measurement.','RPent set_gripper ToolResult success=True follows command execution, not grasp/contact verification.'],validated_candidate_triggers=len(skills),already_same_cached_command=sum(x['already_at_target'] for x in skills),skill_native_counts=sum(x['native_actions'] for x in skills),eef_translation_m=dict(min=min(x['eef_translation_m'] for x in skills),max=max(x['eef_translation_m'] for x in skills)),conclusion='Candidate conditions on cached command, not measured closure/contact. Descriptive motion during repeated target execution cannot establish settling as causal benefit.',limitations=['AST fake-object probes are not physics experiments.','Command state can still be a scheduling feature; this audit does not prove it is always useless.','No changes to upstream, observations, policy/scorer or the frozen candidate; no validation feedback sent to any model.'])
    output.mkdir(parents=True,exist_ok=False);(output/'report.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k not in ('sources','getter_probes')}))
if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.runtime,a.output)
