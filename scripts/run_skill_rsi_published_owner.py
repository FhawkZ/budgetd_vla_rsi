"""One published-source fallback run. No generated artifact execution authority.
CPU integration uses the same owner with a pinned synthetic backend factory.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from skill_rsi_owner_accounting import ActiveWall, BoundSkill
from skill_rsi_owner_process import OwnedSession, render_error
from skill_rsi_published_supervisor import PublishedSupervisor


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_owner(*, source, upstream, factory, factory_sha, output, run_id,
              wall_seconds=240, code_lines=30000, startup_seconds=120,
              api_seconds=60, completion_seconds=15):
    if not 0 < wall_seconds <= 240 or type(code_lines) is not int or not 1 <= code_lines <= 30000:
        raise ValueError('bounded native budgets')
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    execution = ActiveWall(wall_seconds)
    execution.start()  # Includes setup/load, as native Wall does; no caller waits here.
    deadline = started + wall_seconds
    p = sup = owned = binding = sel = stderr = None
    events = []
    report = {'status': 'infrastructure_error', 'run_id': run_id,
              'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'Qwen': 0, 'VLA': 0, 'accepted_update': False,
              'robot_qualified': False, 'api_attempts': 0}
    def record(event):
        events.append(event)
        with (out / 'events.jsonl').open('a') as f:
            f.write(json.dumps(event, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    try:
        sup = PublishedSupervisor(factory, factory_sha, out / 'backend',
            startup_seconds=min(startup_seconds, wall_seconds), call_seconds=api_seconds,
            total_seconds=wall_seconds, max_requests=120)
        execution.check()
        sup.deadline = deadline
        stderr = (out / 'skill.stderr').open('wb')
        p = subprocess.Popen([sys.executable, '-I', '-B',
            str(Path(__file__).with_name('skill_rsi_published_worker.py')), str(upstream)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            close_fds=True, start_new_session=True, bufsize=0, cwd='/',
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        owned = OwnedSession(p)
        binding = BoundSkill(p, run_id, source)  # before source is dispatched
        report['skill_identity'] = owned.receipt.copy()
        init = {'source': source, 'entry': 'fallback', 'args': {}, 'code_lines': code_lines,
                'cpu_seconds': min(240, max(1, math.ceil(wall_seconds)))}
        data = json.dumps(init, allow_nan=False).encode() + b'\n'
        if len(data) > 100000:
            raise ValueError('input frame cap')
        (out / 'input.json').write_bytes(data)
        # Source is <=60k: worker is waiting on this bounded input pipe.
        p.stdin.write(data)
        p.stdin.flush()
        sel = selectors.DefaultSelector()
        sel.register(p.stdout, selectors.EVENT_READ)
        buffer = b''
        ready = False
        terminal = None
        frames = 0
        while True:
            execution.check()
            if sup.watch.check():
                raise RuntimeError('trusted render error')
            if not sel.select(min(.05, max(.001, deadline-time.monotonic()))):
                continue
            chunk = os.read(p.stdout.fileno(), 65537)
            if not chunk:
                if buffer or terminal is None:
                    raise ValueError('incomplete terminal stream')
                break
            buffer += chunk
            if len(buffer) > 65536:
                raise ValueError('output frame cap')
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                row = json.loads(line)
                frames += 1
                if frames > 123 or not isinstance(row, dict) or terminal is not None:
                    raise ValueError('frame order/budget')
                record({'child': row})
                if row.get('type') == 'ready':
                    if ready or row.get('source_sha256') != report['source_sha256'] or row.get('seccomp_allowlist') is not True:
                        raise ValueError('worker readiness identity')
                    ready = True
                elif row.get('type') == 'api':
                    if not ready or set(row) != {'type', 'method', 'args'}:
                        raise ValueError('API order/fields')
                    report['api_attempts'] += 1
                    value = sup.dispatch(row['method'], row['args'])
                    execution.check()
                    answer = {'ok': True, 'value': value}
                    record({'parent': answer})
                    p.stdin.write(json.dumps(answer, allow_nan=False).encode()+b'\n')
                    p.stdin.flush()
                elif row.get('type') == 'result':
                    if not ready or set(row) != {'type', 'value', 'code_lines'}:
                        raise ValueError('terminal order/fields')
                    if type(row['code_lines']) is not int or not 0 <= row['code_lines'] <= code_lines:
                        raise ValueError('line accounting')
                    terminal = row
                else:
                    raise ValueError('worker rejected or failed: '+str(row.get('type')))
        p.wait(timeout=max(.001, deadline-time.monotonic()))
        execution.pause()
        report['receipt'] = binding.consume(p, run_id, source)
        report['terminal'] = terminal
        # Evaluation has separate finite watchdog. No retry on unknown/refused.
        sup.deadline = time.monotonic() + completion_seconds
        sup.call_seconds = completion_seconds
        ack = sup.complete_from_owner(p, outcome='returned', render_error=bool(sup.watch.check()))
        if ack != {'status': 'completion_recorded'} or sup.report.get('render_error'):
            raise RuntimeError('completion/render failure')
        report['status'] = 'completed_private'
    except BaseException as error:
        report.update(error_class=type(error).__name__, error=str(error))
    finally:
        report['execution_wall_seconds'] = execution.elapsed()
        report['execution_wall_limit'] = wall_seconds
        if sel is not None:
            sel.close()
        if p is not None:
            report['skill_exit_before_cleanup'] = p.poll()
            try:
                report['skill_cleanup'] = owned.cleanup() if owned is not None else None
            except BaseException as error:
                report.update(status='cleanup_error', cleanup_error=str(error))
            for stream in [p.stdin, p.stdout]:
                if stream is not None and not stream.closed:
                    stream.close()
        if stderr is not None:
            stderr.close()
        if sup is not None:
            try:
                sup.close()
                report['backend'] = sup.report
            except BaseException as error:
                report.update(status='cleanup_error', backend_cleanup_error=str(error))
        report['elapsed'] = time.monotonic()-started
        (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def validate_native_config(path, expected):
    path = Path(path)
    if path.is_symlink() or sha(path) != expected:
        raise ValueError('protocol hash')
    c = json.loads(path.read_text())
    if c.get('status') != 'FROZEN_NATIVE_ISOLATED' or c.get('source_class') != 'published':
        raise ValueError('published-only independent frozen protocol required')
    if c['gpu'] not in (2, 3):
        raise ValueError('301 GPU2/3 only')
    required_limits = {'wall_seconds': 240, 'code_lines': 30000, 'primitive_budget': 90,
                       'sim_seconds': 90, 'settle_seconds': 2}
    if any(c['limits'].get(k) != v for k,v in required_limits.items()):
        raise ValueError('native budget contract')
    durable = Path('/root/autodl-tmp/qian/Dex_runtime/agent-rsi-migration-20261105/outputs')
    for key in ['output', 'owner_output']:
        if not Path(c[key]).resolve().is_relative_to(durable):
            raise ValueError('native evidence requires durable output root')
    if Path(c['output']).resolve() == Path(c['owner_output']).resolve():
        raise ValueError('owner/backend output separation')
    root = Path(c['upstream']).resolve().parent / 'frozen_skills'
    for key in ['skills_file', 'perception_file']:
        p = Path(c[key])
        if p.is_symlink() or not p.resolve().is_relative_to(root):
            raise ValueError('published source path')
    required = [c['skills_file'], c['perception_file']]
    # Pin all standalone Python source: transitive imports cannot silently change.
    required += [str(p.resolve()) for p in Path(__file__).parent.glob('*.py')]
    if any(p not in c['source_sha256'] for p in required):
        raise ValueError('missing owner source pin')
    for p,h in c['source_sha256'].items():
        if sha(p) != h:
            raise ValueError('source changed: '+p)
    return c


def native_factory_text(protocol, digest, private_output, log_path):
    return f'''from skill_rsi_native_lifecycle import build_native
from skill_rsi_completion import CompletionGate
from skill_rsi_owner_process import render_error
from pathlib import Path

def build():
    return build_native({str(protocol)!r}, {digest!r})

def completion_gate(b):
    def score(task):
        if render_error({str(log_path)!r}):
            raise RuntimeError('render error before score')
        value = task.check_success()
        if render_error({str(log_path)!r}):
            raise RuntimeError('render error during score')
        return value
    return CompletionGate(b, {str(private_output)!r}, b.hooks.env.settle, score)
'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--protocol', required=True)
    p.add_argument('--sha256', required=True)
    args = p.parse_args()
    path = Path(args.protocol).resolve()
    c = validate_native_config(path, args.sha256)
    out = Path(c['owner_output'])
    # Durable owner storage, separate from NativeSession output directory.
    if out.exists() or Path(c['output']).exists():
        raise FileExistsError('run already has evidence')
    factory = out.with_name(out.name+'.factory.py')
    if factory.exists():
        raise FileExistsError('factory already frozen')
    factory.parent.mkdir(parents=True, exist_ok=True)
    factory.write_text(native_factory_text(path, args.sha256, out/'private-evaluation.json', out/'backend/backend.log'))
    row = run_owner(source=Path(c['skills_file']).read_text(), upstream=c['upstream'],
                    factory=factory, factory_sha=sha(factory), output=out, run_id=c['run_id'])
    print(json.dumps({'status': row['status'], 'accepted_update': False}))
    return 0 if row['status'] == 'completed_private' else 1

if __name__ == '__main__':
    raise SystemExit(main())
