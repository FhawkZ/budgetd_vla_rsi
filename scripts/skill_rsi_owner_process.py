"""Owned session cleanup and trusted backend-log monitor (not a setsid jail)."""
import os
from pathlib import Path
import signal
import threading
import time
from skill_rsi_owner_accounting import proc_start

MARKERS = ('OptiX Error:', 'Failed to denoise', 'ErrorInitializationFailed', 'VK_ERROR_DEVICE_LOST')

def render_error(path):
    p = Path(path)
    if not p.exists():
        return None
    if p.stat().st_size > 4 * 2**20:
        return 'backend_log_limit'
    data = p.read_bytes().decode('utf-8', errors='replace')
    return next((m for m in MARKERS if m in data), None)

class OwnedSession:
    def __init__(self, process):
        self.process = process
        self.pid = process.pid
        self.start = proc_start(self.pid)
        if os.getpgid(self.pid) != self.pid or os.getsid(self.pid) != self.pid:
            raise ValueError('fresh owned session required')
        self.receipt = {'pid': self.pid, 'starttime': self.start, 'session': self.pid}
    def members(self):
        rows = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                f = (p / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(f[2]) == self.pid and int(f[3]) == self.pid:
                    rows.append({'pid': int(p.name), 'starttime': f[19], 'state': f[0]})
            except (OSError, ValueError, IndexError):
                continue
        return rows
    def kill(self):
        # A living reused leader is never signalled. Descendants retaining this
        # freshly created session/group remain identifiable after leader exit.
        try:
            if proc_start(self.pid) != self.start:
                raise RuntimeError('leader PID reused')
        except FileNotFoundError:
            pass
        if self.members():
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    def cleanup(self):
        self.receipt['before'] = self.members()
        self.kill()
        self.process.wait(timeout=2)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            rows = self.members()
            if not any(r['state'] != 'Z' for r in rows):
                break
            time.sleep(.01)
        self.receipt['after'] = self.members()
        self.receipt['live_remaining'] = [r for r in self.receipt['after'] if r['state'] != 'Z']
        self.receipt['exit_code'] = self.process.returncode
        if self.receipt['live_remaining']:
            raise RuntimeError('owned group cleanup incomplete')
        return self.receipt

class RenderWatch:
    def __init__(self, path, owned):
        self.path, self.owned = Path(path), owned
        self.error = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
    def check(self):
        if self.error is None:
            try:
                self.error = render_error(self.path)
            except OSError:
                self.error = 'backend_log_unreadable'
        return self.error
    def loop(self):
        while not self.stop_event.wait(.01):
            if self.check():
                self.owned.kill()
                return
    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=1)
        self.check()
