"""Bounded native reset/render/action installation qualification, never an Agent score.

Uses pinned RoboRSI and RoboTwin unchanged. Runtime-only compatibility hooks pin
SAPIEN rendering to the allocated device and preserve native RT shader and select no denoiser explicitly.
The official task physics, controller, assets, and success predicate are unchanged.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

p = argparse.ArgumentParser()
p.add_argument('--task', choices=['stack_blocks_two', 'handover_block'], required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--gpu', type=int, choices=[1], default=1)
a = p.parse_args()
runtime = Path(os.environ['RSI_RUNTIME_ROOT'])
assert Path(sys.prefix) == runtime / 'software/envs/robotwin', 'Use the uv robotwin environment'
assert not a.output.exists(), 'Use a fresh evidence directory; never overwrite previous attempt'
a.output.mkdir(parents=True)
report = {'status': 'preflight', 'classification': 'native_backend_installation_smoke',
          'task': a.task, 'seed': 42, 'gpu': a.gpu, 'model_calls': 0, 'agent_episodes': 0,
          'skill_updates': 0, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'limits': {'wall_seconds': 900, 'reset_physics_steps': 5000, 'action_physics_steps': 120,
                     'reset_attempts': 1, 'actions': 2},
          'compatibility': {'renderer': 'native rt', 'denoiser': 'none',
                            'explicit_render_device': 'visible cuda:0 (physical GPU1)',
                            'official_source_modified': False},
          'started_unix': time.time(), 'phase': 'preflight', 'physics_steps': {}, 'actions': []}

def save():
    report['updated_unix'] = time.time()
    temp = a.output / 'report.tmp'
    temp.write_text(json.dumps(report, indent=2))
    temp.replace(a.output / 'report.json')

def stop(signum, frame):
    raise TimeoutError(f'qualification interrupted signal {signum}')

signal.signal(signal.SIGALRM, stop)
signal.signal(signal.SIGTERM, stop)
signal.alarm(900)
lock = None
env = None
save()
try:
    lock = (runtime / f'locks/gpu{a.gpu}.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    row = subprocess.check_output(['nvidia-smi', '-i', str(a.gpu), '--query-gpu=uuid,memory.used,utilization.gpu',
                                   '--format=csv,noheader,nounits'], text=True).strip().split(',')
    procs = subprocess.check_output(['nvidia-smi', '-i', str(a.gpu), '--query-compute-apps=pid',
                                     '--format=csv,noheader'], text=True).strip()
    assert int(row[1]) < 100 and not procs, f'GPU occupied: {row}, {procs}'
    report['gpu_uuid'] = row[0].strip()
    report['gpu_preflight'] = {'memory_mib': int(row[1]), 'utilization_percent': int(row[2])}
    os.environ['CUDA_VISIBLE_DEVICES'] = str(a.gpu)
    os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
    import numpy as np
    import torch
    import sapien
    from PIL import Image
    import importlib.metadata as metadata
    import importlib
    import curobo
    from curobo.wrap.reacher.motion_gen import MotionGen
    report['versions'] = {k: metadata.version(k) for k in ['torch', 'sapien', 'nvidia-curobo', 'mplib']}
    assert torch.cuda.device_count() == 1
    device = sapien.Device('cuda:0')
    report['render_device'] = {'name': device.name, 'cuda_id': device.cuda_id, 'pci_string': device.pci_string}
    gpu_pci = subprocess.check_output(['nvidia-smi', '-i', str(a.gpu), '--query-gpu=pci.bus_id',
                                      '--format=csv,noheader'], text=True).strip().lower()
    assert device.pci_string and gpu_pci[-7:] == device.pci_string.lower()[-7:], (gpu_pci, device.pci_string)
    # Retain native RT shader; only disable unsupported denoiser. Official files unchanged.
    original_shader = sapien.render.set_camera_shader_dir
    original_denoiser = sapien.render.set_ray_tracing_denoiser
    sapien.render.set_camera_shader_dir = lambda ignored: original_shader('rt')
    sapien.render.set_ray_tracing_denoiser = lambda ignored: original_denoiser('none')
    engine_module = importlib.import_module('sapien.wrapper.engine')
    original_scene = engine_module.Scene
    def counted_scene():
        scene = original_scene([sapien.physx.PhysxCpuSystem(), sapien.render.RenderSystem(device)])
        original_step = scene.step
        def counted_step():
            phase = report['phase']
            n = report['physics_steps'].get(phase, 0)
            bound = report['limits']['reset_physics_steps'] if phase == 'reset' else report['limits']['action_physics_steps']
            assert n < bound, f'physics step bound reached in {phase}'
            result = original_step()
            report['physics_steps'][phase] = n + 1
            return result
        scene.step = counted_step
        return scene
    engine_module.Scene = counted_scene
    # Initialize the render context on the allocated device before deprecated
    # RoboTwin SapienRenderer() is called; it otherwise defaults to device 0.
    import sapien.core as sapien_core
    class PinnedRenderer(sapien.pysapien.render.SapienRenderer):
        def __init__(self, **kwargs):
            super().__init__(device)
        def create_material(self):
            return sapien.render.RenderMaterial()
    sapien.SapienRenderer = PinnedRenderer
    sapien_core.SapienRenderer = PinnedRenderer
    from roborsi.embodied.sim.robotwin.adapter import RoboTwinBackend, _to_sim_obs
    root = Path(os.environ['ROBORSI_ROBOTWIN_ROOT'])
    report['backend_root'] = str(root)
    # Native RoboTwin imports asset indices relative to the repository cwd.
    os.chdir(root)
    report['task_file_sha256'] = hashlib.sha256((root / 'envs' / (a.task + '.py')).read_bytes()).hexdigest()
    report['scorer_unmodified'] = True
    env = RoboTwinBackend(root).make_env(a.task, {'require_depth': True, 'render_freq': 0,
                                               'init_overrides': {'eval_video_log': False}})
    report.update(status='running', phase='reset'); save()
    # Exactly one native setup call: smoke must not silently resample seed 42.
    env._impl = env._init_impl(42)
    env._snapshot_predicate_refs()
    obs = _to_sim_obs(env._impl.get_obs())
    env._last_obs = obs
    robot = env._impl.robot
    def measured():
        return {'left': np.asarray(robot.left_entity.get_qpos(), dtype=float).tolist(),
                'right': np.asarray(robot.right_entity.get_qpos(), dtype=float).tolist()}
    def snapshot(name, observation):
        images = {}
        for camera, arr in observation.images.items():
            arr = np.asarray(arr)
            assert arr.ndim == 3 and arr.shape[-1] in (3, 4) and np.isfinite(arr).all()
            rgb = arr[:, :, :3]
            assert float(rgb.std()) > 1, 'blank image'
            path = a.output / f'{name}-{camera}.png'
            Image.fromarray(rgb.astype('uint8')).save(path)
            images[camera] = {'shape': list(rgb.shape), 'std': float(rgb.std()),
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        assert len(images) >= 3, images
        return {'images': images, 'measured_articulation_qpos': measured(),
                'command_state': np.asarray(observation.state, dtype=float).tolist()}
    report['reset'] = snapshot('reset', obs)
    report['phase'] = 'actions'; save()
    initial = measured()
    hold = np.asarray(obs.state, dtype=np.float64)
    assert hold.shape == (14,) and np.isfinite(hold).all()
    for name in ('hold', 'left_gripper_quarter_close'):
        before = report['physics_steps'].get('actions', 0)
        action = hold.copy()
        if name == 'left_gripper_quarter_close':
            action[6] = max(0., float(action[6]) - 0.25)
        result = env.step(action, action_type='qpos')
        entry = {'name': name, 'action_type': 'qpos', 'command': action.tolist(),
                 'physics_steps': report['physics_steps'].get('actions', 0) - before,
                 'evidence': snapshot(name, result.obs), 'native_done_smoke_only': bool(result.done)}
        assert 1 <= entry['physics_steps'] <= 60
        report['actions'].append(entry); save()
    final = measured()
    change = max(float(np.max(np.abs(np.asarray(final[side]) - np.asarray(initial[side]))))
                 for side in ['left', 'right'])
    report['max_measured_qpos_delta'] = change
    assert change > 1e-4, 'No measured articulation response to gripper action'
    report.update(status='passed', elapsed_seconds=time.time()-report['started_unix'])
except BaseException as exc:
    report.update(status='failed', error=repr(exc), traceback=traceback.format_exc())
    raise
finally:
    if env is not None:
        try: env.close()
        except Exception as exc: report['close_error'] = repr(exc)
    report['limitation'] = 'Fixed diagnostic commands, not autonomous execution, baseline success rate, forgetting, or RSI improvement.'
    save()
    signal.alarm(0)
    if lock is not None: lock.close()
    print(json.dumps({k: report[k] for k in ['status','task','model_calls','agent_episodes','physics_steps']}), flush=True)
