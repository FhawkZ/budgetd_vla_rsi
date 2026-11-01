"""Fail-closed distinction between native pre-policy instability and infrastructure error."""


def native_scene_invalid(episode, rows):
    if episode.get('vla_inferences',0)!=0 or episode.get('native_actions',0)!=0:
        return False
    if episode.get('native_eval_success') is not None:
        return False
    starts=[x for x in rows if x.get('event')=='setup_begin']
    errors=[x for x in rows if x.get('event')=='setup_error']
    if len(starts) not in (1,2) or len(errors)!=1:
        return False
    if [x.get('phase') for x in starts]!=['setup_task','reset'][:len(starts)]:
        return False
    if any(x.get('requested_seed')!=episode['seed'] or x.get('actual_argument_seed')!=episode['seed'] for x in starts):
        return False
    error=errors[0]
    if error.get('error_type')!='UnStableError' or error.get('attempt')!=len(starts):
        return False
    if not rows or rows[-1]!=error:
        return False
    daemons=episode.get('daemon_after_cleanup',[])
    if not daemons or any(x.get('returncode') not in ((0,1) if x.get('name')=='robotwin_env_server' else (0,)) for x in daemons):
        return False
    # Attempt receipts come from the fixed native server, before policy execution.
    return True
