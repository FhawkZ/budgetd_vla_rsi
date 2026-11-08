"""Pinned deployment comparison adapter; published source never edited."""
import argparse
import json
import os
from pathlib import Path
import sys
from run_skill_rsi_published_owner_v4 import validate_native_config, native_factory_text, run_owner, sha

class DirectProjectedAPI:
    def __init__(self, api):
        from skill_rsi_skill_ipc import PublicAPI
        self._public = PublicAPI(api, max_requests=120)
    def task_spec(self): return self._public.dispatch('task_spec', {})
    def observe(self): return self._public.dispatch('observe', {})
    def ee_pose(self, arm): return self._public.dispatch('ee_pose', {'arm':arm})
    def gripper_state(self, arm): return self._public.dispatch('gripper_state', {'arm':arm})
    def move_pose(self, arm, pose): return self._public.dispatch('move_pose', {'arm':arm,'pose':pose})
    def gripper(self, arm, value): return self._public.dispatch('gripper', {'arm':arm,'value':value})
    def wait(self, seconds): return self._public.dispatch('wait', {'seconds':seconds})


def baseline(config, output):
    from run_skill_rsi_native_v2 import worker
    vendor=Path(os.environ['RSI_RUNTIME_ROOT'])/config['vendor']
    sys.path.insert(0,str(vendor/'runtime'))
    import validate
    original=validate.load_skills
    def load(source):
        ns,atoms=original(source)
        fallback=ns['fallback']
        ns['fallback']=lambda api: fallback(DirectProjectedAPI(api))
        return ns,atoms
    validate.load_skills=load
    try:return worker(config,0,Path(output))
    finally:validate.load_skills=original


def isolated(path, expected):
    c=validate_native_config(path,expected)
    out=Path(c['owner_output'])
    if out.exists() or Path(c['output']).exists():raise FileExistsError('already run')
    factory=out.with_name(out.name+'.factory.py')
    if factory.exists():raise FileExistsError('existing factory')
    text=native_factory_text(path,expected,out/'private-evaluation.json',out/'backend/backend.log')
    text=text.replace('    return build_native(', '    b, exceptions = build_native(',1)
    text=text.replace('\ndef completion_gate(b):', '''    b.hooks.common.dump(b.output/'initial-proprioception.json', b.api._state())
    b.hooks.common.dump(b.output/'public-task-spec.json', b.api.task_spec())
    return b, exceptions

def completion_gate(b):''')
    text=text.replace('        return value', '''        b.hooks.common.dump(b.output/'native-cost.json', {
            'monitor_steps_including_settle': b.monitor.steps, 'dt': b.monitor.dt,
            'primitive_calls': b.api._calls_used(), 'CLIP_calls': b.hooks.clip_calls,
            'CLIP_seconds_including_loading': b.hooks.clip_seconds})
        return value''')
    factory.parent.mkdir(parents=True,exist_ok=True)
    factory.write_text(text)
    return run_owner(source=Path(c['skills_file']).read_text(),upstream=c['upstream'],
            factory=factory,factory_sha=sha(factory),output=out,run_id=c['run_id'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['baseline','isolated'],required=True)
    p.add_argument('--protocol',required=True);p.add_argument('--sha256',required=True);p.add_argument('--output')
    a=p.parse_args()
    if sha(a.protocol)!=a.sha256:raise ValueError('case protocol hash')
    cfg=json.loads(Path(a.protocol).read_text())
    result=baseline(cfg,a.output) if a.mode=='baseline' else isolated(Path(a.protocol).resolve(),a.sha256)
    print(json.dumps({'status':result['status']}))
    raise SystemExit(0 if result['status'] in ['completed','completed_private'] else 1)
