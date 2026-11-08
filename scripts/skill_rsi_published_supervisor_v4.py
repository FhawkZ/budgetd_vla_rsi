"""Published-owner completion supervisor v3; not enabled in frozen robot runners.

One fresh process constructs and calls one backend on its main thread. Only JSON
crosses the API boundary. Factories are operator-pinned trusted code, never an
agent-selected path. Timeout poisons the session; no retries or terminal render.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from skill_rsi_skill_ipc import FIELDS, plain
from skill_rsi_owner_process_v4 import OwnedSession, RenderWatch

def trusted_backend_environment(parent):
    # Trusted simulator backend only. Policy/perception children keep their own isolation.
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
    for key in ('LD_LIBRARY_PATH','VK_ICD_FILENAMES','VK_LAYER_PATH','CUDA_VISIBLE_DEVICES',
                'CUDA_DEVICE_ORDER','RSI_EXPECTED_GPU_PCI','PYTORCH_KERNEL_CACHE_PATH'):
        if key in parent:
            value=parent[key]
            if not isinstance(value,str) or '\x00' in value:raise ValueError('invalid backend environment')
            env[key]=value
    return env

CAP = 65536
STATUSES = {'budget_exhausted', 'safety_stop', 'infrastructure_error'}


class APIFailure(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


def encode(row):
    data = json.dumps(row, allow_nan=False, separators=(',', ':')).encode() + b'\n'
    if len(data) > CAP:
        raise ValueError('API frame cap')
    return data


def receive(sock, deadline):
    # No bytes are read past a newline: exactly one outstanding request exists.
    data = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('API deadline')
        sock.settimeout(remaining)
        chunk = sock.recv(1)
        if not chunk:
            raise EOFError('API child disconnected')
        data.extend(chunk)
        if len(data) > CAP:
            raise ValueError('API frame cap')
        if chunk == b'\n':
            return json.loads(data)


def send(sock, row, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('API deadline')
    sock.settimeout(remaining)
    sock.sendall(encode(row))


class PublishedSupervisor:
    def __init__(self, factory, factory_sha256, output, *, startup_seconds=5,
                 call_seconds=5, total_seconds=20, max_requests=120):
        for value in (startup_seconds, call_seconds, total_seconds):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 300:
                raise ValueError('finite supervisor deadline required')
        if not 1 <= max_requests <= 120:
            raise ValueError('request limit')
        factory = Path(factory)
        if factory.is_symlink() or not factory.is_file():
            raise ValueError('trusted factory must be a regular file')
        if hashlib.sha256(factory.read_bytes()).hexdigest() != factory_sha256:
            raise ValueError('factory hash mismatch')
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.deadline = self.started + total_seconds
        self.call_seconds, self.limit, self.n = call_seconds, max_requests, 0
        self.closed = False
        self.events = []
        self.process = None
        self.sock = None
        self.control = None
        self.completion_attempted = False
        self.log = None
        self.owned = None
        self.watch = None
        self.report = {'status': 'starting', 'factory_sha256': factory_sha256,
                       'robot_qualified': False, 'accepted_update': False,
                       'dispatches': 0, 'pending_outcome': None}
        try:
            self.sock, child = socket.socketpair()
            self.control, control_child = socket.socketpair()
            self.log = (self.output / 'backend.log').open('wb')
            try:
                self.process = subprocess.Popen(
                    [sys.executable, '-I', '-B', str(Path(__file__).with_name('skill_rsi_completion_worker.py')),
                     str(child.fileno()), str(factory.resolve()), factory_sha256, str(control_child.fileno())],
                    pass_fds=(child.fileno(),control_child.fileno()), stdin=subprocess.DEVNULL,
                    stdout=self.log, stderr=self.log, close_fds=True, start_new_session=True,
                    env=trusted_backend_environment(os.environ), cwd='/')
            finally:
                child.close()
                control_child.close()
            self.owned = OwnedSession(self.process)
            self.watch = RenderWatch(self.output / 'backend.log', self.owned)
            self.report['pid'] = self.process.pid
            row = receive(self.sock, min(self.deadline, self.started + startup_seconds))
            if row != {'type': 'ready', 'factory_sha256': factory_sha256}:
                raise APIFailure('initialization_error')
            if self.watch.check():
                raise APIFailure('render_error')
            self.report['status'] = 'ready'
        except BaseException as error:
            self._fail('initialization_timeout' if isinstance(error, TimeoutError) else 'initialization_error')
            raise APIFailure(self.report['status']) from None

    def _save(self):
        raw = ''.join(json.dumps(e, allow_nan=False) + '\n' for e in self.events).encode()
        (self.output / 'events.jsonl').write_bytes(raw)
        self.report['events_sha256'] = hashlib.sha256(raw).hexdigest()
        self.report['seconds'] = time.monotonic() - self.started
        (self.output / 'report.json').write_text(json.dumps(self.report, indent=2) + '\n')

    def _fail(self, status):
        self.report['status'] = status
        self.close()

    def dispatch(self, method, args):
        if self.closed:
            raise APIFailure('session_closed')
        if self.watch.check():
            self._fail('render_error')
            raise APIFailure('render_error')
        # Preflight refuses invalid request without touching the backend.
        if method not in FIELDS or not isinstance(args, dict) or set(args) != FIELDS[method]:
            self._fail('request_rejected')
            raise APIFailure('request_rejected')
        try:
            args = plain(args)
            request = {'id': self.n + 1, 'method': method, 'args': args}
            encode(request)
        except (ValueError, TypeError, OverflowError):
            self._fail('request_rejected')
            raise APIFailure('request_rejected') from None
        if self.n >= self.limit:
            self._fail('request_budget_exhausted')
            raise APIFailure('request_budget_exhausted')
        deadline = min(self.deadline, time.monotonic() + self.call_seconds)
        if deadline <= time.monotonic():
            self._fail('session_deadline')
            raise APIFailure('session_deadline')
        self.n += 1
        self.report['dispatches'] = self.n
        self.report['pending_outcome'] = 'unknown'
        self.events.append({'request': request, 'sha256': hashlib.sha256(encode(request)).hexdigest()})
        self._save()  # durable intent before the possibly side-effecting operation
        try:
            send(self.sock, request, deadline)
            answer = receive(self.sock, deadline)
            if not isinstance(answer, dict) or answer.get('id') != self.n:
                raise ValueError('API response identity')
            if answer.get('status') == 'ok' and set(answer) == {'id', 'status', 'value'}:
                if self.watch.check():
                    raise APIFailure('render_error')
                value = plain(answer['value'])
                self.report['pending_outcome'] = 'returned'
                self.events.append({'response': answer})
                self._save()
                return value  # False remains False; transport success is not grasp/task success.
            if set(answer) == {'id', 'status', 'error_class'} and answer['status'] in STATUSES | {'native_error', 'response_rejected'}:
                self.report['pending_outcome'] = 'exception_returned'
                self.events.append({'response': answer})
                raise APIFailure(answer['status'])
            raise ValueError('API response schema')
        except BaseException as error:
            status = (error.status if isinstance(error, APIFailure) else
                      'api_timeout' if isinstance(error, TimeoutError) else 'transport_error')
            self._fail(status)
            raise APIFailure(status) from None

    def complete_from_owner(self, skill_process, *, outcome, render_error=False):
        """Only the trusted owner can call this; never exposed by PublicAPI.
        outcome is from the owner-parsed skill worker report, not a model assertion.
        """
        if self.closed or self.completion_attempted:
            raise APIFailure('completion_unavailable')
        self.completion_attempted = True
        render_error = render_error or bool(self.watch.check())
        try:
            if not isinstance(skill_process, subprocess.Popen):
                raise ValueError('actual owned Popen required')
            exit_code = skill_process.poll()
            receipt = dict(child_exit_code=exit_code,child_alive=exit_code is None,
                pending_api=self.report['pending_outcome']=='unknown',
                transport_failed=self.report['status']!='ready',
                deadline_exceeded=time.monotonic()>=self.deadline,
                render_error=render_error,outcome=outcome)
            if exit_code != 0 or receipt['pending_api'] or receipt['transport_failed'] or receipt['deadline_exceeded'] or render_error or outcome!='returned':
                raise ValueError('owner observed incomplete execution')
            deadline=min(self.deadline,time.monotonic()+self.call_seconds)
            send(self.control,{'control':'complete','receipt':receipt,'deadline':deadline},deadline)
            answer=receive(self.control,deadline)
            if answer!={'status':'completion_recorded'}:
                raise ValueError('invalid private acknowledgement')
            self.report['completion']='recorded_private'
            return answer
        except BaseException as e:
            self.report['completion']='unknown_or_refused'
            raise APIFailure('completion_timeout' if isinstance(e,TimeoutError) else 'completion_refused') from None
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.sock is not None:
            self.sock.close()
        if self.control is not None:
            self.control.close()
        if self.process is not None:
            self.report['exit_before_cleanup'] = self.process.poll()
            try:
                self.process.wait(timeout=.25)
            except subprocess.TimeoutExpired:
                pass
            if self.owned is not None:
                self.report['cleanup'] = self.owned.cleanup()
            else:
                self.process.kill()
                self.process.wait(timeout=2)
            self.report['exit_code'] = self.process.returncode
        if self.watch is not None:
            self.watch.close()
            self.report['render_error'] = self.watch.error
        if self.log is not None:
            self.log.close()
        if self.report['status'] == 'ready':
            self.report['status'] = 'closed'
        self._save()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __getattr__(self, name):
        if name in FIELDS:
            def invoke(*args, **kwargs):
                # Intended for PublicAPI.dispatch which calls keyword arguments only.
                if args:
                    raise TypeError('supervisor API requires keyword arguments')
                return self.dispatch(name, kwargs)
            return invoke
        raise AttributeError(name)
