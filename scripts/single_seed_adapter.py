"""Explicit single-seed deployment adaptation; no change to native stability checks.

The successful setup/reset path follows pinned robotwin SubEnv. Failure closes
the partial task and propagates the original exception without choosing a seed.
This module has no side effects until install() is explicitly called.
"""
import hashlib
import inspect
import time
from pathlib import Path

VECTOR_SHA = '4305a50bbd715ed4e61c9adf03b04cdb3deeb01d588abff5ac68bb64672a7dac'


def make_methods(native, record, *, max_attempts):
    if max_attempts != 2:
        raise ValueError('One preflight setup plus one reset only')
    attempts = 0

    def cleanup(task, *, clear_cache=None):
        if task is None:
            return
        try:
            if clear_cache is None:
                task.close_env()
            else:
                task.close_env(clear_cache=clear_cache)
        except Exception as error:
            record(dict(event='failure_cleanup_error', error=repr(error)))

    def setup(task, phase, requested_seed, **kwargs):
        nonlocal attempts
        if kwargs['seed'] != requested_seed or kwargs['now_ep_num'] != requested_seed:
            raise ValueError('Requested seed changed')
        if attempts >= max_attempts:
            raise RuntimeError('Native setup budget exhausted; no retry')
        attempts += 1
        entry = dict(phase=phase, attempt=attempts, requested_seed=int(requested_seed),
                     actual_argument_seed=int(kwargs['seed']))
        record(dict(entry, event='setup_begin', at_unix=time.time()))
        try:
            task.setup_demo(**kwargs)
        except BaseException as error:
            record(dict(entry, event='setup_error', error_type=type(error).__name__,
                        error=str(error), at_unix=time.time()))
            raise
        record(dict(entry, event='setup_return', at_unix=time.time()))

    def setup_task(self):
        self.close()
        self.task = native.class_decorator(self.task_name)
        with self.global_lock:
            with self.lock:
                trial_seed = self.env_seed
                task = None
                try:
                    task = native.class_decorator(self.task_name)
                    setup(task, 'setup_task', trial_seed, now_ep_num=trial_seed,
                          seed=trial_seed, is_test=True, **self.args)
                    episode_info = task.get_info()
                except Exception:
                    cleanup(task)
                    raise
                task.close_env()
                self.episode_info_list = [episode_info]

    def reset(self, env_seed=None):
        with self.global_lock:
            with self.lock:
                if self.task is not None:
                    self.reset_count += 1
                    should_clear_cache = self.reset_count % self.clear_cache_freq == 0
                    self.task.close_env(clear_cache=should_clear_cache)
                if env_seed is not None:
                    self.env_seed = env_seed
                self.instruction = self.create_instruction()
                self.args['instruction'] = self.instruction
                trial_seed = self.env_seed
                try:
                    setup(self.task, 'reset', trial_seed, now_ep_num=trial_seed,
                          seed=trial_seed, **self.args)
                    self.task.step_lim = self.args['step_lim']
                    self.task.run_steps = 0
                    self.task.reward_step = 0
                except Exception:
                    cleanup(self.task, clear_cache=True)
                    raise

    return {'setup_task': setup_task, 'reset': reset}


def install(vector_module, record, *, max_attempts=2):
    path = Path(vector_module.__file__).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != VECTOR_SHA:
        raise ValueError('Unqualified native vector_env source')
    for name in ('setup_task', 'reset'):
        fn = getattr(vector_module.SubEnv, name)
        if Path(inspect.getsourcefile(fn)).resolve() != path:
            raise ValueError('Native method already replaced: '+name)
    methods = make_methods(vector_module, record, max_attempts=max_attempts)
    for name, fn in methods.items():
        setattr(vector_module.SubEnv, name, fn)
    record(dict(event='adapter_installed', source_sha256=VECTOR_SHA,
                max_native_setup_attempts=max_attempts, auto_resample=False))
