"""CPU AST audit: identify actual observation inputs and action-effect call paths."""
import ast,hashlib,json,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
s=a.source.read_text();tree=ast.parse(s);names=['_build_lingbot_observation','lingbot_act','move_to','rotate_wrist','set_gripper','release','apply_qpos_updates','execute_action'];rows={}
for n in ast.walk(tree):
 if isinstance(n,ast.FunctionDef) and n.name in names:
  text=ast.get_source_segment(s,n);calls=sorted({ast.unparse(c.func) for c in ast.walk(n) if isinstance(c,ast.Call)})
  rows[n.name]={'line':n.lineno,'sha256':hashlib.sha256(text.encode()).hexdigest(),'calls':calls}
assert len(rows)==len(names)
assert 'self.env.get_task_language' in rows['_build_lingbot_observation']['calls']
assert 'self.model.infer' in rows['lingbot_act']['calls'] and 'self.env.chunk_step' in rows['lingbot_act']['calls']
assert 'self.env.plan_arm_path' in rows['move_to']['calls'] and 'self.apply_qpos_updates' in rows['move_to']['calls']
assert 'self.apply_qpos_updates' in rows['set_gripper']['calls']
result={'classification':'static_source_effect_audit_not_policy_performance','source':str(a.source),'source_sha256':hashlib.sha256(s.encode()).hexdigest(),'methods':rows,'findings':['LingBot observations are RGB views, robot state and native environment task language. An unconsumed memory entry or lingbot_act(prompt=...) cannot by itself alter policy input.','Current reduced interface only changes execute prefix/observe/stop. With same50 prefix and no motion between observations, retrieval text alone does not implement a new skill. Do not count newly saved text as learned competence.','Upstream move_to uses plan_arm_path then apply_qpos_updates; set_gripper also uses apply_qpos_updates. These are real execution paths and potential common typed skill extensions, not qualified or beneficial candidates.','Native skill extension must charge planning failures and executed native waypoints and may invalidate any pure-VLA-method interpretation. Compare VLA plus identical skill backend for every adapted method, with frozen VLA-only reference separate.'],'new_models':0,'new_simulations':0,'accepted_updates':0}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'methods':len(rows),'status':'passed','model_calls':0,'simulations':0}))
