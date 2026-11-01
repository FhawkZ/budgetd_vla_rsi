"""Independent typed-skill qualification or candidate panel.
Derived from frozen owner runner; original remains unchanged.
Qualification fixtures are not Agent task scores. Candidate unaccepted until evaluation.
"""
from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
RPENT_COMMIT = "a744bd5f128ebef3cb8c6736cf7cd98adff681f1"
VLA_REVISION = "e727b46cd220b66981ea4d2fd9ba84adc189e2cc"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=lambda x: x.tolist()) + "\n")
    tmp.replace(path)


def append(path, value):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(value, default=lambda x: x.tolist()) + "\n")


def initial_reference_equal(actual, reference):
    # RPC values contain numpy arrays; normalize exactly as recorded evidence.
    def canonical(value):
        return json.dumps(value, sort_keys=True, default=lambda x: x.tolist(), allow_nan=False)
    return all(canonical(actual[key]) == canonical(reference[key])
               for key in ('initial_robot_state', 'initial_image_sha256'))


def validate(cfg):
    assert cfg['status']=='frozen' and cfg['execution_host']=='lzgpu201'
    assert cfg['classification'] in ('typed_skill_fixture_qualification','typed_shared_candidate_development')
    assert cfg['qwen_calls']==0 and cfg['skill_updates']==0 and cfg['weights_frozen']
    assert cfg['gpu']==1 and cfg['horizon']==1200 and cfg['task_config']=='demo_randomized'
    assert cfg['max_environment_reset_rpc_per_episode']==1 and cfg['max_vla_inferences_per_episode']==24
    if cfg['classification']=='typed_skill_fixture_qualification':
        assert len(cfg['cases'])==2 and cfg['max_vla_inferences_total']==0
    else:
        assert len(cfg['cases'])==10 and cfg['max_vla_inferences_total']==240
    return cfg

def preflight(cfg,strict=False):
    import run_official_owner_panel as base
    runtime=Path(os.environ['RSI_RUNTIME_ROOT'])
    parent=ROOT/cfg['base_protocol'];assert digest(parent)==cfg['base_protocol_sha256']
    base_cfg=json.loads(parent.read_text());base.validate(base_cfg)
    receipt=base.preflight(base_cfg,strict=strict)
    for rel,sha in cfg['new_code_sha256'].items():assert digest(ROOT/rel)==sha,rel
    patch=runtime/cfg['patch_path'];assert digest(patch)==cfg['patch_sha256']
    from typed_skill_patch import validate_patch
    assert validate_patch(json.loads(patch.read_text()))['rules']
    if cfg['classification']=='typed_shared_candidate_development':
        qual=runtime/cfg['typed_qualification_report'];assert digest(qual)==cfg['typed_qualification_report_sha256']
        assert json.loads(qual.read_text())['status']=='completed'
        assert cfg['cases']==base_cfg['cases']
    disk=os.statvfs(runtime);total=disk.f_blocks*disk.f_frsize;free=disk.f_bavail*disk.f_frsize
    assert free>max(100*2**30,.2*total)+cfg['expected_output_max_bytes']
    assert disk.f_favail>100000
    receipt['storage']={'free_bytes':free,'capacity_bytes':total,'projected_bytes':cfg['expected_output_max_bytes']}
    return receipt


def proc_identity(pid):
    try:
        # Field 22 (starttime); comm may itself contain spaces.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19], fields[0]
    except FileNotFoundError:
        return None


def cleanup_owned(path):
    cleaned = []
    if not path.exists():
        return cleaned
    for line in path.read_text().splitlines():
        row = json.loads(line)
        pid = row["pid"]
        identity = proc_identity(pid)
        if identity and identity[0] == row["starttime"] and identity[1] != "Z":
            os.kill(pid, signal.SIGTERM)
            for _ in range(30):
                identity = proc_identity(pid)
                if not identity or identity[0] != row["starttime"] or identity[1] == "Z":
                    break
                time.sleep(.1)
            identity = proc_identity(pid)
            if identity and identity[0] == row["starttime"] and identity[1] != "Z":
                os.kill(pid, signal.SIGKILL)
                for _ in range(20):
                    identity = proc_identity(pid)
                    if not identity or identity[0] != row["starttime"] or identity[1] == "Z":
                        break
                    time.sleep(.1)
        identity = proc_identity(pid)
        cleaned.append({"pid": pid, "live": bool(identity and identity[0] == row["starttime"] and identity[1] != "Z")})
    return cleaned


