"""Explicit native RPC runtime compatibility and CPU-only dependency audit.

No GPU/library is initialized at import. install_runtime() is a launch operation:
it owns one live-checked GPU lock and must only be called by the authorized RPC
owner. The native task/scorer files are unchanged. RT shader is preserved, OIDN
is disabled as documented by the completed physical qualification.
"""
from __future__ import annotations
import atexit
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

_OWNER = None

class PhysicsBudget:
    def __init__(self, limit: int, audit_path: Path, metadata: dict):
        if type(limit) is not int or limit <= 0:
            raise ValueError('positive explicit physics-step budget required')
        self.limit = limit
        self.used = 0
        self.audit_path = Path(audit_path)
        self.metadata = metadata
        self.save('initialized')

    def save(self, status: str):
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        state = dict(self.metadata, status=status, physics_steps=self.used,
                     max_physics_steps=self.limit, updated_unix=time.time())
        temp = self.audit_path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, indent=2))
        temp.replace(self.audit_path)
        return state

    def wrap(self, fn):
        def bounded_step(*args, **kwargs):
            if self.used >= self.limit:
                self.save('physics_budget_exhausted')
                raise RuntimeError(f'FROZEN_RPC_PHYSICS_BUDGET_EXHAUSTED {self.used}/{self.limit}')
            result = fn(*args, **kwargs)
            self.used += 1
            if self.used % 25 == 0 or self.used == self.limit:
                self.save('running')
            return result
        return bounded_step


def install_runtime(*, root: Path, gpu: int, max_physics_steps: int, audit_path: Path):
    global _OWNER
    if _OWNER is not None:
        raise RuntimeError('RPC runtime already installed in this process')
    import fcntl
    root = Path(root).resolve(strict=True)
    runtime = Path(os.environ['RSI_RUNTIME_ROOT']).resolve(strict=True)
    if not (root/'envs/_base_task.py').is_file() or not (root/'assets/objects/objaverse/list.json').is_file():
        raise ValueError('complete fixed native backend root required')
    if gpu not in (0, 1):
        raise ValueError('lzgpu201 has only two authorized GPUs')
    lock = (runtime/f'locks/gpu{gpu}.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    row = subprocess.check_output(['nvidia-smi','-i',str(gpu),'--query-gpu=uuid,memory.used,pci.bus_id',
                                   '--format=csv,noheader,nounits'], text=True).strip().split(',')
    procs = subprocess.check_output(['nvidia-smi','-i',str(gpu),'--query-compute-apps=pid',
                                     '--format=csv,noheader'],text=True).strip()
    if int(row[1]) >= 100 or procs:
        lock.close()
        raise RuntimeError(f'allocated GPU is occupied: {row}, {procs}')
    os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu)
    os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
    os.chdir(root)
    import sapien
    import sapien.core as sapien_core
    device = sapien.Device('cuda:0')
    if not device.pci_string or device.pci_string.lower()[-7:] != row[2].strip().lower()[-7:]:
        lock.close()
        raise RuntimeError('SAPIEN device does not match allocated physical GPU')
    metadata = {'classification':'native_rpc_runtime_compatibility', 'pid':os.getpid(),
                'started_unix':time.time(), 'native_root':str(root), 'physical_gpu':gpu,
                'gpu_uuid':row[0].strip(), 'render_device_pci':device.pci_string,
                'renderer':'native rt (not intercepted)', 'denoiser':'none',
                'official_source_modified':False,
                'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'limits_include':'all Scene.step calls across setup/resampling/action scenes in this RPC process',
                'temporary_enumeration_note':'SAPIEN may open 8MiB graphics-only context on GPU0; physical qualification observed release at exit'}
    budget = PhysicsBudget(max_physics_steps, Path(audit_path), metadata)
    original_denoiser = sapien.render.set_ray_tracing_denoiser
    sapien.render.set_ray_tracing_denoiser = lambda requested: original_denoiser('none')
    engine_module = importlib.import_module('sapien.wrapper.engine')
    original_scene = engine_module.Scene
    def make_scene():
        scene = original_scene([sapien.physx.PhysxCpuSystem(), sapien.render.RenderSystem(device)])
        scene.step = budget.wrap(scene.step)
        return scene
    engine_module.Scene = make_scene
    class PinnedRenderer(sapien.pysapien.render.SapienRenderer):
        def __init__(self, **kwargs): super().__init__(device)
        def create_material(self): return sapien.render.RenderMaterial()
    sapien.SapienRenderer = PinnedRenderer
    sapien_core.SapienRenderer = PinnedRenderer
    _OWNER = (lock, budget)
    def finish():
        budget.save('process_exit')
        lock.close()
    atexit.register(finish)
    return budget.save('runtime_installed')


