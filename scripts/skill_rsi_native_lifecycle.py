"""Trusted native API lifecycle with data-only isolated perception.

Not a runnable experiment. build_native requires a separately frozen operator
protocol. Candidate source never executes in this process. No evaluator method
is exported through the supervisor's public seven-method API.
"""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from skill_rsi_skill_ipc import FIELDS, plain
from skill_rsi_perception_ipc import run_perception


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, allow_nan=False, indent=2) + '\n')


class NativeInfrastructure(BaseException):
    pass


class NativeBudget(BaseException):
    pass


class NativeSafety(BaseException):
    pass


EXCEPTIONS = {'budget_exhausted': NativeBudget, 'safety_stop': NativeSafety,
              'infrastructure_error': NativeInfrastructure}


class IsolatedDetect:
    """Only source text, RGBD and calibration cross the perception boundary."""
    def __init__(self, source, upstream, output, invoke=run_perception):
        self.source, self.upstream, self.output = source, upstream, Path(output)
        self.invoke, self.n = invoke, 0

    def __call__(self, rgb, depth, calibration):
        out = self.output / ('perception-%03d' % self.n)
        self.n += 1
        report = self.invoke(self.source, rgb, depth, calibration,
                             self.upstream, out, timeout=15)
        if report.get('status') != 'result' or report.get('exit_code') != 0:
            # Upstream observe catches Exception as a detection failure. A missing
            # or unqualified subprocess result must instead stop the whole session.
            # worker_error provenance is not yet granular enough to blame a policy.
            raise NativeInfrastructure('isolated_perception_incomplete')
        value = report['response']['result']
        if not isinstance(value, list) or len(value) != 2:
            raise NativeInfrastructure('isolated_perception_result_contract')
        return value[0], value[1]