def gpu_snapshot(index):
    row = subprocess.check_output(
        ["nvidia-smi", "-i", str(index), "--query-gpu=uuid,memory.used,utilization.gpu,pci.bus_id",
         "--format=csv,noheader,nounits"], text=True, timeout=10).strip().split(",")
    procs = subprocess.check_output(
        ["nvidia-smi", "-i", str(index), "--query-compute-apps=pid",
         "--format=csv,noheader"], text=True, timeout=10).strip()
    return {"uuid": row[0].strip(), "memory_mib": int(row[1]), "utilization_percent": int(row[2]),
            "pci_bus_id": row[3].strip(), "compute_pids": procs}


# Loaded only inside an owned env_server process. CUDA_VISIBLE_DEVICES does not
# suffice for SAPIEN's Vulkan device choice. No physics or success rule changes.
RENDER_BOOTSTRAP = r'''
import os, sys
if os.environ.get("RSI_VLA_RENDER_CHILD") == "1":
    try:
        import importlib, json, sapien
        device = sapien.Device("cuda:0")
        expected = os.environ["RSI_EXPECTED_GPU_PCI"].lower()[-7:]
        assert device.pci_string.lower()[-7:] == expected
        old_denoiser = sapien.render.set_ray_tracing_denoiser
        sapien.render.set_ray_tracing_denoiser = lambda ignored: old_denoiser("none")
        engine = importlib.import_module("sapien.wrapper.engine")
        old_scene = engine.Scene
        engine.Scene = lambda: old_scene([sapien.physx.PhysxCpuSystem(), sapien.render.RenderSystem(device)])
        import sapien.core as core
        class PinnedRenderer(sapien.pysapien.render.SapienRenderer):
            def __init__(self, **kwargs):
                super().__init__(device)
            def create_material(self):
                return sapien.render.RenderMaterial()
        sapien.SapienRenderer = PinnedRenderer
        core.SapienRenderer = PinnedRenderer
        print("rsi_render_adapter " + json.dumps({"device": device.pci_string, "shader": "native_rt", "denoiser": "none"}), flush=True)
    except BaseException:
        import traceback
        traceback.print_exc()
        os._exit(73)
'''


