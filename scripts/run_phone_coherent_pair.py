"""Four-attempt place_phone_stand coherent package pair (A/B seed1, B/A seed2).

New parent only; every original runner stays byte-identical. Each attempt is one
child `run_native_pair_case.py --mode baseline` on its own single-case protocol
(published-skill worker, PublicAPI seven methods / 120 cap). No model calls, no
isolated mode, no old parent, no re-initialization, retry or replacement seed.
A completed episode with success=false is a valid policy failure; any
init/render/infrastructure/unexpected exit/residual process closes the run and
cancels all unstarted attempts. --check is CPU-only verification.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_skill_rsi_native_v2 import sha, render_log_error
import run_skill_rsi_native_v2 as _v2
from run_skill_rsi_native_v3 import gpu_read
from gpu_idle_gate import wait_idle
from skill_rsi_owner_process import OwnedSession
from run_native_owner_pair import descendants, cleanup_known

SCRIPTS = Path(_v2.__file__).resolve().parent
CASE_RUNNER = SCRIPTS / 'run_native_pair_case.py'
SELF = Path(__file__).resolve()
DURABLE = Path('/root/autodl-tmp/qian/Dex_runtime/agent-rsi-migration-20261105/outputs')
TASK = 'place_phone_stand'
PKG_A, PKG_B = 'place_phone_stand_10bbaf', 'place_phone_stand_4161b3'
GPU = 3
# Transitive local import closure of the case runner and of this parent.
REQUIRED_SCRIPTS = ('run_native_pair_case.py', 'run_skill_rsi_native_v2.py', 'run_skill_rsi_native_v3.py',
    'gpu_idle_gate.py', 'skill_rsi_owner_process.py', 'skill_rsi_owner_accounting.py',
    'run_native_owner_pair.py', 'run_skill_rsi_published_owner.py', 'skill_rsi_published_supervisor.py',
    'skill_rsi_skill_ipc.py')
TOP_KEYS = {'status', 'gpu', 'task', 'packages', 'attempts_max', 'qwen_max', 'vla_max',
    'process_wall_seconds', 'total_wall_seconds', 'expected_output_bytes', 'cases', 'source_files', 'output'}
OPTIONAL_KEYS = {'id', 'note', 'created'}
CASE_KEYS = {'task', 'skill', 'seed', 'protocol', 'sha256'}
V2_LIMITS = {'primitive_budget': 90, 'sim_seconds': 90, 'wall_seconds': 240, 'code_lines': 30000, 'settle_seconds': 2}


class ContractError(ValueError):
    pass


def need(cond, msg):
    if not cond:
        raise ContractError(msg)


def case_dir_name(i, case):
    return f"attempt-{i}-{case['skill']}-seed{case['seed']}"


def verify(c, runtime, output_root=DURABLE):
    """CPU-only contract and hash verification. Returns loaded case configs."""
    need(isinstance(c, dict), 'protocol object')
    need(TOP_KEYS <= set(c) and set(c) <= TOP_KEYS | OPTIONAL_KEYS, 'protocol keys')
    need(c['status'] == 'FROZEN_PHONE_PAIR', 'status')
    need(c['gpu'] == GPU and type(c['gpu']) is int, 'gpu3 only')
    need(c['task'] == TASK and c['packages'] == {'A': PKG_A, 'B': PKG_B}, 'task/packages')
    need(c['attempts_max'] == 4 and type(c['attempts_max']) is int, 'attempts_max')
    need(c['qwen_max'] == 0 and c['vla_max'] == 0 and type(c['qwen_max']) is int and type(c['vla_max']) is int, 'model budgets')
    need(c['process_wall_seconds'] == 300 and type(c['process_wall_seconds']) is int, 'process wall')
    need(c['total_wall_seconds'] == 1320 and type(c['total_wall_seconds']) is int, 'total wall')
    need(c['expected_output_bytes'] == 268435456 and type(c['expected_output_bytes']) is int, 'expected output')
    out = Path(c['output'])
    need(out.is_absolute() and '..' not in out.parts and out.parent == Path(output_root) and out.name not in ('', '.'),
         'output must be a direct child of the durable outputs directory')
    need(out.resolve().parent == Path(output_root).resolve(), 'output resolves outside durable root')
    cases = c['cases']
    need(isinstance(cases, list) and len(cases) == 4, 'four cases')
    for case in cases:
        need(isinstance(case, dict) and set(case) == CASE_KEYS, 'case keys')
        need(case['task'] == TASK, 'case task')
        need(type(case['seed']) is int and case['seed'] >= 0, 'case seed')
    order = [x['skill'] for x in cases]
    need(order == [PKG_A, PKG_B, PKG_B, PKG_A], 'order must be A,B (seed1) then B,A (seed2)')
    s1, s2 = cases[0]['seed'], cases[2]['seed']
    need(cases[1]['seed'] == s1 and cases[3]['seed'] == s2 and s1 != s2, 'paired seeds')
    protos = [str(Path(x['protocol']).resolve()) for x in cases]
    need(len(set(protos)) == 4 and len({x['sha256'] for x in cases}) == 4, 'one distinct protocol per case')
    need(len({case_dir_name(i, x) for i, x in enumerate(cases)}) == 4, 'case output names')
    # Source layout and hashes: full script closure, this parent and both packages.
    src = c['source_files']
    need(isinstance(src, dict) and src, 'source_files')
    for name in REQUIRED_SCRIPTS:
        need(str(SCRIPTS / name) in src, f'source_files missing {name}')
    need(str(SELF) in src, 'source_files missing this parent')
    for mod in (_v2,) + tuple(sys.modules[m] for m in ('run_skill_rsi_native_v3', 'gpu_idle_gate',
            'skill_rsi_owner_process', 'run_native_owner_pair', 'skill_rsi_owner_accounting')):
        need(Path(mod.__file__).resolve().parent == SCRIPTS, f'imported {mod.__name__} outside pinned scripts')
    for p, h in src.items():
        need(Path(p).is_absolute() and Path(p).is_file(), f'source path {p}')
        need(sha(p) == h, f'source hash {p}')
    loaded = []
    for case in cases:
        need(Path(case['protocol']).is_file() and sha(case['protocol']) == case['sha256'], 'case protocol hash')
        cfg = json.loads(Path(case['protocol']).read_text())
        need(cfg.get('status') == 'FROZEN' and cfg.get('attempts_max') == 1, 'case status/attempts')
        need(cfg.get('qwen_max') == 0 and cfg.get('vla_max') == 0 and cfg.get('denoiser') == 'none', 'case budgets')
        need(cfg.get('limits', {}) and all(cfg['limits'].get(k) == v for k, v in V2_LIMITS.items()), 'case limits')
        need(isinstance(cfg.get('cases'), list) and len(cfg['cases']) == 1, 'single case index0')
        inner = cfg['cases'][0]
        need(all(inner.get(k) == case[k] for k in ('task', 'skill', 'seed')), 'case protocol content mismatch')
        need(TASK in cfg.get('task_cards', {}), 'task card')
        for p, h in cfg.get('source_files', {}).items():
            need(sha(p) == h, f'case source hash {p}')
        clip = Path(runtime) / cfg['clip_weight']
        need(clip.is_file() and sha(clip) == cfg['clip_sha256'], 'clip hash')
        for f in ('skills.py', 'perception.py'):
            pkg = Path(runtime) / cfg['vendor'] / 'frozen_skills' / case['skill'] / f
            need(str(pkg) in src and pkg.is_file(), f'package file {pkg} not pinned')
        loaded.append(cfg)
    def common(cfg):
        return {k: v for k, v in cfg.items() if k not in ('id', 'cases')}
    need(all(common(x) == common(loaded[0]) for x in loaded), 'case protocols differ outside id/cases')
    need(len({x.get('id') for x in loaded}) == 4, 'case ids distinct')
    return loaded


def durable_dump(path, obj):
    path = Path(path)
    tmp = path.with_name('.' + path.name + '.tmp')
    with tmp.open('w') as f:
        f.write(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    d = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(d)
    finally: os.close(d)


def durable_append(path, row):
    with Path(path).open('a') as f:
        f.write(json.dumps(row, default=str) + '\n'); f.flush(); os.fsync(f.fileno())


class ResourceError(RuntimeError):
    pass


def storage(expected):
    v = os.statvfs(DURABLE)
    free, total = v.f_bavail * v.f_frsize, v.f_blocks * v.f_frsize
    row = {'free_bytes': free, 'total_bytes': total, 'free_inodes': v.f_favail,
           'required_bytes': max(100 * 2**30, .2 * total) + expected, 'time': time.time()}
    if free < row['required_bytes'] or v.f_favail <= 100000:
        raise ResourceError(f'storage gate failed: {row}')
    return row


def resources(out, expected, pinned=None):
    row = storage(expected)
    durable_append(out / 'resources.jsonl', {'storage': row})
    gpu = wait_idle(lambda: gpu_read(GPU), lambda s: durable_append(out / 'resources.jsonl', {'gpu': s}), timeout=6)
    if pinned is not None and (gpu['uuid'], gpu['pci']) != (pinned['uuid'], pinned['pci']):
        raise ResourceError('GPU3 identity changed')
    return gpu


def tree_bytes(p):
    n = 0
    for root, _, files in os.walk(p):
        for f in files:
            try: n += os.lstat(os.path.join(root, f)).st_size
            except OSError: pass
    return n


def contract_errors(result, case):
    e = []
    if result.get('status') != 'completed': e.append('status_not_completed')
    for k in ('task', 'skill', 'seed'):
        if result.get(k) != case[k]: e.append('mismatch_' + k)
    if result.get('qwen_calls') != 0 or result.get('vla_calls') != 0: e.append('model_calls')
    if result.get('setup_completed') != 1: e.append('setup_not_completed')
    if result.get('infrastructure_error') is not False: e.append('infrastructure_error')
    if result.get('success') not in (True, False): e.append('success_not_boolean')
    return e


COST_KEYS = ('primitive_calls', 'recorded_primitive_calls', 'monitor_steps', 'dt', 'sim_seconds', 'settle_seconds',
             'clip_assignments', 'clip_seconds', 'code_lines', 'wall_seconds', 'process_seconds',
             'qwen_calls', 'vla_calls', 'setup_attempts', 'setup_completed')


def attempt(i, case, c, out, gpu, r, t0):
    name = case_dir_name(i, case)
    ep, logpath = out / name, out / (name + '.log')
    start = time.monotonic()
    row = {'index': i, 'case': case, 'gpu_before': gpu, 'output': str(ep), 'started_unix': time.time()}
    p = owned = None; known = {}; offset = 0; tail = ''
    try:
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(GPU), CUDA_DEVICE_ORDER='PCI_BUS_ID',
                   RSI_EXPECTED_GPU_PCI=gpu['pci'], PYTHONPATH='', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        args = [sys.executable, str(CASE_RUNNER), '--mode', 'baseline', '--protocol', case['protocol'],
                '--sha256', case['sha256'], '--output', str(ep)]
        row['argv'] = args
        with logpath.open('xb') as log:
            p = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            r['attempted'] += 1; r['unstarted'] -= 1
            owned = OwnedSession(p); row['identity'] = owned.receipt.copy()
            r['active'] = row; durable_dump(out / 'report.json', r)
            deadline = min(start + c['process_wall_seconds'], t0 + c['total_wall_seconds'])
            while p.poll() is None:
                for ident in descendants(p.pid): known[(ident['pid'], ident['starttime'])] = ident
                with logpath.open('rb') as f:
                    f.seek(offset); chunk = f.read().decode('utf-8', errors='replace'); offset = f.tell()
                if render_log_error(tail + chunk): raise RuntimeError('render_error')
                tail = (tail + chunk)[-128:]
                if time.monotonic() > deadline: raise TimeoutError('outer process deadline')
                time.sleep(.1)
        row['exit_before_cleanup'] = p.returncode
    except BaseException as e:
        row.update(error_class=type(e).__name__, error=str(e))
        row['exit_before_cleanup'] = p.poll() if p is not None else None
    finally:
        if p is not None and owned is None:
            # Leader identity unavailable: signal only the exact Popen child.
            try:
                p.kill(); p.wait(timeout=2)
            except Exception as e:
                row['leader_kill_error'] = repr(e)
        if owned is not None:
            try:
                row['outer_cleanup'] = owned.cleanup()
            except BaseException as e:
                row['outer_cleanup'] = owned.receipt; row['outer_cleanup_error'] = repr(e)
        try:
            row['tracked_descendant_cleanup'] = cleanup_known(known)
        except BaseException as e:
            row['tracked_descendant_cleanup'] = None; row['descendant_cleanup_error'] = repr(e)
        row['descendants_seen'] = list(known.values())
        row['finished_unix'] = time.time()
        row['outer_process_interval_seconds'] = time.monotonic() - start
    reasons = []
    if 'error_class' in row: reasons.append(row['error_class'] + ':' + row['error'])
    if row.get('exit_before_cleanup') != 0: reasons.append(f"exit:{row.get('exit_before_cleanup')}")
    oc = row.get('outer_cleanup') or {}
    if 'outer_cleanup_error' in row or oc.get('live_remaining'): reasons.append('owned_session_residual')
    if any(m['state'] != 'Z' for m in oc.get('before', [])): reasons.append('residual_before_cleanup')
    if row.get('tracked_descendant_cleanup') is None or row.get('tracked_descendant_cleanup'):
        reasons.append('descendant_residual')
    try:
        logtext = logpath.read_text(errors='replace') if logpath.exists() else ''
    except OSError:
        logtext = ''
    row['render_error'] = render_log_error(logtext)
    if row['render_error']: reasons.append('render_error')
    try:
        row['result'] = json.loads((ep / 'episode.json').read_text())
        if not isinstance(row['result'], dict): raise ValueError('episode not an object')
    except (OSError, ValueError) as e:
        row['result'] = None; reasons.append('episode_unavailable:' + type(e).__name__)
    if row['result'] is not None:
        reasons += contract_errors(row['result'], case)
        row['cost'] = {k: row['result'].get(k) for k in COST_KEYS}
    row['output_bytes_total'] = tree_bytes(out)
    if row['output_bytes_total'] > c['expected_output_bytes']: reasons.append('output_bytes_exceeded')
    row['infrastructure_reasons'] = reasons
    row['valid'] = not reasons
    row['policy_success'] = row['result'].get('success') if row['valid'] else None
    return row


def run(c, path, runtime, sha256):
    out = Path(c['output'])
    out.mkdir(exist_ok=False)  # one-shot exclusive; parent must already exist
    t0 = time.monotonic()
    r = {'status': 'running', 'protocol': str(path), 'protocol_sha256': sha256, 'planned': 4, 'attempted': 0,
         'valid_completed': 0, 'policy_successes': 0, 'policy_failures': 0, 'unstarted': 4, 'episodes': [],
         'active': None, 'started_unix': time.time(), 'qwen_calls': 0, 'vla_calls': 0, 'accepted_updates': 0,
         'gpu': GPU}
    locks = []
    try:
        durable_dump(out / 'protocol.json', c); durable_dump(out / 'report.json', r)
        for name in ('phone-coherent-pair.lock', f'gpu{GPU}.lock'):
            f = (runtime / 'locks' / name).open('a'); locks.append(f)
            try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise ResourceError(f'lock held: {name}')
        pinned = resources(out, c['expected_output_bytes'])
        r['gpu_identity'] = {k: pinned[k] for k in ('index', 'uuid', 'pci')}
        for i, case in enumerate(c['cases']):
            if t0 + c['total_wall_seconds'] - time.monotonic() < c['process_wall_seconds']:
                r['status'] = 'stopped_total_wall_insufficient'; break
            gpu = resources(out, c['expected_output_bytes'], pinned)
            row = attempt(i, case, c, out, gpu, r, t0)
            r['episodes'].append(row); r['active'] = None
            if row['valid']:
                r['valid_completed'] += 1
                r['policy_successes' if row['policy_success'] else 'policy_failures'] += 1
            res = row.get('result') or {}
            r['qwen_calls'] += res.get('qwen_calls') or 0; r['vla_calls'] += res.get('vla_calls') or 0
            durable_dump(out / 'report.json', r)
            if not row['valid']:
                r['status'] = 'stopped_infrastructure'; break
        else:
            r['status'] = 'completed'
    except ResourceError as e:
        r.update(status='stopped_resource', error=str(e))
    except BaseException as e:
        r.update(status='owner_error', error=repr(e))
    finally:
        r['active'] = None
        r['finished_unix'] = time.time()
        r['outer_interval_seconds'] = time.monotonic() - t0
        r['remaining_attempts_canceled'] = r['unstarted']
        r['note'] = 'no retry, re-initialization or replacement seed; success=false on valid episodes is policy failure'
        durable_dump(out / 'report.json', r)
        durable_dump(out / 'CLOSE.json', {'status': 'CLOSED', 'final_status': r['status'],
            'report_sha256': sha(out / 'report.json'), 'remaining_attempts_canceled': r['unstarted']})
        for f in reversed(locks): f.close()
    return r


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if any(a == '--worker' or a.startswith('--worker=') for a in argv):
        raise SystemExit('--worker is not supported by this parent')
    ap = argparse.ArgumentParser()
    ap.add_argument('--protocol', required=True); ap.add_argument('--sha256', required=True)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args(argv)
    path = Path(a.protocol).resolve()
    if sha(path) != a.sha256: raise SystemExit('protocol hash mismatch')
    runtime = Path(os.environ['RSI_RUNTIME_ROOT'])
    c = json.loads(path.read_text()); verify(c, runtime)
    if Path(c['output']).exists(): raise SystemExit('one-shot output already exists')
    if a.check:
        print('phone pair protocol, case protocols and all sources verified; CPU only, nothing started')
        return 0
    r = run(c, path, runtime, a.sha256)
    print(json.dumps({k: r[k] for k in ('status', 'attempted', 'valid_completed', 'policy_successes',
                                        'policy_failures', 'remaining_attempts_canceled')}))
    return 0 if r['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
