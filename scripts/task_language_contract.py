"""Public, hash-pinned task-language binding. CPU qualified; online pending.
Never reads scoring state, coordinates, trajectories or final-test feedback.
"""
import hashlib,json
from pathlib import Path

def load(manifest,backend_root):
 data=json.loads(Path(manifest).read_text());root=Path(backend_root).resolve(strict=True)
 assert data['status']=='PUBLIC_LANGUAGE_BINDING_V1'
 rows={}
 for row in data['tasks']:
  task=row['task'];assert task not in rows and '/' not in task
  path=(root/'description/task_instruction'/f'{task}.json').resolve(strict=True)
  assert path.is_relative_to(root)
  assert hashlib.sha256(path.read_bytes()).hexdigest()==row['source_sha256'],'task language source changed'
  text=json.loads(path.read_text())[row['field']]
  assert isinstance(text,str) and text.strip() and text==row['instruction'],'task language mismatch'
  rows[task]=text
 return rows

def install(env_class,instructions):
 """Bind before the core reads active_env.instruction, preserving reset output."""
 original=env_class.reset
 def reset(env,seed):
  if env.task not in instructions:raise ValueError('task has no frozen public instruction')
  text=instructions[env.task]
  if not isinstance(text,str) or not text.strip():raise ValueError('empty frozen instruction')
  obs=original(env,seed)
  env.instruction=text
  # Native core prioritizes this public field. Do not alter observations or score.
  return obs
 env_class.reset=reset
 return original