class NativeSession:
    """Same lifecycle used by native hooks and focused fake-backend tests."""
    def __init__(self, config, hooks, output, detect):
        self.config, self.hooks, self.output = config, hooks, Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.thread = threading.get_ident()
        self.task = self.api = self.monitor = None
        self.closed = self.poisoned = False
        self.events = []
        self.report = {'status': 'initializing', 'setup_attempts': 0,
                       'seed': config['seed'], 'accepted_update': False,
                       'robot_qualified': False, 'policy_requests': 0}
        try:
            hooks.prepare()
            self.report['setup_attempts'] = 1
            self.event('setup_enter', seed=config['seed'])
            self.task = hooks.setup(config['task'], config['seed'])
            self.event('setup_return', seed=config['seed'])
            spec = hooks.task_spec(self.task, config['task_card'])
            # Retain only the public projection, even inside the API object.
            spec = plain({k: spec[k] for k in ('instruction', 'roles')})
            self.monitor = hooks.attach_monitor(self.task)
            self.api = hooks.make_api(self.task, detect, spec)
            self.report['status'] = 'ready'
            self.event('ready', public_task_spec=spec)
        except BaseException as error:
            self.report.update(status='initialization_error', error_class=type(error).__name__)
            self.event('setup_or_construction_error', error_class=type(error).__name__)
            self.close()
            raise

    def event(self, name, **kwargs):
        row = dict(event=name, thread=threading.get_ident(), time=time.time(), **kwargs)
        self.events.append(row)
        with (self.output / 'lifecycle.jsonl').open('a') as f:
            f.write(json.dumps(row, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        save(self.output / 'lifecycle-report.json', self.report)

    def invoke(self, method, args):
        if self.closed or self.poisoned:
            raise NativeInfrastructure('session_closed_or_poisoned')
        if threading.get_ident() != self.thread:
            self.poisoned = True
            raise NativeInfrastructure('native_thread_identity_changed')
        if method not in FIELDS or set(args) != FIELDS[method]:
            self.poisoned = True
            raise NativeInfrastructure('public_api_contract')
        self.report['policy_requests'] += 1
        self.event('dispatch', method=method, args=plain(args))
        try:
            result = getattr(self.api, method)(**args)
            if method == 'task_spec':
                result = {k: result[k] for k in ('instruction', 'roles')}
            result = plain(result)
        except BaseException as error:
            self.poisoned = True
            self.report.update(status='native_exception', error_class=type(error).__name__)
            self.event('exception', method=method, error_class=type(error).__name__)
            for cls, mapped, label in self.hooks.exception_map:
                if isinstance(error, cls):
                    raise mapped(label) from None
            if isinstance(error, (NativeInfrastructure, NativeBudget, NativeSafety)):
                raise
            raise NativeInfrastructure('unmapped_native_exception') from None
        self.event('returned', method=method, value=result)
        return result  # False is preserved, never interpreted as task/contact success.

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.task is not None:
                self.hooks.close_task(self.task)
                self.event('task_closed')
        except BaseException as error:
            self.report.update(status='cleanup_error', cleanup_error=type(error).__name__)
            self.event('cleanup_error', error_class=type(error).__name__)
        finally:
            try:
                self.hooks.restore()
            finally:
                if self.report['status'] == 'ready':
                    self.report['status'] = 'closed_without_evaluation'
                self.event('closed')
        # No settle/render/scorer call here. EOF/timeout is not evaluation permission.

    def __getattr__(self, name):
        if name in FIELDS:
            return lambda **args: self.invoke(name, args)
        raise AttributeError(name)


class OfficialHooks:
    """Trusted deployment imports and unmodified Skill-RSI API/monitor factory."""
    def __init__(self, config, output):
        self.c, self.out = config, Path(output)
        self.original_capture = self.original_assign = None
        self.clip_calls = 0
        self.clip_seconds = 0.
        self.lease = None

    def prepare(self):
        import fcntl
        import sys
        from run_skill_rsi_native_v2 import pin_render, render_input_error
        from run_skill_rsi_native_v3 import gpu_read
        from gpu_idle_gate import wait_idle
        c = self.c
        self.lease = open(c['gpu_lock'], 'a')
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def record(row):
            with (self.out/'resource-checks.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
        gpu = wait_idle(lambda: gpu_read(c['gpu']), record, timeout=6)
        os.environ.update(CUDA_VISIBLE_DEVICES=str(c['gpu']), CUDA_DEVICE_ORDER='PCI_BUS_ID',
                          HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                          RSI_REMOTE_ROOT=str(self.out/'site'))
        sys.path.insert(0, c['upstream'])
        import common
        common.CLIP_PATH = c['clip_weight']
        import envadapter, observe, perception_frozen
        from api import API
        self.env, self.obs, self.pf, self.API, self.common = envadapter, observe, perception_frozen, API, common
        self.exception_map = [(envadapter.SafetyStop, NativeSafety, 'native_safety_stop'),
                              (envadapter.BudgetExhausted, NativeBudget, 'native_primitive_budget'),
                              (envadapter.SimTimeout, NativeBudget, 'native_sim_timeout'),
                              (common.InfraFailure, NativeInfrastructure, 'native_infrastructure')]
        pin_render(gpu['pci'], 'none')
        self.campaign = self.out/'campaign'
        self.campaign.mkdir()
        (self.campaign/'official').symlink_to(c['native'], target_is_directory=True)
        save(self.campaign/'campaign.json', {'campaign_id': c['run_id'], 'task': c['task'],
             'scene': {'name': 'clutter'}, 'limits': c['limits'], 'monitor': c['monitor']})
        self.original_capture = observe.capture
        def capture(task):
            rgb, depth, cal = self.original_capture(task)
            error = render_input_error(rgb, depth)
            if error:
                raise NativeInfrastructure(error)
            return rgb, depth, cal
        observe.capture = capture
        self.original_assign = perception_frozen.assign_roles
        def assign(crops, roles):
            start = time.monotonic()
            row = {'roles': roles, 'crop_sha256': [hashlib.sha256(x.tobytes()).hexdigest() for x in crops]}
            try:
                result = self.original_assign(crops, roles)
                row['result'] = result
                return result
            finally:
                self.clip_calls += 1
                row['seconds'] = time.monotonic()-start
                self.clip_seconds += row['seconds']
                with (self.out/'clip.jsonl').open('a') as f:
                    f.write(json.dumps(row)+'\n')
        perception_frozen.assign_roles = assign

    def setup(self, task, seed):
        return self.env.setup(self.campaign, task, seed)
    def task_spec(self, task, card):
        return self.env.task_spec(task, card)
    def attach_monitor(self, task):
        return self.env.attach_monitor(task, self.c['limits'], self.c['monitor'])
    def make_api(self, task, detect, spec):
        return self.API(task, self.out, self.c['limits'], detect, spec)
    def close_task(self, task):
        task.close_env()
    def restore(self):
        if self.original_capture is not None:
            self.obs.capture = self.original_capture
        if self.original_assign is not None:
            self.pf.assign_roles = self.original_assign
        if self.lease is not None:
            self.lease.close()
            self.lease = None


def build_native(protocol, expected_sha256):
    """Only an operator-pinned factory may call this; no ready online config exists."""
    path = Path(protocol)
    if path.is_symlink() or digest(path) != expected_sha256:
        raise ValueError('operator protocol pin')
    c = json.loads(path.read_text())
    if c.get('status') != 'FROZEN_NATIVE_ISOLATED' or c.get('source_class') != 'published':
        raise ValueError('no generated candidate execution authorization')
    if c['gpu'] not in (2, 3) or c['limits']['primitive_budget'] != 90 or c['limits']['sim_seconds'] != 90:
        raise ValueError('deployment and budget contract')
    if c['limits']['wall_seconds'] != 240 or c['limits']['settle_seconds'] != 2:
        raise ValueError('native budgets')
    required = [str(Path(c['upstream'])/name) for name in ['api.py','envadapter.py','observe.py','perception_frozen.py','validate.py','common.py']]
    published_root = Path(c['upstream']).resolve().parent/'frozen_skills'
    if Path(c['perception_file']).is_symlink() or not Path(c['perception_file']).resolve().is_relative_to(published_root):
        raise ValueError('only published perception source supported by this factory')
    required += [c['perception_file'], str(Path(__file__).resolve())]
    required += [str(Path(__file__).with_name(name)) for name in ['run_skill_rsi_native_v2.py','run_skill_rsi_native_v3.py','gpu_idle_gate.py','skill_rsi_perception_ipc.py','skill_rsi_perception_worker.py','skill_rsi_skill_ipc.py']]
    if any(p not in c['source_sha256'] for p in required):
        raise ValueError('missing source pin')
    for file, h in c['source_sha256'].items():
        if digest(file) != h:
            raise ValueError('frozen source changed')
    source = Path(c['perception_file']).read_text()
    out = Path(c['output'])
    detect = IsolatedDetect(source, c['upstream'], out)
    backend = NativeSession(c, OfficialHooks(c, out), out, detect)
    return backend, EXCEPTIONS
