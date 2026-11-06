"""Trusted backend owner. This process is not the untrusted skill sandbox.
Factory builds backend and explicit native exception type map on the main thread.
No exception-message heuristic, scoring, candidate code, retry or fallback seed.
"""
import hashlib
import os
from pathlib import Path
import socket
import select
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_rsi_api_supervisor import receive, send, STATUSES
from skill_rsi_skill_ipc import PublicAPI, plain
from skill_rsi_completion import OwnerCompletion


def main():
    channel = socket.socket(fileno=int(sys.argv[1]))
    control = socket.socket(fileno=int(sys.argv[4]))
    path = Path(sys.argv[2])
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != sys.argv[3]:
        raise ValueError('trusted factory changed')
    namespace = {'__file__': str(path), '__name__': 'trusted_api_factory'}
    exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
    backend, exceptions = namespace['build']()
    if set(exceptions) != STATUSES or any(not isinstance(t, type) or not issubclass(t, BaseException) for t in exceptions.values()):
        raise ValueError('explicit exception classes required')
    api = PublicAPI(backend)
    try:
        send(channel, {'type': 'ready', 'factory_sha256': sys.argv[3]}, time.monotonic()+10)
        while True:
            try:
                ready,_,_=select.select([control,channel],[],[],300)
                if not ready:raise TimeoutError('idle backend deadline')
                if control in ready:
                    row=receive(control,time.monotonic()+10)
                    if set(row)!={'control','receipt','deadline'} or row['control']!='complete':
                        raise ValueError('private control contract')
                    gate=namespace['completion_gate'](backend)
                    answer=gate.finish(OwnerCompletion(**row['receipt']),row['deadline'])
                    send(control,answer,min(row['deadline'],time.monotonic()+10))
                    break
                row = receive(channel, time.monotonic()+10)
            except EOFError:
                break
            if set(row) != {'id', 'method', 'args'}:
                raise ValueError('request fields')
            try:
                value = api.dispatch(row['method'], row['args'])
            except BaseException as error:
                # Use class identity (including subclasses), never name/message matching.
                status = next((key for key, cls in exceptions.items() if isinstance(error, cls)), 'native_error')
                answer = {'id': row['id'], 'status': status, 'error_class': type(error).__name__}
                send(channel, answer, time.monotonic()+10)
                break
            try:
                answer = {'id': row['id'], 'status': 'ok', 'value': plain(value)}
                send(channel, answer, time.monotonic()+10)
            except (TypeError, ValueError):
                send(channel, {'id': row['id'], 'status': 'response_rejected', 'error_class': 'ValueError'}, time.monotonic()+10)
                break
    finally:
        # Cleanup can itself block; parent close/deadline kills only its owned child.
        close = getattr(backend, 'close', None)
        if close:
            close()
        channel.close()
        control.close()


if __name__ == '__main__':
    main()
