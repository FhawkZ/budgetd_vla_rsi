"""User-authorized removal of per-action RPC timeout; outer owner remains bounded."""
import json
import urllib.request

class ActionWaitOpener:
    def __init__(self, delegate):
        self.delegate = delegate
    def open(self, request, *, timeout):
        method = json.loads(request.data)['method']
        # None is urllib's blocking socket mode; no retries or replay.
        if method in ('env.step', 'env.chunk_step'):
            timeout = None
        return self.delegate(request, timeout=timeout)

def install(client_class):
    if getattr(client_class, '_rsi_action_wait_installed', False):
        raise RuntimeError('action wait adapter already installed')
    original = client_class.__init__
    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        delegate = self._opener.open if self._opener else urllib.request.urlopen
        self._opener = ActionWaitOpener(delegate)
    client_class.__init__ = init
    client_class._rsi_action_wait_installed = True
