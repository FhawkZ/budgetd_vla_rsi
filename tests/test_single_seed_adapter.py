"""Exact native CPU success-path comparison and injected failure tests."""
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from single_seed_adapter import make_methods, install, VECTOR_SHA
from probe_native_seed_contract import extract


class UnstableFixture(Exception):
    pass


def fixture(failure=None):
    events, receipts, calls = [], [], []
    class Task:
        def setup_demo(self, **kw):
            events.append(('setup_demo', dict(kw))); calls.append(kw['seed'])
            self.seed = kw['seed']
            if failure is not None:
                raise failure
        def get_info(self): return {'seed':self.seed}
        def close_env(self, **kw): events.append(('close_env',kw))
    native=SimpleNamespace(class_decorator=lambda name:Task())
    obj=SimpleNamespace(env_seed=100006,env_id=0,task_name='fixture',task=Task(),
                        args={'step_lim':1200},global_lock=threading.Lock(),lock=threading.Lock(),
                        reset_count=0,clear_cache_freq=8,instruction=None)
    obj.close=lambda:obj.task.close_env()
    obj.create_instruction=lambda:'native fixture language'
    return native,obj,events,receipts,calls


def source():
    p=Path(os.environ['RSI_RUNTIME_ROOT'])/'software/envs/robotwin/lib/python3.11/site-packages/robotwin/envs/vector_env.py'
    import hashlib
    assert hashlib.sha256(p.read_bytes()).hexdigest()==VECTOR_SHA
    return p


@pytest.mark.parametrize('method',['setup_task','reset'])
def test_success_matches_exact_native_methods(method):
    n,a,ea,ra,ca=fixture();m,b,eb,rb,cb=fixture()
    native=extract(source(),'SubEnv',method,dict(class_decorator=n.class_decorator,
                     UnStableError=UnstableFixture,logging=SimpleNamespace()))
    adapted=make_methods(m,rb.append,max_attempts=2)[method]
    assert native(a)==adapted(b)
    assert ea==eb and ca==cb==[100006]
    assert a.args==b.args and a.instruction==b.instruction and a.reset_count==b.reset_count
    assert getattr(a,'episode_info_list',None)==getattr(b,'episode_info_list',None)
    assert [x['event'] for x in rb]==['setup_begin','setup_return']


@pytest.mark.parametrize('method',['setup_task','reset'])
@pytest.mark.parametrize('failure',[UnstableFixture('unstable'),ValueError('generic')])
def test_failure_propagates_same_exception_once(method,failure):
    n,obj,events,receipts,calls=fixture(failure)
    with pytest.raises(type(failure)) as caught:
        make_methods(n,receipts.append,max_attempts=2)[method](obj)
    assert caught.value is failure and calls==[100006] and obj.env_seed==100006
    assert receipts[-1]['event']=='setup_error'
    assert events[-1][0]=='close_env'


def test_two_setup_cap_and_no_implicit_install():
    n,obj,events,receipts,calls=fixture()
    methods=make_methods(n,receipts.append,max_attempts=2)
    methods['setup_task'](obj);methods['reset'](obj)
    with pytest.raises(RuntimeError,match='budget exhausted'):methods['reset'](obj)
    assert calls==[100006,100006]
    assert [x['phase'] for x in receipts if x['event']=='setup_begin']==['setup_task','reset']
    with pytest.raises(ValueError):make_methods(n,receipts.append,max_attempts=3)


def test_source_mismatch_rejected_before_mutation(tmp_path):
    p=tmp_path/'vector.py';p.write_text('unqualified')
    module=SimpleNamespace(__file__=str(p))
    with pytest.raises(ValueError,match='Unqualified'):install(module,lambda x:None)