def audit_imports():
    """No sockets, no model initialization or GPU. Run in a fresh CPU process."""
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '':
        raise RuntimeError("Audit requires CUDA_VISIBLE_DEVICES='' before Python starts")
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    def forbid_network(event, args):
        if event in ('socket.connect','socket.connect_ex'):
            raise RuntimeError('CPU_IMPORT_AUDIT_FORBIDS_NETWORK')
    sys.addaudithook(forbid_network)
    modules = [
        'roborsi.embodied.sim.robotwin.server',
        'roborsi.embodied.agent_loop.vlm_io',
        'roborsi.embodied.agent_loop.rollout',
        'roborsi.embodied.agent_loop.prompt_tools',
        'roborsi.embodied.agent_loop.messages',
        'roborsi.embodied.sim.robotwin.robotwin_agent',
        'roborsi.embodied.sim.robotwin.robotwin_tools',
        'roborsi.embodied.sim.robotwin.robotwin_perceive_tools',
        'roborsi.embodied.skills.base.plan.robotwin.policy',
        'roborsi.embodied.skills.base.detect_object.robotwin.policy',
        'roborsi.evaluation.atomic',
        'roborsi.agents.roles.engineer',
        'roborsi.agents.roles.planner',
        'roborsi.agents.roles.reviewer',
        'roborsi.agents.memory.skill_selector',
        'roborsi.channels.core.agent',
        'roborsi.channels.agent.feishu.live_trace',
        'roborsi.channels.agent.feishu.task_runner',
        'roborsi.store.trace_db',
    ]
    results = {}
    for name in modules:
        try:
            mod = importlib.import_module(name)
            results[name] = {'imported':True,'source':mod.__file__}
        except Exception as e:
            results[name] = {'imported':False,'error':repr(e)}
    import_roots = ['openai','anthropic','httpx','torch','transformers','cv2','PIL',
                    'numpy','msgpack','msgpack_numpy','fastapi','uvicorn','yaml',
                    'imageio_ffmpeg','litellm','lark','zmq','graspnetAPI']
    available = {name:importlib.util.find_spec(name) is not None for name in import_roots}
    return {'classification':'CPU dependency audit; no simulator/model invocation',
            'gpu_used':False,'model_calls':0,'network_allowed':False,
            'modules':results,'package_import_roots':available,
            'success':all(v['imported'] for v in results.values()),
            'required_followups':['Grounding-DINO and SAM revisions/weights must be fixed and locally installed before native perception core runs; role Qwen routing does not cover these deterministic helpers',
                                  'Explicitly disable unconfigured optional GraspGen service or pin/provision it; never silently auto-probe arbitrary service',
                                  'Optional pytorch3d FPS unused with pointcloud=false; graspnetAPI unused without GRASPNET_CKPT',
                                  'All provider/helper/retry calls must still route through the common metered local endpoint']}

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--audit-output',type=Path,required=True);a=p.parse_args()
    r=audit_imports();a.audit_output.parent.mkdir(parents=True,exist_ok=True)
    a.audit_output.write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