def worker(cfg, index, out):
    """Exactly one native reset and only RGB-conditioned learned actions."""
    import numpy as np
    from PIL import Image
    from rpent.utils.daemon import ProcessDaemon
    from rpent.dashboard.events import NullDashboardEventSink
    from robots.robotwin.robot_spec import _init_runtime
    from robots.robotwin.primitives import RoboTwinPrimitives
    from robots.robotwin.env_client import RoboTwinEnvClient

    started = time.time()
    report = {"status": "running", "classification": cfg["classification"], **cfg["cases"][index],
              "qwen_calls": 0, "skill_updates": 0, "strict_rsi_rounds": 0,
              "vla_inferences": 0, "environment_reset_rpc": 0, "native_actions": 0,
              "native_eval_success": None, "started_unix": started}
    save(out / "episode.json", report)
    daemons = []
    original_start = ProcessDaemon.start
    def start_owned(daemon):
        if "robotwin_env_server" == daemon.name:
            asset_root = Path(os.environ["RSI_RUNTIME_ROOT"]) / cfg["assets_relative_path"]
            assert (asset_root / "assets/objects/objaverse/list.json").is_file()
            assert Path(daemon.cmd[1]).name=='env_server.py'
            daemon.cmd[1]=str(ROOT/'scripts/run_owner_env_server.py')
            daemon.subprocess_env.update(RSI_OWNER_QUALIFIED_LAUNCH='candidate_lifecycle_v1',RSI_OWNER_AUDIT_FILE=str(out/'owner-audit.json'))
            daemon.cwd = str(asset_root)
            daemon.subprocess_env.update(ROBOTWIN_ASSETS_ROOT=str(asset_root), ASSETS_PATH=str(asset_root))
            bootstrap = out / "bootstrap"
            bootstrap.mkdir(exist_ok=True)
            (bootstrap / "sitecustomize.py").write_text(RENDER_BOOTSTRAP)
            daemon.subprocess_env["PYTHONPATH"] = str(bootstrap) + os.pathsep + str(ROOT/"scripts") + os.pathsep + daemon.subprocess_env.get("PYTHONPATH", "")
            daemon.subprocess_env["RSI_VLA_RENDER_CHILD"] = "1"
        original_start(daemon)
        daemons.append(daemon)
        identity = proc_identity(daemon._proc.pid)
        assert identity is not None
        append(out / "owned-daemons.jsonl", {"pid": daemon._proc.pid, "starttime": identity[0],
                                            "name": daemon.name, "cmd": daemon.cmd, "cwd": daemon.cwd,
                                            "CUDA_VISIBLE_DEVICES": daemon.subprocess_env.get("CUDA_VISIBLE_DEVICES")})
    ProcessDaemon.start = start_owned
    original_reset = RoboTwinEnvClient.reset
    def counted_reset(env):
        report["environment_reset_rpc"] += 1
        save(out / "episode.json", report)
        assert report["environment_reset_rpc"] <= 1, "Unexpected environment reset"
        return original_reset(env)
    RoboTwinEnvClient.reset = counted_reset
    runtime = Path(os.environ["RSI_RUNTIME_ROOT"])
    kwargs = None
    try:
        args = argparse.Namespace(task_name=report["task"], seed=report["seed"], task_config=cfg["task_config"],
                                  max_episode_steps=cfg["horizon"], env_endpoint=None, vla_endpoint=None,
                                  robotwin_assets_path=str(runtime / cfg["assets_relative_path"]),
                                  vla_model_path=str(runtime / cfg["model_relative_path"]),
                                  lingbot_robot_config=None, cuda_device=str(cfg["gpu"]),
                                  env_cuda_device=None, vla_cuda_device=None)
        _, kwargs = _init_runtime(args, out, NullDashboardEventSink(), None)
        env, model = kwargs["env"], kwargs["model"]
        assert report["environment_reset_rpc"] == 1, "Expected exactly one native reset RPC"
        status = env.last_info["episode_status"]
        assert status["actual_seed"] == report["seed"]
        assert status["step_lim"] == cfg["horizon"], status
        assert status["take_action_cnt"] == 0, status
        assert not status["eval_success"], "Initial state is already successful; invalid screening case"
        instruction = env.get_task_language()
        report["native_task_language"] = instruction
        if cfg.get("public_language_manifest"):
            instruction=cfg["policy_task_instructions"][report["task"]]
            env.get_task_language=lambda: instruction
            report["language_adaptation"]="Client public task language binding; same frozen text required for every comparison arm. Original environment language retained above; no observation/score/action modification."
        assert instruction==cfg["cases"][index]["instruction"], "native language mismatch"
        report["policy_task_language"] = instruction
        report["initial_robot_state"] = env.last_info["robot_state"]
        original_infer = model.infer
        def traced_infer(observation):
            report["vla_inferences"] += 1
            save(out / "episode.json", report)  # failed inference still costs one
            assert report["vla_inferences"] <= cfg["max_vla_inferences_per_episode"]
            assert observation["task_language"] == instruction
            prefix = out / f"inference-{report['vla_inferences']:03d}"
            images = {}
            for camera, view in observation["views"].items():
                rgb = np.asarray(view["rgb"])
                assert rgb.ndim == 3 and rgb.shape[-1] == 3 and rgb.dtype == np.uint8
                file = prefix.with_name(prefix.name + "-" + camera + ".png")
                Image.fromarray(rgb).save(file)
                images[camera] = {"path": file.name, "sha256": digest(file), "shape": list(rgb.shape)}
            before = time.time()
            record = {"index": report["vla_inferences"], "task_language": instruction,
                      "images": images, "robot_state": observation["robot_state"], "started_unix": before}
            save(prefix.with_suffix(".json"), record)
            try:
                actions = original_infer(observation)
                assert actions.ndim == 2 and actions.shape[1] == 16 and np.isfinite(actions).all()
                np.save(prefix.with_suffix(".npy"), actions)
                record.update(status="completed", elapsed_seconds=time.time()-before,
                              action_shape=list(actions.shape), actions_sha256=digest(prefix.with_suffix(".npy")))
                return actions
            except BaseException as exc:
                record.update(status="failed", elapsed_seconds=time.time()-before, error=repr(exc))
                raise
            finally:
                save(prefix.with_suffix(".json"), record)
        model.infer = traced_infer
        primitives = RoboTwinPrimitives(**kwargs, check_cancelled=lambda: None)
        from bounded_vla import BoundedVLA
        harness=BoundedVLA(env,model,primitives._build_lingbot_observation,horizon=cfg["horizon"],max_inferences=24)
        from typed_skill_patch import TypedSkillPatch
        patch_file=runtime/cfg['patch_path']
        patcher=TypedSkillPatch(json.loads(patch_file.read_text()),env,primitives,horizon=cfg['horizon'])
        prefix_length=50
        # Record initial observation before any patch action, separately from VLA inputs.
        initial=primitives._build_lingbot_observation()
        report['initial_robot_state']=initial['robot_state'];report['initial_image_sha256']={}
        for camera,view in initial['views'].items():
            file=out/f'initial-{camera}.png';Image.fromarray(np.asarray(view['rgb'])).save(file)
            report['initial_image_sha256'][camera]=digest(file)
        refs=json.loads((runtime/cfg['input_references']).read_text())['cases']
        ref=next(x for x in refs if x['task']==report['task'] and x['seed']==report['seed'])
        assert initial_reference_equal(report, ref), 'paired initial state/image mismatch'
        report['initial_reference_matches']=True
        report['native_skill_attempts']=0;report['native_skill_actions']=0;report['planner_failures']=0
        save(out/'episode.json',report)
        # Default recording=False: unchanged native RGB inference, boundary PNGs
        # instead of costly every-physics-frame videos.
        for _ in range(1 if cfg['classification']=='typed_skill_fixture_qualification' else cfg['max_vla_inferences_per_episode']):
            status = env.last_info["episode_status"]
            if status["eval_success"] or status["take_action_cnt"] >= cfg["horizon"]:
                break
            skill=patcher.before_vla(report['vla_inferences'])
            if skill is not None:
                append(out/'native-skills.jsonl',skill)
                report['native_skill_attempts']+=1;report['native_skill_actions']+=skill['native_actions'];report['planner_failures']+=int(skill['planning_failure'])
                report['native_actions']=int(env.last_info['episode_status']['take_action_cnt'])
                save(out/'episode.json',report)
            if cfg['classification']=='typed_skill_fixture_qualification':
                assert skill is not None and not skill['planning_failure'] and skill['native_actions']>0,'native typed action fixture failed'
                pose=env.last_info['robot_state'][skill['rule']['arm']+'_eef_pose']
                assert np.linalg.norm(np.asarray(pose[:3])-np.asarray(skill['before']['robot_state'][skill['rule']['arm']+'_eef_pose'][:3]))>1e-5,'no measured EEF change'
                break
            status=env.last_info['episode_status']
            if status['eval_success'] or status['take_action_cnt']>=cfg['horizon']:break
            prior = status['take_action_cnt']
            result = harness.dispatch({"action":"execute_vla_chunk","use_length":prefix_length})
            selected=result.pop("selected_actions")
            chosen=out/f"executed-prefix-{report['vla_inferences']:03d}.npy"
            np.save(chosen,selected)
            result["selected_actions_sha256"]=digest(chosen)
            result["selected_actions_shape"]=list(selected.shape)
            status = env.last_info["episode_status"]
            assert status["actual_seed"] == report["seed"] and status["step_lim"] == cfg["horizon"]
            assert prior < status["take_action_cnt"] <= min(prior + prefix_length, cfg["horizon"])
            append(out / "chunks.jsonl", {"time": time.time(), "result": result,
                                         "robot_state": env.last_info["robot_state"]})
            report.update(native_actions=int(status["take_action_cnt"]), native_eval_success=bool(status["eval_success"]))
            save(out / "episode.json", report)
        report['patch_attempts']=patcher.attempts
        report['interface_status']=harness.status()
        final_status = dict(env.last_info["episode_status"])
        for camera in ("head", "left_wrist", "right_wrist"):
            Image.fromarray(np.asarray(env.render_camera(camera))).save(out / f"terminal-{camera}.png")
        report.update(status="completed", native_episode_status=final_status,
                      native_eval_success=bool(final_status["eval_success"]),
                      native_actions=int(final_status["take_action_cnt"]),
                      final_robot_state=env.last_info["robot_state"],
                      termination="native_success" if final_status["eval_success"] else ("bounded_horizon" if final_status["take_action_cnt"]>=cfg["horizon"] else "inference_cap"),
                      limitation="Fixture qualification is not task score; candidate development does not imply accepted update, forgetting or RSI. Native actions include typed skills and VLA.")
    except BaseException as exc:
        report.update(status="infrastructure_error", error=repr(exc), traceback=traceback.format_exc())
        if kwargs is not None:
            report["last_native_episode_status"] = kwargs["env"].last_info.get("episode_status")
        raise
    finally:
        report['daemon_before_cleanup']=[dict(pid=d._proc.pid,name=d.name,returncode=d.poll()) for d in daemons]
        for daemon in reversed(daemons):
            try:
                daemon.stop(timeout=15)
            except Exception as exc:
                report.setdefault("cleanup_errors", []).append(repr(exc))
        report['daemon_after_cleanup']=[dict(pid=d._proc.pid,name=d.name,returncode=d.poll()) for d in daemons]
        report.update(finished_unix=time.time(), wall_seconds=time.time()-started)
        save(out / "episode.json", report)
        if any(x["returncode"] != 0 for x in report["daemon_after_cleanup"]):
            raise RuntimeError("Owned daemon did not exit cleanly; stop panel")


