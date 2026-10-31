"""Opt-in deployment candidate, not a proven stall fix or research method.

Reuse pinned RPent's main-thread transport and replace only its single-env
VectorEnv reset executor with synchronous Futures. No scorer/action changes.
"""
from concurrent.futures import Future
import threading


class OwnerInlineExecutor:
    def __init__(self, max_workers, **kwargs):
        if max_workers != 1 or kwargs:
            raise ValueError('Owner adapter supports exactly one environment')
        self.owner = threading.get_ident()
        self.closed = False

    def submit(self, fn, /, *args, **kwargs):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Native executor accessed outside its owner thread')
        if self.closed:
            raise RuntimeError('Executor already closed')
        result = Future()
        try:
            result.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            result.set_exception(exc)
        return result

    def shutdown(self, wait=True, *, cancel_futures=False):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Executor shutdown outside owner thread')
        self.closed = True


def construct_on_owner(factory, vector_module, *args, **kwargs):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Native construction requires process main thread')
    prior = vector_module.ThreadPoolExecutor
    vector_module.ThreadPoolExecutor = OwnerInlineExecutor
    try:
        return factory(*args, **kwargs)
    finally:
        vector_module.ThreadPoolExecutor = prior


def adapt_facade(base, mixin):
    class OwnerFacade(mixin, base):
        def __init__(self, *args, **kwargs):
            self._rsi_owner = threading.get_ident()
            super().__init__(*args, **kwargs)

        def _dispatch(self, method, args, kwargs, *, session_id=None):
            if session_id is not None:
                raise ValueError('This single-env facade does not support sessions')
            if threading.get_ident() != self._rsi_owner:
                raise RuntimeError('Business dispatch outside native owner thread')
            # Upstream RoboTwin override omits session_id; bridge explicitly.
            return base._dispatch(self, method, args, kwargs)

        def close(self):
            if threading.get_ident() != self._rsi_owner:
                raise RuntimeError('Native teardown outside owner thread')
            return base.close(self)
    return OwnerFacade


def install(server_module, vector_module, mixin):
    """Only called by the dedicated candidate entrypoint, never legacy launchers."""
    factory = server_module.make_env
    server_module.make_env = lambda *a, **k: construct_on_owner(factory, vector_module, *a, **k)
    server_module.RoboTwinEnvFacade = adapt_facade(server_module.RoboTwinEnvFacade, mixin)
