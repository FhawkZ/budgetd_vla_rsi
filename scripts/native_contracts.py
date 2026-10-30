"""Explicit deployment contracts; no learned policy, motor edits or scoring changes."""
import functools,hashlib,json,os,time
from pathlib import Path
DISABLED_GRASPGEN=frozenset({'grasp_object','grasp_diverse','grasp_top_down'})
def install_capabilities(audit):
 assert os.environ.get('ROBORSI_USE_GRASPGEN')=='0'
 from roborsi.embodied import skills
 original_ns=skills.discover_ns;original=skills.discover
 before={s.name for s in original_ns('robotwin')}
 def discover_ns(ns):
  found=original_ns(ns)
  return [s for s in found if s.name not in DISABLED_GRASPGEN] if ns=='robotwin' else found
 def discover():
  return [s for s in original() if not (s.name in DISABLED_GRASPGEN and 'robotwin' in s.path.parts)]
 skills.discover_ns=discover_ns;skills.discover=discover
 after={s.name for s in skills.discover_ns('robotwin')}
 assert before-after==before & DISABLED_GRASPGEN and not after & DISABLED_GRASPGEN
 assert {'grasp_obb','get_grasp_pose'}<=after
 Path(audit).write_text(json.dumps({'classification':'deployment capability availability filter, not RSI update','removed':sorted(before-after),'kept':sorted(after),'GraspGen_enabled':False,'native_files_changed':False},indent=2))
 return skills

def install_role_audit(instructions,audit,ledger):
 from roborsi.agents.roles.planner import Planner
 from roborsi.agents.roles.engineer import Engineer
 from roborsi.agents.roles.reviewer import Reviewer
 def wrap(cls,method,role):
  original=getattr(cls,method)
  @functools.wraps(original)
  def call(self,*args,**kwargs):
   task=kwargs.get('task') or kwargs['workspace'].task
   expected=instructions[task];value=kwargs.get('user_msg','') if role=='planner' else kwargs.get('task_instruction','')
   matched=(expected in value) if role=='planner' else value==expected
   entry={'role':role,'task':task,'instruction':expected,'instruction_sha256':hashlib.sha256(expected.encode()).hexdigest(),'matched':matched,'started_unix':time.time(),'ledger_before':ledger()}
   try:
    if not matched:raise ValueError(role+' did not receive the frozen public task instruction')
    return original(self,*args,**kwargs)
   finally:
    entry.update(finished_unix=time.time(),ledger_after=ledger())
    with Path(audit).open('a') as f:f.write(json.dumps(entry)+'\n')
  setattr(cls,method,call)
 for cls,method,role in [(Planner,'plan','planner'),(Engineer,'execute','engineer'),(Reviewer,'review','reviewer')]:wrap(cls,method,role)