def run(cfg, config_path, expected_sha):
    assert cfg["status"] == "frozen", "Draft protocol cannot run"
    assert digest(config_path) == expected_sha, "Exact frozen protocol SHA required"
    assert cfg["runner_sha256"] == digest(__file__), "Runner not frozen"
    runtime = Path(os.environ["RSI_RUNTIME_ROOT"]).resolve()
    out = runtime / "outputs" / cfg["run_id"]
    assert out.parent == runtime / "outputs" and not out.exists()
    preflight_result = preflight(cfg, strict=True)
    (runtime / "locks").mkdir(exist_ok=True)
    lock = (runtime / f"locks/gpu{cfg['gpu']}.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    gpu = gpu_snapshot(cfg["gpu"])
    assert gpu["memory_mib"] < 100 and not gpu["compute_pids"], gpu
    out.mkdir()
    save(out / "protocol.json", cfg)
    (out/"code").mkdir()
    import shutil
    for rel in ["scripts/run_typed_skill_panel.py","scripts/typed_skill_patch.py","scripts/bounded_vla.py","scripts/owner_thread_adapter.py","scripts/run_owner_env_server.py"]:shutil.copy2(ROOT/rel,out/"code"/Path(rel).name)
    report = {"status": "running", "classification": cfg["classification"], "started_unix": time.time(),
              "protocol_sha256": expected_sha, "runner_sha256": digest(__file__), "gpu_before": gpu,
              "preflight": preflight_result, "episodes": [], "qwen_calls": 0, "skill_updates": 0}
    save(out / "report.json", report)
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    active = None
    current = None
    try:
        for index, case in enumerate(cfg["cases"]):
            remaining = cfg["total_wall_seconds"] - (time.time() - report["started_unix"])
            assert remaining > 0, "Total wall budget exhausted"
            current = out / f"{index:02d}-{case['task']}-s{case['seed']}"
            current.mkdir()
            env = os.environ.copy()
            for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
                env.pop(key, None)
            source = runtime / "vendor" / ("RPent-" + RPENT_COMMIT)
            env.update(PYTHONPATH=str(source), RPENT_REPO_ROOT=str(source),
                       RPENT_RLINF_ROOT=str(runtime / cfg["rlinf_relative_path"]),
                       CUDA_VISIBLE_DEVICES=str(cfg["gpu"]), CUDA_DEVICE_ORDER="PCI_BUS_ID",
                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       RSI_EXPECTED_GPU_PCI=gpu["pci_bus_id"], NO_PROXY="127.0.0.1,localhost",
                       RSI_VLA_WORKER_PROTOCOL_SHA256=expected_sha)
            with (current / "worker.log").open("w") as log:
                active = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--config", str(config_path),
                                           "--worker", str(index), "--output", str(current)],
                                          env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = active.wait(timeout=min(cfg["episode_wall_seconds"], remaining))
                except subprocess.TimeoutExpired:
                    os.killpg(active.pid, signal.SIGTERM)
                    try:
                        active.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(active.pid, signal.SIGKILL)
                        active.wait(timeout=5)
                    code = 124
            cleanup = cleanup_owned(current / "owned-daemons.jsonl")
            ep = json.loads((current / "episode.json").read_text()) if (current / "episode.json").exists() else {}
            if code != 0:
                ep.update(status="interrupted" if code == 124 else "infrastructure_error", worker_exit_code=code)
                save(current / "episode.json", ep)
            report["episodes"].append({"case": case, "result": ep, "cleanup": cleanup})
            save(out / "report.json", report)
            active = None
            assert not any(x["live"] for x in cleanup), "Owned process remained live"
            if code != 0:
                raise RuntimeError(f"Episode failed with exit {code}; no resampling or automatic retry")
        report["status"] = "completed"
    except BaseException as exc:
        report.update(status="closed_failed", error=repr(exc), traceback=traceback.format_exc())
        raise
    finally:
        if active is not None and active.poll() is None:
            os.killpg(active.pid, signal.SIGTERM)
            try:
                active.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(active.pid, signal.SIGKILL)
                active.wait(timeout=5)
        if current is not None and (current / "episode.json").exists():
            current_case = cfg["cases"][int(current.name.split("-", 1)[0])]
            if not any(row["case"] == current_case for row in report["episodes"]):
                interrupted_episode = json.loads((current / "episode.json").read_text())
                if interrupted_episode.get("status") == "running":
                    interrupted_episode["status"] = "interrupted"
                    save(current / "episode.json", interrupted_episode)
                report["episodes"].append({"case": current_case, "result": interrupted_episode})
        if current is not None:
            report["final_cleanup"] = cleanup_owned(current / "owned-daemons.jsonl")
        report.update(finished_unix=time.time(), GPU_allocation_seconds=time.time()-report["started_unix"],
                      gpu_after=gpu_snapshot(cfg["gpu"]),
                      total_native_actions=sum(x["result"].get("native_actions", 0) for x in report["episodes"]),
                      total_vla_inferences=sum(x["result"].get("vla_inferences", 0) for x in report["episodes"]),
                      strict_rsi_rounds=0)
        save(out / "report.json", report)
        save(out/"CLOSE.json",dict(status=report["status"],unused_allowance="canceled",inferences=report["total_vla_inferences"],maximum=cfg["max_vla_inferences_total"]))
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="CPU-only default")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--protocol-sha256")
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    cfg = validate(json.loads(args.config.read_text()))
    if args.worker is not None:
        assert cfg["status"] == "frozen" and args.output is not None
        assert os.environ.get("RSI_VLA_WORKER_PROTOCOL_SHA256") == digest(args.config)
        assert cfg["runner_sha256"] == digest(__file__)
        worker(cfg, args.worker, args.output)
    elif args.run:
        assert args.protocol_sha256 and not args.check
        run(cfg, args.config.resolve(), args.protocol_sha256)
    else:
        print(json.dumps(preflight(cfg), indent=2))


if __name__ == "__main__":
    main()

