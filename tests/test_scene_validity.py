import copy
from scene_validity import native_scene_invalid


def test_only_native_prepolicy_instability_is_censored():
    ep=dict(seed=100011,vla_inferences=0,native_actions=0,native_eval_success=None,
            daemon_after_cleanup=[dict(name='robotwin_env_server',returncode=1)])
    begin=dict(event='setup_begin',phase='setup_task',attempt=1,requested_seed=100011,actual_argument_seed=100011)
    error=dict(begin,event='setup_error',error_type='UnStableError')
    assert native_scene_invalid(ep,[begin,error])
    for key,value in [('vla_inferences',1),('native_actions',1),('native_eval_success',False),('seed',100012)]:
        bad=dict(ep,**{key:value});assert not native_scene_invalid(bad,[begin,error])
    assert not native_scene_invalid(ep,[begin,dict(error,error_type='TimeoutError')])
    assert not native_scene_invalid(ep,[begin,error,dict(event='setup_return')])
    assert not native_scene_invalid(ep,[])
    bad=copy.deepcopy(ep);bad['daemon_after_cleanup'][0]['returncode']=-11
    assert not native_scene_invalid(bad,[begin,error])
