"""CPU-only execution of pinned native methods with fake tasks, never SAPIEN.

This identifies seed-replacement semantics; it neither fixes the deployment nor
demonstrates that any scene is physically valid. Upstream files stay untouched.
"""
import argparse
import ast
import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

VECTOR_SHA = '4305a50bbd715ed4e61c9adf03b04cdb3deeb01d588abff5ac68bb64672a7dac'


def extract(path, cls, method, namespace):
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    fn = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == method)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[method]


class UnstableFixture(Exception):
    pass


def probe(vector, facade, output):
    assert hashlib.sha256(vector.read_bytes()).hexdigest() == VECTOR_SHA
    results = []
    for method, mode in [('setup_task','success'), ('setup_task','unstable'),
                         ('reset','success'), ('reset','unstable'), ('reset','generic_error')]:
        events, attempted = [], []
        err = UnstableFixture('synthetic instability') if mode == 'unstable' else ValueError('synthetic other failure')
        class Task:
            def setup_demo(self, **kw):
                attempted.append(kw['seed']); self.seed = kw['seed']
                events.append(['setup_demo',kw])
                if mode != 'success' and len(attempted) == 1:
                    raise err
            def get_info(self):
                return {'seed':self.seed}
            def close_env(self, **kw):
                events.append(['close_env',kw])
        ns = dict(class_decorator=lambda name: Task(), UnStableError=UnstableFixture,
                  logging=SimpleNamespace(warning=lambda msg:events.append(['warning',msg]),
                                          error=lambda msg:events.append(['error',msg])))
        fn = extract(vector,'SubEnv',method,ns)
        obj = SimpleNamespace(env_seed=100009, env_id=0, task_name='fixture', task=Task(),
                              args={'step_lim':1200}, global_lock=threading.Lock(), lock=threading.Lock(),
                              reset_count=0, clear_cache_freq=8, instruction=None)
        obj.close = lambda: obj.task.close_env()
        obj.create_instruction = lambda: 'native fixture language'
        caught = None
        try:
            fn(obj, env_seed=100009) if method=='reset' else fn(obj)
        except Exception as exc:
            caught = exc
        expected = [100009,100010] if mode=='unstable' else [100009]
        assert attempted == expected
        if mode=='generic_error':
            assert caught is err
        else:
            assert caught is None
        results.append(dict(method=method, mode=mode, attempted_seeds=attempted,
                            retained_requested_seed=obj.env_seed, exception_propagated=caught is err,
                            actual_initialized_seed=getattr(obj.task,'seed',None), events=events))
    # Execute the exact public facade guard: mismatch must not reach observation/language.
    calls = []
    def forbidden(*a, **kw):
        raise AssertionError('A failed exact-seed check reached language or observations')
    env = SimpleNamespace(reset=lambda **kw:(calls.append(kw) or ({},{'episode_status':{'actual_seed':100010}})))
    obj = SimpleNamespace(_metadata={'seed':100009}, _env=env, _strip_single_env_observation=forbidden)
    fn = extract(facade,'RoboTwinEnvFacade','reset',{'_evaluation_language':forbidden,'Any':object})
    try:
        fn(obj)
    except RuntimeError as exc:
        assert 'requested 100009, initialized 100010' in str(exc)
    else:
        raise AssertionError('Exact-seed guard did not reject replacement')
    assert len(calls)==1
    result = dict(status='passed', classification='exact_pinned_source_CPU_fake_task_semantics_only',
                  tests=6, model_calls=0, robot_resets=0, robot_actions=0,
                  source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (vector,facade)},
                  cases=results, facade_rejects_actual_seed_mismatch=True,
                  conclusions=['SubEnv.setup_task catches all exceptions and increments trial_seed until setup succeeds.',
                               'SubEnv.reset increments trial_seed on UnStableError; generic errors propagate.',
                               'One public reset RPC is not one physical scene-construction attempt.',
                               'Facade detects a replacement only after fallback initialization; guard worked in the validation.',
                               'Future single-attempt adaptation must cover BOTH setup_task and reset, with explicit receipts and qualification.'],
                  deployment_changed=False, physical_cause_or_scene_feasibility_proven=False)
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','source_hashes')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--vector',type=Path,required=True)
    p.add_argument('--facade',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();probe(a.vector,a.facade,a.output)
